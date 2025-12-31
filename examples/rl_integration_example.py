"""Example of integrating the reward function into an RL training loop.

This shows how the reward function would be used in practice to train
an agent to encode tax/benefit policies.
"""

from rac.rl.reward import (
    EncodingRewardFunction,
    StructuralRewardFunction,
    CombinedRewardFunction,
    PolicyEngineOracle,
)


def mock_agent_training_loop():
    """Simulated RL training loop with reward function.

    In practice, this would be integrated with RLTrainer or a custom
    training loop that generates code and learns from rewards.
    """
    print("=" * 60)
    print("RL TRAINING LOOP INTEGRATION EXAMPLE")
    print("=" * 60)

    # Setup oracles
    try:
        oracles = [PolicyEngineOracle()]
        print("✓ PolicyEngine oracle loaded")
    except ImportError:
        print("✗ PolicyEngine not available - using mock")
        return

    # Create reward functions
    structural_fn = StructuralRewardFunction()
    semantic_fn = EncodingRewardFunction(
        oracles=oracles, tolerance_absolute=1.0, tolerance_relative=0.01, partial_credit=True
    )

    # Combined reward with curriculum learning
    combined_fn = CombinedRewardFunction(structural_fn, semantic_fn, alpha=0.5)

    # Mock training data
    statute_text = """
    IRC Section 32 - Earned Income Tax Credit
    For tax year 2024, single filers with no children:
    - Maximum credit: $632
    - Phase-in rate: 7.65%
    - Phase-out starts: $11,610
    - Phase-out ends: $18,591
    """

    # Test cases (from IRS Publication 596)
    test_cases = [
        {
            "inputs": {
                "earned_income": 8000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 0,
            },
            "expected": {"eitc": 612.0},  # 8000 * 7.65%
        },
        {
            "inputs": {
                "earned_income": 15000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 0,
            },
            "expected": {"eitc": 200.0},  # In phaseout region
        },
        {
            "inputs": {
                "earned_income": 20000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 0,
            },
            "expected": {"eitc": 0.0},  # Fully phased out
        },
    ]

    print(f"\nTraining statute: IRC Section 32 (EITC)")
    print(f"Test cases: {len(test_cases)}")
    print(f"Target accuracy: 95%")

    # Simulated training iterations
    max_iterations = 10

    for iteration in range(1, max_iterations + 1):
        print(f"\n--- Iteration {iteration} ---")

        # In real usage, agent would generate code here
        # For demo, we simulate structural metadata
        if iteration < 3:
            # Early iterations: poor structure
            structural_metadata = {
                "parses": iteration >= 2,
                "uses_valid_primitives": False,
                "has_required_metadata": False,
                "follows_naming_conventions": False,
                "references_valid_dependencies": False,
            }
        elif iteration < 6:
            # Middle iterations: good structure, learning semantics
            structural_metadata = {
                "parses": True,
                "uses_valid_primitives": True,
                "has_required_metadata": True,
                "follows_naming_conventions": True,
                "references_valid_dependencies": True,
            }
        else:
            # Late iterations: perfect structure
            structural_metadata = {
                "parses": True,
                "uses_valid_primitives": True,
                "has_required_metadata": True,
                "follows_naming_conventions": True,
                "references_valid_dependencies": True,
            }

        # Curriculum learning: adjust alpha over time
        if iteration <= 3:
            alpha = 0.5  # Early: 50% structural
        elif iteration <= 6:
            alpha = 0.3  # Middle: 30% structural
        else:
            alpha = 0.1  # Late: 10% structural

        combined_fn.set_alpha(alpha)

        # Evaluate (in real usage, would pass encoded params)
        # For demo, we simulate improving accuracy over time
        encoded_params = {}  # Mock

        # Get reward
        reward, semantic_result = combined_fn.evaluate(
            code="mock_code",
            structural_metadata=structural_metadata,
            encoded_params=encoded_params,
            variable="eitc",
            test_cases=test_cases,
            year=2024,
        )

        # Report progress
        structural_score = structural_fn.evaluate("mock_code", structural_metadata)

        print(f"  Alpha: {alpha:.1f}")
        print(f"  Structural score: {structural_score:.3f}")
        print(f"  Semantic reward: {semantic_result.reward:.3f}")
        print(f"  Combined reward: {reward:.3f}")
        print(f"  Accuracy: {semantic_result.accuracy:.1%}")
        print(f"  Cases passed: {semantic_result.n_passed}/{semantic_result.n_cases}")

        # In real training:
        # - Agent would update based on reward
        # - Generate new code for next iteration
        # - Check convergence criteria

        # Simulate convergence
        if semantic_result.accuracy >= 0.95:
            print(f"\n✓ Converged at iteration {iteration}!")
            print(f"  Final accuracy: {semantic_result.accuracy:.1%}")
            print(f"  Final reward: {reward:.3f}")
            break

    if semantic_result.accuracy < 0.95:
        print(f"\n⚠ Did not converge after {max_iterations} iterations")
        print(f"  Best accuracy: {semantic_result.accuracy:.1%}")

        # Show diagnostics for failures
        if semantic_result.diagnostics.get("failed_cases"):
            print(f"\n  Failed cases:")
            for case in semantic_result.diagnostics["failed_cases"][:3]:
                print(
                    f"    - {case['test_id']}: expected ${case['expected']:.2f}, "
                    f"got ${case['actual']:.2f} (error: {case['rel_error_pct']:.1f}%)"
                )

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)


def show_reward_usage_pattern():
    """Show the standard pattern for using rewards in training."""
    print("\n" + "=" * 60)
    print("STANDARD REWARD FUNCTION USAGE PATTERN")
    print("=" * 60)

    code = '''
# 1. Setup (once per training run)
from rac.rl.reward import (
    EncodingRewardFunction,
    StructuralRewardFunction,
    CombinedRewardFunction,
    PolicyEngineOracle,
)

oracles = [PolicyEngineOracle()]
structural_fn = StructuralRewardFunction()
semantic_fn = EncodingRewardFunction(oracles=oracles)
combined_fn = CombinedRewardFunction(structural_fn, semantic_fn, alpha=0.3)

# 2. Training loop
for iteration in range(max_iterations):
    # Agent generates code
    generated_code = agent.generate(statute_text, prompt)

    # Parse and compile
    structural_metadata = parser.analyze(generated_code)
    encoded_params = compiler.extract_params(generated_code)

    # Evaluate reward
    reward, result = combined_fn.evaluate(
        code=generated_code,
        structural_metadata=structural_metadata,
        encoded_params=encoded_params,
        variable=target_variable,
        test_cases=test_cases,
        year=tax_year,
    )

    # Update agent (RL algorithm specific)
    agent.update(reward=reward)

    # Check convergence
    if result.accuracy >= target_accuracy:
        break

    # Curriculum learning: reduce alpha over time
    combined_fn.set_alpha(max(0.0, alpha - 0.05 * iteration))

# 3. Final validation
final_result = semantic_fn.evaluate(
    encoded_params=final_params,
    variable=target_variable,
    test_cases=validation_cases,
    year=tax_year,
)

if final_result.accuracy >= 0.95:
    print("Success!")
else:
    print("Failed cases:", final_result.diagnostics["failed_cases"])
'''

    print(code)


if __name__ == "__main__":
    mock_agent_training_loop()
    show_reward_usage_pattern()
