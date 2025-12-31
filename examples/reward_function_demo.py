"""Demo of the reward function for policy encoding validation.

This script demonstrates how to use the reward function to validate
encoded tax/benefit parameters against oracles.
"""

from rac.rl.reward import (
    EncodingRewardFunction,
    StructuralRewardFunction,
    CombinedRewardFunction,
    PolicyEngineOracle,
    TaxsimOracle,
)


def demo_basic_reward():
    """Demo basic reward function usage."""
    print("=" * 60)
    print("DEMO 1: Basic Reward Function")
    print("=" * 60)

    # Create oracles
    try:
        pe_oracle = PolicyEngineOracle()
        print("✓ PolicyEngine oracle loaded")
    except ImportError:
        print("✗ PolicyEngine not available (install: pip install policyengine-us)")
        pe_oracle = None

    try:
        taxsim_oracle = TaxsimOracle()
        print("✓ TAXSIM oracle loaded")
    except (ImportError, FileNotFoundError) as e:
        print(f"✗ TAXSIM not available: {e}")
        taxsim_oracle = None

    if not pe_oracle and not taxsim_oracle:
        print("\nNo oracles available. Install validators:")
        print("  pip install 'cosilico-validators[policyengine]'")
        return

    oracles = [o for o in [pe_oracle, taxsim_oracle] if o is not None]

    # Create reward function
    reward_fn = EncodingRewardFunction(
        oracles=oracles,
        tolerance_absolute=1.0,  # $1 tolerance
        tolerance_relative=0.01,  # 1% tolerance
        partial_credit=True,
    )

    # Test cases for EITC
    test_cases = [
        {
            "inputs": {
                "earned_income": 15000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 0,
            },
            "expected": {"eitc": 560.0},
        },
        {
            "inputs": {
                "earned_income": 25000,
                "filing_status": "JOINT",
                "eitc_qualifying_children_count": 2,
            },
            "expected": {"eitc": 6000.0},
        },
    ]

    # Evaluate (parameters not actually used in this demo)
    result = reward_fn.evaluate({}, "eitc", test_cases, year=2024)

    print(f"\nResults:")
    print(f"  Reward: {result.reward:.3f}")
    print(f"  Accuracy: {result.accuracy:.1%}")
    print(f"  Cases passed: {result.n_passed}/{result.n_cases}")
    print(f"  Mean error: ${result.mean_error:.2f}")
    print(f"  Max error: ${result.max_error:.2f}")

    if result.n_failed > 0:
        print(f"\nFailed cases:")
        for case in result.diagnostics["failed_cases"]:
            print(
                f"  {case['test_id']}: expected ${case['expected']:.2f}, "
                f"got ${case['actual']:.2f} "
                f"(error: {case['rel_error_pct']:.1f}%)"
            )


def demo_phaseout_bug_detection():
    """Demo detecting the EITC phaseout bug."""
    print("\n" + "=" * 60)
    print("DEMO 2: Detecting EITC Phaseout Bug")
    print("=" * 60)

    try:
        oracle = PolicyEngineOracle()
    except ImportError:
        print("PolicyEngine not available - skipping demo")
        return

    reward_fn = EncodingRewardFunction(oracles=[oracle])

    # Test cases that would expose phaseout threshold bug
    test_cases = [
        {
            "inputs": {
                "earned_income": 8000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 0,
            },
            "expected": {"eitc": 560.0},  # Phase-in region - should work
        },
        {
            "inputs": {
                "earned_income": 11500,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 0,
            },
            "expected": {
                "eitc": 300.0
            },  # Start of phaseout (correct threshold = 11,610)
        },
        {
            "inputs": {
                "earned_income": 18000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 0,
            },
            "expected": {"eitc": 0.0},  # Should be fully phased out
        },
    ]

    print("\nScenario: Correct phaseout threshold (11,610)")
    result = reward_fn.evaluate({}, "eitc", test_cases, year=2024)
    print(f"  Reward: {result.reward:.3f}")
    print(f"  Accuracy: {result.accuracy:.1%}")

    # Now simulate buggy threshold (22,610 instead of 11,610)
    print("\nScenario: BUGGY phaseout threshold (22,610)")
    print("  This bug would make high earners still get credit")
    print("  The reward function should detect this error")

    # In real usage, the buggy parameters would cause different calculations
    # Here we just show what the reward function would report
    if result.n_failed > 0:
        print(f"\n  ✓ Detected {result.n_failed} failing test case(s)")
        print("  Failed cases:")
        for case in result.diagnostics["failed_cases"]:
            print(
                f"    - Income ${case['expected']:.0f} should have "
                f"EITC=${case['actual']:.2f}"
            )
    else:
        print("  All tests passed")


def demo_partial_credit():
    """Demo partial credit for near-correct answers."""
    print("\n" + "=" * 60)
    print("DEMO 3: Partial Credit for Close Answers")
    print("=" * 60)

    try:
        oracle = PolicyEngineOracle()
    except ImportError:
        print("PolicyEngine not available - skipping demo")
        return

    # Test with partial credit enabled
    reward_fn_partial = EncodingRewardFunction(oracles=[oracle], partial_credit=True)

    # Test with partial credit disabled
    reward_fn_exact = EncodingRewardFunction(oracles=[oracle], partial_credit=False)

    # Test case with small error
    test_cases = [
        {
            "inputs": {
                "earned_income": 15000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 1,
            },
            "expected": {
                "eitc": 3600.0
            },  # Slightly off from actual (demonstration purposes)
        }
    ]

    print("\nWith partial credit:")
    result = reward_fn_partial.evaluate({}, "eitc", test_cases, year=2024)
    print(f"  Reward: {result.reward:.3f}")
    print(
        f"  (Even if not exactly correct, close answers get partial credit)"
    )

    print("\nWithout partial credit:")
    result = reward_fn_exact.evaluate({}, "eitc", test_cases, year=2024)
    print(f"  Reward: {result.reward:.3f}")
    print(f"  (Binary: either correct or not)")


def demo_combined_reward():
    """Demo combined structural + semantic reward."""
    print("\n" + "=" * 60)
    print("DEMO 4: Combined Structural + Semantic Reward")
    print("=" * 60)

    try:
        oracle = PolicyEngineOracle()
    except ImportError:
        print("PolicyEngine not available - skipping demo")
        return

    # Create component reward functions
    structural_fn = StructuralRewardFunction()
    semantic_fn = EncodingRewardFunction(oracles=[oracle])

    # Test different alpha values (curriculum learning)
    alphas = [0.5, 0.3, 0.1, 0.0]
    alpha_names = ["Early training", "Middle training", "Late training", "Final"]

    # Mock structural metadata
    structural_metadata = {
        "parses": True,
        "uses_valid_primitives": True,
        "has_required_metadata": True,
        "follows_naming_conventions": True,
        "references_valid_dependencies": True,
    }  # Perfect structure = 1.0

    test_cases = [
        {
            "inputs": {
                "earned_income": 15000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 1,
            },
            "expected": {"eitc": 3600.0},
        }
    ]

    print("\nCurriculum Learning Schedule:")
    print("(Shows how reward weighting changes during training)\n")

    for alpha, name in zip(alphas, alpha_names):
        combined_fn = CombinedRewardFunction(structural_fn, semantic_fn, alpha=alpha)

        reward, semantic_result = combined_fn.evaluate(
            code="...",  # Mock code
            structural_metadata=structural_metadata,
            encoded_params={},
            variable="eitc",
            test_cases=test_cases,
            year=2024,
        )

        structural_weight = alpha * 100
        semantic_weight = (1 - alpha) * 100

        print(f"{name:20s} (α={alpha:.1f})")
        print(f"  Structural weight: {structural_weight:3.0f}%")
        print(f"  Semantic weight:   {semantic_weight:3.0f}%")
        print(f"  Combined reward:   {reward:.3f}")
        print()


def demo_oracle_consensus():
    """Demo oracle consensus checking."""
    print("\n" + "=" * 60)
    print("DEMO 5: Oracle Consensus")
    print("=" * 60)

    try:
        pe_oracle = PolicyEngineOracle()
        print("Using PolicyEngine oracle")
    except ImportError:
        print("PolicyEngine not available - skipping demo")
        return

    try:
        taxsim_oracle = TaxsimOracle()
        print("Using TAXSIM oracle")
        oracles = [pe_oracle, taxsim_oracle]
    except (ImportError, FileNotFoundError):
        print("TAXSIM not available - using PolicyEngine only")
        oracles = [pe_oracle]

    reward_fn = EncodingRewardFunction(oracles=oracles)

    test_cases = [
        {
            "inputs": {
                "earned_income": 15000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 1,
            },
            "expected": {"eitc": 3600.0},
        }
    ]

    result = reward_fn.evaluate({}, "eitc", test_cases, year=2023)

    print(f"\nResults with {len(oracles)} oracle(s):")
    print(f"  Reward: {result.reward:.3f}")

    if result.diagnostics.get("comparisons"):
        comparison = result.diagnostics["comparisons"][0]
        print(f"  Oracle values:")
        for oracle_name, value in comparison["oracles"].items():
            print(f"    {oracle_name}: ${value:.2f}")
        print(f"  Consensus: {comparison['consensus']}")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print(" COSILICO REWARD FUNCTION DEMONSTRATION")
    print("=" * 70)

    demo_basic_reward()
    demo_phaseout_bug_detection()
    demo_partial_credit()
    demo_combined_reward()
    demo_oracle_consensus()

    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)
    print(
        "\nTo use the reward function in RL training, integrate it with"
        " the RLTrainer"
    )
    print("in rac.rl.trainer to provide reward signals for policy encoding.")
    print()


if __name__ == "__main__":
    main()
