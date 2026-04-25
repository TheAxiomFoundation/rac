#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the FA 2013 s.99 ATED cases."""
from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import Dataset, ExecutionQuery, ExecutionRequest, RAC
from rac_api.loader import load_program
from rac_api.models import InputRecord, Interval, Period, ScalarValue

CONSOLE = Console()

OUTPUTS = [
    "band_number",
    "annual_chargeable_amount",
    "days_in_period",
    "days_from_entry",
    "tax_chargeable",
]


class ExpectedOutputs(BaseModel):
    band_number: int | None = None
    annual_chargeable_amount: str | None = None
    days_in_period: int | None = None
    days_from_entry: int | None = None
    tax_chargeable: str | None = None


class InterestCase(BaseModel):
    name: str
    interest_id: str
    period: Period
    taxable_value: str
    in_charge_on_first_day: bool
    entry_day: str
    expected: ExpectedOutputs


class InterestCaseFile(BaseModel):
    cases: list[InterestCase]


def build_dataset(case: InterestCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    return Dataset(
        inputs=[
            InputRecord(
                name="taxable_value",
                entity="DwellingInterest",
                entity_id=case.interest_id,
                interval=interval,
                value=ScalarValue(kind="decimal", value=case.taxable_value),
            ),
            InputRecord(
                name="in_charge_on_first_day",
                entity="DwellingInterest",
                entity_id=case.interest_id,
                interval=interval,
                value=ScalarValue(kind="bool", value=case.in_charge_on_first_day),
            ),
            InputRecord(
                name="entry_day",
                entity="DwellingInterest",
                entity_id=case.interest_id,
                interval=interval,
                value=ScalarValue(kind="date", value=case.entry_day),
            ),
        ]
    )


def render_trace(case_name: str, result) -> None:
    tree = Tree(
        f"[bold]{case_name}[/bold] — tax_chargeable = "
        f"£{result.outputs['tax_chargeable'].value.value}"
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

    attach(tree, "tax_chargeable")
    CONSOLE.print(tree)


def check_expected(case: InterestCase, result) -> tuple[bool, list[str]]:
    problems = []
    for field, expected_value in case.expected.model_dump().items():
        if expected_value is None:
            continue
        actual = result.outputs[field].value.value
        if field in {"band_number", "days_in_period", "days_from_entry"}:
            if int(expected_value) != int(actual):
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        else:
            if Decimal(str(expected_value)) != Decimal(str(actual)):
                problems.append(f"{field}: expected {expected_value}, got {actual}")
    return (len(problems) == 0, problems)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run FA 2013 s.99 ATED cases in explain mode"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ukpga/2013/29/section/99/rules.rac"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "ukpga/2013/29/section/99/cases.yaml"),
    )
    parser.add_argument(
        "--no-trace",
        dest="trace",
        action="store_false",
        help="Suppress the legislation trace tree (shown by default)",
    )
    parser.set_defaults(trace=True)
    args = parser.parse_args()

    program = load_program(args.program, binary_path=args.binary)
    case_file = InterestCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]FA 2013 s.99 ATED — explain mode")
    all_ok = True

    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.interest_id,
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
        summary.add_row("band_number", str(result.outputs["band_number"].value.value))
        summary.add_row(
            "annual_amount",
            f"£{result.outputs['annual_chargeable_amount'].value.value}",
        )
        summary.add_row(
            "days_in_period", str(result.outputs["days_in_period"].value.value)
        )
        summary.add_row(
            "days_from_entry", str(result.outputs["days_from_entry"].value.value)
        )
        summary.add_row(
            "tax_chargeable",
            f"£{result.outputs['tax_chargeable'].value.value}",
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
