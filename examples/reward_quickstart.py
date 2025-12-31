"""Quick start guide for the reward function.

This minimal example shows how to use the reward function in 5 lines of code.
"""

from rac.rl.reward import EncodingRewardFunction, PolicyEngineOracle


def minimal_example():
    """Minimal working example."""
    # 1. Create oracle
    oracle = PolicyEngineOracle()

    # 2. Create reward function
    reward_fn = EncodingRewardFunction(oracles=[oracle])

    # 3. Define test case
    test_cases = [
        {
            "inputs": {
                "earned_income": 15000,
                "filing_status": "SINGLE",
                "eitc_qualifying_children_count": 0,
            },
            "expected": {"eitc": 560.0},
        }
    ]

    # 4. Evaluate
    result = reward_fn.evaluate({}, "eitc", test_cases, 2024)

    # 5. Use reward
    print(f"Reward: {result.reward:.3f}")
    print(f"Accuracy: {result.accuracy:.1%}")


if __name__ == "__main__":
    try:
        minimal_example()
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("\nInstall with:")
        print("  pip install 'cosilico-validators[policyengine]'")
