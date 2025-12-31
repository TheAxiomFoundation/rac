"""Agentic training loop for Cosilico DSL generation.

This is the DSL-native version of the agent that generates proper
Cosilico DSL code instead of Python functions.
"""

import json
import os
from typing import Any

import anthropic

from .dsl_executor import DSLExecutor, get_default_parameters
from .scorer import FailureDiagnoser, Scorer
from .types import GeneratedCode, Statute, TestCase


# Tool definitions for Claude
TOOLS = [
    {
        "name": "execute_dsl",
        "description": """Execute Cosilico DSL code against test cases and return accuracy metrics.

Use this tool after generating DSL code to test if it correctly implements the statute.
The tool will:
1. Parse the DSL code
2. Execute it against all test cases
3. Return accuracy, pass/fail counts, and specific failure details

Call this tool with your generated DSL code to see how well it performs.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "dsl_code": {
                    "type": "string",
                    "description": "The Cosilico DSL code to execute"
                }
            },
            "required": ["dsl_code"]
        }
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
                "dsl_code": {
                    "type": "string",
                    "description": "The final Cosilico DSL code"
                },
                "explanation": {
                    "type": "string",
                    "description": "Brief explanation of the implementation and any remaining issues"
                }
            },
            "required": ["dsl_code", "explanation"]
        }
    }
]


DSL_SYSTEM_PROMPT = """You are an expert tax law encoder. Your task is to convert statutory text into Cosilico DSL code.

## Cosilico DSL Overview

Cosilico DSL is a purpose-built language for encoding tax and benefit rules. Key principles:
- **Statute-organized**: Code structure mirrors legal structure (path = citation)
- **No hardcoded values**: All rates, thresholds, and amounts come from parameter references
- **References block**: Variables are aliased by their statute paths before use in formulas
- **Traceable**: Every rule links to legal citations
- **Indexing-aware**: Inflation adjustments reference the indexing provision, not hardcoded current values

## File Organization

**The path IS the legal citation.** Files live at statute paths (separate repo per jurisdiction):

```
statute/26/32/                     # 26 USC §32 (EITC) in US repo
├── a/1/earned_income_credit.rac        # §32(a)(1)
├── a/2/A/initial_credit_amount.rac     # §32(a)(2)(A)
├── b/1/credit_percentage.yaml               # §32(b)(1) parameters
├── b/2/A/amounts.yaml                       # §32(b)(2)(A) indexed amounts
├── j/1/indexing_rule.yaml                   # §32(j)(1) cost-of-living adjustment
└── j/2/rounding_rule.yaml                   # §32(j)(2) rounding rules

# UK repo would use same structure:
statute/FA2003/...                           # Finance Act 2003
```

The path `statute/26/32/a/1/` maps directly to "26 USC §32(a)(1)".
The `statute/` prefix distinguishes from `regs/` (regulations) and `guidance/` (IRS notices, etc.).

## DSL Syntax

### Module Declaration

```cosilico
# Module path matches file location
module statute.26.32.a.1
version "2024.1"
```

### References Block (CRITICAL)

The `references` block maps local aliases to statute paths. This creates auditability
by tracing every variable use to a specific statute section.

```cosilico
references {
  # Alias: statute_path/variable_name
  earned_income: statute/26/32/c/2/A/earned_income
  adjusted_gross_income: statute/26/62/a/adjusted_gross_income
  filing_status: statute/26/1/filing_status

  # Credit components from other subsections
  initial_credit_amount: statute/26/32/a/2/A/initial_credit_amount
  credit_reduction_amount: statute/26/32/a/2/B/credit_reduction_amount

  # Parameters can also be referenced
  credit_percentage: statute/26/32/b/1/credit_percentage
  earned_income_amount: statute/26/32/b/2/A/earned_income_amount
}
```

### Variable Definition

```cosilico
variable <name> {
  entity <EntityType>           # Person, TaxUnit, Household
  period <PeriodType>           # Year, Month
  dtype <DataType>              # Money, Rate, Count, Bool
  reference "<legal citation>"  # Required - cite the exact statute subsection

  formula {
    # Use aliased names from references block
    let <var> = <expression>
    return <expression>
  }
}
```

### Parameter References

Parameters are stored in YAML files at their statute location and referenced by path:

```cosilico
# Indexed by number of children
parameter(gov.irs.eitc.phase_in_rate[n_children])

# Indexed by filing status
parameter(gov.irs.deductions.standard[filing_status])
```

**IMPORTANT**: Do NOT hardcode numeric values. Always use parameter() references.

## Inflation Indexing (CRITICAL)

Many statutory dollar amounts are indexed for inflation. When encoding indexed parameters:

1. **Identify the indexing provision**: Look for "cost-of-living adjustment" or "adjusted for inflation"
2. **Reference the indexing rule**: The rule lives at its statutory location (e.g., §32(j) for EITC)
3. **Encode base values, not current values**: The base year amount is the authoritative value
4. **Three-tier precedence**: The system resolves values using:
   - PUBLISHED: Official IRS values (Rev. Proc., etc.) - highest priority
   - PROJECTED: Our calculations using forecast inflation
   - CALCULATED: On-the-fly from base year + index

### Example: EITC Indexing (§32(j))

The EITC earned income amounts in §32(b)(2)(A) are indexed per §32(j)(1):

```yaml
# statute/26/32/b/2/A/amounts.yaml
earned_income_amount:
  reference: "26 USC § 32(b)(2)(A)"
  indexing_rule: statute/26/32/j/1/indexing_rule  # Points to where indexing is defined

  # Base values (the statute's original amounts from 2015)
  base:
    year: 2015
    by_num_qualifying_children:
      0: 6580
      1: 9880
      2: 13870
      3: 13870

  # Published values (from Rev. Proc.) - authoritative
  published:
    - effective_from: 2024-01-01
      source: "Rev. Proc. 2023-34"
      by_num_qualifying_children:
        0: 7840
        1: 12390
        2: 17400
        3: 17400
```

The indexing rule at §32(j)(1) references §1(f)(3) for the cost-of-living adjustment formula:

```yaml
# statute/26/32/j/1/indexing_rule.yaml
indexing_rule:
  description: EITC cost-of-living adjustment
  reference: "26 USC § 32(j)(1)"
  method:
    type: cost_of_living_adjustment
    reference_section: statute/26/1/f/3/cost_of_living_adjustment
    base_year: 2015
  rounding:
    reference: "26 USC § 32(j)(2)(A)"
    rule: round_down_to_nearest
    amount: 10  # Nearest $10
```

### Why This Matters

**BAD** (hardcoding current values - will be wrong next year):
```cosilico
# DON'T DO THIS
let cap = match n_children {
  0 => 7840,   # Where does this come from?
  1 => 12390,  # How to update for 2025?
  2 => 17400,
  _ => 17400,
}
```

**GOOD** (reference the parameter, system handles indexing):
```cosilico
# Reference parameter - system resolves correct value for any year
let cap = earned_income_amount[n_children]  # Aliased in references block
```

When you see statutory text mentioning inflation adjustment, identify:
1. Which dollar amounts are indexed
2. Where the indexing rule is defined (e.g., "pursuant to section 1(f)(3)")
3. The base year and base amounts
4. Any special rounding rules

### Expressions

**Arithmetic:** `+`, `-`, `*`, `/`
**Comparison:** `==`, `!=`, `<`, `>`, `<=`, `>=`
**Logical:** `and`, `or`, `not`
**Functions:** `min(a, b)`, `max(a, b)`, `abs(x)`

**Conditionals:**
```cosilico
if condition then expr1 else expr2
```

## Complete Example: EITC (26 USC §32)

```cosilico
# statute/26/32/a/1/earned_income_credit.rac
#
# 26 USC §32(a)(1) - Earned Income Credit
#
# "In the case of an eligible individual, there shall be allowed as a credit
# against the tax imposed by this subtitle for the taxable year an amount
# equal to the credit percentage of so much of the taxpayer's earned income
# for the taxable year as does not exceed the earned income amount."

module statute.26.32.a.1
version "2024.1"

references {
  # Inputs from other IRC sections
  earned_income: statute/26/32/c/2/A/earned_income
  adjusted_gross_income: statute/26/62/a/adjusted_gross_income
  filing_status: statute/26/1/filing_status

  # Eligibility from §32(c)(1)
  is_eligible_individual: statute/26/32/c/1/A/i/is_eligible_individual

  # Credit components from §32(a)(2)
  initial_credit_amount: statute/26/32/a/2/A/initial_credit_amount
  credit_reduction_amount: statute/26/32/a/2/B/credit_reduction_amount

  # AGI limit (indexed parameter from §32(b)(2)(A))
  agi_limit: statute/26/32/b/2/A/agi_limit
}

variable earned_income_credit {
  entity TaxUnit
  period Year
  dtype Money
  unit "USD"
  reference "26 USC § 32(a)(1)"
  label "Earned Income Tax Credit"

  formula {
    # Only eligible individuals receive the credit
    if not is_eligible_individual then
      return 0

    # Credit = phase-in amount minus phase-out reduction, but not below zero
    return max(0, initial_credit_amount - credit_reduction_amount)
  }
}
```

## Phase-In Calculation (§32(a)(2)(A))

```cosilico
# statute/26/32/a/2/A/initial_credit_amount.rac

module statute.26.32.a.2.A
version "2024.1"

references {
  earned_income: statute/26/32/c/2/A/earned_income
  num_qualifying_children: statute/26/32/c/3/A/num_qualifying_children

  # Parameters from §32(b) - indexed annually per §32(j)
  credit_percentage: statute/26/32/b/1/credit_percentage
  earned_income_amount: statute/26/32/b/2/A/earned_income_amount  # Indexed parameter
}

variable initial_credit_amount {
  entity TaxUnit
  period Year
  dtype Money
  reference "26 USC § 32(a)(2)(A)"

  formula {
    # Get parameters indexed by number of qualifying children
    # earned_income_amount is resolved via indexing system (PUBLISHED > PROJECTED > CALCULATED)
    let rate = credit_percentage[num_qualifying_children]
    let cap = earned_income_amount[num_qualifying_children]

    # Credit = rate × min(earned_income, cap)
    return rate * min(earned_income, cap)
  }
}
```

## Important Rules

1. **MODULE PATH = FILE PATH**: Module declaration matches the statute-organized file location (e.g., `statute.26.32.a.1`)
2. **REFERENCES BLOCK**: Declare all external variables/parameters with statute paths
3. **NO HARDCODED VALUES**: Use parameter() or references for all rates, amounts, thresholds
4. **ONE VARIABLE PER CLAUSE**: Each statutory subsection gets its own file/variable
5. **USE ALIASES IN FORMULAS**: After declaring in references, use the alias names directly
6. **IDENTIFY INDEXING**: Look for inflation adjustment language and reference the indexing provision

## Your Task

1. Read the statutory text carefully
2. Identify the statute section (e.g., "26 USC § 32(a)(1)")
3. Create module path matching the statute structure (e.g., `statute.26.32.a.1`)
4. Identify any inflation-indexed amounts and their indexing provisions
5. Declare references for all inputs and dependencies using statute paths (e.g., `statute/26/32/b/2/A/earned_income_amount`)
6. Generate DSL code using references and parameters - NO hardcoded values
7. Use the `execute_dsl` tool to test your implementation
8. When you reach 95%+ accuracy, use `submit_final_code`

The parameter values are already defined in the system. Your job is to write the FORMULA that correctly combines them using proper references. The indexing system handles resolving the correct values for any tax year."""


class DSLAgentTrainingLoop:
    """Agentic training loop for DSL generation."""

    def __init__(
        self,
        model: str = "claude-opus-4-5-20251101",
        max_iterations: int = 10,
        target_accuracy: float = 0.95,
        api_key: str | None = None,
        parameters: dict | None = None,
        system_prompt: str | None = None,  # Allow evolved prompt injection
    ):
        self.model = model
        self.max_iterations = max_iterations
        self.target_accuracy = target_accuracy
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

        # System prompt - use provided or default
        self.system_prompt = system_prompt or DSL_SYSTEM_PROMPT

        # Execution components - use DSL executor with YAML parameters
        self.executor = DSLExecutor(
            parameters=parameters or get_default_parameters(),
            use_yaml_params=True,
        )
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

        # Trajectory logging
        self.trajectory: list[dict] = []
        self.conversation_log: list[dict] = []

    def get_cost_estimate(self) -> dict:
        """Estimate API cost based on token usage."""
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
            "model": self.model
        }

    def _build_user_prompt(self, statute: Statute, test_cases: list[TestCase]) -> str:
        """Build the user prompt with statute and test cases."""
        sample_cases = test_cases[:5]

        # Format test cases based on available inputs
        cases_lines = []
        for tc in sample_cases:
            parts = []
            if "earned_income" in tc.inputs:
                parts.append(f"earned_income=${tc.inputs['earned_income']}")
            if "n_children" in tc.inputs:
                parts.append(f"n_children={tc.inputs['n_children']}")
            elif "n_qualifying_children" in tc.inputs:
                parts.append(f"n_children={tc.inputs['n_qualifying_children']}")
            if "filing_status" in tc.inputs:
                parts.append(f"filing_status={tc.inputs['filing_status']}")
            if "agi" in tc.inputs:
                parts.append(f"agi=${tc.inputs['agi']}")

            # Get expected value
            exp_val = list(tc.expected.values())[0] if tc.expected else 0
            exp_key = list(tc.expected.keys())[0] if tc.expected else "output"

            cases_lines.append(f"- {', '.join(parts)} → {exp_key}=${exp_val:.2f}")

        cases_str = "\n".join(cases_lines)

        return f"""## Statutory Text to Encode

**Citation:** {statute.citation}

{statute.text}

## Test Cases (sample of {len(test_cases)} total)

{cases_str}

## Instructions

1. Analyze the statutory text
2. Write Cosilico DSL code that implements it
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

        # Execute using DSL executor
        results = self.executor.execute(dsl_code, self.test_cases)

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
                    "actual": f.actual
                }
                for f in failures[:5]
            ]
            response["suggestion"] = "Analyze the failures and adjust your formula or parameters."

        # Log to trajectory
        self.trajectory.append({
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
                }
                for f in failures
            ],
            "is_best": score.accuracy >= self.best_accuracy,
        })

        return json.dumps(response, indent=2)

    def _submit_final(self, dsl_code: str, explanation: str) -> str:
        """Handle final code submission."""
        results = self.executor.execute(dsl_code, self.test_cases)
        score = self.scorer.score(results)

        return json.dumps({
            "status": "SUBMITTED",
            "final_accuracy": f"{score.accuracy:.1%}",
            "iterations": self.iteration,
            "explanation": explanation
        })

    def train(
        self,
        statute: Statute,
        test_cases: list[TestCase],
        verbose: bool = True
    ) -> dict[str, Any]:
        """Run the agentic training loop."""
        self.test_cases = test_cases
        self.iteration = 0
        self.best_code = None
        self.best_accuracy = 0.0
        self.trajectory = []
        self.conversation_log = []

        # Initialize conversation
        messages = [
            {"role": "user", "content": self._build_user_prompt(statute, test_cases)}
        ]

        if verbose:
            print(f"Starting DSL training loop for: {statute.citation}")
            print(f"Test cases: {len(test_cases)}, Target: {self.target_accuracy:.0%}")
            print("-" * 60)

        final_result = None

        # Main agentic loop
        for turn in range(self.max_iterations * 2):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,  # Use instance's prompt (may be evolved)
                tools=TOOLS,
                messages=messages
            )

            # Track token usage
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens

            # Process response
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # Log assistant response
            assistant_text = ""
            for block in assistant_content:
                if hasattr(block, "text"):
                    assistant_text += block.text
            self.conversation_log.append({
                "turn": turn,
                "role": "assistant",
                "text": assistant_text,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            })

            # Check for tool use
            tool_uses = [block for block in assistant_content if block.type == "tool_use"]

            if not tool_uses:
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

                self.conversation_log.append({
                    "turn": turn,
                    "role": "tool_call",
                    "tool_name": tool_use.name,
                    "tool_input": tool_use.input,
                    "tool_result": result,
                })

                if verbose:
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

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result
                })

                if tool_use.name == "submit_final_code":
                    final_result = json.loads(result)
                    break

            if final_result:
                break

            messages.append({"role": "user", "content": tool_results})

            if self.iteration >= self.max_iterations:
                if verbose:
                    print(f"\nMax iterations ({self.max_iterations}) reached.")
                break

        # Build final result
        cost = self.get_cost_estimate()

        return {
            "success": self.best_accuracy >= self.target_accuracy,
            "final_code": self.best_code,
            "final_accuracy": self.best_accuracy,
            "iterations": self.iteration,
            "submitted": final_result is not None,
            "cost": cost,
            "trajectory": self.trajectory,
            "conversation": self.conversation_log,
        }
