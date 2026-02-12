"""Agentic training loop using Anthropic SDK with tool use.

This implements a closed-loop system where Claude:
1. Reads statutory text
2. Generates RAC DSL code
3. Executes it against test cases (via tool)
4. Gets structured feedback
5. Iterates until accuracy threshold is met
"""

import json
import os
from typing import Any

import anthropic

from .executor import Executor
from .oracles import MockOracle
from .scorer import FailureDiagnoser, Scorer
from .types import GeneratedCode, Statute, TestCase

# Tool definitions for Claude
TOOLS = [
    {
        "name": "execute_dsl",
        "description": """Execute RAC DSL code against test cases and return accuracy metrics.

Use this tool after generating DSL code to test if it correctly implements the statute.
The tool will:
1. Parse the DSL code
2. Execute it against all test cases
3. Return accuracy, pass/fail counts, and specific failure details

Call this tool with your generated DSL code to see how well it performs.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "dsl_code": {"type": "string", "description": "The RAC DSL code to execute"}
            },
            "required": ["dsl_code"],
        },
    },
    {
        "name": "submit_final_code",
        "description": """Submit your final DSL code when you've achieved the target accuracy or exhausted improvement options.

Only call this when:
1. You've achieved >= 95% accuracy, OR
2. You've made multiple attempts and accuracy has plateaued

Include the final code and a brief explanation of the implementation.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "dsl_code": {"type": "string", "description": "The final RAC DSL code"},
                "explanation": {
                    "type": "string",
                    "description": "Brief explanation of the implementation and any remaining issues",
                },
            },
            "required": ["dsl_code", "explanation"],
        },
    },
]


class AgentTrainingLoop:
    """Agentic training loop using Claude with tools."""

    def __init__(
        self,
        model: str = "claude-opus-4-5-20251101",
        max_iterations: int = 10,
        target_accuracy: float = 0.95,
        api_key: str | None = None,
    ):
        self.model = model
        self.max_iterations = max_iterations
        self.target_accuracy = target_accuracy
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

        # Execution components
        self.executor = Executor()
        self.scorer = Scorer()
        self.diagnoser = FailureDiagnoser()

        # State
        self.test_cases: list[TestCase] = []
        self.iteration = 0
        self.best_code: str | None = None
        self.best_accuracy: float = 0.0

        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        # Trajectory logging - captures the full RL loop
        self.trajectory: list[dict] = []

        # Full conversation log for visualization
        self.conversation_log: list[dict] = []

    def get_cost_estimate(self) -> dict:
        """Estimate API cost based on token usage.

        Pricing (as of Dec 2024):
        - Claude Sonnet: $3/M input, $15/M output
        - Claude Opus: $15/M input, $75/M output
        """
        if "opus" in self.model.lower():
            input_rate = 15.0 / 1_000_000
            output_rate = 75.0 / 1_000_000
        else:  # sonnet
            input_rate = 3.0 / 1_000_000
            output_rate = 15.0 / 1_000_000

        input_cost = self.total_input_tokens * input_rate
        output_cost = self.total_output_tokens * output_rate
        total_cost = input_cost + output_cost

        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "input_cost_usd": input_cost,
            "output_cost_usd": output_cost,
            "total_cost_usd": total_cost,
            "model": self.model,
        }

    def _build_system_prompt(self) -> str:
        return """You are an expert tax law encoder. Your task is to convert statutory text into executable Python code.

## Output Format

Generate a Python function that takes a dictionary of inputs and returns a dictionary with the calculated value.

```python
def calculate(inputs: dict) -> dict:
    # Extract inputs
    earned_income = inputs.get("earned_income", 0)
    n_children = inputs.get("n_qualifying_children", inputs.get("n_children", 0))
    filing_status = inputs.get("filing_status", "SINGLE")

    # Parameters (hardcode from statute/IRS tables)
    # ...

    # Calculate
    result = ...

    return {"variable_name": result}
```

## Important Rules

1. Always return a dict with a single key matching the expected output variable
2. Use inputs.get() with defaults to safely access input values
3. Hardcode parameter values from the statute (rates, thresholds, etc.)
4. Handle all filing statuses if relevant: "SINGLE", "JOINT", "MARRIED_FILING_SEPARATELY", "HEAD_OF_HOUSEHOLD"
5. Use standard Python: min(), max(), if/else, etc.

## Example - EITC Phase-In

```python
def calculate(inputs: dict) -> dict:
    earned_income = inputs.get("earned_income", 0)
    n_children = inputs.get("n_qualifying_children", inputs.get("n_children", 0))

    # 2024 parameters by number of qualifying children
    params = {
        0: {"rate": 0.0765, "earned_income_amount": 7840},
        1: {"rate": 0.34, "earned_income_amount": 11750},
        2: {"rate": 0.40, "earned_income_amount": 16510},
        3: {"rate": 0.45, "earned_income_amount": 16510},
    }

    p = params.get(min(n_children, 3))
    credit = min(earned_income, p["earned_income_amount"]) * p["rate"]

    return {"eitc_phase_in_credit": credit}
```

## Your Task

1. Read the statutory text carefully
2. Generate Python code that implements the rules
3. Use the execute_dsl tool to test your code (it accepts Python)
4. Analyze failures and iterate
5. When you reach 95%+ accuracy, use submit_final_code

Be precise with the formula - small errors in rates or thresholds cause test failures."""

    def _build_user_prompt(self, statute: Statute, test_cases: list[TestCase]) -> str:
        # Show a sample of test cases
        sample_cases = test_cases[:5]
        cases_str = "\n".join(
            [
                f"- earned_income=${tc.inputs.get('earned_income', 0)}, "
                f"n_children={tc.inputs.get('n_children', 0)} → "
                f"expected EITC=${tc.expected.get('eitc', tc.expected.get('eitc_phase_in_credit', 0)):.2f}"
                for tc in sample_cases
            ]
        )

        return f"""## Statutory Text to Encode

**Citation:** {statute.citation}

{statute.text}

## Test Cases (sample of {len(test_cases)} total)

{cases_str}

## Instructions

1. Analyze the statutory text
2. Write RAC DSL code that implements it
3. Use the `execute_dsl` tool to test your implementation
4. Iterate based on failure feedback until you reach 95%+ accuracy
5. Use `submit_final_code` when done

Start by generating your initial DSL code and testing it."""

    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        """Handle a tool call from Claude."""
        if tool_name == "execute_dsl":
            return self._execute_dsl(tool_input["dsl_code"])
        elif tool_name == "submit_final_code":
            return self._submit_final(tool_input["dsl_code"], tool_input.get("explanation", ""))
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def _execute_dsl(self, dsl_code: str) -> str:
        """Execute DSL code against test cases."""
        self.iteration += 1

        # Create a GeneratedCode object
        code = GeneratedCode(source=dsl_code, citation="test", iteration=self.iteration)

        # Execute
        results = self.executor.execute(code, self.test_cases)

        # Score
        score = self.scorer.score(results)

        # Track best
        if score.accuracy > self.best_accuracy:
            self.best_accuracy = score.accuracy
            self.best_code = dsl_code

        # Diagnose failures
        failures = self.diagnoser.diagnose(results)

        # Build response
        response = {
            "iteration": self.iteration,
            "accuracy": f"{score.accuracy:.1%}",
            "passed": int(score.accuracy * score.n_cases),
            "total": score.n_cases,
            "target": f"{self.target_accuracy:.0%}",
            "mean_absolute_error": f"${score.mean_absolute_error:.2f}",
        }

        if score.accuracy >= self.target_accuracy:
            response["status"] = "SUCCESS - Target accuracy reached!"
            response["suggestion"] = "Use submit_final_code to complete."
        else:
            response["status"] = "NEEDS_IMPROVEMENT"
            response["failures"] = [
                {
                    "type": f.type,
                    "message": f.message[:100],
                    "expected": f.expected,
                    "actual": f.actual,
                }
                for f in failures[:5]
            ]
            response["suggestion"] = "Analyze the failures and adjust your formula or parameters."

        # Log to trajectory for RL analysis
        self.trajectory.append(
            {
                "iteration": self.iteration,
                "code": dsl_code,
                "accuracy": score.accuracy,
                "passed": int(score.accuracy * score.n_cases),
                "total": score.n_cases,
                "mean_absolute_error": score.mean_absolute_error,
                "failures": [
                    {
                        "type": f.type,
                        "message": f.message,
                        "expected": f.expected,
                        "actual": f.actual,
                        "inputs": f.inputs if hasattr(f, "inputs") else None,
                    }
                    for f in failures
                ],
                "is_best": score.accuracy >= self.best_accuracy,
            }
        )

        return json.dumps(response, indent=2)

    def _submit_final(self, dsl_code: str, explanation: str) -> str:
        """Handle final code submission."""
        # One final execution to get accurate metrics
        code = GeneratedCode(source=dsl_code, citation="final", iteration=self.iteration)
        results = self.executor.execute(code, self.test_cases)
        score = self.scorer.score(results)

        return json.dumps(
            {
                "status": "SUBMITTED",
                "final_accuracy": f"{score.accuracy:.1%}",
                "iterations": self.iteration,
                "explanation": explanation,
            }
        )

    def train(
        self, statute: Statute, test_cases: list[TestCase], verbose: bool = True
    ) -> dict[str, Any]:
        """Run the agentic training loop.

        Returns dict with:
        - success: bool
        - final_code: str
        - final_accuracy: float
        - iterations: int
        - conversation: list of messages
        """
        self.test_cases = test_cases
        self.iteration = 0
        self.best_code = None
        self.best_accuracy = 0.0
        self.trajectory = []  # Reset trajectory for new training run
        self.conversation_log = []  # Reset conversation log

        # Initialize conversation
        messages = [{"role": "user", "content": self._build_user_prompt(statute, test_cases)}]

        if verbose:
            print(f"Starting agentic training loop for: {statute.citation}")
            print(f"Test cases: {len(test_cases)}, Target: {self.target_accuracy:.0%}")
            print("-" * 60)

        final_result = None

        # Main agentic loop
        for turn in range(self.max_iterations * 2):  # Allow multiple tool calls per iteration
            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self._build_system_prompt(),
                tools=TOOLS,
                messages=messages,
            )

            # Track token usage
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens

            # Process response
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # Log assistant response for visualization
            assistant_text = ""
            for block in assistant_content:
                if hasattr(block, "text"):
                    assistant_text += block.text
            self.conversation_log.append(
                {
                    "turn": turn,
                    "role": "assistant",
                    "text": assistant_text,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }
            )

            # Check for tool use
            tool_uses = [block for block in assistant_content if block.type == "tool_use"]

            if not tool_uses:
                # No tool call - Claude is done or needs prompting
                if verbose:
                    for block in assistant_content:
                        if hasattr(block, "text"):
                            print(f"\n[Claude]: {block.text[:300]}...")
                break

            # Handle each tool call
            tool_results = []
            for tool_use in tool_uses:
                if verbose:
                    print(f"\n[Tool: {tool_use.name}]")

                result = self._handle_tool_call(tool_use.name, tool_use.input)

                # Log tool call for visualization
                self.conversation_log.append(
                    {
                        "turn": turn,
                        "role": "tool_call",
                        "tool_name": tool_use.name,
                        "tool_input": tool_use.input,
                        "tool_result": result,
                    }
                )

                if verbose:
                    # Parse and display key info
                    try:
                        result_data = json.loads(result)
                        if "accuracy" in result_data:
                            print(f"  Accuracy: {result_data['accuracy']}")
                        if "status" in result_data:
                            print(f"  Status: {result_data['status']}")
                        if "failures" in result_data and result_data["failures"]:
                            print(f"  Failures ({len(result_data['failures'])}):")
                            for f in result_data["failures"][:2]:
                                print(f"    - {f['message'][:60]}...")
                    except json.JSONDecodeError:
                        print(f"  {result[:100]}")

                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tool_use.id, "content": result}
                )

                # Check if this was final submission
                if tool_use.name == "submit_final_code":
                    final_result = json.loads(result)
                    break

            if final_result:
                break

            # Add tool results to conversation
            messages.append({"role": "user", "content": tool_results})

            # Check iteration limit
            if self.iteration >= self.max_iterations:
                if verbose:
                    print(f"\nMax iterations ({self.max_iterations}) reached.")
                break

        # Build final result
        cost = self.get_cost_estimate()

        if final_result:
            return {
                "success": self.best_accuracy >= self.target_accuracy,
                "final_code": self.best_code,
                "final_accuracy": self.best_accuracy,
                "iterations": self.iteration,
                "submitted": True,
                "cost": cost,
                "trajectory": self.trajectory,  # Full RL learning history
                "conversation": self.conversation_log,  # Full conversation for visualization
            }
        else:
            return {
                "success": self.best_accuracy >= self.target_accuracy,
                "final_code": self.best_code,
                "final_accuracy": self.best_accuracy,
                "iterations": self.iteration,
                "submitted": False,
                "cost": cost,
                "trajectory": self.trajectory,  # Full RL learning history
                "conversation": self.conversation_log,  # Full conversation for visualization
            }


def create_eitc_test_cases() -> list[TestCase]:
    """Create test cases for EITC using mock oracle."""
    oracle = MockOracle()
    cases = []

    # Test various income levels and child counts
    incomes = [0, 1000, 5000, 7840, 10000, 11750, 15000, 16510, 20000]
    for i, income in enumerate(incomes):
        for n_children in [0, 1, 2, 3]:
            inputs = {
                "earned_income": income,
                "filing_status": "SINGLE",
                "n_children": n_children,
                "n_qualifying_children": n_children,
            }
            expected = oracle.evaluate(inputs)
            cases.append(
                TestCase(
                    id=f"case_{i}_{n_children}",
                    inputs=inputs,
                    expected=expected,
                )
            )
    return cases


# CLI entry point
def main():
    import argparse

    parser = argparse.ArgumentParser(description="RAC Agentic Training Loop")
    parser.add_argument("--model", default="claude-opus-4-5-20251101", help="Claude model to use")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max iterations")
    parser.add_argument("--target-accuracy", type=float, default=0.95, help="Target accuracy")
    args = parser.parse_args()

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set")
        print("Set with: export ANTHROPIC_API_KEY=your_key")
        return

    # Create statute and test cases
    statute = Statute(
        citation="26 USC § 32(a)(1)",
        text="""
(a) Allowance of credit
    (1) In general
    In the case of an eligible individual, there shall be allowed as a credit
    against the tax imposed by this subtitle for the taxable year an amount
    equal to the credit percentage of so much of the taxpayer's earned income
    for the taxable year as does not exceed the earned income amount.
        """.strip(),
        jurisdiction="us",
    )

    test_cases = create_eitc_test_cases()

    print("=" * 60)
    print("RAC Agentic Training Loop")
    print("=" * 60)
    print(f"Model: {args.model}")
    print(f"Statute: {statute.citation}")
    print(f"Test cases: {len(test_cases)}")
    print(f"Target accuracy: {args.target_accuracy:.0%}")
    print("=" * 60)

    # Run training
    loop = AgentTrainingLoop(
        model=args.model,
        max_iterations=args.max_iterations,
        target_accuracy=args.target_accuracy,
    )

    result = loop.train(statute, test_cases, verbose=True)

    print("\n" + "=" * 60)
    print("FINAL RESULT")
    print("=" * 60)
    print(f"Success: {result['success']}")
    print(f"Final accuracy: {result['final_accuracy']:.1%}")
    print(f"Iterations: {result['iterations']}")
    print(f"Submitted: {result['submitted']}")

    # Print cost
    cost = result.get("cost", {})
    print("\nAPI Usage:")
    print(f"  Input tokens:  {cost.get('input_tokens', 0):,}")
    print(f"  Output tokens: {cost.get('output_tokens', 0):,}")
    print(f"  Total tokens:  {cost.get('total_tokens', 0):,}")
    print(f"  Estimated cost: ${cost.get('total_cost_usd', 0):.4f}")

    if result["final_code"]:
        print("\nFinal code:")
        print("-" * 40)
        print(result["final_code"])


if __name__ == "__main__":
    main()
