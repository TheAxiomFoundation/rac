#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the LGFA 1992 s.11 council tax discount cases."""
from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import Dataset, ExecutionQuery, ExecutionRequest, Program, RAC
from rac_api.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

CONSOLE = Console()

OUTPUTS = [
    "num_non_disregarded_residents",
    "single_occupier_discount_applies",
    "empty_home_discount_applies",
    "appropriate_percentage",
    "discount_fraction",
]


class Resident(BaseModel):
    id: str
    is_disregarded: bool


class ExpectedOutputs(BaseModel):
    num_non_disregarded_residents: int | None = None
    single_occupier_discount_applies: Literal[
        "holds", "not_holds", "undetermined"
    ] | None = None
    empty_home_discount_applies: Literal[
        "holds", "not_holds", "undetermined"
    ] | None = None
    discount_fraction: str | None = None


class DwellingCase(BaseModel):
    name: str
    dwelling_id: str
    period: Period
    empty_home_override_applies: bool
    residents: list[Resident]
    expected: ExpectedOutputs


class DwellingCaseFile(BaseModel):
    cases: list[DwellingCase]


def build_dataset(case: DwellingCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    inputs = [
        InputRecord(
            name="empty_home_override_applies",
            entity="Dwelling",
            entity_id=case.dwelling_id,
            interval=interval,
            value=ScalarValue(kind="bool", value=case.empty_home_override_applies),
        ),
    ]
    relations = []
    for r in case.residents:
        inputs.append(
            InputRecord(
                name="is_disregarded",
                entity="Person",
                entity_id=r.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=r.is_disregarded),
            )
        )
        relations.append(
            RelationRecord(
                name="resident_of",
                tuple=[r.id, case.dwelling_id],
                interval=interval,
            )
        )
    return Dataset(inputs=inputs, relations=relations)


def render_trace(case_name: str, result) -> None:
    tree = Tree(
        f"[bold]{case_name}[/bold] — discount_fraction = "
        f"{result.outputs['discount_fraction'].value.value}"
    )
    shown: set[str] = set()

    def attach(parent: Tree, name: str, depth: int = 0) -> None:
        if name in shown or depth > 6:
            return
        shown.add(name)
        node = result.trace.get(name)
        if node is None:
            return
        value = node.value.value if node.kind == "scalar" else node.outcome
        label = f"[bold cyan]{name}[/bold cyan] = {value}"
        if node.unit:
            label += f" [dim]{node.unit}[/dim]"
        if node.source:
            label += f" [italic]{node.source}[/italic]"
        branch = parent.add(label)
        for dep in node.dependencies:
            attach(branch, dep, depth + 1)

    attach(tree, "discount_fraction")
    CONSOLE.print(tree)


def check_expected(case: DwellingCase, result) -> tuple[bool, list[str]]:
    problems = []
    for field, expected_value in case.expected.model_dump().items():
        if expected_value is None:
            continue
        if field in {"single_occupier_discount_applies", "empty_home_discount_applies"}:
            actual = result.outputs[field].outcome
            if str(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        else:
            actual = result.outputs[field].value.value
            if field == "num_non_disregarded_residents":
                if int(expected_value) != int(actual):
                    problems.append(f"{field}: expected {expected_value}, got {actual}")
            else:
                if Decimal(str(expected_value)) != Decimal(str(actual)):
                    problems.append(f"{field}: expected {expected_value}, got {actual}")
    return (len(problems) == 0, problems)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run LGFA 1992 s.11 council tax discount cases"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ukpga/1992/14/section/11/program.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "ukpga/1992/14/section/11/cases.yaml"),
    )
    parser.add_argument(
        "--no-trace",
        dest="trace",
        action="store_false",
    )
    parser.set_defaults(trace=True)
    args = parser.parse_args()

    program = Program.model_validate(yaml.safe_load(Path(args.program).read_text()))
    case_file = DwellingCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]LGFA 1992 s.11 — explain mode")
    all_ok = True

    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.dwelling_id,
                    period=case.period,
                    outputs=list(OUTPUTS),
                )
            ],
        )
        started = time.perf_counter()
        response = client.execute(request)
        duration = time.perf_counter() - started
        result = response.results[0]
        ok, problems = check_expected(case, result)
        all_ok = all_ok and ok
        status = (
            "[green]matches expected[/green]"
            if ok
            else "[red]differs: " + "; ".join(problems) + "[/red]"
        )

        summary = Table.grid(padding=(0, 2))
        summary.add_column(style="cyan")
        summary.add_column()
        summary.add_row(
            "non_disregarded",
            str(result.outputs["num_non_disregarded_residents"].value.value),
        )
        summary.add_row(
            "single_occupier",
            result.outputs["single_occupier_discount_applies"].outcome,
        )
        summary.add_row(
            "empty_home",
            result.outputs["empty_home_discount_applies"].outcome,
        )
        summary.add_row(
            "discount_fraction",
            str(result.outputs["discount_fraction"].value.value),
        )
        summary.add_row("duration", f"{duration:.4f}s")
        summary.add_row("check", status)
        CONSOLE.print(Panel(summary, title=case.name, expand=False, border_style="blue"))
        if args.trace:
            render_trace(case.name, result)
            CONSOLE.print()

    final = Table(title="Summary", show_header=False)
    final.add_column(style="bold cyan")
    final.add_column()
    final.add_row("Cases", str(len(case_file.cases)))
    final.add_row("All match expected", str(all_ok))
    CONSOLE.print(final)


if __name__ == "__main__":
    main()
