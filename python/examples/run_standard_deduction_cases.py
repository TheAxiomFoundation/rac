#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from axiom_rules import Dataset, ExecutionQuery, ExecutionRequest, AxiomRulesEngine
from axiom_rules.example_cases import coerce_period, load_case_list
from axiom_rules.loader import load_program
from axiom_rules.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

CONSOLE = Console()


class MemberCase(BaseModel):
    person_id: str
    is_aged_65_or_over: bool


class ExpectedOutputs(BaseModel):
    basic_std_ded_amount: int | str | None = None
    num_aged_members: int | None = None
    additional_std_ded_amount: int | str | None = None
    standard_deduction: int | str | None = None


class StandardDeductionCase(BaseModel):
    name: str
    tax_unit_id: str
    period: Period
    filing_status: int
    members: list[MemberCase]
    expected: ExpectedOutputs


class CaseFile(BaseModel):
    cases: list[StandardDeductionCase]


def load_cases(path: str | Path) -> CaseFile:
    cases = []
    for index, raw in enumerate(load_case_list(path), start=1):
        tax_unit_id = raw.get("tax_unit_id", f"tax-unit-{index}")
        inputs = raw["input"]
        members = [
            {
                "person_id": member.get("id", f"{tax_unit_id}-member-{member_index}"),
                "is_aged_65_or_over": member["is_aged_65_or_over"],
            }
            for member_index, member in enumerate(
                inputs.get("member_of_tax_unit", []), start=1
            )
        ]
        cases.append(
            {
                "name": raw["name"],
                "tax_unit_id": tax_unit_id,
                "period": coerce_period(raw["period"]),
                "filing_status": inputs["filing_status"],
                "members": members,
                "expected": raw["output"],
            }
        )
    return CaseFile.model_validate({"cases": cases})


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
                name="is_aged_65_or_over",
                entity="Person",
                entity_id=member.person_id,
                interval=interval,
                value=ScalarValue(kind="bool", value=member.is_aged_65_or_over),
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

    checks = {
        "basic_std_ded_amount": basic,
        "num_aged_members": int(num_aged),
        "additional_std_ded_amount": additional,
        "standard_deduction": total,
    }
    expected = case.expected.model_dump()
    ok = all(
        str(actual) == str(expected_value)
        for field, actual in checks.items()
        if (expected_value := expected[field]) is not None
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
        description="Run IRC §63(c) standard deduction cases through the Axiom Rules Engine"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "axiom-rules"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "usc/26/63/c/rules.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "usc/26/63/c/rules.test.yaml"),
    )
    args = parser.parse_args()

    program = load_program(args.program, binary_path=args.binary)
    case_file = load_cases(args.cases)
    client = AxiomRulesEngine(binary_path=args.binary)

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
