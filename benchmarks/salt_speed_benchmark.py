#!/usr/bin/env python3
"""Speed benchmark: Cosilico SALT deduction cap vs PolicyEngine-US.

Measures execution time for SALT deduction calculations across various scenarios.
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


def cosilico_salt(
    state_income_tax: float,
    real_property_tax: float,
    personal_property_tax: float,
    filing_status: str,
    resolver,
    tax_year: int = 2024,
) -> dict:
    """Calculate SALT deduction using Cosilico resolver.

    Returns dict with salt_before_cap, salt_cap_amount, salt_deduction, salt_cap_reduction.
    """
    # Load cap parameters
    cap_data = resolver.load_base_value("statute/26/164/b/6/cap")

    # Get applicable cap based on filing status
    fs = filing_status.upper()
    if fs == "MARRIED_SEPARATE":
        salt_cap = get_value_for_year(
            cap_data["salt_cap_married_separate"]["values"], tax_year
        )
    else:
        salt_cap = get_value_for_year(cap_data["salt_cap"]["values"], tax_year)

    # Calculate total SALT before cap
    salt_before_cap = real_property_tax + personal_property_tax + state_income_tax

    # Apply cap
    if math.isinf(salt_cap):
        capped_salt = salt_before_cap
        cap_reduction = 0
    else:
        capped_salt = min(salt_before_cap, salt_cap)
        cap_reduction = max(0, salt_before_cap - salt_cap)

    return {
        "salt_before_cap": salt_before_cap,
        "salt_cap_amount": salt_cap,
        "salt_deduction": capped_salt,
        "salt_cap_reduction": cap_reduction,
    }


def policyengine_salt(
    state_income_tax: float,
    real_property_tax: float,
    personal_property_tax: float,
    filing_status: str,
    tax_year: int = 2024,
) -> dict:
    """Calculate SALT deduction using PolicyEngine-US.

    Note: PolicyEngine calculates SALT as part of full tax simulation.
    """
    is_married = filing_status.upper() == "JOINT"

    # Create situation with appropriate income to generate state tax
    situation = {
        "people": {
            "adult": {
                "age": {tax_year: 40},
                "employment_income": {tax_year: 100000},
                # PolicyEngine uses real_estate_taxes variable
                "real_estate_taxes": {tax_year: real_property_tax},
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

    if is_married:
        situation["people"]["spouse"] = {
            "age": {tax_year: 40},
            "employment_income": {tax_year: 0},
        }
        situation["tax_units"]["tax_unit"]["members"].append("spouse")
        situation["spm_units"]["spm_unit"]["members"].append("spouse")
        situation["households"]["household"]["members"].append("spouse")

    sim = Simulation(situation=situation)

    # PolicyEngine has "salt_deduction" variable
    try:
        salt = float(sim.calculate("salt_deduction", tax_year).sum())
    except Exception:
        salt = 0

    return {
        "salt_before_cap": 0,  # PolicyEngine doesn't expose this
        "salt_cap_amount": 0,
        "salt_deduction": salt,
        "salt_cap_reduction": 0,
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
            result = cosilico_salt(
                tc["state_income_tax"],
                tc["real_property_tax"],
                tc["personal_property_tax"],
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
            result = policyengine_salt(
                tc["state_income_tax"],
                tc["real_property_tax"],
                tc["personal_property_tax"],
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
    print("SALT Deduction Cap Speed Benchmark: Cosilico vs PolicyEngine-US")
    print("=" * 70)

    # Initialize Cosilico resolver
    print("\nInitializing Cosilico resolver...")
    resolver = create_resolver(str(COSILICO_US_ROOT))

    # Test cases covering various scenarios
    test_cases = [
        # Below cap
        {"state_income_tax": 3000, "real_property_tax": 5000, "personal_property_tax": 500, "filing_status": "SINGLE"},
        {"state_income_tax": 4000, "real_property_tax": 4000, "personal_property_tax": 1000, "filing_status": "JOINT"},
        # At cap
        {"state_income_tax": 5000, "real_property_tax": 5000, "personal_property_tax": 0, "filing_status": "SINGLE"},
        # Above cap - moderate
        {"state_income_tax": 8000, "real_property_tax": 15000, "personal_property_tax": 2000, "filing_status": "SINGLE"},
        {"state_income_tax": 10000, "real_property_tax": 20000, "personal_property_tax": 5000, "filing_status": "JOINT"},
        # High-tax state scenarios
        {"state_income_tax": 20000, "real_property_tax": 25000, "personal_property_tax": 0, "filing_status": "JOINT"},
        {"state_income_tax": 50000, "real_property_tax": 30000, "personal_property_tax": 5000, "filing_status": "JOINT"},
        # MFS filers
        {"state_income_tax": 3000, "real_property_tax": 3000, "personal_property_tax": 0, "filing_status": "MARRIED_SEPARATE"},
        {"state_income_tax": 10000, "real_property_tax": 10000, "personal_property_tax": 0, "filing_status": "MARRIED_SEPARATE"},
        # Very high SALT
        {"state_income_tax": 100000, "real_property_tax": 50000, "personal_property_tax": 10000, "filing_status": "JOINT"},
    ]

    # Single case benchmark
    print("\n" + "-" * 70)
    print("SINGLE CASE BENCHMARK (moderate SALT, single filer)")
    print("-" * 70)

    tc = test_cases[0]

    print("\nCosilico (100 iterations):")
    cosilico_stats = benchmark_single(
        cosilico_salt,
        tc["state_income_tax"], tc["real_property_tax"], tc["personal_property_tax"],
        tc["filing_status"],
        resolver,
        iterations=100,
    )
    print(f"  SALT Before Cap:  ${cosilico_stats['result']['salt_before_cap']:.2f}")
    print(f"  SALT Cap:         ${cosilico_stats['result']['salt_cap_amount']:.2f}")
    print(f"  SALT Deduction:   ${cosilico_stats['result']['salt_deduction']:.2f}")
    print(f"  Cap Reduction:    ${cosilico_stats['result']['salt_cap_reduction']:.2f}")
    print(f"  Mean:             {cosilico_stats['mean_ms']:.3f} ms")
    print(f"  Median:           {cosilico_stats['median_ms']:.3f} ms")
    print(f"  Stdev:            {cosilico_stats['stdev_ms']:.3f} ms")
    print(f"  Range:            {cosilico_stats['min_ms']:.3f} - {cosilico_stats['max_ms']:.3f} ms")

    if HAS_POLICYENGINE:
        print("\nPolicyEngine (10 iterations - slower due to initialization):")
        pe_stats = benchmark_single(
            policyengine_salt,
            tc["state_income_tax"], tc["real_property_tax"], tc["personal_property_tax"],
            tc["filing_status"],
            iterations=10,
        )
        print(f"  SALT Deduction:   ${pe_stats['result']['salt_deduction']:.2f}")
        print(f"  Mean:             {pe_stats['mean_ms']:.3f} ms")
        print(f"  Median:           {pe_stats['median_ms']:.3f} ms")
        print(f"  Stdev:            {pe_stats['stdev_ms']:.3f} ms")
        print(f"  Range:            {pe_stats['min_ms']:.3f} - {pe_stats['max_ms']:.3f} ms")

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
