#!/usr/bin/env python3
# ruff: noqa: E402
"""Run UK income tax 2025-26 cases through the rac executable in explain mode.

Each case lists only the inputs it actually exercises under `inputs:`; the
programme's `input_or_else` declarations cover everything else (no savings,
no dividends, no reducers, etc.). `country` is always explicit — there is
no legally meaningful default for UK residence.

Every derived output carries an ITA 2007 / ITTOIA 2005 / ITEPA 2003 /
FA 2004 citation. The `--trace` flag renders the full dependency tree so the
explain output reads as a statutory proof of the tax liability.
"""
from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import Dataset, ExecutionQuery, ExecutionRequest, RAC
from rac_api.loader import load_program
from rac_api.models import InputRecord, Interval, Period, ScalarValue

CONSOLE = Console()

# Outputs whose trees make the statutory reasoning readable. These are the
# nodes worth rooting the trace at — not every derived output, since most are
# internal plumbing consumed only by the next derived output in the chain.
TRACE_ROOTS = [
    "income_tax",
    "tax_reducers_used",
    "tax_additions",
    "taxable_income",
    "personal_allowance",
    "gross_income",
]


def parse_input_value(value) -> ScalarValue:
    if isinstance(value, bool):
        return ScalarValue(kind="bool", value=value)
    if isinstance(value, str):
        if value in ("true", "false"):
            return ScalarValue(kind="bool", value=value == "true")
        try:
            Decimal(value)
            return ScalarValue(kind="decimal", value=value)
        except Exception:
            return ScalarValue(kind="text", value=value)
    raise ValueError(f"unsupported input value: {value!r}")


def build_dataset(case: dict) -> Dataset:
    period = case["period"]
    interval = Interval(start=period["start"], end=period["end"])
    return Dataset(
        inputs=[
            InputRecord(
                name=name,
                entity="Taxpayer",
                entity_id=case["taxpayer_id"],
                interval=interval,
                value=parse_input_value(value),
            )
            for name, value in case["inputs"].items()
        ]
    )


def format_value(node) -> str:
    if hasattr(node, "value") and node.value is not None:
        v = node.value.value
        kind = getattr(node.value, "kind", None)
        if kind in ("decimal", "integer"):
            d = Decimal(str(v))
            if d == d.to_integral_value():
                return f"£{int(d):,}"
            return f"£{d:,.2f}"
        if kind == "bool":
            return "yes" if v else "no"
        return str(v)
    if hasattr(node, "outcome"):
        return str(node.outcome)
    return "?"


def _is_decimal(s: str) -> bool:
    try:
        Decimal(s)
        return True
    except Exception:
        return False


def render_trace(case_name: str, result) -> None:
    """Render each root output as a tree of its legislative dependencies."""
    shown: set[str] = set()

    def attach(parent: Tree, name: str, depth: int = 0) -> None:
        if name in shown or depth > 10:
            return
        shown.add(name)
        node = result.trace.get(name)
        if node is None:
            return
        label = [f"[bold cyan]{name}[/bold cyan]", f"= {format_value(node)}"]
        if node.source:
            label.append(f"[italic dim]{node.source}[/italic dim]")
        branch = parent.add(" ".join(label))
        for dep in node.dependencies:
            attach(branch, dep, depth + 1)

    tree = Tree(f"[bold]{case_name}[/bold]")
    for output in TRACE_ROOTS:
        if output in result.trace:
            # Render each root fresh so citations can repeat.
            shown.clear()
            attach(tree, output)
    CONSOLE.print(tree)


def print_case_result(
    case: dict, result, duration: float, show_trace: bool
) -> bool:
    expected = case["expected"]
    outputs = result.outputs
    actual = {name: outputs[name].value.value for name in expected}
    ok = all(Decimal(actual[f]) == Decimal(expected[f]) for f in expected)

    timing = Table.grid(padding=(0, 2))
    timing.add_column(style="cyan")
    timing.add_column(style="white")
    timing.add_row("Engine path", "requested=explain actual=explain")
    timing.add_row("Execute", f"{duration:.4f}s")

    outputs_table = Table(box=None, show_header=False, pad_edge=False)
    outputs_table.add_column(style="bold")
    outputs_table.add_column()
    for field in expected:
        node = outputs[field]
        trace_node = result.trace.get(field)
        cite = trace_node.source if trace_node and trace_node.source else ""
        cite_md = f" [italic dim]{cite}[/italic dim]" if cite else ""
        outputs_table.add_row(
            field.replace("_", " "),
            f"{format_value(node)}{cite_md}",
        )
    status = (
        "[green]matches expected[/green]"
        if ok
        else "[red]DIFFERS FROM EXPECTED[/red]"
    )
    outputs_table.add_row("check", status)

    CONSOLE.print(
        Panel(timing, title=case["name"], expand=False, border_style="blue")
    )
    CONSOLE.print(outputs_table)
    if show_trace:
        render_trace(case["name"], result)
    CONSOLE.print()
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the full UK 2025-26 income-tax case pack in explain mode."
    )
    parser.add_argument(
        "--binary",
        default=str(ROOT / "target" / "debug" / "rac"),
        help="Path to the compiled rac executable.",
    )
    parser.add_argument(
        "--program",
        default=str(ROOT / "programmes" / "ukpga/2007/3/rules.rac"),
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "programmes" / "ukpga/2007/3/cases.yaml"),
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Render the full legislation-citation trace for each case.",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Run only cases whose name contains this substring.",
    )
    args = parser.parse_args()

    program = load_program(args.program, binary_path=args.binary)
    cases = yaml.safe_load(Path(args.cases).read_text())["cases"]
    if args.only:
        cases = [c for c in cases if args.only in c["name"]]
    client = RAC(binary_path=args.binary)

    CONSOLE.rule("[bold blue]UK income tax 2025-26 — explain mode")
    total_started = time.perf_counter()
    total_execution = 0.0
    failures = 0

    for case in cases:
        dataset = build_dataset(case)
        period_obj = Period(
            period_kind=case["period"]["period_kind"],
            start=case["period"]["start"],
            end=case["period"]["end"],
        )
        request = ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=case["taxpayer_id"],
                    period=period_obj,
                    outputs=list(case["expected"].keys()) + TRACE_ROOTS,
                )
            ],
        )
        started = time.perf_counter()
        response = client.execute(request)
        duration = time.perf_counter() - started
        total_execution += duration
        if not print_case_result(case, response.results[0], duration, args.trace):
            failures += 1

    total_duration = time.perf_counter() - total_started
    summary = Table(title="Summary", show_header=False)
    summary.add_column(style="bold cyan")
    summary.add_column()
    summary.add_row("Cases", str(len(cases)))
    summary.add_row("Matching expected", str(len(cases) - failures))
    summary.add_row("Total duration", f"{total_duration:.4f}s")
    summary.add_row("Total execution", f"{total_execution:.4f}s")
    CONSOLE.print(summary)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
