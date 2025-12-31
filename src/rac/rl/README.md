# Reward Functions for Policy Encoding

This module provides reward functions for validating AI-encoded tax and benefit policies against authoritative oracles (PolicyEngine, TAXSIM, IRS tables).

## Overview

The reward function is the core feedback signal for RL-based policy encoding. It:

1. **Compares encoded parameters** against multiple validation oracles
2. **Returns a scalar reward** (0-1) indicating accuracy
3. **Provides diagnostics** to help agents learn from failures

## Architecture

### Two-Level Reward Structure

```
┌─────────────────────────────────────────────────────────────┐
│                    COMBINED REWARD                           │
│                                                              │
│  Reward = α × Structural + (1-α) × Semantic                 │
│                                                              │
├──────────────────────────┬───────────────────────────────────┤
│  STRUCTURAL (Fast)       │  SEMANTIC (Accurate)              │
│  ─────────────────       │  ───────────────────              │
│  • Parses (0.3)          │  • Oracle consensus               │
│  • Valid primitives (0.2)│  • Test case accuracy             │
│  • Metadata (0.2)        │  • Partial credit                 │
│  • Naming (0.1)          │  • Error analysis                 │
│  • Dependencies (0.2)    │                                   │
└──────────────────────────┴───────────────────────────────────┘
```

### Oracles

| Oracle | Type | Priority | Coverage | Years |
|--------|------|----------|----------|-------|
| IRS Tables | Ground Truth | 1 | Limited (official examples) | All |
| PolicyEngine | Reference | 2 | Comprehensive | 2015+ |
| TAXSIM | Reference | 2 | Federal taxes | 1960-2023 |

## Usage

### Basic Usage

```python
from cosilico.rl.reward import (
    EncodingRewardFunction,
    PolicyEngineOracle,
    TaxsimOracle,
)

# Create oracles
oracles = [
    PolicyEngineOracle(),
    TaxsimOracle(),
]

# Create reward function
reward_fn = EncodingRewardFunction(
    oracles=oracles,
    tolerance_absolute=1.0,      # $1 tolerance
    tolerance_relative=0.01,     # 1% tolerance
    partial_credit=True,         # Give credit for close answers
)

# Test cases
test_cases = [
    {
        "inputs": {
            "earned_income": 15000,
            "filing_status": "SINGLE",
            "eitc_qualifying_children_count": 0,
        },
        "expected": {"eitc": 560.0},
    },
]

# Evaluate
result = reward_fn.evaluate(
    encoded_params={},  # Your encoded parameters
    variable="eitc",
    test_cases=test_cases,
    year=2024,
)

print(f"Reward: {result.reward:.3f}")
print(f"Accuracy: {result.accuracy:.1%}")
print(f"Failed cases: {result.n_failed}")
```

### Combined Structural + Semantic

For curriculum learning, use combined reward:

```python
from cosilico.rl.reward import (
    EncodingRewardFunction,
    StructuralRewardFunction,
    CombinedRewardFunction,
)

structural_fn = StructuralRewardFunction()
semantic_fn = EncodingRewardFunction(oracles=[...])

# Early training: more structural weight
combined_fn = CombinedRewardFunction(
    structural_fn=structural_fn,
    semantic_fn=semantic_fn,
    alpha=0.5,  # 50% structural, 50% semantic
)

# Late training: focus on semantics
combined_fn.set_alpha(0.1)  # 10% structural, 90% semantic
```

### Curriculum Learning Schedule

| Training Stage | Alpha | Focus |
|----------------|-------|-------|
| Initial | 0.5 | Learn DSL structure |
| Middle | 0.3 | Balance structure and correctness |
| Late | 0.1 | Focus on calculation accuracy |
| Final | 0.0 | Pure correctness (structure assumed) |

## Reward Components

### Partial Credit Schedule

Rather than binary pass/fail, partial credit encourages progress:

| Relative Error | Reward | Rationale |
|----------------|--------|-----------|
| < 0.1% | 1.00 | Essentially perfect |
| < 1% | 0.95 | Very close |
| < 5% | 0.80 | Close enough to learn |
| < 10% | 0.60 | Right direction |
| < 25% | 0.30 | Some signal |
| ≥ 25% | 0.00 | Too far off |

### Tolerance Handling

Two types of tolerance:

1. **Absolute tolerance** (default $1): For small dollar amounts
2. **Relative tolerance** (default 1%): For large dollar amounts

Example:
- $1000 ± $10 = within tolerance (1%)
- $5 ± $0.50 = within tolerance ($1 absolute)

## Error Detection

The reward function identifies common encoding errors:

### Example: EITC Phaseout Bug

```python
# Real bug: phaseout threshold was 22,610 instead of 11,610
test_cases = [
    {
        "inputs": {
            "earned_income": 25000,
            "filing_status": "SINGLE",
            "eitc_qualifying_children_count": 0,
        },
        "expected": {"eitc": 0.0},  # Should be phased out
    }
]

result = reward_fn.evaluate({}, "eitc", test_cases, 2024)

if result.n_failed > 0:
    print("Detected phaseout error!")
    for case in result.diagnostics["failed_cases"]:
        print(f"Expected ${case['expected']}, got ${case['actual']}")
```

## Oracle Implementation

### Creating Custom Oracles

```python
from cosilico.rl.reward import Oracle

class MyCustomOracle(Oracle):
    name = "MyOracle"
    priority = 3  # Lower = higher priority

    def supports(self, variable: str, year: int) -> bool:
        return variable in ["eitc", "ctc"]

    def calculate(
        self,
        inputs: dict,
        variable: str,
        year: int
    ) -> float | None:
        # Your calculation logic
        return calculated_value
```

### Oracle Consensus

When multiple oracles are available:

1. **Highest-priority oracle** is used as ground truth
2. **Consensus flag** indicates if all oracles agree
3. **Oracle results** are logged for debugging

## Integration with RL Training

The reward function integrates with the RL training loop:

```python
from cosilico.rl import RLTrainer
from cosilico.rl.reward import EncodingRewardFunction, PolicyEngineOracle

# Create reward function
reward_fn = EncodingRewardFunction(
    oracles=[PolicyEngineOracle()],
    partial_credit=True,
)

# In training loop
for iteration in range(max_iterations):
    # Agent generates code
    generated_code = agent.generate(statute)

    # Compile and extract parameters
    encoded_params = compile_and_extract(generated_code)

    # Evaluate against oracles
    result = reward_fn.evaluate(
        encoded_params=encoded_params,
        variable=target_variable,
        test_cases=test_cases,
        year=tax_year,
    )

    # Use reward to update agent
    agent.update(reward=result.reward)

    # Check if we've reached target accuracy
    if result.accuracy >= 0.95:
        break
```

## Diagnostics

The `RewardResult` provides rich diagnostics:

```python
result = reward_fn.evaluate(...)

# Overall metrics
print(f"Reward: {result.reward}")
print(f"Accuracy: {result.accuracy}")
print(f"Mean error: {result.mean_error}")
print(f"Max error: {result.max_error}")

# Per-case analysis
for comp in result.diagnostics["comparisons"]:
    print(f"Test {comp['test_id']}:")
    print(f"  Expected: {comp['expected']}")
    print(f"  Actual: {comp['actual']}")
    print(f"  Match: {comp['match']}")
    print(f"  Oracles: {comp['oracles']}")
    print(f"  Consensus: {comp['consensus']}")

# Failed cases only
for case in result.diagnostics["failed_cases"]:
    print(f"Failed: {case['test_id']}")
    print(f"  Error: ${case['error']:.2f} ({case['rel_error_pct']:.1f}%)")
```

## Testing

Run the test suite:

```bash
cd rac
pytest tests/test_reward.py -v
```

Run the demo:

```bash
python examples/reward_function_demo.py
```

## Dependencies

Core:
- `rac-validators` - Validation infrastructure

Optional (for specific oracles):
- `policyengine-us` - PolicyEngine oracle
- `taxsim` executable - TAXSIM oracle

Install:
```bash
pip install rac-validators[policyengine]
```

## Design Documentation

For full design rationale, see:
- `/Users/maxghenis/CosilicoAI/rac/docs/ai-encoding/reward-functions.md`

## Examples

See complete working examples in:
- `/Users/maxghenis/CosilicoAI/rac/examples/reward_function_demo.py`
