#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import sys
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
from rac_api.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

CONSOLE = Console()


class MemberCase(BaseModel):
    person_id: str
    age: int


class ExpectedOutputs(BaseModel):
    basic_std_ded_amount: str
    num_aged_members: int
    additional_std_ded_amount: str
    standard_deduction: str


class StandardDeductionCase(BaseModel):
    name: str
    tax_unit_id: str
    period: Period
    filing_status: int
    members: list[MemberCase]
    expected: ExpectedOutputs


class CaseFile(BaseModel):
    cases: list[StandardDeductionCase]


def build_dataset(case: StandardDeductionCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    inputs: list[InputRecord] = [
        InputRecord(
            name="filing_status",
            entity="TaxUnit",
            entity_id=case.tax_unit_id,
            interval=interval,
            value=ScalarValue(kind="integer", value=case.filing_status),
        ),
    ]
    relations: list[RelationRecord] = []
    for member in case.members:
        inputs.append(
            InputRecord(
                name="age",
                entity="Person",
                entity_id=member.person_id,
                interval=interval,
                value=ScalarValue(kind="integer", value=member.age),
            )
        )
        relations.append(
            RelationRecord(
                name="member_of_tax_unit",
                tuple=[member.person_id, case.tax_unit_id],
                interval=interval,
            )
        )
    return Dataset(inputs=inputs, relations=relations)


def print_case(case: StandardDeductionCase, result) -> bool:
    outputs = result.outputs
    basic = str(outputs["basic_std_ded_amount"].value.value)
    num_aged = outputs["num_aged_members"].value.value
    additional = str(outputs["additional_std_ded_amount"].value.value)
    total = str(outputs["standard_deduction"].value.value)

    ok = (
        basic == case.expected.basic_std_ded_amount
        and int(num_aged) == case.expected.num_aged_members
        and additional == case.expected.additional_std_ded_amount
        and total == case.expected.standard_deduction
    )

    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column(style="bold")
    table.add_column()
    table.add_column(style="cyan")
    table.add_row("basic_std_ded_amount", basic, f"(expected {case.expected.basic_std_ded_amount})")
    table.add_row("num_aged_members", str(num_aged), f"(expected {case.expected.num_aged_members})")
    table.add_row("additional_std_ded_amount", additional, f"(expected {case.expected.additional_std_ded_amount})")
    table.add_row("standard_deduction", total, f"(expected {case.expected.standard_deduction})")
    table.add_row("status", "match" if ok else "MISMATCH", "")

    CONSOLE.print(Panel(table, title=case.name, expand=False, border_style="green" if ok else "red"))
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run IRC §63(c) standard deduction cases through the rac engine"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "usc/26/63/c/program.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "usc/26/63/c/cases.yaml"),
    )
    args = parser.parse_args()

    program = Program.model_validate(yaml.safe_load(Path(args.program).read_text()))
    case_file = CaseFile.model_validate(yaml.safe_load(Path(args.cases).read_text()))
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]IRC §63(c) standard deduction — explain mode")
    passed = 0
    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.tax_unit_id,
                    period=case.period,
                    outputs=[
                        "basic_std_ded_amount",
                        "num_aged_members",
                        "additional_std_ded_amount",
                        "standard_deduction",
                    ],
                )
            ],
        )
        response = client.execute(request)
        if print_case(case, response.results[0]):
            passed += 1

    summary = Table(title="Summary", show_header=False)
    summary.add_column(style="bold cyan")
    summary.add_column()
    summary.add_row("Cases", str(len(case_file.cases)))
    summary.add_row("Passed", str(passed))
    CONSOLE.print(summary)
    sys.exit(0 if passed == len(case_file.cases) else 1)


if __name__ == "__main__":
    main()
