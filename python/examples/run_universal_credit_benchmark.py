#!/usr/bin/env python3
# ruff: noqa: E402
"""Bulk-execute Universal Credit over millions of synthetic benefit units."""
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

from axiom_rules import CompiledDenseProgram, DenseRelationBatch  # noqa: E402

OUTPUTS = [
    "standard_allowance",
    "child_element_total",
    "disabled_child_element_total",
    "lcwra_element",
    "carer_element",
    "housing_element",
    "max_uc",
    "work_allowance_amount",
    "earnings_deduction",
    "tariff_income",
    "over_capital_limit",
    "uc_award",
]

console = Console()


@dataclass
class BenchmarkStats:
    benefit_units: int = 0
    total_max_uc: float = 0.0
    total_award: float = 0.0
    over_capital_limit: int = 0
    has_housing: int = 0
    has_earnings: int = 0
    has_lcwra: int = 0
    has_children: int = 0
    couples: int = 0
    compile_duration: float = 0.0
    generation_durations: list[float] = field(default_factory=list)
    execution_durations: list[float] = field(default_factory=list)


def benchmark_period() -> tuple[str, str, str]:
    return "month", "2025-05-01", "2025-05-31"


def sample_couple(rng: random.Random) -> bool:
    return rng.random() < 0.35


def sample_children_count(rng: random.Random) -> int:
    return rng.choices([0, 1, 2, 3, 4], weights=[0.55, 0.20, 0.15, 0.07, 0.03])[0]


def sample_housing(rng: random.Random) -> tuple[bool, int, int]:
    has_housing = rng.random() < 0.55
    if not has_housing:
        return (False, 0, 0)
    eligible = rng.randint(400, 1_500)
    non_dep = rng.randint(0, 150) if rng.random() < 0.1 else 0
    return (True, eligible, non_dep)


def sample_earnings(rng: random.Random) -> int:
    roll = rng.random()
    if roll < 0.45:
        return 0
    if roll < 0.75:
        return rng.randint(300, 1_400)
    return rng.randint(1_400, 3_500)


def sample_capital(rng: random.Random) -> int:
    roll = rng.random()
    if roll < 0.80:
        return rng.randint(0, 1_500)
    if roll < 0.95:
        return rng.randint(1_500, 8_000)
    return rng.randint(8_000, 20_000)


def generate_batch(
    benefit_units: int,
    rng: random.Random,
    stats: BenchmarkStats,
) -> tuple[dict[str, np.ndarray], dict[str, DenseRelationBatch]]:
    is_couple = np.zeros(benefit_units, dtype=np.bool_)
    has_housing_costs = np.zeros(benefit_units, dtype=np.bool_)
    eligible_housing_costs = np.zeros(benefit_units, dtype=np.int64)
    non_dep_deductions_total = np.zeros(benefit_units, dtype=np.int64)
    earned_income_monthly = np.zeros(benefit_units, dtype=np.int64)
    unearned_income_monthly = np.zeros(benefit_units, dtype=np.int64)
    capital_total = np.zeros(benefit_units, dtype=np.int64)

    adult_offsets = np.zeros(benefit_units + 1, dtype=np.int64)
    adult_age_25_or_over: list[bool] = []
    adult_has_lcwra: list[bool] = []
    adult_is_carer: list[bool] = []

    child_offsets = np.zeros(benefit_units + 1, dtype=np.int64)
    child_qualifies: list[bool] = []
    child_disability: list[str] = []

    adult_cursor = 0
    child_cursor = 0

    for index in range(benefit_units):
        couple = sample_couple(rng)
        is_couple[index] = couple
        if couple:
            stats.couples += 1

        n_adults = 2 if couple else 1
        any_lcwra = False
        for _ in range(n_adults):
            adult_age_25_or_over.append(rng.random() < 0.80)
            lcwra = rng.random() < 0.12
            adult_has_lcwra.append(lcwra)
            adult_is_carer.append(rng.random() < 0.05)
            any_lcwra = any_lcwra or lcwra
            adult_cursor += 1
        adult_offsets[index + 1] = adult_cursor
        if any_lcwra:
            stats.has_lcwra += 1

        n_children = sample_children_count(rng)
        if n_children >= 1:
            stats.has_children += 1
        for slot in range(n_children):
            qualifies = slot < 2  # two-child limit, first two qualify
            child_qualifies.append(qualifies)
            roll = rng.random()
            if roll < 0.96:
                child_disability.append("none")
            elif roll < 0.99:
                child_disability.append("lower")
            else:
                child_disability.append("higher")
            child_cursor += 1
        child_offsets[index + 1] = child_cursor

        housing, eligible, non_dep = sample_housing(rng)
        if housing:
            stats.has_housing += 1
        has_housing_costs[index] = housing
        eligible_housing_costs[index] = eligible
        non_dep_deductions_total[index] = non_dep

        earnings = sample_earnings(rng)
        if earnings > 0:
            stats.has_earnings += 1
        earned_income_monthly[index] = earnings
        unearned_income_monthly[index] = 0

        capital_total[index] = sample_capital(rng)

    return (
        {
            "is_couple": is_couple,
            "has_housing_costs": has_housing_costs,
            "eligible_housing_costs": eligible_housing_costs,
            "non_dep_deductions_total": non_dep_deductions_total,
            "earned_income_monthly": earned_income_monthly,
            "unearned_income_monthly": unearned_income_monthly,
            "capital_total": capital_total,
        },
        {
            "adult_of_benefit_unit::1/0": DenseRelationBatch(
                offsets=adult_offsets,
                inputs={
                    "age_25_or_over": np.asarray(adult_age_25_or_over, dtype=np.bool_),
                    "has_lcwra": np.asarray(adult_has_lcwra, dtype=np.bool_),
                    "is_carer": np.asarray(adult_is_carer, dtype=np.bool_),
                },
            ),
            "child_of_benefit_unit::1/0": DenseRelationBatch(
                offsets=child_offsets,
                inputs={
                    "qualifies_for_child_element": np.asarray(
                        child_qualifies, dtype=np.bool_
                    ),
                    "disability_level": np.asarray(child_disability, dtype=object),
                },
            ),
        },
    )


def consume_results(stats: BenchmarkStats, result: dict[str, object]) -> None:
    outputs = result["outputs"]
    assert isinstance(outputs, dict)
    max_uc = np.asarray(outputs["max_uc"], dtype=np.float64)
    award = np.asarray(outputs["uc_award"], dtype=np.float64)
    over_cap = np.asarray(outputs["over_capital_limit"])
    stats.total_max_uc += float(max_uc.sum())
    stats.total_award += float(award.sum())
    stats.over_capital_limit += int((over_cap == 1).sum())


def run(args: argparse.Namespace) -> BenchmarkStats:
    stats = BenchmarkStats()
    rng = random.Random(args.seed)
    period_kind, start, end = benchmark_period()
    batches = (args.benefit_units + args.batch_size - 1) // args.batch_size

    compile_started = time.perf_counter()
    compiled = CompiledDenseProgram.from_file(args.program, entity=args.entity)
    stats.compile_duration = time.perf_counter() - compile_started
    console.print(
        f"[bold]engine_path[/bold]: requested=fast actual=fast(generic_dense_native) "
        f"root_entity={compiled.root_entity}"
    )

    relation_keys = {relation.name: relation.key for relation in compiled.relations}

    for batch_index in range(batches):
        batch_size = min(
            args.batch_size,
            args.benefit_units - (batch_index * args.batch_size),
        )
        generation_started = time.perf_counter()
        inputs, raw_relations = generate_batch(batch_size, rng, stats)
        relations = {
            relation_keys[name.split("::")[0]]: batch
            for name, batch in raw_relations.items()
        }
        generation_duration = time.perf_counter() - generation_started

        execution_started = time.perf_counter()
        result = compiled.execute(
            period_kind=period_kind,
            start=start,
            end=end,
            inputs=inputs,
            relations=relations,
            outputs=list(OUTPUTS),
        )
        execution_duration = time.perf_counter() - execution_started
        consume_results(stats, result)

        stats.benefit_units += batch_size
        stats.generation_durations.append(generation_duration)
        stats.execution_durations.append(execution_duration)

        rate = (
            batch_size / execution_duration if execution_duration else float("inf")
        )
        console.print(
            f"batch {batch_index + 1}/{batches}: generated in {generation_duration:.4f}s, "
            f"executed in {execution_duration:.4f}s ({rate:,.0f} benefit_units/s)"
        )

    return stats


def print_summary(stats: BenchmarkStats, total_duration: float) -> None:
    total_generation = sum(stats.generation_durations)
    total_execution = sum(stats.execution_durations)
    throughput = (
        stats.benefit_units / total_execution if total_execution else float("inf")
    )
    mean_award = (
        stats.total_award / stats.benefit_units if stats.benefit_units else 0.0
    )
    mean_max_uc = (
        stats.total_max_uc / stats.benefit_units if stats.benefit_units else 0.0
    )

    def share(value: int) -> str:
        if not stats.benefit_units:
            return "-"
        return f"{value / stats.benefit_units:.1%}"

    table = Table(title="Universal Credit 2025-26 benchmark")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("benefit_units", f"{stats.benefit_units:,}")
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
    table.add_row("execution_throughput", f"{throughput:,.0f} benefit_units/s")
    table.add_row("mean_max_uc", f"£{mean_max_uc:,.2f}")
    table.add_row("mean_uc_award", f"£{mean_award:,.2f}")
    table.add_row("couple_share", share(stats.couples))
    table.add_row("with_children_share", share(stats.has_children))
    table.add_row("with_housing_share", share(stats.has_housing))
    table.add_row("with_earnings_share", share(stats.has_earnings))
    table.add_row("with_lcwra_share", share(stats.has_lcwra))
    table.add_row("over_capital_limit_share", share(stats.over_capital_limit))
    console.print()
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-execute Universal Credit through the generic dense Python path."
    )
    parser.add_argument("--benefit-units", type=int, default=1_000_000)
    parser.add_argument("--batch-size", type=int, default=1_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "uksi/2013/376/rules.rac"),
        help="Path to the Universal Credit programme YAML.",
    )
    parser.add_argument(
        "--entity",
        default="BenefitUnit",
        help="Root entity for generic dense compilation.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    stats = run(args)
    total_duration = time.perf_counter() - started
    print_summary(stats, total_duration)


if __name__ == "__main__":
    main()
