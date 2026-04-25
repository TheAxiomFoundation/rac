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

OUTPUTS = [
    "cb_recipient_count",
    "has_cb_recipient",
    "needs_fallback",
    "sole_claim_fallback",
    "usual_residence_fallback",
    "responsible_person",
]


class ExpectedOutputs(BaseModel):
    cb_recipient_count: int
    has_cb_recipient: Literal["holds", "not_holds", "undetermined"]
    needs_fallback: Literal["holds", "not_holds", "undetermined"]
    sole_claim_fallback: Literal["holds", "not_holds", "undetermined"]
    usual_residence_fallback: Literal["holds", "not_holds", "undetermined"]
    responsible_person: str


class ChildCase(BaseModel):
    name: str
    child_id: str
    period: Period
    cb_recipients: list[str]
    cb_claim_count: int
    cb_recipient_id: str
    sole_claimant_id: str
    usual_resident_id: str
    expected: ExpectedOutputs


class ChildCaseFile(BaseModel):
    cases: list[ChildCase]


def build_dataset(case: ChildCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    inputs = [
        InputRecord(
            name="cb_claim_count",
            entity="Child",
            entity_id=case.child_id,
            interval=interval,
            value=ScalarValue(kind="integer", value=case.cb_claim_count),
        ),
        InputRecord(
            name="cb_recipient_id",
            entity="Child",
            entity_id=case.child_id,
            interval=interval,
            value=ScalarValue(kind="text", value=case.cb_recipient_id),
        ),
        InputRecord(
            name="sole_claimant_id",
            entity="Child",
            entity_id=case.child_id,
            interval=interval,
            value=ScalarValue(kind="text", value=case.sole_claimant_id),
        ),
        InputRecord(
            name="usual_resident_id",
            entity="Child",
            entity_id=case.child_id,
            interval=interval,
            value=ScalarValue(kind="text", value=case.usual_resident_id),
        ),
    ]
    relations = [
        RelationRecord(
            name="cb_receipt",
            tuple=[recipient, case.child_id],
            interval=interval,
        )
        for recipient in case.cb_recipients
    ]
    return Dataset(inputs=inputs, relations=relations)


def print_case_result(
    case: ChildCase,
    result,
    *,
    build_duration: float,
    execution_duration: float,
) -> None:
    outputs = result.outputs
    cb_count = int(outputs["cb_recipient_count"].value.value)
    has_cb = outputs["has_cb_recipient"].outcome
    needs_fallback = outputs["needs_fallback"].outcome
    sole_claim = outputs["sole_claim_fallback"].outcome
    usual_residence = outputs["usual_residence_fallback"].outcome
    responsible = outputs["responsible_person"].value.value

    expected_ok = (
        cb_count == case.expected.cb_recipient_count
        and has_cb == case.expected.has_cb_recipient
        and needs_fallback == case.expected.needs_fallback
        and sole_claim == case.expected.sole_claim_fallback
        and usual_residence == case.expected.usual_residence_fallback
        and responsible == case.expected.responsible_person
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
    outputs_table.add_row("CB recipient count", str(cb_count))
    outputs_table.add_row("Has CB recipient", has_cb)
    outputs_table.add_row("Needs fallback (anti-join)", needs_fallback)
    outputs_table.add_row("Sole-claim fallback", sole_claim)
    outputs_table.add_row("Usual-residence fallback", usual_residence)
    outputs_table.add_row("Responsible person", responsible)
    outputs_table.add_row("Expected check", status)

    CONSOLE.print(Panel(timing, title=case.name, expand=False, border_style="blue"))
    CONSOLE.print(outputs_table)
    CONSOLE.print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the reg 15 child-benefit responsibility cases through the Axiom Rules Engine (`axiom-rules`) executable in explain mode"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "axiom-rules"),
        help="Path to the compiled Axiom Rules Engine (`axiom-rules`) executable",
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "uksi/1987/1967/regulation/15/rules.rac"),
        help="Path to the reg 15 programme YAML document",
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "uksi/1987/1967/regulation/15/cases.yaml"),
        help="Path to the reg 15 cases YAML document",
    )
    args = parser.parse_args()

    program = load_program(args.program, binary_path=args.binary)
    case_file = ChildCaseFile.model_validate(yaml.safe_load(Path(args.cases).read_text()))
    client = AxiomRulesEngine(binary_path=args.binary)

    CONSOLE.rule("[bold blue]SI 1987/1967 reg 15 — explain mode")
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
                    entity_id=case.child_id,
                    period=case.period,
                    outputs=list(OUTPUTS),
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
