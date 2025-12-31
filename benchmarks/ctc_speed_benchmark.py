#!/usr/bin/env python3
"""Speed benchmark: Cosilico CTC vs PolicyEngine-US.

Measures execution time for Child Tax Credit calculations across various scenarios.
"""

import math
import time
import statistics
from datetime import date
from pathlib import Path

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


def get_value_for_year(values_dict: dict, tax_year: int):
    """Get the applicable value from a date-keyed dict for a tax year."""
    target_date = date(tax_year, 12, 31)
    applicable_value = None
    applicable_date = None

    for d, value in values_dict.items():
        if d <= target_date:
            if applicable_date is None or d > applicable_date:
                applicable_date = d
                applicable_value = value

    return applicable_value


def cosilico_ctc(
    agi: float,
    num_qualifying_children: int,
    filing_status: str,
    earned_income: float,
    tax_liability: float,
    resolver,
    tax_year: int = 2024,
) -> dict:
    """Calculate CTC using Cosilico resolver.

    Returns dict with child_tax_credit and additional_child_tax_credit.
    """
    # Get parameters from resolver
    credit_data = resolver.load_base_value("statute/26/24/h/2/credit_amount")
    credit_per_child = get_value_for_year(
        credit_data["credit_amount"]["values"], tax_year
    )

    thresholds = resolver.load_base_value("statute/26/24/b/1/threshold")
    if filing_status.upper() == "JOINT":
        phaseout_threshold = get_value_for_year(
            thresholds["phaseout_threshold_joint"]["values"], tax_year
        )
    else:
        phaseout_threshold = get_value_for_year(
            thresholds["phaseout_threshold_single"]["values"], tax_year
        )

    phaseout_rate_data = resolver.load_base_value("statute/26/24/b/2/phaseout_rate")
    phaseout_per_1000 = get_value_for_year(
        phaseout_rate_data["phaseout_rate"]["values"], tax_year
    )

    actc_params = resolver.load_base_value("statute/26/24/d/1/B/parameters")
    earned_income_threshold = get_value_for_year(
        actc_params["earned_income_threshold"]["values"], tax_year
    )
    refundable_rate = get_value_for_year(
        actc_params["refundable_rate"]["values"], tax_year
    )

    refundable_max = resolver.resolve(
        "statute/26/24/h/5/refundable_maximum",
        fragment="refundable_maximum",
        tax_year=tax_year,
    )

    # Calculate base credit
    base_credit = credit_per_child * num_qualifying_children

    # Calculate phaseout
    if agi > phaseout_threshold:
        excess = agi - phaseout_threshold
        thousands_over = math.ceil(excess / 1000)
        phaseout = phaseout_per_1000 * thousands_over
    else:
        phaseout = 0

    credit_after_phaseout = max(0, base_credit - phaseout)

    # Split into CTC and ACTC
    ctc = min(credit_after_phaseout, tax_liability)
    remaining_credit = credit_after_phaseout - ctc

    actc_from_earned = refundable_rate * max(0, earned_income - earned_income_threshold)
    refundable_cap = refundable_max * num_qualifying_children
    actc = min(remaining_credit, actc_from_earned, refundable_cap)

    return {
        "child_tax_credit": ctc,
        "additional_child_tax_credit": actc,
        "total_credit": ctc + actc,
    }


def policyengine_ctc(
    agi: float,
    num_qualifying_children: int,
    filing_status: str,
    earned_income: float,
    tax_liability: float,
    tax_year: int = 2024,
) -> dict:
    """Calculate CTC using PolicyEngine-US."""
    is_married = filing_status.upper() == "JOINT"

    situation = {
        "people": {
            "adult": {
                "age": {tax_year: 30},
                "employment_income": {tax_year: earned_income},
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
            "age": {tax_year: 30},
            "employment_income": {tax_year: 0},
        }
        situation["tax_units"]["tax_unit"]["members"].append("spouse")
        situation["spm_units"]["spm_unit"]["members"].append("spouse")
        situation["households"]["household"]["members"].append("spouse")

    # Add children
    for i in range(num_qualifying_children):
        child_name = f"child{i}"
        situation["people"][child_name] = {
            "age": {tax_year: 10},
            "employment_income": {tax_year: 0},
        }
        situation["tax_units"]["tax_unit"]["members"].append(child_name)
        situation["spm_units"]["spm_unit"]["members"].append(child_name)
        situation["households"]["household"]["members"].append(child_name)

    sim = Simulation(situation=situation)
    # PolicyEngine uses "ctc" for total CTC (both refundable and nonrefundable)
    total_ctc = float(sim.calculate("ctc", tax_year).sum())

    return {
        "child_tax_credit": total_ctc,  # PolicyEngine doesn't split CTC/ACTC this way
        "additional_child_tax_credit": 0,  # Included in total
        "total_credit": total_ctc,
    }


def benchmark_single(func, *args, iterations=100, **kwargs):
    """Run a function multiple times and return timing stats."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)  # Convert to ms

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
            result = cosilico_ctc(
                tc["agi"],
                tc["num_children"],
                tc["filing_status"],
                tc["earned_income"],
                tc["tax_liability"],
                resolver,
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
            result = policyengine_ctc(
                tc["agi"],
                tc["num_children"],
                tc["filing_status"],
                tc["earned_income"],
                tc["tax_liability"],
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


def main():
    print("=" * 70)
    print("CTC Speed Benchmark: Cosilico vs PolicyEngine-US")
    print("=" * 70)

    # Initialize Cosilico resolver
    print("\nInitializing Cosilico resolver...")
    resolver = create_resolver(str(COSILICO_US_ROOT))

    # Test cases covering various scenarios
    test_cases = [
        # Basic cases below phaseout
        {"agi": 50000, "num_children": 1, "filing_status": "SINGLE", "earned_income": 50000, "tax_liability": 5000},
        {"agi": 75000, "num_children": 2, "filing_status": "SINGLE", "earned_income": 75000, "tax_liability": 8000},
        {"agi": 150000, "num_children": 3, "filing_status": "JOINT", "earned_income": 150000, "tax_liability": 15000},
        # Phaseout cases
        {"agi": 210000, "num_children": 1, "filing_status": "SINGLE", "earned_income": 210000, "tax_liability": 40000},
        {"agi": 420000, "num_children": 2, "filing_status": "JOINT", "earned_income": 420000, "tax_liability": 80000},
        # ACTC cases
        {"agi": 15000, "num_children": 1, "filing_status": "SINGLE", "earned_income": 15000, "tax_liability": 0},
        {"agi": 25000, "num_children": 3, "filing_status": "SINGLE", "earned_income": 25000, "tax_liability": 0},
        # High income
        {"agi": 500000, "num_children": 4, "filing_status": "JOINT", "earned_income": 500000, "tax_liability": 100000},
    ]

    # Single case benchmark
    print("\n" + "-" * 70)
    print("SINGLE CASE BENCHMARK (1 child, $50k income)")
    print("-" * 70)

    tc = test_cases[0]

    print("\nCosilico (100 iterations):")
    cosilico_stats = benchmark_single(
        cosilico_ctc,
        tc["agi"], tc["num_children"], tc["filing_status"],
        tc["earned_income"], tc["tax_liability"],
        resolver,
        iterations=100,
    )
    print(f"  Total Credit: ${cosilico_stats['result']['total_credit']:.2f}")
    print(f"    CTC: ${cosilico_stats['result']['child_tax_credit']:.2f}")
    print(f"    ACTC: ${cosilico_stats['result']['additional_child_tax_credit']:.2f}")
    print(f"  Mean:   {cosilico_stats['mean_ms']:.3f} ms")
    print(f"  Median: {cosilico_stats['median_ms']:.3f} ms")
    print(f"  Stdev:  {cosilico_stats['stdev_ms']:.3f} ms")
    print(f"  Range:  {cosilico_stats['min_ms']:.3f} - {cosilico_stats['max_ms']:.3f} ms")

    if HAS_POLICYENGINE:
        print("\nPolicyEngine (10 iterations - slower due to initialization):")
        pe_stats = benchmark_single(
            policyengine_ctc,
            tc["agi"], tc["num_children"], tc["filing_status"],
            tc["earned_income"], tc["tax_liability"],
            iterations=10,
        )
        print(f"  Total Credit: ${pe_stats['result']['total_credit']:.2f}")
        print(f"    CTC: ${pe_stats['result']['child_tax_credit']:.2f}")
        print(f"    ACTC: ${pe_stats['result']['additional_child_tax_credit']:.2f}")
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

        speedup = pe_batch['throughput_per_sec'] / cosilico_batch['throughput_per_sec']
        if speedup < 1:
            print(f"\n  Cosilico throughput: {1/speedup:.1f}x higher")
        else:
            print(f"\n  PolicyEngine throughput: {speedup:.1f}x higher")

    # Projected microsim performance
    print("\n" + "-" * 70)
    print("PROJECTED MICROSIM PERFORMANCE")
    print("-" * 70)

    cases_per_sec = cosilico_batch['throughput_per_sec']

    projections = [
        (1_000, "1K households"),
        (10_000, "10K households"),
        (100_000, "100K households (CPS)"),
        (1_000_000, "1M households"),
        (130_000_000, "130M households (full US)"),
    ]

    print("\nCosilico (single-threaded, current implementation):")
    for n, label in projections:
        time_sec = n / cases_per_sec
        if time_sec < 60:
            print(f"  {label:25s} -> {time_sec:.2f} seconds")
        elif time_sec < 3600:
            print(f"  {label:25s} -> {time_sec/60:.1f} minutes")
        else:
            print(f"  {label:25s} -> {time_sec/3600:.1f} hours")

    print("\nNote: Vectorized NumPy implementation would be 100-1000x faster")
    print("Target: 130M households in <1 hour with vectorization + parallelization")

    print("\n" + "=" * 70)
    print("Benchmark complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
