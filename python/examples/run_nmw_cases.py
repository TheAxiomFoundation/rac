#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the NMWA 1998 s.1 NMW entitlement cases."""
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import Dataset, ExecutionQuery, ExecutionRequest, Program, RAC
from rac_api.models import InputRecord, Interval, Period, ScalarValue

CONSOLE = Console()

OUTPUTS = [
    "qualifies_for_nmw",
    "age_band_number",
    "rate_owed",
    "effective_hourly",
    "is_compliant",
    "shortfall_total",
]

Outcome = Literal["holds", "not_holds", "undetermined"]


class ExpectedOutputs(BaseModel):
    qualifies_for_nmw: Outcome | None = None
    age_band_number: int | None = None
    rate_owed: str | None = None
    effective_hourly: str | None = None
    is_compliant: Outcome | None = None
    shortfall_total: str | None = None


class WorkerCase(BaseModel):
    name: str
    worker_id: str
    period: Period
    is_worker: bool
    works_in_uk: bool
    above_compulsory_school_age: bool
    current_age_years: int
    is_apprentice_first_year: bool
    remuneration_in_prp: str
    hours_worked_in_prp: str
    expected: ExpectedOutputs


class WorkerCaseFile(BaseModel):
    cases: list[WorkerCase]


def build_dataset(case: WorkerCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    return Dataset(
        inputs=[
            InputRecord(
                name=name,
                entity="Worker",
                entity_id=case.worker_id,
                interval=interval,
                value=value,
            )
            for name, value in [
                ("is_worker", ScalarValue(kind="bool", value=case.is_worker)),
                ("works_in_uk", ScalarValue(kind="bool", value=case.works_in_uk)),
                (
                    "above_compulsory_school_age",
                    ScalarValue(kind="bool", value=case.above_compulsory_school_age),
                ),
                (
                    "current_age_years",
                    ScalarValue(kind="integer", value=case.current_age_years),
                ),
                (
                    "is_apprentice_first_year",
                    ScalarValue(kind="bool", value=case.is_apprentice_first_year),
                ),
                (
                    "remuneration_in_prp",
                    ScalarValue(kind="decimal", value=case.remuneration_in_prp),
                ),
                (
                    "hours_worked_in_prp",
                    ScalarValue(kind="decimal", value=case.hours_worked_in_prp),
                ),
            ]
        ]
    )


def check_expected(case: WorkerCase, result) -> tuple[bool, list[str]]:
    problems = []
    for field, expected_value in case.expected.model_dump().items():
        if expected_value is None:
            continue
        if field in {"qualifies_for_nmw", "is_compliant"}:
            actual = result.outputs[field].outcome
            if str(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        elif field == "age_band_number":
            actual = int(result.outputs[field].value.value)
            if int(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        else:
            actual = str(result.outputs[field].value.value)
            if Decimal(str(expected_value)) != Decimal(actual):
                problems.append(f"{field}: expected {expected_value}, got {actual}")
    return (len(problems) == 0, problems)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run NMWA 1998 s.1 cases in explain mode"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ukpga/1998/39/section/1/rules.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "ukpga/1998/39/section/1/cases.yaml"),
    )
    args = parser.parse_args()

    program = Program.model_validate(yaml.safe_load(Path(args.program).read_text()))
    case_file = WorkerCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]NMWA 1998 s.1 — explain mode")
    all_ok = True

    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.worker_id,
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
            "qualifies", result.outputs["qualifies_for_nmw"].outcome
        )
        summary.add_row(
            "rate_owed", f"£{result.outputs['rate_owed'].value.value}"
        )
        summary.add_row(
            "effective_hourly", f"£{result.outputs['effective_hourly'].value.value}"
        )
        summary.add_row("is_compliant", result.outputs["is_compliant"].outcome)
        summary.add_row(
            "shortfall_total", f"£{result.outputs['shortfall_total'].value.value}"
        )
        summary.add_row("duration", f"{duration:.4f}s")
        summary.add_row("check", status)
        CONSOLE.print(Panel(summary, title=case.name, expand=False, border_style="blue"))

    final = Table(title="Summary", show_header=False)
    final.add_column(style="bold cyan")
    final.add_column()
    final.add_row("Cases", str(len(case_file.cases)))
    final.add_row("All match expected", str(all_ok))
    CONSOLE.print(final)


if __name__ == "__main__":
    main()
