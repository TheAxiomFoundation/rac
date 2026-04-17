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

from rac_api import CompiledDenseProgram, DenseRelationBatch  # noqa: E402

OUTPUTS = [
    "cb_recipient_count",
    "has_cb_recipient",
    "needs_fallback",
    "sole_claim_fallback",
    "usual_residence_fallback",
    "responsible_person",
]

console = Console()


@dataclass
class BenchmarkStats:
    children: int = 0
    cb_recipients: int = 0
    needs_fallback: int = 0
    sole_claim_fallback: int = 0
    usual_residence_fallback: int = 0
    compile_duration: float = 0.0
    generation_durations: list[float] = field(default_factory=list)
    execution_durations: list[float] = field(default_factory=list)


def benchmark_period() -> tuple[str, str, str]:
    return "benefit_week", "2026-01-05", "2026-01-11"


def generate_dense_batch(
    children: int,
    start_index: int,
    rng: random.Random,
    relation_key: str,
) -> tuple[dict[str, np.ndarray], dict[str, DenseRelationBatch], int]:
    cb_claim_count = np.zeros(children, dtype=np.int64)
    cb_recipient_id: list[str] = []
    sole_claimant_id: list[str] = []
    usual_resident_id: list[str] = []
    offsets = np.zeros(children + 1, dtype=np.int64)
    recipient_count = 0

    for child_index in range(children):
        global_index = start_index + child_index
        roll = rng.random()
        if roll < 0.55:
            # cb receipt wins
            cb_claim_count[child_index] = 1
            cb_recipient_id.append(f"person-receiver-{global_index}")
            sole_claimant_id.append(f"person-receiver-{global_index}")
            usual_resident_id.append(f"person-resident-{global_index}")
            recipient_count += 1
        elif roll < 0.75:
            # no cb + single past claim
            cb_claim_count[child_index] = 1
            cb_recipient_id.append("")
            sole_claimant_id.append(f"person-claimant-{global_index}")
            usual_resident_id.append(f"person-resident-{global_index}")
        elif roll < 0.95:
            # no cb + multiple past claims
            cb_claim_count[child_index] = 2 + int(rng.random() * 3)
            cb_recipient_id.append("")
            sole_claimant_id.append("")
            usual_resident_id.append(f"person-resident-{global_index}")
        else:
            # no cb + zero claims ever
            cb_claim_count[child_index] = 0
            cb_recipient_id.append("")
            sole_claimant_id.append("")
            usual_resident_id.append(f"person-resident-{global_index}")
        offsets[child_index + 1] = recipient_count

    return (
        {
            "cb_claim_count": cb_claim_count,
            "cb_recipient_id": np.asarray(cb_recipient_id, dtype=object),
            "sole_claimant_id": np.asarray(sole_claimant_id, dtype=object),
            "usual_resident_id": np.asarray(usual_resident_id, dtype=object),
        },
        {
            relation_key: DenseRelationBatch(
                offsets=offsets,
                inputs={},
            )
        },
        recipient_count,
    )


def consume_results(stats: BenchmarkStats, result: dict[str, object]) -> None:
    outputs = result["outputs"]
    assert isinstance(outputs, dict)
    has_recipient = np.asarray(outputs["has_cb_recipient"])
    needs_fallback = np.asarray(outputs["needs_fallback"])
    sole_claim = np.asarray(outputs["sole_claim_fallback"])
    usual_residence = np.asarray(outputs["usual_residence_fallback"])
    # judgments come back as ints: 1=holds, 0=not_holds, -1=undetermined
    stats.cb_recipients += int((has_recipient == 1).sum())
    stats.needs_fallback += int((needs_fallback == 1).sum())
    stats.sole_claim_fallback += int((sole_claim == 1).sum())
    stats.usual_residence_fallback += int((usual_residence == 1).sum())


def run(args: argparse.Namespace) -> BenchmarkStats:
    stats = BenchmarkStats()
    rng = random.Random(args.seed)
    period_kind, period_start, period_end = benchmark_period()
    batches = (args.children + args.batch_size - 1) // args.batch_size

    compile_started = time.perf_counter()
    compiled = CompiledDenseProgram.from_file(args.program, entity=args.entity)
    stats.compile_duration = time.perf_counter() - compile_started
    if len(compiled.relations) != 1:
        raise RuntimeError(
            "child benefit benchmark expected exactly one dense relation, "
            f"found {len(compiled.relations)}"
        )
    relation_key = compiled.relations[0].key

    console.print(
        f"[bold]engine_path[/bold]: requested=fast actual=fast(generic_dense_native) "
        f"root_entity={compiled.root_entity}"
    )

    start_index = 0
    for batch_index in range(batches):
        batch_children = min(
            args.batch_size,
            args.children - (batch_index * args.batch_size),
        )
        generation_started = time.perf_counter()
        inputs, relations, _ = generate_dense_batch(
            batch_children, start_index, rng, relation_key
        )
        generation_duration = time.perf_counter() - generation_started

        execution_started = time.perf_counter()
        result = compiled.execute(
            period_kind=period_kind,
            start=period_start,
            end=period_end,
            inputs=inputs,
            relations=relations,
            outputs=list(OUTPUTS),
        )
        execution_duration = time.perf_counter() - execution_started
        consume_results(stats, result)

        stats.children += batch_children
        stats.generation_durations.append(generation_duration)
        stats.execution_durations.append(execution_duration)

        rate = (
            batch_children / execution_duration
            if execution_duration
            else float("inf")
        )
        console.print(
            f"batch {batch_index + 1}/{batches}: generated in {generation_duration:.4f}s, "
            f"executed in {execution_duration:.4f}s ({rate:,.0f} children/s)"
        )
        start_index += batch_children

    return stats


def print_summary(stats: BenchmarkStats, total_duration: float) -> None:
    total_generation = sum(stats.generation_durations)
    total_execution = sum(stats.execution_durations)
    execution_throughput = (
        stats.children / total_execution if total_execution else float("inf")
    )
    cb_share = stats.cb_recipients / stats.children if stats.children else 0.0
    fallback_share = stats.needs_fallback / stats.children if stats.children else 0.0

    table = Table(title="reg 15 child benefit benchmark")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("children", f"{stats.children:,}")
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
    table.add_row("execution_throughput", f"{execution_throughput:,.0f} children/s")
    table.add_row("cb_recipient_share", f"{cb_share:.1%}")
    table.add_row("anti_join_share", f"{fallback_share:.1%}")
    table.add_row(
        "sole_claim_fallback_share",
        f"{stats.sole_claim_fallback / stats.children:.1%}" if stats.children else "-",
    )
    table.add_row(
        "usual_residence_fallback_share",
        f"{stats.usual_residence_fallback / stats.children:.1%}"
        if stats.children
        else "-",
    )
    console.print()
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-execute reg 15 child-benefit responsibility through the generic dense Python path."
    )
    parser.add_argument("--children", type=int, default=1_000_000)
    parser.add_argument("--batch-size", type=int, default=1_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--program",
        default=str(
            ROOT / "programmes" / "uksi/1987/1967/regulation/15/program.yaml"
        ),
        help="Path to the reg 15 programme YAML document.",
    )
    parser.add_argument(
        "--entity",
        default="Child",
        help="Root entity for generic dense compilation.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    stats = run(args)
    total_duration = time.perf_counter() - started
    print_summary(stats, total_duration)


if __name__ == "__main__":
    main()
