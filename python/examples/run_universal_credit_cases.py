#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the Universal Credit cases in explain mode and render the legislation trace."""
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


class AdultCase(BaseModel):
    id: str
    age_25_or_over: bool
    has_lcwra: bool
    is_carer: bool


class ChildCase(BaseModel):
    id: str
    qualifies_for_child_element: bool
    is_higher_rate_first_child: bool = False
    disability_level: Literal["none", "lower", "higher"]


class ExpectedOutputs(BaseModel):
    standard_allowance: str | None = None
    child_element_total: str | None = None
    disabled_child_element_total: str | None = None
    lcwra_element: str | None = None
    carer_element: str | None = None
    housing_element: str | None = None
    max_uc: str | None = None
    work_allowance_amount: str | None = None
    earnings_deduction: str | None = None
    tariff_income: str | None = None
    over_capital_limit: Literal["holds", "not_holds", "undetermined"] | None = None
    uc_award: str | None = None


class BenefitUnitCase(BaseModel):
    name: str
    benefit_unit_id: str
    period: Period
    is_couple: bool
    has_housing_costs: bool
    eligible_housing_costs: str
    non_dep_deductions_total: str
    earned_income_monthly: str
    unearned_income_monthly: str
    capital_total: str
    adults: list[AdultCase]
    children: list[ChildCase]
    expected: ExpectedOutputs


class BenefitUnitCaseFile(BaseModel):
    cases: list[BenefitUnitCase]


def build_dataset(case: BenefitUnitCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)

    def bu_text(name: str, value: str) -> InputRecord:
        return InputRecord(
            name=name,
            entity="BenefitUnit",
            entity_id=case.benefit_unit_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=value),
        )

    def bu_bool(name: str, value: bool) -> InputRecord:
        return InputRecord(
            name=name,
            entity="BenefitUnit",
            entity_id=case.benefit_unit_id,
            interval=interval,
            value=ScalarValue(kind="bool", value=value),
        )

    inputs = [
        bu_bool("is_couple", case.is_couple),
        bu_bool("has_housing_costs", case.has_housing_costs),
        bu_text("eligible_housing_costs", case.eligible_housing_costs),
        bu_text("non_dep_deductions_total", case.non_dep_deductions_total),
        bu_text("earned_income_monthly", case.earned_income_monthly),
        bu_text("unearned_income_monthly", case.unearned_income_monthly),
        bu_text("capital_total", case.capital_total),
    ]

    relations: list[RelationRecord] = []
    for adult in case.adults:
        inputs.extend([
            InputRecord(
                name="age_25_or_over",
                entity="Adult",
                entity_id=adult.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=adult.age_25_or_over),
            ),
            InputRecord(
                name="has_lcwra",
                entity="Adult",
                entity_id=adult.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=adult.has_lcwra),
            ),
            InputRecord(
                name="is_carer",
                entity="Adult",
                entity_id=adult.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=adult.is_carer),
            ),
        ])
        relations.append(
            RelationRecord(
                name="adult_of_benefit_unit",
                tuple=[adult.id, case.benefit_unit_id],
                interval=interval,
            )
        )

    for child in case.children:
        inputs.extend([
            InputRecord(
                name="qualifies_for_child_element",
                entity="Child",
                entity_id=child.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=child.qualifies_for_child_element),
            ),
            InputRecord(
                name="is_higher_rate_first_child",
                entity="Child",
                entity_id=child.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=child.is_higher_rate_first_child),
            ),
            InputRecord(
                name="disability_level",
                entity="Child",
                entity_id=child.id,
                interval=interval,
                value=ScalarValue(kind="text", value=child.disability_level),
            ),
        ])
        relations.append(
            RelationRecord(
                name="child_of_benefit_unit",
                tuple=[child.id, case.benefit_unit_id],
                interval=interval,
            )
        )

    return Dataset(inputs=inputs, relations=relations)


def format_value(node) -> str:
    if node.kind == "scalar":
        return f"{node.value.value}"
    return node.outcome


def format_unit(node) -> str:
    return node.unit or ""


def render_trace(case_name: str, result) -> None:
    tree = Tree(
        f"[bold]{case_name}[/bold] — uc_award = "
        f"£{result.outputs['uc_award'].value.value}"
    )

    # Build a set of already-rendered nodes to avoid duplicating a sub-tree
    # when two top-level outputs share dependencies.
    shown: set[str] = set()

    def attach(parent: Tree, name: str, depth: int = 0) -> None:
        if name in shown or depth > 8:
            return
        shown.add(name)
        node = result.trace.get(name)
        if node is None:
            return
        label_bits = [f"[bold cyan]{name}[/bold cyan]"]
        label_bits.append(f"= {format_value(node)}")
        unit = format_unit(node)
        if unit:
            label_bits.append(f"[dim]{unit}[/dim]")
        if node.source:
            label_bits.append(f"[italic]{node.source}[/italic]")
        branch = parent.add(" ".join(label_bits))
        for dep in node.dependencies:
            attach(branch, dep, depth + 1)

    for output_name in [
        "uc_award",
        "uc_award_before_capital_test",
        "max_uc",
        "earnings_deduction",
        "tariff_income",
        "over_capital_limit",
    ]:
        if output_name in result.trace:
            attach(tree, output_name)

    CONSOLE.print(tree)


def check_expected(case: BenefitUnitCase, result) -> tuple[bool, list[str]]:
    problems = []
    expected = case.expected
    for field, expected_value in expected.model_dump().items():
        if expected_value is None:
            continue
        if field == "over_capital_limit":
            actual = result.outputs[field].outcome
            if str(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        else:
            actual = str(result.outputs[field].value.value)
            if Decimal(str(expected_value)) != Decimal(actual):
                problems.append(f"{field}: expected {expected_value}, got {actual}")
    return (len(problems) == 0, problems)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Universal Credit prototype cases in explain mode with legislation trace"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
        help="Path to the compiled rac executable",
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "examples" / "universal_credit_program.yaml"),
        help="Path to the UC programme YAML",
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "examples" / "universal_credit_cases.yaml"),
        help="Path to the UC cases YAML",
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
    case_file = BenefitUnitCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]Universal Credit 2025-26 — explain mode")
    total_started = time.perf_counter()
    all_ok = True

    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.benefit_unit_id,
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
        summary.add_row("uc_award", f"£{result.outputs['uc_award'].value.value}")
        summary.add_row("standard_allowance", f"£{result.outputs['standard_allowance'].value.value}")
        summary.add_row("child_element_total", f"£{result.outputs['child_element_total'].value.value}")
        summary.add_row("housing_element", f"£{result.outputs['housing_element'].value.value}")
        summary.add_row("lcwra_element", f"£{result.outputs['lcwra_element'].value.value}")
        summary.add_row("earnings_deduction", f"£{result.outputs['earnings_deduction'].value.value}")
        summary.add_row("tariff_income", f"£{result.outputs['tariff_income'].value.value}")
        summary.add_row("over_capital_limit", result.outputs['over_capital_limit'].outcome)
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
