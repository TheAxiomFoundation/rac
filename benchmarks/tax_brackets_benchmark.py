#!/usr/bin/env python3
"""Speed benchmark: Cosilico Tax Brackets vs PolicyEngine-US.

Measures execution time for income tax calculations across various scenarios.
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


def cosilico_income_tax(
    taxable_income: float,
    filing_status: str,
    resolver,
    tax_year: int = 2024,
) -> float:
    """Calculate federal income tax using Cosilico resolver.

    Implements 26 USC Section 1 marginal rate brackets.
    """
    # Tax rates are fixed in statute (not indexed)
    rates = [0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37]

    # Get thresholds for this filing status (these are indexed)
    thresholds = []
    for rate in rates:
        threshold = resolver.resolve(
            "statute/26/1/brackets/base_thresholds",
            fragment=filing_status,
            tax_year=tax_year,
            rate=rate,
        )
        thresholds.append(threshold)

    # Calculate tax by applying marginal rates
    total_tax = 0.0

    for i, rate in enumerate(rates):
        bracket_floor = thresholds[i]
        if i + 1 < len(thresholds):
            bracket_ceiling = thresholds[i + 1]
        else:
            bracket_ceiling = float('inf')

        if taxable_income > bracket_floor:
            if taxable_income <= bracket_ceiling:
                taxable_at_rate = taxable_income - bracket_floor
                total_tax += taxable_at_rate * rate
                break
            else:
                taxable_at_rate = bracket_ceiling - bracket_floor
                total_tax += taxable_at_rate * rate

    return total_tax


def cosilico_income_tax_vectorized(
    taxable_incomes: np.ndarray,
    filing_status: str,
    resolver,
    tax_year: int = 2024,
) -> np.ndarray:
    """Calculate federal income tax using vectorized NumPy.

    This demonstrates the performance advantage of vectorization.
    """
    rates = np.array([0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37])

    # Get thresholds
    thresholds = []
    for rate in rates:
        threshold = resolver.resolve(
            "statute/26/1/brackets/base_thresholds",
            fragment=filing_status,
            tax_year=tax_year,
            rate=float(rate),
        )
        thresholds.append(threshold)
    thresholds = np.array(thresholds)

    # Add infinity as the top ceiling
    thresholds_with_inf = np.append(thresholds, np.inf)

    # Vectorized bracket calculation
    n = len(taxable_incomes)
    taxes = np.zeros(n)

    for i, rate in enumerate(rates):
        floor = thresholds_with_inf[i]
        ceiling = thresholds_with_inf[i + 1]

        # Income in this bracket = min(income, ceiling) - floor, clamped at 0
        income_in_bracket = np.maximum(
            np.minimum(taxable_incomes, ceiling) - floor,
            0
        )
        taxes += income_in_bracket * rate

    return taxes


def policyengine_income_tax(
    taxable_income: float,
    filing_status: str,
    tax_year: int = 2024,
) -> float:
    """Calculate federal income tax using PolicyEngine-US."""
    is_married = filing_status in ("married_filing_jointly", "married_filing_separately")
    is_hoh = filing_status == "head_of_household"

    situation = {
        "people": {
            "adult": {
                "age": {tax_year: 30},
                # Use wages as proxy for taxable income
                "employment_income": {tax_year: taxable_income},
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

    # Add spouse if married
    if is_married:
        situation["people"]["spouse"] = {
            "age": {tax_year: 30},
            "employment_income": {tax_year: 0},
        }
        situation["tax_units"]["tax_unit"]["members"].append("spouse")
        situation["spm_units"]["spm_unit"]["members"].append("spouse")
        situation["households"]["household"]["members"].append("spouse")

    # Add child if HoH
    if is_hoh:
        situation["people"]["child"] = {
            "age": {tax_year: 10},
            "employment_income": {tax_year: 0},
        }
        situation["tax_units"]["tax_unit"]["members"].append("child")
        situation["spm_units"]["spm_unit"]["members"].append("child")
        situation["households"]["household"]["members"].append("child")

    sim = Simulation(situation=situation)
    result = sim.calculate("income_tax", tax_year)
    return float(result.sum())


def benchmark_single(func, *args, iterations=100, **kwargs):
    """Run a function multiple times and return timing stats."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(*args, **kwargs)
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
    """Benchmark Cosilico on a batch of test cases (scalar)."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        results = []
        for tc in test_cases:
            result = cosilico_income_tax(
                tc["taxable_income"],
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


def benchmark_vectorized_cosilico(n_cases, resolver, iterations=10):
    """Benchmark Cosilico vectorized on random incomes."""
    # Generate random taxable incomes between $0 and $500,000
    np.random.seed(42)
    incomes = np.random.uniform(0, 500000, n_cases)

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        results = cosilico_income_tax_vectorized(incomes, "single", resolver)
        elapsed = time.perf_counter() - start
        times.append(elapsed * 1000)

    return {
        "total_cases": n_cases,
        "mean_batch_ms": statistics.mean(times),
        "mean_per_case_ms": statistics.mean(times) / n_cases,
        "throughput_per_sec": n_cases / (statistics.mean(times) / 1000),
    }


def main():
    print("=" * 70)
    print("Income Tax Bracket Speed Benchmark: Cosilico vs PolicyEngine-US")
    print("=" * 70)

    # Initialize Cosilico resolver
    print("\nInitializing Cosilico resolver...")
    resolver = create_resolver(str(COSILICO_US_ROOT))

    # Test cases across different income levels and filing statuses
    test_cases = [
        {"taxable_income": 10000, "filing_status": "single"},
        {"taxable_income": 25000, "filing_status": "single"},
        {"taxable_income": 50000, "filing_status": "single"},
        {"taxable_income": 75000, "filing_status": "single"},
        {"taxable_income": 100000, "filing_status": "single"},
        {"taxable_income": 200000, "filing_status": "single"},
        {"taxable_income": 50000, "filing_status": "married_filing_jointly"},
        {"taxable_income": 100000, "filing_status": "married_filing_jointly"},
        {"taxable_income": 40000, "filing_status": "head_of_household"},
        {"taxable_income": 75000, "filing_status": "married_filing_separately"},
    ]

    # Single case benchmark
    print("\n" + "-" * 70)
    print("SINGLE CASE BENCHMARK (Single, $50k income)")
    print("-" * 70)

    tc = test_cases[2]  # $50k single

    print("\nCosilico (100 iterations):")
    cosilico_stats = benchmark_single(
        cosilico_income_tax,
        tc["taxable_income"], tc["filing_status"],
        resolver,
        iterations=100,
    )
    print(f"  Result: ${cosilico_stats['result']:.2f}")
    print(f"  Mean:   {cosilico_stats['mean_ms']:.3f} ms")
    print(f"  Median: {cosilico_stats['median_ms']:.3f} ms")
    print(f"  Range:  {cosilico_stats['min_ms']:.3f} - {cosilico_stats['max_ms']:.3f} ms")

    if HAS_POLICYENGINE:
        print("\nPolicyEngine (10 iterations):")
        pe_stats = benchmark_single(
            policyengine_income_tax,
            tc["taxable_income"], tc["filing_status"],
            iterations=10,
        )
        print(f"  Result: ${pe_stats['result']:.2f}")
        print(f"  Mean:   {pe_stats['mean_ms']:.3f} ms")

        speedup = pe_stats['mean_ms'] / cosilico_stats['mean_ms']
        print(f"\n  Speedup: Cosilico is {speedup:.1f}x faster")

    # Batch benchmark (scalar)
    print("\n" + "-" * 70)
    print(f"BATCH BENCHMARK - SCALAR ({len(test_cases)} cases)")
    print("-" * 70)

    print("\nCosilico Scalar (10 batch iterations):")
    cosilico_batch = benchmark_batch_cosilico(test_cases, resolver, iterations=10)
    print(f"  Total batch time:  {cosilico_batch['mean_batch_ms']:.3f} ms")
    print(f"  Per case:          {cosilico_batch['mean_per_case_ms']:.3f} ms")
    print(f"  Throughput:        {cosilico_batch['throughput_per_sec']:.0f} cases/sec")

    # Vectorized benchmark
    print("\n" + "-" * 70)
    print("VECTORIZED BENCHMARK")
    print("-" * 70)

    for n_cases in [1000, 10000, 100000]:
        print(f"\nCosilico Vectorized ({n_cases:,} cases, 10 iterations):")
        vec_stats = benchmark_vectorized_cosilico(n_cases, resolver, iterations=10)
        print(f"  Total batch time:  {vec_stats['mean_batch_ms']:.3f} ms")
        print(f"  Per case:          {vec_stats['mean_per_case_ms']:.6f} ms")
        print(f"  Throughput:        {vec_stats['throughput_per_sec']:,.0f} cases/sec")

    # Projected microsim performance
    print("\n" + "-" * 70)
    print("PROJECTED MICROSIM PERFORMANCE (vectorized)")
    print("-" * 70)

    # Use 100k vectorized benchmark for projection
    vec_100k = benchmark_vectorized_cosilico(100000, resolver, iterations=5)
    cases_per_sec = vec_100k['throughput_per_sec']

    projections = [
        (100_000, "100K households (CPS)"),
        (1_000_000, "1M households"),
        (10_000_000, "10M households"),
        (130_000_000, "130M households (full US)"),
    ]

    print(f"\nUsing vectorized throughput: {cases_per_sec:,.0f} cases/sec")
    for n, label in projections:
        time_sec = n / cases_per_sec
        if time_sec < 1:
            print(f"  {label:30s} -> {time_sec*1000:.1f} ms")
        elif time_sec < 60:
            print(f"  {label:30s} -> {time_sec:.2f} seconds")
        elif time_sec < 3600:
            print(f"  {label:30s} -> {time_sec/60:.1f} minutes")
        else:
            print(f"  {label:30s} -> {time_sec/3600:.1f} hours")

    print("\n" + "=" * 70)
    print("Benchmark complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
