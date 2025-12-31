#!/usr/bin/env python3
"""Speed benchmark: Cosilico AMT vs PolicyEngine-US.

Measures execution time for Alternative Minimum Tax calculations across various scenarios.
"""

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


def cosilico_amt(
    amti: float,
    regular_tax: float,
    filing_status: str,
    resolver,
    tax_year: int = 2024,
) -> dict:
    """Calculate AMT using Cosilico resolver.

    Returns dict with exemption, taxable_excess, tentative_minimum_tax, amt.
    """
    # Load parameters
    exemption_data = resolver.load_base_value("statute/26/55/d/1/exemption")
    phaseout_data = resolver.load_base_value("statute/26/55/d/2/phaseout")
    rate_data = resolver.load_base_value("statute/26/55/b/1/rate")
    bracket_data = resolver.load_base_value("statute/26/55/b/3/bracket")

    # Get values based on filing status
    fs = filing_status.upper()
    if fs == "JOINT":
        exemption_base = get_value_for_year(
            exemption_data["exemption_joint"]["values"], tax_year
        )
        phaseout_threshold = get_value_for_year(
            phaseout_data["phaseout_threshold_joint"]["values"], tax_year
        )
        bracket_threshold = get_value_for_year(
            bracket_data["amt_bracket_joint"]["values"], tax_year
        )
    elif fs == "MARRIED_SEPARATE":
        exemption_base = get_value_for_year(
            exemption_data["exemption_married_separate"]["values"], tax_year
        )
        phaseout_threshold = get_value_for_year(
            phaseout_data["phaseout_threshold_married_separate"]["values"], tax_year
        )
        bracket_threshold = get_value_for_year(
            bracket_data["amt_bracket_married_separate"]["values"], tax_year
        )
    else:  # SINGLE or HEAD_OF_HOUSEHOLD
        exemption_base = get_value_for_year(
            exemption_data["exemption_single"]["values"], tax_year
        )
        phaseout_threshold = get_value_for_year(
            phaseout_data["phaseout_threshold_single"]["values"], tax_year
        )
        bracket_threshold = get_value_for_year(
            bracket_data["amt_bracket_single"]["values"], tax_year
        )

    phaseout_rate = get_value_for_year(
        phaseout_data["phaseout_rate"]["values"], tax_year
    )
    rate_low = get_value_for_year(rate_data["amt_rate_low"]["values"], tax_year)
    rate_high = get_value_for_year(rate_data["amt_rate_high"]["values"], tax_year)

    # Calculate exemption with phaseout
    excess_over_threshold = max(0, amti - phaseout_threshold)
    phaseout_amount = excess_over_threshold * phaseout_rate
    exemption = max(0, exemption_base - phaseout_amount)

    # Calculate taxable excess
    taxable_excess = max(0, amti - exemption)

    # Calculate tentative minimum tax (two-bracket)
    amount_at_26_pct = min(taxable_excess, bracket_threshold)
    amount_at_28_pct = max(0, taxable_excess - bracket_threshold)
    tmt = (amount_at_26_pct * rate_low) + (amount_at_28_pct * rate_high)

    # AMT is excess of TMT over regular tax
    amt = max(0, tmt - regular_tax)

    return {
        "exemption": exemption,
        "taxable_excess": taxable_excess,
        "tentative_minimum_tax": tmt,
        "amt": amt,
    }


def policyengine_amt(
    amti: float,
    regular_tax: float,
    filing_status: str,
    tax_year: int = 2024,
) -> dict:
    """Calculate AMT using PolicyEngine-US.

    Note: PolicyEngine calculates AMT as part of full tax simulation,
    so we approximate by setting up a situation with appropriate income.
    """
    is_married = filing_status.upper() == "JOINT"

    # PolicyEngine needs employment income to derive tax
    # We use AMTI as a proxy for income
    situation = {
        "people": {
            "adult": {
                "age": {tax_year: 40},
                "employment_income": {tax_year: amti},
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

    # PolicyEngine has "alternative_minimum_tax" variable
    try:
        amt = float(sim.calculate("alternative_minimum_tax", tax_year).sum())
    except Exception:
        amt = 0

    return {
        "exemption": 0,  # PolicyEngine doesn't expose intermediate values
        "taxable_excess": 0,
        "tentative_minimum_tax": 0,
        "amt": amt,
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
            result = cosilico_amt(
                tc["amti"],
                tc["regular_tax"],
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
            result = policyengine_amt(
                tc["amti"],
                tc["regular_tax"],
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
    print("AMT Speed Benchmark: Cosilico vs PolicyEngine-US")
    print("=" * 70)

    # Initialize Cosilico resolver
    print("\nInitializing Cosilico resolver...")
    resolver = create_resolver(str(COSILICO_US_ROOT))

    # Test cases covering various scenarios
    test_cases = [
        # Below phaseout threshold
        {"amti": 100000, "regular_tax": 15000, "filing_status": "SINGLE"},
        {"amti": 200000, "regular_tax": 25000, "filing_status": "JOINT"},
        {"amti": 150000, "regular_tax": 10000, "filing_status": "SINGLE"},
        # Partial phaseout
        {"amti": 700000, "regular_tax": 100000, "filing_status": "SINGLE"},
        {"amti": 1400000, "regular_tax": 300000, "filing_status": "JOINT"},
        # Full phaseout
        {"amti": 1000000, "regular_tax": 200000, "filing_status": "SINGLE"},
        {"amti": 2000000, "regular_tax": 500000, "filing_status": "JOINT"},
        # Married filing separately
        {"amti": 150000, "regular_tax": 15000, "filing_status": "MARRIED_SEPARATE"},
        # Very high income
        {"amti": 5000000, "regular_tax": 1500000, "filing_status": "SINGLE"},
        {"amti": 10000000, "regular_tax": 3000000, "filing_status": "JOINT"},
    ]

    # Single case benchmark
    print("\n" + "-" * 70)
    print("SINGLE CASE BENCHMARK (AMTI $100k, single filer)")
    print("-" * 70)

    tc = test_cases[0]

    print("\nCosilico (100 iterations):")
    cosilico_stats = benchmark_single(
        cosilico_amt,
        tc["amti"], tc["regular_tax"], tc["filing_status"],
        resolver,
        iterations=100,
    )
    print(f"  AMT:      ${cosilico_stats['result']['amt']:.2f}")
    print(f"  Exemption: ${cosilico_stats['result']['exemption']:.2f}")
    print(f"  TMT:      ${cosilico_stats['result']['tentative_minimum_tax']:.2f}")
    print(f"  Mean:     {cosilico_stats['mean_ms']:.3f} ms")
    print(f"  Median:   {cosilico_stats['median_ms']:.3f} ms")
    print(f"  Stdev:    {cosilico_stats['stdev_ms']:.3f} ms")
    print(f"  Range:    {cosilico_stats['min_ms']:.3f} - {cosilico_stats['max_ms']:.3f} ms")

    if HAS_POLICYENGINE:
        print("\nPolicyEngine (10 iterations - slower due to initialization):")
        pe_stats = benchmark_single(
            policyengine_amt,
            tc["amti"], tc["regular_tax"], tc["filing_status"],
            iterations=10,
        )
        print(f"  AMT:      ${pe_stats['result']['amt']:.2f}")
        print(f"  Mean:     {pe_stats['mean_ms']:.3f} ms")
        print(f"  Median:   {pe_stats['median_ms']:.3f} ms")
        print(f"  Stdev:    {pe_stats['stdev_ms']:.3f} ms")
        print(f"  Range:    {pe_stats['min_ms']:.3f} - {pe_stats['max_ms']:.3f} ms")

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
