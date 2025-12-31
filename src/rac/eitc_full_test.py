#!/usr/bin/env python3
"""Test the agentic loop on full EITC (phase-in + phase-out).

This is a harder test that requires understanding the full EITC structure:
1. Phase-in: credit increases with earned income up to earned_income_amount
2. Plateau: credit stays at max from earned_income_amount to phase_out_start
3. Phase-out: credit decreases from phase_out_start to phase_out_end

The formula is more complex and requires proper handling of all three regions.
"""

import os

from rac.agent import AgentTrainingLoop
from rac.types import Statute, TestCase


def eitc_calculator(earned_income: float, n_children: int) -> float:
    """Calculate full EITC for 2024 (phase-in + plateau + phase-out)."""
    # 2024 parameters
    params = {
        0: {"rate": 0.0765, "ei_amt": 7840, "max_credit": 600, "po_start": 9800, "po_end": 17640, "po_rate": 0.0765},
        1: {"rate": 0.34, "ei_amt": 11750, "max_credit": 3995, "po_start": 22720, "po_end": 49080, "po_rate": 0.1598},
        2: {"rate": 0.40, "ei_amt": 16510, "max_credit": 6604, "po_start": 22720, "po_end": 55770, "po_rate": 0.2106},
        3: {"rate": 0.45, "ei_amt": 16510, "max_credit": 7430, "po_start": 22720, "po_end": 59900, "po_rate": 0.2106},
    }

    p = params.get(min(n_children, 3))

    # Phase-in
    phase_in_credit = min(earned_income, p["ei_amt"]) * p["rate"]

    # Phase-out reduction
    if earned_income > p["po_start"]:
        reduction = (earned_income - p["po_start"]) * p["po_rate"]
    else:
        reduction = 0

    # Final credit
    credit = max(0, min(phase_in_credit, p["max_credit"]) - reduction)

    return credit


def create_full_eitc_test_cases() -> list[TestCase]:
    """Create comprehensive test cases covering all EITC regions."""
    cases = []

    # Test at key boundary points and in between
    income_points = [
        0, 1000, 5000,  # Early phase-in
        7840, 8000,  # Around phase-in end for 0 children
        9800, 10000, 15000,  # Phase-out region for 0 children
        11750, 12000,  # Around phase-in end for 1 child
        16510, 17000,  # Around phase-in end for 2-3 children
        17640, 18000,  # Phase-out end for 0 children
        22720, 25000, 30000, 35000, 40000, 45000,  # Phase-out for 1+ children
        49080, 50000,  # Phase-out end for 1 child
        55770, 56000,  # Phase-out end for 2 children
        59900, 60000,  # Phase-out end for 3 children
    ]

    case_id = 0
    for income in income_points:
        for n_children in [0, 1, 2, 3]:
            expected_eitc = eitc_calculator(income, n_children)

            cases.append(TestCase(
                id=f"full_eitc_{case_id}",
                inputs={
                    "earned_income": income,
                    "filing_status": "SINGLE",
                    "n_children": n_children,
                    "n_qualifying_children": n_children,
                },
                expected={"eitc": expected_eitc},
                description=f"income=${income}, children={n_children}, expected=${expected_eitc:.2f}"
            ))
            case_id += 1

    return cases


FULL_EITC_STATUTE = Statute(
    citation="26 USC § 32",
    text="""
26 USC § 32 - Earned Income Tax Credit

(a) Allowance of credit
    (1) In general
    In the case of an eligible individual, there shall be allowed as a credit
    against the tax imposed by this subtitle for the taxable year an amount
    equal to the credit percentage of so much of the taxpayer's earned income
    for the taxable year as does not exceed the earned income amount.

    (2) Limitation
    The amount of the credit allowable to a taxpayer under paragraph (1) for
    any taxable year shall not exceed the excess (if any) of—
        (A) the credit percentage of the earned income amount, over
        (B) the phaseout percentage of so much of the adjusted gross income
        (or, if greater, the earned income) of the taxpayer for the taxable
        year as exceeds the phaseout amount.

Parameters (2024, Single filing status):
- 0 children: rate=7.65%, earned_income_amount=$7,840, max_credit=$600,
              phaseout_start=$9,800, phaseout_end=$17,640, phaseout_rate=7.65%
- 1 child: rate=34%, earned_income_amount=$11,750, max_credit=$3,995,
           phaseout_start=$22,720, phaseout_end=$49,080, phaseout_rate=15.98%
- 2 children: rate=40%, earned_income_amount=$16,510, max_credit=$6,604,
              phaseout_start=$22,720, phaseout_end=$55,770, phaseout_rate=21.06%
- 3+ children: rate=45%, earned_income_amount=$16,510, max_credit=$7,430,
               phaseout_start=$22,720, phaseout_end=$59,900, phaseout_rate=21.06%

The credit calculation:
1. Phase-in credit = min(earned_income, earned_income_amount) × credit_rate
2. Max credit = earned_income_amount × credit_rate (or explicit max)
3. Phase-out reduction = max(0, earned_income - phaseout_start) × phaseout_rate
4. Final credit = max(0, min(phase_in_credit, max_credit) - phase_out_reduction)
    """.strip(),
    jurisdiction="us",
)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test agentic loop on full EITC")
    parser.add_argument("--model", default="claude-opus-4-5-20251101")
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--target-accuracy", type=float, default=0.90)
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set")
        return

    test_cases = create_full_eitc_test_cases()

    print("=" * 70)
    print("Full EITC Agentic Training Test")
    print("=" * 70)
    print(f"Model: {args.model}")
    print(f"Test cases: {len(test_cases)} (covering phase-in, plateau, phase-out)")
    print(f"Target accuracy: {args.target_accuracy:.0%}")
    print("=" * 70)

    # Show sample cases
    print("\nSample test cases:")
    for tc in test_cases[:5]:
        print(f"  {tc.description}")
    print("  ...")

    loop = AgentTrainingLoop(
        model=args.model,
        max_iterations=args.max_iterations,
        target_accuracy=args.target_accuracy,
    )

    result = loop.train(FULL_EITC_STATUTE, test_cases, verbose=True)

    print("\n" + "=" * 70)
    print("FINAL RESULT")
    print("=" * 70)
    print(f"Success: {result['success']}")
    print(f"Final accuracy: {result['final_accuracy']:.1%}")
    print(f"Iterations: {result['iterations']}")

    if result["final_code"]:
        print("\nFinal code:")
        print("-" * 40)
        print(result["final_code"])


if __name__ == "__main__":
    main()
