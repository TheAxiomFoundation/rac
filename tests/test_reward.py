"""Tests for reward function."""

import pytest

from src.rac.rl.reward import (
    CombinedRewardFunction,
    EncodingRewardFunction,
    Oracle,
    PolicyEngineOracle,
    StructuralRewardFunction,
)


class MockOracle(Oracle):
    """Mock oracle for testing."""

    def __init__(self, name: str, values: dict[str, float], priority: int = 2):
        self.name = name
        self.priority = priority
        self._values = values  # Map of test_id -> value

    def supports(self, variable: str, year: int) -> bool:
        return True

    def calculate(self, inputs: dict, variable: str, year: int) -> float | None:
        # Use a unique key based on inputs
        key = f"{inputs.get('earned_income', 0)}_{inputs.get('children', 0)}"
        return self._values.get(key)


class TestEncodingRewardFunction:
    """Test encoding reward function."""

    def test_perfect_match_gives_full_reward(self):
        """Perfect match across all test cases should give reward = 1.0."""
        oracle = MockOracle(
            "test",
            {
                "25000_2": 6000.0,
                "45000_1": 3000.0,
            },
        )

        reward_fn = EncodingRewardFunction(oracles=[oracle])

        test_cases = [
            {
                "inputs": {"earned_income": 25000, "children": 2},
                "expected": {"eitc": 6000.0},
            },
            {
                "inputs": {"earned_income": 45000, "children": 1},
                "expected": {"eitc": 3000.0},
            },
        ]

        result = reward_fn.evaluate({}, "eitc", test_cases, 2024)

        assert result.reward == 1.0
        assert result.accuracy == 1.0
        assert result.n_passed == 2
        assert result.n_failed == 0
        assert result.mean_error == 0.0

    def test_complete_failure_gives_zero_reward(self):
        """Complete mismatch should give low/zero reward."""
        oracle = MockOracle(
            "test",
            {
                "25000_2": 6000.0,  # Oracle says 6000
                "45000_1": 3000.0,  # Oracle says 3000
            },
        )

        reward_fn = EncodingRewardFunction(oracles=[oracle], partial_credit=False)

        test_cases = [
            {
                "inputs": {"earned_income": 25000, "children": 2},
                "expected": {"eitc": 1000.0},  # Wrong - expected 1000 vs actual 6000
            },
            {
                "inputs": {"earned_income": 45000, "children": 1},
                "expected": {"eitc": 500.0},  # Wrong - expected 500 vs actual 3000
            },
        ]

        result = reward_fn.evaluate({}, "eitc", test_cases, 2024)

        assert result.reward == 0.0
        assert result.accuracy == 0.0
        assert result.n_passed == 0
        assert result.n_failed == 2
        assert result.mean_error > 0

    def test_partial_credit_for_close_answers(self):
        """Close answers should get partial credit."""
        oracle = MockOracle("test", {"25000_2": 6000.0})

        reward_fn = EncodingRewardFunction(oracles=[oracle], partial_credit=True)

        # Test case with 5% error (should get 0.8 credit)
        test_cases = [
            {
                "inputs": {"earned_income": 25000, "children": 2},
                "expected": {"eitc": 6300.0},  # 5% off from 6000
            }
        ]

        result = reward_fn.evaluate({}, "eitc", test_cases, 2024)

        # 5% error should give 0.8 credit per the schedule
        assert 0.75 <= result.reward <= 0.85
        assert result.accuracy == 0.0  # Exact match fails
        assert result.n_failed == 1

    def test_phaseout_error_detected(self):
        """Test that phase-out errors (like our EITC bug) are detected."""
        # Oracle with correct phase-out behavior
        oracle = MockOracle(
            "test",
            {
                "15000_0": 500.0,  # In phase-in region
                "25000_0": 0.0,  # Fully phased out (correct)
            },
        )

        reward_fn = EncodingRewardFunction(oracles=[oracle])

        # Our buggy implementation had wrong phaseout threshold
        test_cases = [
            {
                "inputs": {"earned_income": 15000, "children": 0},
                "expected": {"eitc": 500.0},  # Should match
            },
            {
                "inputs": {"earned_income": 25000, "children": 0},
                "expected": {"eitc": 250.0},  # WRONG - should be 0
            },
        ]

        result = reward_fn.evaluate({}, "eitc", test_cases, 2024)

        # Should catch the phaseout error
        assert result.accuracy < 1.0
        assert result.n_failed >= 1
        # Check that test case 1 (index 1) failed
        assert len(result.diagnostics["failed_cases"]) >= 1
        assert result.diagnostics["failed_cases"][0]["expected"] == 250.0
        assert result.diagnostics["failed_cases"][0]["actual"] == 0.0

    def test_tolerance_handling(self):
        """Test absolute and relative tolerance."""
        oracle = MockOracle("test", {"25000_2": 6000.0})

        # Test absolute tolerance ($1)
        reward_fn = EncodingRewardFunction(
            oracles=[oracle],
            tolerance_absolute=1.0,
            tolerance_relative=0.01,
            partial_credit=False,  # Disable partial credit for this test
        )

        test_cases = [
            {
                "inputs": {"earned_income": 25000, "children": 2},
                "expected": {"eitc": 6000.50},  # $0.50 off - within $1 tolerance
            }
        ]

        result = reward_fn.evaluate({}, "eitc", test_cases, 2024)
        assert result.reward == 1.0  # Should pass with tolerance
        assert result.accuracy == 1.0  # Within tolerance counts as pass

        # Test relative tolerance (1%)
        test_cases = [
            {
                "inputs": {"earned_income": 25000, "children": 2},
                "expected": {"eitc": 6060.0},  # 1% off - within tolerance
            }
        ]

        result = reward_fn.evaluate({}, "eitc", test_cases, 2024)
        assert result.reward == 1.0  # Should pass with tolerance
        assert result.accuracy == 1.0  # Within tolerance counts as pass

    def test_multiple_oracles_consensus(self):
        """Test consensus checking across multiple oracles."""
        oracle1 = MockOracle("Oracle1", {"25000_2": 6000.0}, priority=1)
        oracle2 = MockOracle("Oracle2", {"25000_2": 6000.0}, priority=2)
        oracle3 = MockOracle("Oracle3", {"25000_2": 5900.0}, priority=3)

        reward_fn = EncodingRewardFunction(oracles=[oracle1, oracle2, oracle3])

        test_cases = [
            {
                "inputs": {"earned_income": 25000, "children": 2},
                "expected": {"eitc": 6000.0},
            }
        ]

        result = reward_fn.evaluate({}, "eitc", test_cases, 2024)

        # Should use highest priority oracle (oracle1) as ground truth
        assert result.reward == 1.0

        # Check consensus (oracle3 disagrees by 100, should fail consensus)
        comparison = result.diagnostics["comparisons"][0]
        assert comparison["consensus"] is False  # Oracles disagree

    def test_zero_expected_value_handling(self):
        """Test handling of cases where expected value is $0."""
        oracle = MockOracle("test", {"50000_0": 0.0})

        reward_fn = EncodingRewardFunction(oracles=[oracle])

        # Correct zero
        test_cases = [
            {
                "inputs": {"earned_income": 50000, "children": 0},
                "expected": {"eitc": 0.0},
            }
        ]

        result = reward_fn.evaluate({}, "eitc", test_cases, 2024)
        assert result.reward == 1.0

        # Incorrect - should be zero but isn't
        test_cases = [
            {
                "inputs": {"earned_income": 50000, "children": 0},
                "expected": {"eitc": 500.0},  # Wrong!
            }
        ]

        result = reward_fn.evaluate({}, "eitc", test_cases, 2024)
        assert result.reward < 1.0

    def test_empty_test_cases(self):
        """Test behavior with no test cases."""
        oracle = MockOracle("test", {})
        reward_fn = EncodingRewardFunction(oracles=[oracle])

        result = reward_fn.evaluate({}, "eitc", [], 2024)

        assert result.reward == 0.0
        assert result.n_cases == 0


class TestStructuralRewardFunction:
    """Test structural reward function."""

    def test_perfect_structure(self):
        """Perfect structural correctness should give 1.0."""
        structural_fn = StructuralRewardFunction()

        metadata = {
            "parses": True,
            "uses_valid_primitives": True,
            "has_required_metadata": True,
            "follows_naming_conventions": True,
            "references_valid_dependencies": True,
        }

        score = structural_fn.evaluate("code", metadata)
        assert score == 1.0

    def test_partial_structure(self):
        """Partial structural correctness should give partial score."""
        structural_fn = StructuralRewardFunction()

        # Only parses
        metadata = {
            "parses": True,
            "uses_valid_primitives": False,
            "has_required_metadata": False,
            "follows_naming_conventions": False,
            "references_valid_dependencies": False,
        }

        score = structural_fn.evaluate("code", metadata)
        assert score == 0.3  # Only parsing weight

        # Parses + primitives
        metadata["uses_valid_primitives"] = True
        score = structural_fn.evaluate("code", metadata)
        assert score == 0.5  # 0.3 + 0.2

    def test_no_structure(self):
        """No structural correctness should give 0.0."""
        structural_fn = StructuralRewardFunction()

        metadata = {
            "parses": False,
            "uses_valid_primitives": False,
            "has_required_metadata": False,
            "follows_naming_conventions": False,
            "references_valid_dependencies": False,
        }

        score = structural_fn.evaluate("code", metadata)
        assert score == 0.0


class TestCombinedRewardFunction:
    """Test combined reward function."""

    def test_alpha_weighting(self):
        """Test alpha weighting between structural and semantic."""
        structural_fn = StructuralRewardFunction()
        oracle = MockOracle("test", {"25000_2": 6000.0})
        semantic_fn = EncodingRewardFunction(oracles=[oracle])

        # Alpha = 0.5 (equal weighting)
        combined_fn = CombinedRewardFunction(structural_fn, semantic_fn, alpha=0.5)

        structural_metadata = {
            "parses": True,
            "uses_valid_primitives": True,
            "has_required_metadata": True,
            "follows_naming_conventions": True,
            "references_valid_dependencies": True,
        }  # Structural score = 1.0

        test_cases = [
            {
                "inputs": {"earned_income": 25000, "children": 2},
                "expected": {"eitc": 6000.0},
            }
        ]  # Semantic score = 1.0

        reward, semantic_result = combined_fn.evaluate(
            "code", structural_metadata, {}, "eitc", test_cases, 2024
        )

        # 0.5 * 1.0 + 0.5 * 1.0 = 1.0
        assert reward == 1.0

    def test_curriculum_learning_schedule(self):
        """Test alpha scheduling for curriculum learning."""
        structural_fn = StructuralRewardFunction()
        oracle = MockOracle("test", {"25000_2": 6000.0})
        semantic_fn = EncodingRewardFunction(oracles=[oracle])

        combined_fn = CombinedRewardFunction(structural_fn, semantic_fn, alpha=0.5)

        # Early training: focus on structure (alpha=0.5)
        combined_fn.set_alpha(0.5)
        assert combined_fn.alpha == 0.5

        # Middle training: balance (alpha=0.3)
        combined_fn.set_alpha(0.3)
        assert combined_fn.alpha == 0.3

        # Late training: focus on semantics (alpha=0.1)
        combined_fn.set_alpha(0.1)
        assert combined_fn.alpha == 0.1

        # Final: pure semantics (alpha=0.0)
        combined_fn.set_alpha(0.0)
        assert combined_fn.alpha == 0.0


class TestPolicyEngineOracle:
    """Test PolicyEngine oracle integration."""

    @pytest.mark.skip(reason="Requires policyengine-us installation")
    def test_policyengine_oracle_eitc(self):
        """Test PolicyEngine oracle calculates EITC correctly."""
        oracle = PolicyEngineOracle()

        assert oracle.supports("eitc", 2024)

        inputs = {
            "earned_income": 15000,
            "filing_status": "SINGLE",
            "eitc_qualifying_children_count": 0,
        }

        result = oracle.calculate(inputs, "eitc", 2024)

        # Should return a non-None value
        assert result is not None
        assert isinstance(result, float)
        assert result >= 0


@pytest.mark.integration
class TestRewardFunctionIntegration:
    """Integration tests with real validators."""

    @pytest.mark.skip(reason="Requires validator setup")
    def test_eitc_phaseout_bug_detection(self):
        """Test that reward function detects EITC phaseout bug.

        This is the real bug we had: phase-out threshold was 22,610 instead of 11,610
        for single filers with no children.
        """
        # Use real PolicyEngine oracle
        oracle = PolicyEngineOracle()
        reward_fn = EncodingRewardFunction(oracles=[oracle])

        # Test cases spanning the phase-out region
        test_cases = [
            {
                "inputs": {
                    "earned_income": 8000,
                    "filing_status": "SINGLE",
                    "eitc_qualifying_children_count": 0,
                },
                "expected": {"eitc": 560.0},  # In phase-in
            },
            {
                "inputs": {
                    "earned_income": 11500,
                    "filing_status": "SINGLE",
                    "eitc_qualifying_children_count": 0,
                },
                "expected": {"eitc": 200.0},  # In phase-out (correct threshold)
            },
            {
                "inputs": {
                    "earned_income": 18000,
                    "filing_status": "SINGLE",
                    "eitc_qualifying_children_count": 0,
                },
                "expected": {"eitc": 0.0},  # Fully phased out
            },
            {
                "inputs": {
                    "earned_income": 25000,
                    "filing_status": "SINGLE",
                    "eitc_qualifying_children_count": 0,
                },
                "expected": {
                    "eitc": 250.0
                },  # BUG: with wrong threshold (22610), this would still have credit
            },
        ]

        # Buggy parameters (wrong phaseout threshold)
        buggy_params = {
            "eitc": {
                "phase_out_start": {
                    "single": {"0_children": 22610}  # WRONG - should be 11610
                }
            }
        }

        result = reward_fn.evaluate(buggy_params, "eitc", test_cases, 2024)

        # Should detect the error in the high-income case
        assert result.accuracy < 1.0
        assert result.n_failed > 0

        # The failed case should be the $25,000 case
        failed = result.diagnostics["failed_cases"]
        assert any(tc["expected"] != tc["actual"] for tc in failed)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
