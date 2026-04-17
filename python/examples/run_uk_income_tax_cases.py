#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import Dataset, ExecutionQuery, ExecutionRequest, Program, RAC
from rac_api.models import InputRecord, Interval, Period, ScalarValue

CONSOLE = Console()

OUTPUTS = [
    "gross_income",
    "personal_allowance",
    "taxable_income",
    "income_tax",
    "net_income",
]


class ExpectedOutputs(BaseModel):
    gross_income: str
    personal_allowance: str
    taxable_income: str
    income_tax: str
    net_income: str


class TaxpayerCase(BaseModel):
    name: str
    taxpayer_id: str
    period: Period
    employment_income: str
    self_employment_income: str
    pension_income: str
    property_income: str
    savings_income: str
    expected: ExpectedOutputs


class TaxpayerCaseFile(BaseModel):
    cases: list[TaxpayerCase]


def money(value: str) -> ScalarValue:
    return ScalarValue(kind="decimal", value=value)


def build_dataset(case: TaxpayerCase) -> Dataset:
    interval = Interval(start=case.period.start, end=case.period.end)
    return Dataset(
        inputs=[
            InputRecord(
                name=name,
                entity="Taxpayer",
                entity_id=case.taxpayer_id,
                interval=interval,
                value=money(value),
            )
            for name, value in [
                ("employment_income", case.employment_income),
                ("self_employment_income", case.self_employment_income),
                ("pension_income", case.pension_income),
                ("property_income", case.property_income),
                ("savings_income", case.savings_income),
            ]
        ]
    )


def print_case_result(case: TaxpayerCase, result, *, execution_duration: float) -> None:
    outputs = result.outputs
    values = {name: outputs[name].value.value for name in OUTPUTS}
    expected = case.expected.model_dump()
    expected_ok = all(str(values[name]) == expected[name] for name in OUTPUTS)
    status = "matches expected" if expected_ok else "differs from expected"

    timing = Table.grid(padding=(0, 2))
    timing.add_column(style="cyan")
    timing.add_column(style="white")
    timing.add_row("Engine path", "requested=explain actual=explain")
    timing.add_row("Execute", f"{execution_duration:.4f}s")

    outputs_table = Table(box=None, show_header=False, pad_edge=False)
    outputs_table.add_column(style="bold")
    outputs_table.add_column()
    outputs_table.add_row("Gross income", f"£{values['gross_income']}")
    outputs_table.add_row("Personal allowance", f"£{values['personal_allowance']}")
    outputs_table.add_row("Taxable income", f"£{values['taxable_income']}")
    outputs_table.add_row("Income tax", f"£{values['income_tax']}")
    outputs_table.add_row("Net income", f"£{values['net_income']}")
    outputs_table.add_row("Expected check", status)

    CONSOLE.print(Panel(timing, title=case.name, expand=False, border_style="blue"))
    CONSOLE.print(outputs_table)
    CONSOLE.print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the rUK 2025-26 income-tax cases through the rac executable in explain mode"
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
        help="Path to the compiled rac executable",
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ukpga/2007/3/program.yaml"),
        help="Path to the income-tax programme YAML document",
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "ukpga/2007/3/cases.yaml"),
        help="Path to the income-tax cases YAML document",
    )
    args = parser.parse_args()

    program = Program.model_validate(yaml.safe_load(Path(args.program).read_text()))
    case_file = TaxpayerCaseFile.model_validate(
        yaml.safe_load(Path(args.cases).read_text())
    )
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]rUK income tax 2025-26 — explain mode")
    total_execution_duration = 0.0
    total_started = time.perf_counter()

    for case in case_file.cases:
        dataset = build_dataset(case)
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case.taxpayer_id,
                    period=case.period,
                    outputs=list(OUTPUTS),
                )
            ],
        )
        execution_started = time.perf_counter()
        response = client.execute(request)
        execution_duration = time.perf_counter() - execution_started
        total_execution_duration += execution_duration
        print_case_result(
            case,
            response.results[0],
            execution_duration=execution_duration,
        )

    total_duration = time.perf_counter() - total_started
    summary = Table(title="Summary", show_header=False)
    summary.add_column(style="bold cyan")
    summary.add_column()
    summary.add_row("Cases", str(len(case_file.cases)))
    summary.add_row("Total duration", f"{total_duration:.4f}s")
    summary.add_row("Total execution duration", f"{total_execution_duration:.4f}s")
    CONSOLE.print(summary)


if __name__ == "__main__":
    main()
