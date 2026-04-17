#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

import numpy as np
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import CompiledDenseProgram  # noqa: E402

OUTPUTS = [
    "gross_income",
    "personal_allowance",
    "taxable_income",
    "income_tax",
    "net_income",
]

console = Console()


@dataclass
class BenchmarkStats:
    taxpayers: int = 0
    total_gross_income: float = 0.0
    total_income_tax: float = 0.0
    total_tapered: int = 0
    total_additional_rate: int = 0
    compile_duration: float = 0.0
    generation_durations: list[float] = field(default_factory=list)
    execution_durations: list[float] = field(default_factory=list)


def benchmark_period() -> tuple[str, str, str]:
    return "tax_year", "2025-04-06", "2026-04-05"


# A crude but not absurd gross-income distribution for rUK employees and the
# self-employed. Share values roughly follow HMRC SPI percentiles.
INCOME_BUCKETS = [
    # (weight, lower, upper)
    (0.12, 6_000, 12_569),
    (0.33, 12_570, 30_000),
    (0.25, 30_000, 50_000),
    (0.13, 50_000, 80_000),
    (0.08, 80_000, 100_000),
    (0.05, 100_000, 125_140),
    (0.03, 125_140, 200_000),
    (0.01, 200_000, 500_000),
]


def sample_gross(rng: random.Random) -> int:
    roll = rng.random()
    acc = 0.0
    for weight, lower, upper in INCOME_BUCKETS:
        acc += weight
        if roll <= acc:
            return rng.randint(lower, upper)
    return rng.randint(6_000, 500_000)


def generate_batch(taxpayers: int, rng: random.Random) -> dict[str, np.ndarray]:
    employment = np.zeros(taxpayers, dtype=np.int64)
    self_employment = np.zeros(taxpayers, dtype=np.int64)
    pension = np.zeros(taxpayers, dtype=np.int64)
    property_ = np.zeros(taxpayers, dtype=np.int64)
    savings = np.zeros(taxpayers, dtype=np.int64)
    for index in range(taxpayers):
        gross = sample_gross(rng)
        # split gross across components with most of it in employment
        employment[index] = int(gross * rng.uniform(0.7, 1.0))
        residual = gross - employment[index]
        if residual > 0:
            share = rng.random()
            if share < 0.6:
                self_employment[index] = residual
            elif share < 0.8:
                pension[index] = residual
            elif share < 0.95:
                property_[index] = residual
            else:
                savings[index] = residual
    return {
        "employment_income": employment,
        "self_employment_income": self_employment,
        "pension_income": pension,
        "property_income": property_,
        "savings_income": savings,
    }


def consume_results(stats: BenchmarkStats, result: dict[str, object]) -> None:
    outputs = result["outputs"]
    assert isinstance(outputs, dict)
    gross = np.asarray(outputs["gross_income"], dtype=np.float64)
    tax = np.asarray(outputs["income_tax"], dtype=np.float64)
    pa = np.asarray(outputs["personal_allowance"], dtype=np.float64)
    stats.total_gross_income += float(gross.sum())
    stats.total_income_tax += float(tax.sum())
    stats.total_tapered += int((pa < 12570).sum())
    stats.total_additional_rate += int((gross > 125140).sum())


def run(args: argparse.Namespace) -> BenchmarkStats:
    stats = BenchmarkStats()
    rng = random.Random(args.seed)
    period_kind, start, end = benchmark_period()
    batches = (args.taxpayers + args.batch_size - 1) // args.batch_size

    compile_started = time.perf_counter()
    compiled = CompiledDenseProgram.from_file(args.program, entity=args.entity)
    stats.compile_duration = time.perf_counter() - compile_started
    console.print(
        f"[bold]engine_path[/bold]: requested=fast actual=fast(generic_dense_native) "
        f"root_entity={compiled.root_entity}"
    )

    for batch_index in range(batches):
        batch_size = min(
            args.batch_size,
            args.taxpayers - (batch_index * args.batch_size),
        )
        generation_started = time.perf_counter()
        inputs = generate_batch(batch_size, rng)
        generation_duration = time.perf_counter() - generation_started

        execution_started = time.perf_counter()
        result = compiled.execute(
            period_kind=period_kind,
            start=start,
            end=end,
            inputs=inputs,
            relations=None,
            outputs=list(OUTPUTS),
        )
        execution_duration = time.perf_counter() - execution_started
        consume_results(stats, result)

        stats.taxpayers += batch_size
        stats.generation_durations.append(generation_duration)
        stats.execution_durations.append(execution_duration)

        rate = (
            batch_size / execution_duration if execution_duration else float("inf")
        )
        console.print(
            f"batch {batch_index + 1}/{batches}: generated in {generation_duration:.4f}s, "
            f"executed in {execution_duration:.4f}s ({rate:,.0f} taxpayers/s)"
        )

    return stats


def print_summary(stats: BenchmarkStats, total_duration: float) -> None:
    total_generation = sum(stats.generation_durations)
    total_execution = sum(stats.execution_durations)
    execution_throughput = (
        stats.taxpayers / total_execution if total_execution else float("inf")
    )
    mean_income = (
        stats.total_gross_income / stats.taxpayers if stats.taxpayers else 0.0
    )
    mean_tax = stats.total_income_tax / stats.taxpayers if stats.taxpayers else 0.0
    effective_rate = (
        stats.total_income_tax / stats.total_gross_income
        if stats.total_gross_income
        else 0.0
    )
    taper_share = (
        stats.total_tapered / stats.taxpayers if stats.taxpayers else 0.0
    )
    additional_rate_share = (
        stats.total_additional_rate / stats.taxpayers if stats.taxpayers else 0.0
    )

    table = Table(title="rUK income tax 2025-26 benchmark")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("taxpayers", f"{stats.taxpayers:,}")
    table.add_row("compile_duration", f"{stats.compile_duration:.4f}s")
    table.add_row("total_duration", f"{total_duration:.4f}s")
    table.add_row("total_generation_duration", f"{total_generation:.4f}s")
    table.add_row("total_execution_duration", f"{total_execution:.4f}s")
    table.add_row(
        "mean_generation_duration",
        f"{mean(stats.generation_durations) if stats.generation_durations else 0.0:.4f}s",
    )
    table.add_row(
        "mean_execution_duration",
        f"{mean(stats.execution_durations) if stats.execution_durations else 0.0:.4f}s",
    )
    table.add_row("execution_throughput", f"{execution_throughput:,.0f} taxpayers/s")
    table.add_row("mean_gross_income", f"£{mean_income:,.0f}")
    table.add_row("mean_income_tax", f"£{mean_tax:,.0f}")
    table.add_row("effective_tax_rate", f"{effective_rate:.1%}")
    table.add_row("tapered_pa_share", f"{taper_share:.1%}")
    table.add_row("additional_rate_share", f"{additional_rate_share:.1%}")
    console.print()
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-execute rUK 2025-26 income tax via the generic dense Python path."
    )
    parser.add_argument("--taxpayers", type=int, default=1_000_000)
    parser.add_argument("--batch-size", type=int, default=1_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ukpga/2007/3/program.yaml"),
        help="Path to the UK income tax programme YAML document.",
    )
    parser.add_argument(
        "--entity",
        default="Taxpayer",
        help="Root entity for generic dense compilation.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    stats = run(args)
    total_duration = time.perf_counter() - started
    print_summary(stats, total_duration)


if __name__ == "__main__":
    main()
