#!/usr/bin/env python3
# ruff: noqa: E402
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from axiom_rules import Dataset, ExecutionQuery, ExecutionRequest, AxiomRulesEngine
from axiom_rules.loader import load_program
from axiom_rules.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

CONSOLE = Console()


class HouseholdMemberCase(BaseModel):
    person_id: str
    earned_income: str
    unearned_income: str


class ExpectedOutputs(BaseModel):
    household_size: int
    gross_income: str
    net_income: str
    passes_gross_income_test: Literal["holds", "not_holds", "undetermined"]
    passes_net_income_test: Literal["holds", "not_holds", "undetermined"]
    snap_eligible: Literal["holds", "not_holds", "undetermined"]
    snap_allotment: str


class SnapCase(BaseModel):
    name: str
    household_id: str
    period: Period
    members: list[HouseholdMemberCase]
    dependent_care_deduction: str
    child_support_deduction: str
    medical_deduction: str
    shelter_costs: str
    has_elderly_or_disabled_member: bool
    expected: ExpectedOutputs


class SnapCaseFile(BaseModel):
    cases: list[SnapCase]


def build_dataset(case: SnapCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    inputs = [
        InputRecord(
            name="dependent_care_deduction",
            entity="Household",
            entity_id=case.household_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.dependent_care_deduction),
        ),
        InputRecord(
            name="child_support_deduction",
            entity="Household",
            entity_id=case.household_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.child_support_deduction),
        ),
        InputRecord(
            name="medical_deduction",
            entity="Household",
            entity_id=case.household_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.medical_deduction),
        ),
        InputRecord(
            name="shelter_costs",
            entity="Household",
            entity_id=case.household_id,
            interval=interval,
            value=ScalarValue(kind="decimal", value=case.shelter_costs),
        ),
        InputRecord(
            name="has_elderly_or_disabled_member",
            entity="Household",
            entity_id=case.household_id,
            interval=interval,
            value=ScalarValue(kind="bool", value=case.has_elderly_or_disabled_member),
        ),
    ]
    relations: list[RelationRecord] = []

    for member in case.members:
        inputs.extend(
            [
                InputRecord(
                    name="earned_income",
                    entity="Person",
                    entity_id=member.person_id,
                    interval=interval,
                    value=ScalarValue(kind="decimal", value=member.earned_income),
                ),
                InputRecord(
                    name="unearned_income",
                    entity="Person",
                    entity_id=member.person_id,
                    interval=interval,
                    value=ScalarValue(kind="decimal", value=member.unearned_income),
                ),
            ]
        )
        relations.append(
            RelationRecord(
                name="member_of_household",
                tuple=[member.person_id, case.household_id],
                interval=interval,
            )
        )

    return Dataset(inputs=inputs, relations=relations)


def print_case_result(case: SnapCase, result, *, build_duration: float, execution_duration: float) -> None:
    outputs = result.outputs
    household_size = outputs["household_size"].value.value
    gross_income = outputs["gross_income"].value.value
    net_income = outputs["net_income"].value.value
    gross_test = outputs["passes_gross_income_test"].outcome
    net_test = outputs["passes_net_income_test"].outcome
    eligible = outputs["snap_eligible"].outcome
    allotment = outputs["snap_allotment"].value.value
    expected_ok = (
        str(household_size) == str(case.expected.household_size)
        and str(gross_income) == case.expected.gross_income
        and str(net_income) == case.expected.net_income
        and gross_test == case.expected.passes_gross_income_test
        and net_test == case.expected.passes_net_income_test
        and eligible == case.expected.snap_eligible
        and str(allotment) == case.expected.snap_allotment
    )
    status = "matches expected" if expected_ok else "differs from expected"

    timing = Table.grid(padding=(0, 2))
    timing.add_column(style="cyan")
    timing.add_column(style="white")
    timing.add_row("Engine path", "requested=explain actual=explain")
    timing.add_row("Build", f"{build_duration:.4f}s")
    timing.add_row("Execute", f"{execution_duration:.4f}s")

    outputs_table = Table(box=None, show_header=False, pad_edge=False)
    outputs_table.add_column(style="bold")
    outputs_table.add_column()
    outputs_table.add_row("Household size", str(household_size))
    outputs_table.add_row("Gross income", f"{gross_income} USD")
    outputs_table.add_row("Net income", f"{net_income} USD")
    outputs_table.add_row("Passes gross income test", gross_test)
    outputs_table.add_row("Passes net income test", net_test)
    outputs_table.add_row("SNAP eligible", eligible)
    outputs_table.add_row("SNAP allotment", f"{allotment} USD")
    outputs_table.add_row("Expected check", status)

    CONSOLE.print(Panel(timing, title=case.name, expand=False, border_style="blue"))
    CONSOLE.print(outputs_table)
    CONSOLE.print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the SNAP prototype cases through the Axiom Rules Engine (`axiom-rules`) executable in explain mode"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "axiom-rules"),
        help="Path to the compiled Axiom Rules Engine (`axiom-rules`) executable",
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "other/snap/rules.rac"),
        help="Path to the SNAP law YAML document",
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "other/snap/cases.yaml"),
        help="Path to the SNAP example cases YAML document",
    )
    args = parser.parse_args()

    program = load_program(args.program, binary_path=args.binary)
    case_file = SnapCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = AxiomRulesEngine(binary_path=args.binary)

    CONSOLE.rule("[bold blue]SNAP explain mode")
    total_build_duration = 0.0
    total_execution_duration = 0.0
    total_started = time.perf_counter()

    for case in case_file.cases:
        build_started = time.perf_counter()
        dataset = build_dataset(case)
        build_duration = time.perf_counter() - build_started
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.household_id,
                    period=case.period,
                    outputs=[
                        "household_size",
                        "gross_income",
                        "net_income",
                        "passes_gross_income_test",
                        "passes_net_income_test",
                        "snap_eligible",
                        "snap_allotment",
                    ],
                )
            ],
        )
        execution_started = time.perf_counter()
        response = client.execute(request)
        execution_duration = time.perf_counter() - execution_started
        total_build_duration += build_duration
        total_execution_duration += execution_duration
        print_case_result(
            case,
            response.results[0],
            build_duration=build_duration,
            execution_duration=execution_duration,
        )

    total_duration = time.perf_counter() - total_started
    summary = Table(title="Summary", show_header=False)
    summary.add_column(style="bold cyan")
    summary.add_column()
    summary.add_row("Cases", str(len(case_file.cases)))
    summary.add_row("Total duration", f"{total_duration:.4f}s")
    summary.add_row("Total build duration", f"{total_build_duration:.4f}s")
    summary.add_row("Total execution duration", f"{total_execution_duration:.4f}s")
    CONSOLE.print(summary)


if __name__ == "__main__":
    main()
