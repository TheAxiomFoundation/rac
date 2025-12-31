"""DSL Experiment Runner.

Runs experiments using the DSL agent to generate Cosilico DSL code
instead of Python functions.
"""

import json
import os
from datetime import datetime
from typing import Any

from .dsl_agent import DSLAgentTrainingLoop
from .dsl_executor import get_default_parameters
from .types import Statute, TestCase


# Tax provision test generators - same as experiment.py but returns TestCase objects
def generate_eitc_phase_in_tests() -> list[TestCase]:
    """EITC Phase-In Credit tests using 2024 parameters."""
    cases = []
    # 2024 parameters
    params = {
        0: {"rate": 0.0765, "cap": 7840},
        1: {"rate": 0.34, "cap": 11750},
        2: {"rate": 0.40, "cap": 16510},
        3: {"rate": 0.45, "cap": 16510},
    }

    incomes = [0, 1000, 5000, 7840, 10000, 11750, 15000, 16510, 20000]
    for income in incomes:
        for n_children in [0, 1, 2, 3]:
            p = params[n_children]
            expected = min(income, p["cap"]) * p["rate"]
            cases.append(TestCase(
                id=f"eitc_phase_in_{income}_{n_children}",
                inputs={
                    "earned_income": income,
                    "n_qualifying_children": n_children,
                    "n_children": n_children,
                    "filing_status": "SINGLE",
                },
                expected={"eitc_phase_in": expected},
            ))
    return cases


def generate_standard_deduction_tests() -> list[TestCase]:
    """Standard Deduction tests for 2024."""
    cases = []
    # 2024 amounts
    amounts = {
        "SINGLE": 14600,
        "JOINT": 29200,
        "MARRIED_FILING_SEPARATELY": 14600,
        "HEAD_OF_HOUSEHOLD": 21900,
    }

    for status, amount in amounts.items():
        cases.append(TestCase(
            id=f"std_ded_{status}",
            inputs={"filing_status": status},
            expected={"standard_deduction": amount},
        ))
    return cases


def generate_salt_cap_tests() -> list[TestCase]:
    """SALT Cap tests for 2024."""
    cases = []

    # Under cap
    cases.append(TestCase(
        id="salt_under",
        inputs={
            "state_and_local_taxes_paid": 8000,
            "filing_status": "SINGLE",
        },
        expected={"salt_deduction": 8000},
    ))

    # Over cap
    cases.append(TestCase(
        id="salt_over",
        inputs={
            "state_and_local_taxes_paid": 15000,
            "filing_status": "SINGLE",
        },
        expected={"salt_deduction": 10000},
    ))

    # Married separate has $5000 cap
    cases.append(TestCase(
        id="salt_mfs",
        inputs={
            "state_and_local_taxes_paid": 8000,
            "filing_status": "MARRIED_FILING_SEPARATELY",
        },
        expected={"salt_deduction": 5000},
    ))

    return cases


# Define statutes
STATUTES = {
    "eitc_phase_in": Statute(
        citation="26 USC § 32(a)(1)",
        text="""
(a) Allowance of credit
    (1) In general
    In the case of an eligible individual, there shall be allowed as a credit
    against the tax imposed by this subtitle for the taxable year an amount
    equal to the credit percentage of so much of the taxpayer's earned income
    for the taxable year as does not exceed the earned income amount.

2024 Parameters (from IRS):
- 0 children: 7.65% rate, $7,840 cap
- 1 child: 34% rate, $11,750 cap
- 2 children: 40% rate, $16,510 cap
- 3+ children: 45% rate, $16,510 cap
        """.strip(),
    ),

    "standard_deduction": Statute(
        citation="26 USC § 63(c)",
        text="""
(c) Standard deduction
    For purposes of this subtitle—
    (1) In general
    Except as otherwise provided in this subsection, the term "standard deduction" means
    the sum of—
        (A) the basic standard deduction, and
        (B) the additional standard deduction.

2024 Basic Standard Deduction Amounts:
- Single: $14,600
- Married Filing Jointly: $29,200
- Married Filing Separately: $14,600
- Head of Household: $21,900
        """.strip(),
    ),

    "salt_cap": Statute(
        citation="26 USC § 164(b)(6)",
        text="""
(b) Definitions and special rules
    (6) Limitation on individual deductions for taxable years 2018 through 2025
    In the case of an individual and a taxable year beginning after December 31, 2017,
    and before January 1, 2026—
        (A) foreign real property taxes shall not be taken into account under subsection (a)(1), and
        (B) the aggregate amount of taxes taken into account under paragraphs (1), (2), and (3)
            of subsection (a) and paragraph (5) of this subsection for any taxable year shall
            not exceed $10,000 ($5,000 in the case of a married individual filing a separate return).

The deduction is the lesser of:
- Actual state and local taxes paid, OR
- $10,000 ($5,000 if married filing separately)
        """.strip(),
    ),
}

TEST_GENERATORS = {
    "eitc_phase_in": generate_eitc_phase_in_tests,
    "standard_deduction": generate_standard_deduction_tests,
    "salt_cap": generate_salt_cap_tests,
}


def run_dsl_experiment(
    provisions: list[str] | None = None,
    model: str = "claude-opus-4-5-20251101",
    max_iterations: int = 5,
    target_accuracy: float = 0.95,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run DSL generation experiment on tax provisions.

    Args:
        provisions: List of provision keys to test. Defaults to all.
        model: Claude model to use
        max_iterations: Max iterations per provision
        target_accuracy: Target accuracy threshold
        verbose: Print progress

    Returns:
        Dict with experiment results
    """
    if provisions is None:
        provisions = list(STATUTES.keys())

    results = {
        "model": model,
        "target_accuracy": target_accuracy,
        "max_iterations": max_iterations,
        "timestamp": datetime.now().isoformat(),
        "provisions": {},
        "summary": {},
    }

    total_cost = 0.0
    successes = 0

    for provision in provisions:
        if provision not in STATUTES:
            print(f"Unknown provision: {provision}")
            continue

        if verbose:
            print(f"\n{'='*60}")
            print(f"Running DSL experiment: {provision}")
            print(f"{'='*60}")

        statute = STATUTES[provision]
        test_cases = TEST_GENERATORS[provision]()

        # Create agent
        agent = DSLAgentTrainingLoop(
            model=model,
            max_iterations=max_iterations,
            target_accuracy=target_accuracy,
        )

        # Run training
        result = agent.train(statute, test_cases, verbose=verbose)

        # Store result
        results["provisions"][provision] = {
            "success": result["success"],
            "accuracy": result["final_accuracy"],
            "iterations": result["iterations"],
            "cost": result["cost"],
            "final_code": result["final_code"],
        }

        total_cost += result["cost"]["total_cost_usd"]
        if result["success"]:
            successes += 1

        if verbose:
            print(f"\n{provision}: {'PASS' if result['success'] else 'FAIL'}")
            print(f"  Accuracy: {result['final_accuracy']:.1%}")
            print(f"  Iterations: {result['iterations']}")
            print(f"  Cost: ${result['cost']['total_cost_usd']:.4f}")

    # Summary
    results["summary"] = {
        "total_provisions": len(provisions),
        "successes": successes,
        "pass_rate": successes / len(provisions) if provisions else 0,
        "total_cost_usd": total_cost,
    }

    if verbose:
        print(f"\n{'='*60}")
        print("EXPERIMENT SUMMARY")
        print(f"{'='*60}")
        print(f"Passed: {successes}/{len(provisions)} ({results['summary']['pass_rate']:.0%})")
        print(f"Total cost: ${total_cost:.4f}")

    return results


def main():
    """Run DSL experiment from command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Run DSL generation experiment")
    parser.add_argument("--provisions", nargs="+", help="Provisions to test")
    parser.add_argument("--model", default="claude-opus-4-5-20251101")
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--target-accuracy", type=float, default=0.95)
    parser.add_argument("--output", help="Output JSON file")
    args = parser.parse_args()

    results = run_dsl_experiment(
        provisions=args.provisions,
        model=args.model,
        max_iterations=args.max_iterations,
        target_accuracy=args.target_accuracy,
    )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
