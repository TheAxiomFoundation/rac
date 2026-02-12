#!/usr/bin/env python3
"""Demo script for the RAC training loop.

Run with:
    python -m rac.demo

Or with PolicyEngine oracle:
    python -m rac.demo --use-pe
"""

import argparse

from .generator import CodeGenerator, MockGenerator
from .oracles import MockOracle, PolicyEngineOracle
from .training import TestCaseGenerator, TrainingLoop
from .types import Statute, TestCase

# The statutory text we're encoding
EITC_PHASE_IN_STATUTE = Statute(
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


def create_mock_test_cases() -> list[TestCase]:
    """Create test cases using mock oracle (no PE dependency)."""
    oracle = MockOracle()

    cases = []
    incomes = [0, 5000, 7840, 10000, 15000, 20000]
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
                    id=f"mock_{i}_{n_children}",
                    inputs=inputs,
                    expected=expected,
                )
            )
    return cases


def run_mock_demo():
    """Run demo with mock components (no API calls)."""
    print("=" * 60)
    print("RAC Training Loop - Mock Demo")
    print("=" * 60)

    # Create mock test cases
    test_cases = create_mock_test_cases()
    print(f"\nCreated {len(test_cases)} test cases")

    # Create training loop with mock generator
    loop = TrainingLoop(
        generator=MockGenerator(),
        max_iterations=3,
        target_accuracy=0.95,
    )

    # Run training
    print("\nStarting training loop...")
    result = loop.train(
        statute=EITC_PHASE_IN_STATUTE,
        test_cases=test_cases,
        verbose=True,
    )

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Iterations: {result.iterations}")
    print(f"Final accuracy: {result.history[-1].score.accuracy:.2%}")

    print("\nGenerated code:")
    print("-" * 40)
    print(result.final_code.source)


def run_pe_demo():
    """Run demo with PolicyEngine oracle."""
    print("=" * 60)
    print("RAC Training Loop - PolicyEngine Demo")
    print("=" * 60)

    # Check for PolicyEngine
    try:
        from policyengine_us import Simulation  # noqa: F401

        print("PolicyEngine-US loaded successfully")
    except ImportError:
        print("ERROR: PolicyEngine-US not installed")
        print("Install with: pip install policyengine-us")
        return

    # Create test cases from PE oracle
    print("\nGenerating test cases from PolicyEngine oracle...")
    oracle = PolicyEngineOracle(year=2024)
    test_gen = TestCaseGenerator(oracle=oracle)

    test_cases = test_gen.generate_eitc_cases(n_cases=50)
    print(f"Created {len(test_cases)} test cases")

    # Show sample
    if test_cases:
        sample = test_cases[0]
        print(f"\nSample case: {sample.description}")
        print(f"  Inputs: {sample.inputs}")
        print(f"  Expected: {sample.expected}")

    # Create training loop with mock generator (avoid API costs for demo)
    # In production, use CodeGenerator() with real LLM
    print("\nNote: Using MockGenerator to avoid API costs.")
    print("For real training, use CodeGenerator() with ANTHROPIC_API_KEY set.")

    loop = TrainingLoop(
        generator=MockGenerator(),
        oracles=[oracle],
        max_iterations=5,
        target_accuracy=0.90,
    )

    # Run training
    print("\nStarting training loop...")
    result = loop.train(
        statute=EITC_PHASE_IN_STATUTE,
        test_cases=test_cases,
        verbose=True,
    )

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Iterations: {result.iterations}")
    if result.history:
        print(f"Final accuracy: {result.history[-1].score.accuracy:.2%}")
        print(f"MAE: ${result.history[-1].score.mean_absolute_error:.2f}")

    print("\nGenerated code:")
    print("-" * 40)
    print(result.final_code.source)


def run_llm_demo():
    """Run demo with real LLM (requires ANTHROPIC_API_KEY)."""
    import os

    print("=" * 60)
    print("RAC Training Loop - LLM Demo")
    print("=" * 60)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set")
        print("Set with: export ANTHROPIC_API_KEY=your_key")
        return

    # Create test cases
    test_cases = create_mock_test_cases()
    print(f"\nCreated {len(test_cases)} test cases")

    # Create training loop with real generator
    loop = TrainingLoop(
        generator=CodeGenerator(model="claude-opus-4-5-20251101"),
        max_iterations=5,
        target_accuracy=0.95,
    )

    # Run training
    print("\nStarting training loop with Claude...")
    result = loop.train(
        statute=EITC_PHASE_IN_STATUTE,
        test_cases=test_cases,
        verbose=True,
    )

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Iterations: {result.iterations}")
    if result.history:
        print(f"Final accuracy: {result.history[-1].score.accuracy:.2%}")

    print("\nGenerated code:")
    print("-" * 40)
    print(result.final_code.source)


def main():
    parser = argparse.ArgumentParser(description="RAC Training Loop Demo")
    parser.add_argument(
        "--mode",
        choices=["mock", "pe", "llm"],
        default="mock",
        help="Demo mode: mock (no deps), pe (PolicyEngine), llm (real Claude)",
    )
    args = parser.parse_args()

    if args.mode == "mock":
        run_mock_demo()
    elif args.mode == "pe":
        run_pe_demo()
    elif args.mode == "llm":
        run_llm_demo()


if __name__ == "__main__":
    main()
