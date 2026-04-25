#!/usr/bin/env python3
# ruff: noqa: E402
"""Run the SI 2006/965 reg 2 child benefit rate cases."""
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

from axiom_rules import Dataset, ExecutionQuery, ExecutionRequest, AxiomRulesEngine
from axiom_rules.loader import load_program
from axiom_rules.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

CONSOLE = Console()

OUTPUTS = [
    "num_children_total",
    "num_children_eligible_for_enhanced",
    "num_enhanced_rate",
    "num_standard_rate",
    "weekly_child_benefit",
]


class ChildCase(BaseModel):
    id: str
    is_eldest_in_household: bool
    resides_with_parent: bool


class ExpectedOutputs(BaseModel):
    num_children_total: int | None = None
    num_children_eligible_for_enhanced: int | None = None
    num_enhanced_rate: int | None = None
    num_standard_rate: int | None = None
    weekly_child_benefit: str | None = None


class ClaimantCase(BaseModel):
    name: str
    claimant_id: str
    period: Period
    is_voluntary_org: bool
    children: list[ChildCase]
    expected: ExpectedOutputs


class ClaimantCaseFile(BaseModel):
    cases: list[ClaimantCase]


def build_dataset(case: ClaimantCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    inputs = [
        InputRecord(
            name="is_voluntary_org",
            entity="Claimant",
            entity_id=case.claimant_id,
            interval=interval,
            value=ScalarValue(kind="bool", value=case.is_voluntary_org),
        ),
    ]
    relations = []
    for child in case.children:
        inputs.extend([
            InputRecord(
                name="is_enhanced_eligible",
                entity="Child",
                entity_id=child.id,
                interval=interval,
                value=ScalarValue(
                    kind="bool",
                    value=child.is_eldest_in_household and not child.resides_with_parent,
                ),
            ),
        ])
        relations.append(
            RelationRecord(
                name="child_of_claim",
                tuple=[child.id, case.claimant_id],
                interval=interval,
            )
        )
    return Dataset(inputs=inputs, relations=relations)


def render_trace(case_name: str, result) -> None:
    tree = Tree(
        f"[bold]{case_name}[/bold] — weekly = "
        f"£{result.outputs['weekly_child_benefit'].value.value}"
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

    attach(tree, "weekly_child_benefit")
    CONSOLE.print(tree)


def check_expected(case: ClaimantCase, result) -> tuple[bool, list[str]]:
    problems = []
    for field, expected_value in case.expected.model_dump().items():
        if expected_value is None:
            continue
        actual = result.outputs[field].value.value
        if field == "weekly_child_benefit":
            if Decimal(str(expected_value)) != Decimal(str(actual)):
                problems.append(f"{field}: expected {expected_value}, got {actual}")
        else:
            if int(expected_value) != int(actual):
                problems.append(f"{field}: expected {expected_value}, got {actual}")
    return (len(problems) == 0, problems)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run SI 2006/965 reg 2 child benefit rate cases in explain mode"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "axiom-rules"),
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "uksi/2006/965/regulation/2/rules.yaml"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "uksi/2006/965/regulation/2/cases.yaml"),
    )
    parser.add_argument(
        "--no-trace",
        dest="trace",
        action="store_false",
    )
    parser.set_defaults(trace=True)
    args = parser.parse_args()

    program = load_program(args.program, binary_path=args.binary)
    case_file = ClaimantCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = AxiomRulesEngine(binary_path=args.binary)

    CONSOLE.rule("[bold blue]SI 2006/965 reg 2 — explain mode")
    all_ok = True

    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.claimant_id,
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
            "num_children_total",
            str(result.outputs["num_children_total"].value.value),
        )
        summary.add_row(
            "num_enhanced_rate",
            str(result.outputs["num_enhanced_rate"].value.value),
        )
        summary.add_row(
            "num_standard_rate",
            str(result.outputs["num_standard_rate"].value.value),
        )
        summary.add_row(
            "weekly_child_benefit",
            f"£{result.outputs['weekly_child_benefit'].value.value}",
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
