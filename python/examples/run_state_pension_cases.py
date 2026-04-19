#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the Pensions Act 2014 s.4 transitional state pension cases."""
from __future__ import annotations

import argparse
import sys
import time
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
    "pre_commencement_qy_count",
    "post_commencement_qy_count",
    "total_qy_count",
    "reached_pensionable_age",
    "meets_minimum_qy",
    "has_any_pre_commencement_year",
    "entitled_to_transitional_rate",
]


class QualifyingYear(BaseModel):
    id: str
    year_start: str
    is_qualifying: bool
    is_reckonable_1979: bool


class ExpectedOutputs(BaseModel):
    pre_commencement_qy_count: int | None = None
    post_commencement_qy_count: int | None = None
    total_qy_count: int | None = None
    reached_pensionable_age: Literal["holds", "not_holds", "undetermined"] | None = None
    meets_minimum_qy: Literal["holds", "not_holds", "undetermined"] | None = None
    has_any_pre_commencement_year: Literal[
        "holds", "not_holds", "undetermined"
    ] | None = None
    entitled_to_transitional_rate: Literal[
        "holds", "not_holds", "undetermined"
    ] | None = None


class PersonCase(BaseModel):
    name: str
    person_id: str
    period: Period
    current_age_years: int
    pensionable_age_years: int
    qualifying_years: list[QualifyingYear]
    expected: ExpectedOutputs


class PersonCaseFile(BaseModel):
    cases: list[PersonCase]


def build_dataset(case: PersonCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    inputs = [
        InputRecord(
            name="current_age_years",
            entity="Person",
            entity_id=case.person_id,
            interval=interval,
            value=ScalarValue(kind="integer", value=case.current_age_years),
        ),
        InputRecord(
            name="pensionable_age_years",
            entity="Person",
            entity_id=case.person_id,
            interval=interval,
            value=ScalarValue(kind="integer", value=case.pensionable_age_years),
        ),
    ]
    relations = []
    for qy in case.qualifying_years:
        inputs.extend([
            InputRecord(
                name="year_start",
                entity="QualifyingYear",
                entity_id=qy.id,
                interval=interval,
                value=ScalarValue(kind="date", value=qy.year_start),
            ),
            InputRecord(
                name="is_qualifying",
                entity="QualifyingYear",
                entity_id=qy.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=qy.is_qualifying),
            ),
            InputRecord(
                name="is_reckonable_1979",
                entity="QualifyingYear",
                entity_id=qy.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=qy.is_reckonable_1979),
            ),
        ])
        relations.append(
            RelationRecord(
                name="qualifying_year_of",
                tuple=[qy.id, case.person_id],
                interval=interval,
            )
        )
    return Dataset(inputs=inputs, relations=relations)


def render_trace(case_name: str, result) -> None:
    tree = Tree(
        f"[bold]{case_name}[/bold] — entitled = "
        f"{result.outputs['entitled_to_transitional_rate'].outcome}"
    )
    shown: set[str] = set()

    def attach(parent: Tree, name: str, depth: int = 0) -> None:
        if name in shown or depth > 6:
            return
        shown.add(name)
        node = result.trace.get(name)
        if node is None:
            return
        if node.kind == "scalar":
            value = node.value.value
        else:
            value = node.outcome
        label = f"[bold cyan]{name}[/bold cyan] = {value}"
        if node.unit:
            label += f" [dim]{node.unit}[/dim]"
        if node.source:
            label += f" [italic]{node.source}[/italic]"
        branch = parent.add(label)
        for dep in node.dependencies:
            attach(branch, dep, depth + 1)

    attach(tree, "entitled_to_transitional_rate")
    CONSOLE.print(tree)


def check_expected(case: PersonCase, result) -> tuple[bool, list[str]]:
    problems = []
    for field, expected_value in case.expected.model_dump().items():
        if expected_value is None:
            continue
        if field.endswith("_count"):
            actual = int(result.outputs[field].value.value)
            if int(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        else:
            actual = result.outputs[field].outcome
            if str(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
    return (len(problems) == 0, problems)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Pensions Act 2014 s.4 cases in explain mode with legislation trace"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ukpga/2014/19/section/4/rules.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "ukpga/2014/19/section/4/cases.yaml"),
    )
    parser.add_argument(
        "--no-trace",
        dest="trace",
        action="store_false",
        help="Suppress the legislation trace tree (shown by default)",
    )
    parser.set_defaults(trace=True)
    args = parser.parse_args()

    program = Program.model_validate(yaml.safe_load(Path(args.program).read_text()))
    case_file = PersonCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]Pensions Act 2014 s.4 — explain mode")
    all_ok = True
    total_started = time.perf_counter()

    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.person_id,
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
            "pre_commencement_qy",
            str(result.outputs["pre_commencement_qy_count"].value.value),
        )
        summary.add_row(
            "post_commencement_qy",
            str(result.outputs["post_commencement_qy_count"].value.value),
        )
        summary.add_row(
            "total_qy", str(result.outputs["total_qy_count"].value.value)
        )
        summary.add_row(
            "reached_pensionable_age",
            result.outputs["reached_pensionable_age"].outcome,
        )
        summary.add_row(
            "meets_minimum_qy", result.outputs["meets_minimum_qy"].outcome
        )
        summary.add_row(
            "has_pre_commencement",
            result.outputs["has_any_pre_commencement_year"].outcome,
        )
        summary.add_row(
            "entitled_transitional",
            result.outputs["entitled_to_transitional_rate"].outcome,
        )
        summary.add_row("duration", f"{duration:.4f}s")
        summary.add_row("check", status)

        CONSOLE.print(Panel(summary, title=case.name, expand=False, border_style="blue"))
        if args.trace:
            render_trace(case.name, result)
            CONSOLE.print()

    total = time.perf_counter() - total_started
    final = Table(title="Summary", show_header=False)
    final.add_column(style="bold cyan")
    final.add_column()
    final.add_row("Cases", str(len(case_file.cases)))
    final.add_row("All match expected", str(all_ok))
    final.add_row("Total duration", f"{total:.4f}s")
    CONSOLE.print(final)


if __name__ == "__main__":
    main()
