#!/usr/bin/env python3
"""Speed benchmark: Cosilico Standard Deduction vs PolicyEngine-US.

Measures execution time for Standard Deduction calculations across various scenarios.
"""

import time
import statistics
from pathlib import Path

import numpy as np

# Cosilico imports
from rac.parameters.override_resolver import create_resolver

# PolicyEngine imports
try:
    from policyengine_us import Simulation
    HAS_POLICYENGINE = True
except ImportError:
    HAS_POLICYENGINE = False
    print("Warning: policyengine-us not installed. Install with: pip install policyengine-us")


COSILICO_US_ROOT = Path("/Users/maxghenis/CosilicoAI/cosilico-us")


def cosilico_standard_deduction(
    filing_status: str,
    age: int,
    spouse_age: int | None,
    is_blind: bool,
    spouse_is_blind: bool,
    is_dependent: bool,
    earned_income: float,
    is_nonresident_alien: bool,
    spouse_itemizes: bool,
    resolver,
    tax_year: int = 2024,
) -> float:
    """Calculate standard deduction using Cosilico resolver."""
    # SS 63(c)(6): Ineligibility
    if is_nonresident_alien:
        return 0
    if filing_status == "MARRIED_SEPARATE" and spouse_itemizes:
        return 0

    is_married = filing_status in ["JOINT", "MARRIED_SEPARATE"]

    # Get basic amount by filing status
    if filing_status == "JOINT":
        basic = resolver.resolve(
            "statute/26/63/c/2/basic_amounts",
            fragment="basic_joint",
            tax_year=tax_year,
        )
    elif filing_status == "HEAD_OF_HOUSEHOLD":
        basic = resolver.resolve(
            "statute/26/63/c/2/basic_amounts",
            fragment="basic_head_of_household",
            tax_year=tax_year,
        )
    else:
        basic = resolver.resolve(
            "statute/26/63/c/2/basic_amounts",
            fragment="basic_single",
            tax_year=tax_year,
        )

    # SS 63(c)(5): Dependent limitation
    if is_dependent:
        dep_min = resolver.resolve(
            "statute/26/63/c/5/parameters",
            fragment="dependent_minimum",
            tax_year=tax_year,
        )
        dep_addon = resolver.resolve(
            "statute/26/63/c/5/parameters",
            fragment="dependent_earned_addon",
            tax_year=tax_year,
        )
        earned_plus = earned_income + dep_addon
        basic = min(max(dep_min, earned_plus), basic)

    # SS 63(f): Additional amounts
    additional = 0
    if is_married:
        aged_amount = resolver.resolve(
            "statute/26/63/f/1/aged_amount",
            fragment="additional_aged_married",
            tax_year=tax_year,
        )
        blind_amount = resolver.resolve(
            "statute/26/63/f/2/blind_amount",
            fragment="additional_blind_married",
            tax_year=tax_year,
        )
    else:
        aged_amount = resolver.resolve(
            "statute/26/63/f/1/aged_amount",
            fragment="additional_aged_unmarried",
            tax_year=tax_year,
        )
        blind_amount = resolver.resolve(
            "statute/26/63/f/2/blind_amount",
            fragment="additional_blind_unmarried",
            tax_year=tax_year,
        )

    if age >= 65:
        additional += aged_amount
    if is_blind:
        additional += blind_amount

    if filing_status == "JOINT" and spouse_age is not None:
        if spouse_age >= 65:
            additional += aged_amount
        if spouse_is_blind:
            additional += blind_amount

    return basic + additional


def policyengine_standard_deduction(
    filing_status: str,
    age: int,
    spouse_age: int | None,
    is_blind: bool,
    spouse_is_blind: bool,
    is_dependent: bool,
    earned_income: float,
    is_nonresident_alien: bool,
    spouse_itemizes: bool,
    tax_year: int = 2024,
) -> float:
    """Calculate standard deduction using PolicyEngine-US."""
    is_married = filing_status == "JOINT"

    situation = {
        "people": {
            "adult": {
                "age": {tax_year: age},
                "employment_income": {tax_year: earned_income},
                "is_blind": {tax_year: is_blind},
            }
        },
        "tax_units": {
            "tax_unit": {
                "members": ["adult"],
            }
        },
        "spm_units": {
            "spm_unit": {
                "members": ["adult"],
            }
        },
        "households": {
            "household": {
                "members": ["adult"],
                "state_code": {tax_year: "CA"},
            }
        },
    }

    # Add spouse if joint
    if is_married:
        situation["people"]["spouse"] = {
            "age": {tax_year: spouse_age or 30},
            "employment_income": {tax_year: 0},
            "is_blind": {tax_year: spouse_is_blind},
        }
        situation["tax_units"]["tax_unit"]["members"].append("spouse")
        situation["spm_units"]["spm_unit"]["members"].append("spouse")
        situation["households"]["household"]["members"].append("spouse")

    sim = Simulation(situation=situation)
    result = sim.calculate("standard_deduction", tax_year)
    return float(result.sum())


def benchmark_single(func, iterations=100, **kwargs):
    """Run a function multiple times and return timing stats."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(**kwargs)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)

    return {
        "result": result,
        "mean_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "stdev_ms": statistics.stdev(times) if len(times) > 1 else 0,
        "min_ms": min(times),
        "max_ms": max(times),
        "iterations": iterations,
    }


def benchmark_batch_cosilico(test_cases, resolver, iterations=10):
    """Benchmark Cosilico on a batch of test cases."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        results = []
        for tc in test_cases:
            result = cosilico_standard_deduction(
                resolver=resolver,
                **tc,
            )
            results.append(result)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)

    return {
        "total_cases": len(test_cases),
        "mean_batch_ms": statistics.mean(times),
        "mean_per_case_ms": statistics.mean(times) / len(test_cases),
        "throughput_per_sec": len(test_cases) / (statistics.mean(times) / 1000),
    }


def benchmark_batch_policyengine(test_cases, iterations=3):
    """Benchmark PolicyEngine on a batch of test cases."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        results = []
        for tc in test_cases:
            result = policyengine_standard_deduction(**tc)
            results.append(result)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)

    return {
        "total_cases": len(test_cases),
        "mean_batch_ms": statistics.mean(times),
        "mean_per_case_ms": statistics.mean(times) / len(test_cases),
        "throughput_per_sec": len(test_cases) / (statistics.mean(times) / 1000),
    }


def main():
    print("=" * 70)
    print("Standard Deduction Speed Benchmark: Cosilico vs PolicyEngine-US")
    print("=" * 70)

    # Initialize Cosilico resolver
    print("\nInitializing Cosilico resolver...")
    resolver = create_resolver(str(COSILICO_US_ROOT))

    # Test cases covering various scenarios
    test_cases = [
        # Basic filing statuses
        {"filing_status": "SINGLE", "age": 35, "spouse_age": None, "is_blind": False,
         "spouse_is_blind": False, "is_dependent": False, "earned_income": 50000,
         "is_nonresident_alien": False, "spouse_itemizes": False},
        {"filing_status": "JOINT", "age": 40, "spouse_age": 38, "is_blind": False,
         "spouse_is_blind": False, "is_dependent": False, "earned_income": 100000,
         "is_nonresident_alien": False, "spouse_itemizes": False},
        {"filing_status": "HEAD_OF_HOUSEHOLD", "age": 35, "spouse_age": None, "is_blind": False,
         "spouse_is_blind": False, "is_dependent": False, "earned_income": 60000,
         "is_nonresident_alien": False, "spouse_itemizes": False},
        # Aged taxpayers
        {"filing_status": "SINGLE", "age": 65, "spouse_age": None, "is_blind": False,
         "spouse_is_blind": False, "is_dependent": False, "earned_income": 50000,
         "is_nonresident_alien": False, "spouse_itemizes": False},
        {"filing_status": "JOINT", "age": 67, "spouse_age": 66, "is_blind": False,
         "spouse_is_blind": False, "is_dependent": False, "earned_income": 80000,
         "is_nonresident_alien": False, "spouse_itemizes": False},
        # Blind taxpayers
        {"filing_status": "SINGLE", "age": 65, "spouse_age": None, "is_blind": True,
         "spouse_is_blind": False, "is_dependent": False, "earned_income": 50000,
         "is_nonresident_alien": False, "spouse_itemizes": False},
        # Dependents
        {"filing_status": "SINGLE", "age": 16, "spouse_age": None, "is_blind": False,
         "spouse_is_blind": False, "is_dependent": True, "earned_income": 0,
         "is_nonresident_alien": False, "spouse_itemizes": False},
        {"filing_status": "SINGLE", "age": 19, "spouse_age": None, "is_blind": False,
         "spouse_is_blind": False, "is_dependent": True, "earned_income": 3000,
         "is_nonresident_alien": False, "spouse_itemizes": False},
    ]

    # Single case benchmark
    print("\n" + "-" * 70)
    print("SINGLE CASE BENCHMARK (Single filer, age 35)")
    print("-" * 70)

    tc = test_cases[0]

    print("\nCosilico (100 iterations):")
    cosilico_stats = benchmark_single(
        cosilico_standard_deduction,
        resolver=resolver,
        iterations=100,
        **tc,
    )
    print(f"  Result: ${cosilico_stats['result']:.2f}")
    print(f"  Mean:   {cosilico_stats['mean_ms']:.3f} ms")
    print(f"  Median: {cosilico_stats['median_ms']:.3f} ms")
    print(f"  Stdev:  {cosilico_stats['stdev_ms']:.3f} ms")
    print(f"  Range:  {cosilico_stats['min_ms']:.3f} - {cosilico_stats['max_ms']:.3f} ms")

    if HAS_POLICYENGINE:
        print("\nPolicyEngine (10 iterations - slower due to initialization):")
        pe_stats = benchmark_single(
            policyengine_standard_deduction,
            iterations=10,
            **tc,
        )
        print(f"  Result: ${pe_stats['result']:.2f}")
        print(f"  Mean:   {pe_stats['mean_ms']:.3f} ms")
        print(f"  Median: {pe_stats['median_ms']:.3f} ms")
        print(f"  Stdev:  {pe_stats['stdev_ms']:.3f} ms")
        print(f"  Range:  {pe_stats['min_ms']:.3f} - {pe_stats['max_ms']:.3f} ms")

        speedup = pe_stats['mean_ms'] / cosilico_stats['mean_ms']
        print(f"\n  Speedup: Cosilico is {speedup:.1f}x faster")

    # Batch benchmark
    print("\n" + "-" * 70)
    print(f"BATCH BENCHMARK ({len(test_cases)} cases)")
    print("-" * 70)

    print("\nCosilico (10 batch iterations):")
    cosilico_batch = benchmark_batch_cosilico(test_cases, resolver, iterations=10)
    print(f"  Total batch time:  {cosilico_batch['mean_batch_ms']:.3f} ms")
    print(f"  Per case:          {cosilico_batch['mean_per_case_ms']:.3f} ms")
    print(f"  Throughput:        {cosilico_batch['throughput_per_sec']:.0f} cases/sec")

    if HAS_POLICYENGINE:
        print("\nPolicyEngine (3 batch iterations):")
        pe_batch = benchmark_batch_policyengine(test_cases, iterations=3)
        print(f"  Total batch time:  {pe_batch['mean_batch_ms']:.3f} ms")
        print(f"  Per case:          {pe_batch['mean_per_case_ms']:.3f} ms")
        print(f"  Throughput:        {pe_batch['throughput_per_sec']:.0f} cases/sec")

        throughput_ratio = cosilico_batch['throughput_per_sec'] / pe_batch['throughput_per_sec']
        print(f"\n  Cosilico throughput: {throughput_ratio:.1f}x higher")

    # Verify calculations against IRS values
    print("\n" + "-" * 70)
    print("VERIFICATION: 2024 IRS VALUES (Rev. Proc. 2023-34)")
    print("-" * 70)

    verifications = [
        ("Single, under 65", "SINGLE", 35, None, False, False, False, 50000, 14600),
        ("MFJ, under 65", "JOINT", 40, 38, False, False, False, 100000, 29200),
        ("HOH, under 65", "HEAD_OF_HOUSEHOLD", 35, None, False, False, False, 60000, 21900),
        ("Single, 65+", "SINGLE", 65, None, False, False, False, 50000, 16550),
        ("MFJ, both 65+", "JOINT", 67, 66, False, False, False, 80000, 32300),
        ("Single, 65+ & blind", "SINGLE", 65, None, True, False, False, 50000, 18500),
        ("MFJ, both 65+ & blind", "JOINT", 70, 68, True, True, False, 60000, 35400),
        ("Dependent, no income", "SINGLE", 16, None, False, False, True, 0, 1300),
        ("Dependent, $3k earned", "SINGLE", 19, None, False, False, True, 3000, 3450),
    ]

    print("\n{:25s} {:>10s} {:>10s} {:>8s}".format("Scenario", "Expected", "Cosilico", "Pass?"))
    print("-" * 55)

    all_pass = True
    for desc, fs, age, spouse_age, blind, spouse_blind, dep, earned, expected in verifications:
        result = cosilico_standard_deduction(
            filing_status=fs,
            age=age,
            spouse_age=spouse_age,
            is_blind=blind,
            spouse_is_blind=spouse_blind,
            is_dependent=dep,
            earned_income=earned,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        passed = abs(result - expected) < 1
        all_pass = all_pass and passed
        status = "Yes" if passed else "NO"
        print(f"{desc:25s} ${expected:>9,.0f} ${result:>9,.0f} {status:>8s}")

    print("\n" + ("All tests passed!" if all_pass else "SOME TESTS FAILED"))

    print("\n" + "=" * 70)
    print("Benchmark complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
