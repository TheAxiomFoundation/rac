#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the Housing Act 1988 s.21 notice-validity cases.

The top-level output is a statutory conclusion (`section_21_notice_valid`)
rather than a currency amount — the first non-tax-benefit demonstrator in
the repo. Each case toggles exactly one gate (deposit protection timing,
EPC, gas safety, licensing, retaliatory bar, s.21(4B) four-month minimum,
or the tenancy-form gate) to verify the cascade catches each failure
independently.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from axiom_rules import Dataset, ExecutionQuery, ExecutionRequest, AxiomRulesEngine
from axiom_rules.example_cases import coerce_period, load_case_list
from axiom_rules.loader import load_program
from axiom_rules.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

CONSOLE = Console()

Outcome = Literal["holds", "not_holds", "undetermined"]

OUTPUTS = [
    "tenancy_is_assured_shorthold",
    "deposit_protected_in_time",
    "prescribed_info_in_time",
    "no_deposit_taken",
    "deposit_requirements_met",
    "epc_requirement_met",
    "gas_safety_requirement_met",
    "how_to_rent_requirement_met",
    "licensing_requirement_met",
    "qualifying_council_notices",
    "no_retaliation_bar",
    "tenancy_age_days_at_notice",
    "not_served_too_early",
    "section_21_notice_valid",
]


class CouncilNoticeCase(BaseModel):
    id: str
    is_in_retaliation_window: bool


class ExpectedOutputs(BaseModel):
    tenancy_is_assured_shorthold: Outcome | None = None
    deposit_protected_in_time: Outcome | None = None
    prescribed_info_in_time: Outcome | None = None
    no_deposit_taken: Outcome | None = None
    deposit_requirements_met: Outcome | None = None
    epc_requirement_met: Outcome | None = None
    gas_safety_requirement_met: Outcome | None = None
    how_to_rent_requirement_met: Outcome | None = None
    licensing_requirement_met: Outcome | None = None
    qualifying_council_notices: int | None = None
    no_retaliation_bar: Outcome | None = None
    not_served_too_early: Outcome | None = None
    section_21_notice_valid: Outcome | None = None


class TenancyCase(BaseModel):
    name: str
    tenancy_id: str
    period: Period
    is_assured_shorthold: bool
    tenancy_start_date: date
    notice_served_date: date
    deposit_taken: bool
    deposit_received_date: date
    deposit_protected_date: date
    prescribed_info_given_date: date
    epc_given_before_tenancy: bool
    gas_safety_given_before_occupation: bool
    how_to_rent_guide_given: bool
    property_requires_licence: bool
    landlord_has_licence: bool
    council_notices: list[CouncilNoticeCase]
    expected: ExpectedOutputs


class TenancyCaseFile(BaseModel):
    cases: list[TenancyCase]


def load_cases(path: str | Path) -> TenancyCaseFile:
    cases = []
    for index, raw in enumerate(load_case_list(path), start=1):
        tenancy_id = raw.get("tenancy_id", f"tenancy-{index}")
        inputs = raw["input"]
        notices = [
            {
                "id": notice.get("id", f"{tenancy_id}-notice-{notice_index}"),
                "is_in_retaliation_window": notice["is_in_retaliation_window"],
            }
            for notice_index, notice in enumerate(
                inputs.get("council_notice_of_tenancy", []), start=1
            )
        ]
        cases.append(
            {
                "name": raw["name"],
                "tenancy_id": tenancy_id,
                "period": coerce_period(raw["period"]),
                "is_assured_shorthold": inputs["is_assured_shorthold"],
                "tenancy_start_date": inputs["tenancy_start_date"],
                "notice_served_date": inputs["notice_served_date"],
                "deposit_taken": inputs["deposit_taken"],
                "deposit_received_date": inputs["deposit_received_date"],
                "deposit_protected_date": inputs["deposit_protected_date"],
                "prescribed_info_given_date": inputs["prescribed_info_given_date"],
                "epc_given_before_tenancy": inputs["epc_given_before_tenancy"],
                "gas_safety_given_before_occupation": inputs[
                    "gas_safety_given_before_occupation"
                ],
                "how_to_rent_guide_given": inputs["how_to_rent_guide_given"],
                "property_requires_licence": inputs["property_requires_licence"],
                "landlord_has_licence": inputs["landlord_has_licence"],
                "council_notices": notices,
                "expected": raw["output"],
            }
        )
    return TenancyCaseFile.model_validate({"cases": cases})


def build_dataset(case: TenancyCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)

    def tenancy_bool(name: str, value: bool) -> InputRecord:
        return InputRecord(
            name=name,
            entity="Tenancy",
            entity_id=case.tenancy_id,
            interval=interval,
            value=ScalarValue(kind="bool", value=value),
        )

    def tenancy_date(name: str, value: date) -> InputRecord:
        return InputRecord(
            name=name,
            entity="Tenancy",
            entity_id=case.tenancy_id,
            interval=interval,
            value=ScalarValue(kind="date", value=value.isoformat()),
        )

    inputs: list[InputRecord] = [
        tenancy_bool("is_assured_shorthold", case.is_assured_shorthold),
        tenancy_date("tenancy_start_date", case.tenancy_start_date),
        tenancy_date("notice_served_date", case.notice_served_date),
        tenancy_bool("deposit_taken", case.deposit_taken),
        tenancy_date("deposit_received_date", case.deposit_received_date),
        tenancy_date("deposit_protected_date", case.deposit_protected_date),
        tenancy_date("prescribed_info_given_date", case.prescribed_info_given_date),
        tenancy_bool("epc_given_before_tenancy", case.epc_given_before_tenancy),
        tenancy_bool(
            "gas_safety_given_before_occupation",
            case.gas_safety_given_before_occupation,
        ),
        tenancy_bool("how_to_rent_guide_given", case.how_to_rent_guide_given),
        tenancy_bool("property_requires_licence", case.property_requires_licence),
        tenancy_bool("landlord_has_licence", case.landlord_has_licence),
    ]

    relations: list[RelationRecord] = []
    for notice in case.council_notices:
        inputs.append(
            InputRecord(
                name="is_in_retaliation_window",
                entity="CouncilNotice",
                entity_id=notice.id,
                interval=interval,
                value=ScalarValue(kind="bool", value=notice.is_in_retaliation_window),
            )
        )
        relations.append(
            RelationRecord(
                name="council_notice_of_tenancy",
                tuple=[notice.id, case.tenancy_id],
                interval=interval,
            )
        )

    return Dataset(inputs=inputs, relations=relations)


def format_value(node) -> str:
    if node.kind == "judgment":
        return node.outcome
    return str(node.value.value)


def render_trace(case_name: str, result) -> None:
    verdict = result.outputs["section_21_notice_valid"].outcome
    colour = "green" if verdict == "holds" else "red"
    tree = Tree(
        f"[bold]{case_name}[/bold] — "
        f"section_21_notice_valid = [{colour}]{verdict}[/{colour}]"
    )
    shown: set[str] = set()

    def attach(parent: Tree, name: str, depth: int = 0) -> None:
        if name in shown or depth > 6:
            return
        shown.add(name)
        node = result.trace.get(name)
        if node is None:
            return
        value = format_value(node)
        label = f"[bold cyan]{name}[/bold cyan] = {value}"
        if node.source:
            label += f" [italic dim]{node.source}[/italic dim]"
        branch = parent.add(label)
        for dep in node.dependencies:
            attach(branch, dep, depth + 1)

    attach(tree, "section_21_notice_valid")
    CONSOLE.print(tree)


def check_expected(case: TenancyCase, result) -> tuple[bool, list[str]]:
    problems: list[str] = []
    for field, expected_value in case.expected.model_dump().items():
        if expected_value is None:
            continue
        block = result.outputs.get(field)
        if block is None:
            problems.append(f"{field}: not in response")
            continue
        if field == "qualifying_council_notices":
            actual = int(block.value.value)
            if int(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        else:
            actual = block.outcome
            if str(expected_value) != actual:
                problems.append(f"{field}: expected {expected_value}, got {actual}")
    return (len(problems) == 0, problems)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "axiom-rules"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ukpga/1988/50/section/21/rules.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "ukpga/1988/50/section/21/rules.test.yaml"),
    )
    parser.add_argument("--no-trace", dest="trace", action="store_false")
    parser.set_defaults(trace=False)
    args = parser.parse_args()

    program = load_program(args.program, binary_path=args.binary)
    case_file = load_cases(args.cases)
    client = AxiomRulesEngine(binary_path=args.binary)

    CONSOLE.rule("[bold blue]Housing Act 1988 s.21 — notice validity")
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
                    entity_id=case.tenancy_id,
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
        verdict = result.outputs["section_21_notice_valid"].outcome
        colour = "green" if verdict == "holds" else "red"
        status = (
            "[green]matches expected[/green]"
            if ok
            else "[red]differs: " + "; ".join(problems) + "[/red]"
        )

        summary = Table.grid(padding=(0, 2))
        summary.add_column(style="cyan")
        summary.add_column()
        summary.add_row(
            "section_21_notice_valid", f"[{colour}]{verdict}[/{colour}]"
        )
        for name in [
            "deposit_requirements_met",
            "epc_requirement_met",
            "gas_safety_requirement_met",
            "how_to_rent_requirement_met",
            "licensing_requirement_met",
            "no_retaliation_bar",
            "not_served_too_early",
        ]:
            summary.add_row(name, result.outputs[name].outcome)
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
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
