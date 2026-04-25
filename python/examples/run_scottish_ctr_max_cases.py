#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the SSI 2021/249 reg 79 Scottish CTR daily maximum cases."""
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

from axiom_rules import Dataset, ExecutionQuery, ExecutionRequest, AxiomRulesEngine
from axiom_rules.loader import load_program
from axiom_rules.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

CONSOLE = Console()

OUTPUTS = [
    "days_in_fy",
    "num_non_student_liable",
    "a_raw",
    "liable_divisor",
    "a_effective",
    "is_band_e_to_h",
    "a_after_taper",
    "daily_max_reduction",
]


Outcome = Literal["holds", "not_holds", "undetermined"]


class LiablePerson(BaseModel):
    id: str
    is_student: bool


class ExpectedOutputs(BaseModel):
    days_in_fy: int | None = None
    num_non_student_liable: int | None = None
    a_raw: str | None = None
    liable_divisor: int | None = None
    a_effective: str | None = None
    is_band_e_to_h: Outcome | None = None
    a_after_taper: str | None = None
    daily_max_reduction: str | None = None


class DwellingCase(BaseModel):
    name: str
    dwelling_id: str
    period: Period
    ct_annual: str
    ct_discounts: str
    ct_other_reductions: str
    band_number: int
    non_dep_deductions_daily: str
    partner_only_joint: bool
    liable_persons: list[LiablePerson]
    expected: ExpectedOutputs


class DwellingCaseFile(BaseModel):
    cases: list[DwellingCase]


def build_dataset(case: DwellingCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    inputs = [
        InputRecord(
            name="ct_annual",
            entity="Dwelling",
            entity_id=case.dwelling_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.ct_annual),
        ),
        InputRecord(
            name="ct_discounts",
            entity="Dwelling",
            entity_id=case.dwelling_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.ct_discounts),
        ),
        InputRecord(
            name="ct_other_reductions",
            entity="Dwelling",
            entity_id=case.dwelling_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.ct_other_reductions),
        ),
        InputRecord(
            name="band_number",
            entity="Dwelling",
            entity_id=case.dwelling_id,
            interval=interval,
            value=ScalarValue(kind="integer", value=case.band_number),
        ),
        InputRecord(
            name="non_dep_deductions_daily",
            entity="Dwelling",
            entity_id=case.dwelling_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.non_dep_deductions_daily),
        ),
        InputRecord(
            name="partner_only_joint",
            entity="Dwelling",
            entity_id=case.dwelling_id,
            interval=interval,
            value=ScalarValue(kind="bool", value=case.partner_only_joint),
        ),
    ]
    relations = []
    for person in case.liable_persons:
        inputs.append(
            InputRecord(
                name="is_not_student",
                entity="Person",
                entity_id=person.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=not person.is_student),
            )
        )
        relations.append(
            RelationRecord(
                name="liable_person",
                tuple=[person.id, case.dwelling_id],
                interval=interval,
            )
        )
    return Dataset(inputs=inputs, relations=relations)


def render_trace(case_name: str, result) -> None:
    tree = Tree(
        f"[bold]{case_name}[/bold] — daily_max = "
        f"£{result.outputs['daily_max_reduction'].value.value}"
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

    attach(tree, "daily_max_reduction")
    CONSOLE.print(tree)


def check_expected(case: DwellingCase, result) -> tuple[bool, list[str]]:
    problems = []
    for field, expected_value in case.expected.model_dump().items():
        if expected_value is None:
            continue
        if field == "is_band_e_to_h":
            actual = result.outputs[field].outcome
            if str(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        else:
            actual = result.outputs[field].value.value
            if field in {"days_in_fy", "num_non_student_liable", "liable_divisor"}:
                if int(expected_value) != int(actual):
                    problems.append(f"{field}: expected {expected_value}, got {actual}")
            else:
                if Decimal(str(expected_value)) != Decimal(str(actual)):
                    problems.append(f"{field}: expected {expected_value}, got {actual}")
    return (len(problems) == 0, problems)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run SSI 2021/249 reg 79 Scottish CTR daily max cases"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "axiom-rules"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ssi/2021/249/regulation/79/rules.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "ssi/2021/249/regulation/79/cases.yaml"),
    )
    parser.add_argument(
        "--no-trace",
        dest="trace",
        action="store_false",
    )
    parser.set_defaults(trace=True)
    args = parser.parse_args()

    program = load_program(args.program, binary_path=args.binary)
    case_file = DwellingCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = AxiomRulesEngine(binary_path=args.binary)

    CONSOLE.rule("[bold blue]SSI 2021/249 reg 79 — explain mode")
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
        summary.add_row("days_in_fy", str(result.outputs["days_in_fy"].value.value))
        summary.add_row("a_raw", f"£{result.outputs['a_raw'].value.value}")
        summary.add_row(
            "liable_divisor", str(result.outputs["liable_divisor"].value.value)
        )
        summary.add_row(
            "band_e_to_h", result.outputs["is_band_e_to_h"].outcome
        )
        summary.add_row(
            "daily_max_reduction",
            f"£{result.outputs['daily_max_reduction'].value.value}",
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
