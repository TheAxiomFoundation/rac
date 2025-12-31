#!/usr/bin/env python3
"""Speed benchmark: Cosilico EITC vs PolicyEngine-US.

Measures execution time for EITC calculations across various scenarios.
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


def cosilico_eitc(
    earned_income: float,
    agi: float,
    num_children: int,
    filing_status: str,
    resolver,
    tax_year: int = 2024,
) -> float:
    """Calculate EITC using Cosilico resolver."""
    n = min(num_children, 3)

    # Fixed percentages from statute
    credit_percentages = {0: 0.0765, 1: 0.34, 2: 0.40, 3: 0.45}
    phaseout_percentages = {0: 0.0765, 1: 0.1598, 2: 0.2106, 3: 0.2106}

    credit_pct = credit_percentages[n]
    phaseout_pct = phaseout_percentages[n]

    # Get inflation-adjusted amounts from resolver
    earned_income_amount = resolver.resolve(
        "statute/26/32/b/2/A/base_amounts",
        fragment="earned_income_amount",
        tax_year=tax_year,
        num_qualifying_children=n,
    )

    phaseout_amount = resolver.resolve(
        "statute/26/32/b/2/A/base_amounts",
        fragment="phaseout_amount",
        tax_year=tax_year,
        num_qualifying_children=n,
    )

    joint_adjustment = resolver.resolve(
        "statute/26/32/b/2/B/base_joint_return_adjustment",
        fragment="joint_return_adjustment",
        tax_year=tax_year,
    )

    # Adjust threshold for joint filers
    if filing_status == "JOINT":
        phaseout_threshold = phaseout_amount + joint_adjustment
    else:
        phaseout_threshold = phaseout_amount

    # Phase-in credit
    phase_in_credit = credit_pct * min(earned_income, earned_income_amount)
    max_credit = credit_pct * earned_income_amount

    # Phase-out
    income_for_phaseout = max(agi, earned_income)
    if income_for_phaseout > phaseout_threshold:
        phase_out_reduction = phaseout_pct * (income_for_phaseout - phaseout_threshold)
    else:
        phase_out_reduction = 0

    return max(0, min(phase_in_credit, max_credit) - phase_out_reduction)


def policyengine_eitc(
    earned_income: float,
    agi: float,
    num_children: int,
    filing_status: str,
    tax_year: int = 2024,
) -> float:
    """Calculate EITC using PolicyEngine-US."""
    is_married = filing_status == "JOINT"

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
    for i in range(num_children):
        child_name = f"child{i}"
        situation["people"][child_name] = {
            "age": {tax_year: 10},
            "employment_income": {tax_year: 0},
        }
        situation["tax_units"]["tax_unit"]["members"].append(child_name)
        situation["spm_units"]["spm_unit"]["members"].append(child_name)
        situation["households"]["household"]["members"].append(child_name)

    sim = Simulation(situation=situation)
    result = sim.calculate("eitc", tax_year)
    # PolicyEngine returns an array; sum for tax unit total
    return float(result.sum())


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
            result = cosilico_eitc(
                tc["earned_income"],
                tc["agi"],
                tc["num_children"],
                tc["filing_status"],
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
            result = policyengine_eitc(
                tc["earned_income"],
                tc["agi"],
                tc["num_children"],
                tc["filing_status"],
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
    print("EITC Speed Benchmark: Cosilico vs PolicyEngine-US")
    print("=" * 70)

    # Initialize Cosilico resolver
    print("\nInitializing Cosilico resolver...")
    resolver = create_resolver(str(COSILICO_US_ROOT))

    # Test cases
    test_cases = [
        {"earned_income": 20000, "agi": 20000, "num_children": 1, "filing_status": "SINGLE"},
        {"earned_income": 30000, "agi": 30000, "num_children": 2, "filing_status": "SINGLE"},
        {"earned_income": 15000, "agi": 15000, "num_children": 0, "filing_status": "SINGLE"},
        {"earned_income": 25000, "agi": 25000, "num_children": 1, "filing_status": "JOINT"},
        {"earned_income": 40000, "agi": 40000, "num_children": 3, "filing_status": "SINGLE"},
        {"earned_income": 10000, "agi": 10000, "num_children": 2, "filing_status": "JOINT"},
        {"earned_income": 50000, "agi": 50000, "num_children": 1, "filing_status": "SINGLE"},
        {"earned_income": 5000, "agi": 5000, "num_children": 0, "filing_status": "SINGLE"},
    ]

    # Single case benchmark
    print("\n" + "-" * 70)
    print("SINGLE CASE BENCHMARK (1 child, $20k income)")
    print("-" * 70)

    tc = test_cases[0]

    print("\nCosilico (100 iterations):")
    cosilico_stats = benchmark_single(
        cosilico_eitc,
        tc["earned_income"], tc["agi"], tc["num_children"], tc["filing_status"],
        resolver,
        iterations=100,
    )
    print(f"  Result: ${cosilico_stats['result']:.2f}")
    print(f"  Mean:   {cosilico_stats['mean_ms']:.3f} ms")
    print(f"  Median: {cosilico_stats['median_ms']:.3f} ms")
    print(f"  Stdev:  {cosilico_stats['stdev_ms']:.3f} ms")
    print(f"  Range:  {cosilico_stats['min_ms']:.3f} - {cosilico_stats['max_ms']:.3f} ms")

    if HAS_POLICYENGINE:
        print("\nPolicyEngine (10 iterations - slower due to initialization):")
        pe_stats = benchmark_single(
            policyengine_eitc,
            tc["earned_income"], tc["agi"], tc["num_children"], tc["filing_status"],
            iterations=10,
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
            print(f"  {label:25s} → {time_sec:.2f} seconds")
        elif time_sec < 3600:
            print(f"  {label:25s} → {time_sec/60:.1f} minutes")
        else:
            print(f"  {label:25s} → {time_sec/3600:.1f} hours")

    print("\nNote: Vectorized NumPy implementation would be 100-1000x faster")
    print("Target: 130M households in <1 hour with vectorization + parallelization")

    print("\n" + "=" * 70)
    print("Benchmark complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
