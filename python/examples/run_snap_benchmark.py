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
import yaml
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import (  # noqa: E402
    CompiledDenseProgram,
    Dataset,
    DenseRelationBatch,
    ExecutionQuery,
    ExecutionRequest,
    Program,
    RAC,
)
from rac_api.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

OUTPUTS = [
    "household_size",
    "gross_income",
    "net_income",
    "passes_gross_income_test",
    "passes_net_income_test",
    "snap_eligible",
    "snap_allotment",
]

console = Console()


@dataclass
class BenchmarkStats:
    households: int = 0
    members: int = 0
    eligible_households: int = 0
    total_allotment_usd: float = 0.0
    compile_duration: float = 0.0
    generation_durations: list[float] = field(default_factory=list)
    execution_durations: list[float] = field(default_factory=list)


def default_binary_path() -> Path:
    release = ROOT / "target" / "release" / "rac"
    debug = ROOT / "target" / "debug" / "rac"
    return release if release.exists() else debug


def benchmark_period() -> Period:
    return Period(period_kind="month", start="2026-01-01", end="2026-01-31")


def random_household_size(rng: random.Random) -> int:
    return rng.choices([1, 2, 3, 4, 5, 6], weights=[22, 26, 19, 15, 10, 8], k=1)[0]


def money(value: int | float | str) -> ScalarValue:
    return ScalarValue(kind="decimal", value=str(value))


def bool_value(value: bool) -> ScalarValue:
    return ScalarValue(kind="bool", value=value)


def generate_dense_batch(
    households: int,
    rng: random.Random,
    relation_key: str,
) -> tuple[dict[str, np.ndarray], dict[str, DenseRelationBatch], int]:
    dependent_care = np.zeros(households, dtype=np.int64)
    child_support = np.zeros(households, dtype=np.int64)
    medical = np.zeros(households, dtype=np.int64)
    shelter = np.zeros(households, dtype=np.int64)
    elderly_or_disabled = np.zeros(households, dtype=np.bool_)
    offsets = np.zeros(households + 1, dtype=np.int64)
    earned_income: list[int] = []
    unearned_income: list[int] = []
    member_count = 0

    for household_index in range(households):
        household_size = random_household_size(rng)
        member_count += household_size

        has_elderly_or_disabled_member = rng.random() < 0.16
        dependent_care[household_index] = (
            rng.randrange(0, 601) if household_size >= 2 and rng.random() < 0.32 else 0
        )
        child_support[household_index] = (
            rng.randrange(0, 401) if rng.random() < 0.12 else 0
        )
        medical[household_index] = (
            rng.randrange(0, 801)
            if has_elderly_or_disabled_member and rng.random() < 0.45
            else 0
        )
        shelter[household_index] = rng.randrange(250, 1901)
        elderly_or_disabled[household_index] = has_elderly_or_disabled_member

        for _ in range(household_size):
            earned_income.append(rng.randrange(0, 3201) if rng.random() < 0.72 else 0)
            unearned_income.append(rng.randrange(0, 1801) if rng.random() < 0.38 else 0)

        offsets[household_index + 1] = len(earned_income)

    return (
        {
            "dependent_care_deduction": dependent_care,
            "child_support_deduction": child_support,
            "medical_deduction": medical,
            "shelter_costs": shelter,
            "has_elderly_or_disabled_member": elderly_or_disabled,
        },
        {
            relation_key: DenseRelationBatch(
                offsets=offsets,
                inputs={
                    "earned_income": np.asarray(earned_income, dtype=np.int64),
                    "unearned_income": np.asarray(unearned_income, dtype=np.int64),
                },
            )
        },
        member_count,
    )


def generate_cli_batch(
    start_index: int,
    households: int,
    rng: random.Random,
    period: Period,
) -> tuple[Dataset, list[ExecutionQuery], int]:
    interval = Interval(start=period.start, end=period.end)
    inputs: list[InputRecord] = []
    relations: list[RelationRecord] = []
    queries: list[ExecutionQuery] = []
    member_count = 0

    for household_index in range(start_index, start_index + households):
        household_id = f"household-{household_index}"
        household_size = random_household_size(rng)
        member_count += household_size
        has_elderly_or_disabled_member = rng.random() < 0.16
        shelter_costs = rng.randrange(250, 1901)
        dependent_care_deduction = (
            rng.randrange(0, 601) if household_size >= 2 and rng.random() < 0.32 else 0
        )
        child_support_deduction = rng.randrange(0, 401) if rng.random() < 0.12 else 0
        medical_deduction = (
            rng.randrange(0, 801)
            if has_elderly_or_disabled_member and rng.random() < 0.45
            else 0
        )

        inputs.extend(
            [
                InputRecord(
                    name="dependent_care_deduction",
                    entity="Household",
                    entity_id=household_id,
                    interval=interval,
                    value=money(dependent_care_deduction),
                ),
                InputRecord(
                    name="child_support_deduction",
                    entity="Household",
                    entity_id=household_id,
                    interval=interval,
                    value=money(child_support_deduction),
                ),
                InputRecord(
                    name="medical_deduction",
                    entity="Household",
                    entity_id=household_id,
                    interval=interval,
                    value=money(medical_deduction),
                ),
                InputRecord(
                    name="shelter_costs",
                    entity="Household",
                    entity_id=household_id,
                    interval=interval,
                    value=money(shelter_costs),
                ),
                InputRecord(
                    name="has_elderly_or_disabled_member",
                    entity="Household",
                    entity_id=household_id,
                    interval=interval,
                    value=bool_value(has_elderly_or_disabled_member),
                ),
            ]
        )

        for member_slot in range(household_size):
            person_id = f"{household_id}-person-{member_slot + 1}"
            earned_income = rng.randrange(0, 3201) if rng.random() < 0.72 else 0
            unearned_income = rng.randrange(0, 1801) if rng.random() < 0.38 else 0

            inputs.extend(
                [
                    InputRecord(
                        name="earned_income",
                        entity="Person",
                        entity_id=person_id,
                        interval=interval,
                        value=money(earned_income),
                    ),
                    InputRecord(
                        name="unearned_income",
                        entity="Person",
                        entity_id=person_id,
                        interval=interval,
                        value=money(unearned_income),
                    ),
                ]
            )
            relations.append(
                RelationRecord(
                    name="member_of_household",
                    tuple=[person_id, household_id],
                    interval=interval,
                )
            )

        queries.append(
            ExecutionQuery(entity_id=household_id, period=period, outputs=list(OUTPUTS))
        )

    return Dataset(inputs=inputs, relations=relations), queries, member_count


def consume_native_results(stats: BenchmarkStats, result: dict[str, object]) -> None:
    outputs = result["outputs"]
    assert isinstance(outputs, dict)
    snap_eligible = np.asarray(outputs["snap_eligible"])
    snap_allotment = np.asarray(outputs["snap_allotment"], dtype=np.float64)
    stats.eligible_households += int((snap_eligible == 1).sum())
    stats.total_allotment_usd += float(snap_allotment.sum())


def consume_cli_results(stats: BenchmarkStats, response) -> None:
    for result in response.results:
        outputs = result.outputs
        if outputs["snap_eligible"].outcome == "holds":
            stats.eligible_households += 1
        stats.total_allotment_usd += float(outputs["snap_allotment"].value.value)


def benchmark_native(args: argparse.Namespace) -> BenchmarkStats:
    stats = BenchmarkStats()
    rng = random.Random(args.seed)
    period = benchmark_period()
    batches = (args.households + args.batch_size - 1) // args.batch_size

    compile_started = time.perf_counter()
    compiled = CompiledDenseProgram.from_file(args.program, entity=args.entity)
    stats.compile_duration = time.perf_counter() - compile_started
    if len(compiled.relations) != 1:
        raise RuntimeError(
            "SNAP benchmark expected exactly one dense relation schema, "
            f"found {len(compiled.relations)}"
        )
    relation_key = compiled.relations[0].key

    console.print(
        f"[bold]engine_path[/bold]: requested=fast actual=fast(generic_dense_native) "
        f"root_entity={compiled.root_entity}"
    )

    for batch_index in range(batches):
        batch_households = min(
            args.batch_size,
            args.households - (batch_index * args.batch_size),
        )
        generation_started = time.perf_counter()
        inputs, relations, member_count = generate_dense_batch(
            batch_households, rng, relation_key
        )
        generation_duration = time.perf_counter() - generation_started

        execution_started = time.perf_counter()
        result = compiled.execute(
            period_kind=period.period_kind,
            start=str(period.start),
            end=str(period.end),
            inputs=inputs,
            relations=relations,
            outputs=list(OUTPUTS),
        )
        execution_duration = time.perf_counter() - execution_started
        consume_native_results(stats, result)

        stats.households += batch_households
        stats.members += member_count
        stats.generation_durations.append(generation_duration)
        stats.execution_durations.append(execution_duration)

        rate = (
            batch_households / execution_duration
            if execution_duration
            else float("inf")
        )
        console.print(
            f"batch {batch_index + 1}/{batches}: generated in {generation_duration:.4f}s, "
            f"executed in {execution_duration:.4f}s ({rate:,.0f} households/s)"
        )

    return stats


def benchmark_cli(args: argparse.Namespace) -> BenchmarkStats:
    stats = BenchmarkStats()
    rng = random.Random(args.seed)
    period = benchmark_period()
    batches = (args.households + args.batch_size - 1) // args.batch_size
    runner = RAC(binary_path=args.binary)
    program = Program.model_validate(yaml.safe_load(Path(args.program).read_text()))

    console.print("[bold]engine_path[/bold]: requested=fast actual=fast(cli)")
    for batch_index in range(batches):
        batch_households = min(
            args.batch_size,
            args.households - (batch_index * args.batch_size),
        )
        generation_started = time.perf_counter()
        dataset, queries, member_count = generate_cli_batch(
            start_index=batch_index * args.batch_size,
            households=batch_households,
            rng=rng,
            period=period,
        )
        generation_duration = time.perf_counter() - generation_started

        execution_started = time.perf_counter()
        response = runner.execute(
            ExecutionRequest(
                mode="fast",
                program=program,
                dataset=dataset,
                queries=queries,
            )
        )
        execution_duration = time.perf_counter() - execution_started
        consume_cli_results(stats, response)

        stats.households += batch_households
        stats.members += member_count
        stats.generation_durations.append(generation_duration)
        stats.execution_durations.append(execution_duration)

        rate = (
            batch_households / execution_duration
            if execution_duration
            else float("inf")
        )
        console.print(
            f"batch {batch_index + 1}/{batches}: generated in {generation_duration:.4f}s, "
            f"executed in {execution_duration:.4f}s ({rate:,.0f} households/s)"
        )

    return stats


def print_summary(engine: str, stats: BenchmarkStats, total_duration: float) -> None:
    total_generation = sum(stats.generation_durations)
    total_execution = sum(stats.execution_durations)
    execution_throughput = (
        stats.households / total_execution if total_execution else float("inf")
    )
    eligible_share = (
        stats.eligible_households / stats.households if stats.households else 0.0
    )
    mean_allotment = (
        stats.total_allotment_usd / stats.households if stats.households else 0.0
    )

    table = Table(title="SNAP benchmark summary")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("engine", engine)
    table.add_row("households", f"{stats.households:,}")
    table.add_row("members", f"{stats.members:,}")
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
    table.add_row("execution_throughput", f"{execution_throughput:,.0f} households/s")
    table.add_row("eligible_share", f"{eligible_share:.1%}")
    table.add_row("mean_allotment", f"{mean_allotment:.2f} USD")
    console.print()
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the SNAP YAML through either the generic dense Python path or the CLI."
    )
    parser.add_argument("--households", type=int, default=100_000)
    parser.add_argument("--batch-size", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--engine",
        choices=["native", "cli"],
        default="native",
        help="Benchmark the generic dense Python binding or the slower CLI boundary.",
    )
    parser.add_argument(
        "--binary",
        default=str(default_binary_path()),
        help="Path to the compiled rac executable when using --engine cli.",
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "examples" / "snap_program.yaml"),
        help="Path to the SNAP law YAML document.",
    )
    parser.add_argument(
        "--entity",
        default="Household",
        help="Root entity for generic dense compilation.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    if args.engine == "native":
        stats = benchmark_native(args)
        engine_label = "generic_dense_native"
    else:
        stats = benchmark_cli(args)
        engine_label = "cli"
    total_duration = time.perf_counter() - started
    print_summary(engine_label, stats, total_duration)


if __name__ == "__main__":
    main()
