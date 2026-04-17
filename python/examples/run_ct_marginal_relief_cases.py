#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the CTA 2010 s.18B marginal-relief cases."""
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
    "ap_days",
    "num_associates",
    "associates_divisor",
    "lower_limit_effective",
    "upper_limit_effective",
    "within_marginal_band",
    "eligible_for_marginal_relief",
    "marginal_relief",
    "gross_corporation_tax",
    "corporation_tax_after_relief",
]


class ExpectedOutputs(BaseModel):
    ap_days: int | None = None
    num_associates: int | None = None
    associates_divisor: int | None = None
    lower_limit_effective: str | None = None
    upper_limit_effective: str | None = None
    within_marginal_band: Literal["holds", "not_holds", "undetermined"] | None = None
    eligible_for_marginal_relief: Literal[
        "holds", "not_holds", "undetermined"
    ] | None = None
    marginal_relief: str | None = None
    gross_corporation_tax: str | None = None
    corporation_tax_after_relief: str | None = None


class CompanyCase(BaseModel):
    name: str
    company_id: str
    period: Period
    uk_resident: bool
    close_investment_holding: bool
    augmented_profits: str
    taxable_total_profits: str
    ring_fence_profits: str
    associates: list[str]
    expected: ExpectedOutputs


class CompanyCaseFile(BaseModel):
    cases: list[CompanyCase]


def build_dataset(case: CompanyCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    inputs = [
        InputRecord(
            name="uk_resident",
            entity="Company",
            entity_id=case.company_id,
            interval=interval,
            value=ScalarValue(kind="bool", value=case.uk_resident),
        ),
        InputRecord(
            name="close_investment_holding",
            entity="Company",
            entity_id=case.company_id,
            interval=interval,
            value=ScalarValue(kind="bool", value=case.close_investment_holding),
        ),
        InputRecord(
            name="augmented_profits",
            entity="Company",
            entity_id=case.company_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.augmented_profits),
        ),
        InputRecord(
            name="taxable_total_profits",
            entity="Company",
            entity_id=case.company_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.taxable_total_profits),
        ),
        InputRecord(
            name="ring_fence_profits",
            entity="Company",
            entity_id=case.company_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.ring_fence_profits),
        ),
    ]
    relations = [
        RelationRecord(
            name="associate_of",
            tuple=[aid, case.company_id],
            interval=interval,
        )
        for aid in case.associates
    ]
    return Dataset(inputs=inputs, relations=relations)


def render_trace(case_name: str, result) -> None:
    tree = Tree(
        f"[bold]{case_name}[/bold] — ct_after_relief = "
        f"£{result.outputs['corporation_tax_after_relief'].value.value}"
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

    attach(tree, "corporation_tax_after_relief")
    CONSOLE.print(tree)


def check_expected(case: CompanyCase, result) -> tuple[bool, list[str]]:
    problems = []
    for field, expected_value in case.expected.model_dump().items():
        if expected_value is None:
            continue
        if field in {"within_marginal_band", "eligible_for_marginal_relief"}:
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
        description="Run CTA 2010 s.18B marginal-relief cases in explain mode"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "examples" / "ct_marginal_relief_program.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "examples" / "ct_marginal_relief_cases.yaml"),
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
    case_file = CompanyCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]CTA 2010 s.18B — explain mode")
    all_ok = True

    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.company_id,
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
        summary.add_row("ap_days", str(result.outputs["ap_days"].value.value))
        summary.add_row(
            "associates", str(result.outputs["num_associates"].value.value)
        )
        summary.add_row(
            "L_eff", f"£{result.outputs['lower_limit_effective'].value.value}"
        )
        summary.add_row(
            "U_eff", f"£{result.outputs['upper_limit_effective'].value.value}"
        )
        summary.add_row(
            "eligible",
            result.outputs["eligible_for_marginal_relief"].outcome,
        )
        summary.add_row(
            "marginal_relief",
            f"£{result.outputs['marginal_relief'].value.value}",
        )
        summary.add_row(
            "ct_after_relief",
            f"£{result.outputs['corporation_tax_after_relief'].value.value}",
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
