#!/usr/bin/env python3
# ruff: noqa: E402
"""Compare the Axiom Rules Engine Universal Credit output against entitledto.co.uk figures
recorded in tests/uc_entitledto_testpack.md. Uses the 2026-27 uprating
amendments file (SI 2026/148) so the engine runs at entitledto's current rates."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from axiom_rules import Dataset, ExecutionQuery, ExecutionRequest, AxiomRulesEngine, load_program
from axiom_rules.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

CONSOLE = Console()

UC_PROGRAMME = (
    ROOT / "programmes" / "uksi" / "2026" / "148" / "rules.rac"
)


@dataclass
class Adult:
    id: str
    age_25_or_over: bool = True
    has_lcwra: bool = False
    is_carer: bool = False


@dataclass
class Child:
    id: str
    qualifies_for_child_element: bool = True
    is_higher_rate_first_child: bool = False
    disability_level: Literal["none", "lower", "higher"] = "none"


@dataclass
class Scenario:
    number: int
    name: str
    is_couple: bool
    has_housing_costs: bool
    eligible_housing_costs: Decimal
    earned_income_monthly: Decimal
    unearned_income_monthly: Decimal
    capital_total: Decimal
    adults: list[Adult]
    children: list[Child]
    entitledto_uc_2026_27: Decimal | None = None
    non_dep_deductions_total: Decimal = Decimal("0")


def build_dataset(scenario: Scenario, period: Period) -> Dataset:
    interval = Interval(start=period.start, end=period.end)
    bu_id = f"bu-{scenario.number}"
    inputs = [
        InputRecord(name="is_couple", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="bool", value=scenario.is_couple)),
        InputRecord(name="has_housing_costs", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="bool", value=scenario.has_housing_costs)),
        InputRecord(name="eligible_housing_costs", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value=str(scenario.eligible_housing_costs))),
        InputRecord(name="non_dep_deductions_total", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value=str(scenario.non_dep_deductions_total))),
        InputRecord(name="earned_income_monthly", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value=str(scenario.earned_income_monthly))),
        InputRecord(name="unearned_income_monthly", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value=str(scenario.unearned_income_monthly))),
        InputRecord(name="capital_total", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value=str(scenario.capital_total))),
    ]
    relations = []
    for adult in scenario.adults:
        inputs.extend([
            InputRecord(name="age_25_or_over", entity="Adult", entity_id=adult.id, interval=interval, value=ScalarValue(kind="bool", value=adult.age_25_or_over)),
            InputRecord(name="has_lcwra", entity="Adult", entity_id=adult.id, interval=interval, value=ScalarValue(kind="bool", value=adult.has_lcwra)),
            InputRecord(name="is_carer", entity="Adult", entity_id=adult.id, interval=interval, value=ScalarValue(kind="bool", value=adult.is_carer)),
        ])
        relations.append(RelationRecord(name="adult_of_benefit_unit", tuple=[adult.id, bu_id], interval=interval))
    for child in scenario.children:
        inputs.extend([
            InputRecord(name="qualifies_for_child_element", entity="Child", entity_id=child.id, interval=interval, value=ScalarValue(kind="bool", value=child.qualifies_for_child_element)),
            InputRecord(name="is_higher_rate_first_child", entity="Child", entity_id=child.id, interval=interval, value=ScalarValue(kind="bool", value=child.is_higher_rate_first_child)),
            InputRecord(name="disability_level", entity="Child", entity_id=child.id, interval=interval, value=ScalarValue(kind="text", value=child.disability_level)),
        ])
        relations.append(RelationRecord(name="child_of_benefit_unit", tuple=[child.id, bu_id], interval=interval))
    return Dataset(inputs=inputs, relations=relations)


def run(scenario: Scenario, client: AxiomRulesEngine, program: Program, period: Period) -> Decimal:
    dataset = build_dataset(scenario, period)
    response = client.execute(
        ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=f"bu-{scenario.number}",
                    period=period,
                    outputs=["uc_award"],
                )
            ],
        )
    )
    return Decimal(str(response.results[0].outputs["uc_award"].value.value))


def scenarios() -> list[Scenario]:
    return [
        Scenario(
            number=1,
            name="Single 25+, no other income",
            is_couple=False,
            has_housing_costs=False,
            eligible_housing_costs=Decimal("0"),
            earned_income_monthly=Decimal("0"),
            unearned_income_monthly=Decimal("0"),
            capital_total=Decimal("0"),
            adults=[Adult(id="adult-1a")],
            children=[],
            entitledto_uc_2026_27=Decimal("424.90"),
        ),
        Scenario(
            number=2,
            name="Single parent, 2 kids (post-Apr-2017), £800 earnings",
            is_couple=False,
            has_housing_costs=False,
            eligible_housing_costs=Decimal("0"),
            earned_income_monthly=Decimal("800"),
            unearned_income_monthly=Decimal("0"),
            capital_total=Decimal("0"),
            adults=[Adult(id="adult-2a")],
            children=[
                Child(id="child-2a"),
                Child(id="child-2b"),
            ],
            entitledto_uc_2026_27=Decimal("983.28"),
        ),
        Scenario(
            number=3,
            name="Couple, 2 kids, £800 rent, £1,500 earnings",
            is_couple=True,
            has_housing_costs=True,
            eligible_housing_costs=Decimal("800"),
            earned_income_monthly=Decimal("1500"),
            unearned_income_monthly=Decimal("0"),
            capital_total=Decimal("0"),
            adults=[Adult(id="adult-3a"), Adult(id="adult-3b")],
            children=[Child(id="child-3a"), Child(id="child-3b")],
            entitledto_uc_2026_27=None,
        ),
        Scenario(
            number=4,
            name="Couple, LCWRA + carer, no earnings",
            is_couple=True,
            has_housing_costs=False,
            eligible_housing_costs=Decimal("0"),
            earned_income_monthly=Decimal("0"),
            unearned_income_monthly=Decimal("0"),
            capital_total=Decimal("0"),
            adults=[
                Adult(id="adult-4a", has_lcwra=True),
                Adult(id="adult-4b", is_carer=True),
            ],
            children=[],
            entitledto_uc_2026_27=None,
        ),
        Scenario(
            number=5,
            name="Single, £8.5k capital, £200 pension",
            is_couple=False,
            has_housing_costs=False,
            eligible_housing_costs=Decimal("0"),
            earned_income_monthly=Decimal("0"),
            unearned_income_monthly=Decimal("200"),
            capital_total=Decimal("8500"),
            adults=[Adult(id="adult-5a")],
            children=[],
            entitledto_uc_2026_27=Decimal("181.40"),
        ),
        Scenario(
            number=6,
            name="Couple, 3 kids (1 higher disabled, 1 excluded), LCWRA, £1,200 rent",
            is_couple=True,
            has_housing_costs=True,
            eligible_housing_costs=Decimal("1200"),
            earned_income_monthly=Decimal("0"),
            unearned_income_monthly=Decimal("0"),
            capital_total=Decimal("0"),
            adults=[
                Adult(id="adult-6a", has_lcwra=True),
                Adult(id="adult-6b"),
            ],
            children=[
                Child(id="child-6a"),
                Child(id="child-6b", disability_level="higher"),
                Child(id="child-6c", qualifies_for_child_element=False),
            ],
            entitledto_uc_2026_27=None,
        ),
    ]


def main() -> None:
    program = load_program(UC_PROGRAMME)
    client = AxiomRulesEngine(binary_path=str(ROOT / "target" / "debug" / "axiom-rules"))
    period = Period(period_kind="month", start=date(2026, 5, 1), end=date(2026, 5, 31))

    CONSOLE.rule("[bold blue]UC — Axiom Rules Engine vs entitledto.co.uk (2026-27 rates)")
    CONSOLE.print(f"Programme: {UC_PROGRAMME.relative_to(ROOT)}")
    CONSOLE.print(f"Assessment period: {period.start} to {period.end}\n")

    table = Table()
    table.add_column("#", justify="right")
    table.add_column("scenario")
    table.add_column("Axiom UC", justify="right")
    table.add_column("entitledto UC", justify="right")
    table.add_column("Δ (£)", justify="right")
    table.add_column("verdict")

    max_gap = Decimal("1")

    for s in scenarios():
        rac_uc = run(s, client, program, period)
        if s.entitledto_uc_2026_27 is not None:
            gap = rac_uc - s.entitledto_uc_2026_27
            verdict = (
                "[green]match[/green]"
                if abs(gap) <= max_gap
                else f"[red]mismatch ({gap:+.2f})[/red]"
            )
            entitledto_cell = f"£{s.entitledto_uc_2026_27:,.2f}"
            gap_cell = f"{gap:+.2f}"
        else:
            entitledto_cell = "[dim]not run[/dim]"
            gap_cell = "-"
            verdict = "[dim]no reference[/dim]"
        table.add_row(
            str(s.number),
            s.name,
            f"£{rac_uc:,.2f}",
            entitledto_cell,
            gap_cell,
            verdict,
        )

    CONSOLE.print(table)


if __name__ == "__main__":
    main()
