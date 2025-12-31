# Appendix: Code Listings

This appendix contains key code from the Cosilico AI training system.

## Agent Training Loop

The core agentic loop that drives statute encoding:

```python
class AgentTrainingLoop:
    """Agentic training loop using Claude with tools."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 10,
        target_accuracy: float = 0.95,
    ):
        self.model = model
        self.max_iterations = max_iterations
        self.target_accuracy = target_accuracy
        self.client = anthropic.Anthropic()

    def train(self, statute: Statute, test_cases: list[TestCase]) -> dict:
        """Run the agentic training loop."""
        messages = [
            {"role": "user", "content": self._build_prompt(statute, test_cases)}
        ]

        for turn in range(self.max_iterations * 2):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self._build_system_prompt(),
                tools=TOOLS,
                messages=messages
            )

            # Handle tool calls
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                break

            for tool_use in tool_uses:
                result = self._handle_tool_call(tool_use.name, tool_use.input)
                # ... process results

        return {"success": self.best_accuracy >= self.target_accuracy, ...}
```

## Tool Definitions

Tools available to the Claude agent:

```python
TOOLS = [
    {
        "name": "execute_dsl",
        "description": "Execute Cosilico DSL code against test cases",
        "input_schema": {
            "type": "object",
            "properties": {
                "dsl_code": {"type": "string"}
            },
            "required": ["dsl_code"]
        }
    },
    {
        "name": "submit_final_code",
        "description": "Submit final DSL code when accuracy target is met",
        "input_schema": {
            "type": "object",
            "properties": {
                "dsl_code": {"type": "string"},
                "explanation": {"type": "string"}
            },
            "required": ["dsl_code"]
        }
    }
]
```

## DSL Executor

The executor that parses and runs generated DSL:

```python
class Executor:
    def execute(self, code: GeneratedCode, test_cases: list[TestCase]):
        parsed = self._parse(code.source)

        results = []
        for tc in test_cases:
            try:
                output = self._evaluate_formula(
                    parsed["formula"],
                    tc.inputs,
                    parsed["references"]
                )
                match = abs(output - tc.expected["eitc"]) <= 1.0
                results.append(ExecutionResult(match=match, ...))
            except Exception as e:
                results.append(ExecutionResult(error=str(e)))

        return results
```

## Oracle Interface

PolicyEngine oracle wrapper:

```python
class PolicyEngineOracle:
    def __init__(self, year: int = 2024):
        from policyengine_us import Simulation
        self.Simulation = Simulation
        self.year = year

    def evaluate(self, inputs: dict) -> dict:
        situation = self._build_situation(inputs)
        sim = self.Simulation(situation=situation)

        return {
            "eitc": float(sim.calculate("eitc", self.year)),
            "earned_income": float(sim.calculate("earned_income", self.year)),
            # ... other variables
        }
```

## Full Source

Complete source code available at:
https://github.com/CosilicoAI/rac/tree/main/src/cosilico
