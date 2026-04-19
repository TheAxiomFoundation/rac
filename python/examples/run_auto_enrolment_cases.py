#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the Pensions Act 2008 s.3 auto-enrolment duty cases."""
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
from rac_api.models import InputRecord, Interval, Period, ScalarValue

CONSOLE = Console()

OUTPUTS = [
    "earnings_trigger_for_prp",
    "age_at_least_22",
    "below_pensionable_age",
    "earnings_above_trigger",
    "not_already_active_member",
    "not_recently_opted_out",
    "employer_enrolment_duty",
]

Outcome = Literal["holds", "not_holds", "undetermined"]


class ExpectedOutputs(BaseModel):
    earnings_trigger_for_prp: str | None = None
    age_at_least_22: Outcome | None = None
    below_pensionable_age: Outcome | None = None
    earnings_above_trigger: Outcome | None = None
    not_already_active_member: Outcome | None = None
    not_recently_opted_out: Outcome | None = None
    employer_enrolment_duty: Outcome | None = None


class JobholderCase(BaseModel):
    name: str
    jobholder_id: str
    period: Period
    current_age_years: int
    pensionable_age_years: int
    earnings_this_prp: str
    prp_months: str
    active_member_of_qualifying_scheme: bool
    recently_opted_out: bool
    expected: ExpectedOutputs


class JobholderCaseFile(BaseModel):
    cases: list[JobholderCase]


def build_dataset(case: JobholderCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    return Dataset(
        inputs=[
            InputRecord(
                name="current_age_years",
                entity="Jobholder",
                entity_id=case.jobholder_id,
                interval=interval,
                value=ScalarValue(kind="integer", value=case.current_age_years),
            ),
            InputRecord(
                name="pensionable_age_years",
                entity="Jobholder",
                entity_id=case.jobholder_id,
                interval=interval,
                value=ScalarValue(kind="integer", value=case.pensionable_age_years),
            ),
            InputRecord(
                name="earnings_this_prp",
                entity="Jobholder",
                entity_id=case.jobholder_id,
                interval=interval,
                value=ScalarValue(kind="decimal", value=case.earnings_this_prp),
            ),
            InputRecord(
                name="prp_months",
                entity="Jobholder",
                entity_id=case.jobholder_id,
                interval=interval,
                value=ScalarValue(kind="decimal", value=case.prp_months),
            ),
            InputRecord(
                name="active_member_of_qualifying_scheme",
                entity="Jobholder",
                entity_id=case.jobholder_id,
                interval=interval,
                value=ScalarValue(
                    kind="bool", value=case.active_member_of_qualifying_scheme
                ),
            ),
            InputRecord(
                name="recently_opted_out",
                entity="Jobholder",
                entity_id=case.jobholder_id,
                interval=interval,
                value=ScalarValue(kind="bool", value=case.recently_opted_out),
            ),
        ]
    )


def render_trace(case_name: str, result) -> None:
    tree = Tree(
        f"[bold]{case_name}[/bold] — duty = "
        f"{result.outputs['employer_enrolment_duty'].outcome}"
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

    attach(tree, "employer_enrolment_duty")
    CONSOLE.print(tree)


def check_expected(case: JobholderCase, result) -> tuple[bool, list[str]]:
    problems = []
    for field, expected_value in case.expected.model_dump().items():
        if expected_value is None:
            continue
        if field == "earnings_trigger_for_prp":
            actual = str(result.outputs[field].value.value)
            if Decimal(str(expected_value)) != Decimal(actual):
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        else:
            actual = result.outputs[field].outcome
            if str(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
    return (len(problems) == 0, problems)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Pensions Act 2008 s.3 cases in explain mode"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ukpga/2008/30/section/3/rules.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "ukpga/2008/30/section/3/cases.yaml"),
    )
    parser.add_argument(
        "--no-trace",
        dest="trace",
        action="store_false",
    )
    parser.set_defaults(trace=True)
    args = parser.parse_args()

    program = Program.model_validate(yaml.safe_load(Path(args.program).read_text()))
    case_file = JobholderCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]Pensions Act 2008 s.3 — explain mode")
    all_ok = True

    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.jobholder_id,
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
            "trigger", f"£{result.outputs['earnings_trigger_for_prp'].value.value}"
        )
        summary.add_row("duty", result.outputs["employer_enrolment_duty"].outcome)
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
