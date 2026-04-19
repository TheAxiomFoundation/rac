#!/usr/bin/env python3
# ruff: noqa: E402
"""Household demo — run a synthetic UK working-age household through five
encoded legislation programmes and assemble the results into one summary:

  - rUK income tax 2025-26 (ITA 2007 et al.) — per adult, annual
  - NMW compliance check (NMWA 1998 s.1) — per adult, per pay reference period
  - Auto-enrolment duty (Pensions Act 2008 s.3) — per adult, per PRP
  - Council tax discount (LGFA 1992 s.11) — per dwelling, per day
  - Universal Credit (UC Regs 2013) — per benefit unit, per assessment period
  - Child benefit rate (SI 2006/965 reg 2) — per claimant, per week

The demo shows that the DSL can drive a coherent benefits-and-taxes stack
for the same synthetic population. Each programme is queried in isolation;
their outputs are composed at the Python level into a household-level
picture of weekly/monthly/annual cashflow.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import Dataset, ExecutionQuery, ExecutionRequest, Program, RAC
from rac_api.models import InputRecord, Interval, Period, RelationRecord, ScalarValue

CONSOLE = Console()

PROGRAMMES_ROOT = ROOT / "programmes"


@dataclass
class Adult:
    name: str
    age_years: int
    is_worker: bool = True
    works_in_uk: bool = True
    annual_earnings: Decimal = Decimal("0")
    monthly_earnings: Decimal = Decimal("0")
    monthly_hours: Decimal = Decimal("0")
    is_apprentice_first_year: bool = False
    active_member_of_qualifying_scheme: bool = False
    recently_opted_out: bool = False
    pensionable_age_years: int = 67
    has_lcwra: bool = False
    is_carer: bool = False


@dataclass
class Child:
    name: str
    qualifies_for_child_element: bool = True
    is_higher_rate_first_child: bool = False
    is_eldest_in_household: bool = False
    disability_level: Literal["none", "lower", "higher"] = "none"


@dataclass
class Household:
    name: str
    adults: list[Adult]
    children: list[Child]
    dwelling_band_number: int = 2  # council tax band B
    empty_home_override_applies: bool = False
    monthly_eligible_housing_costs: Decimal = Decimal("0")
    non_dep_deductions_total: Decimal = Decimal("0")
    capital_total: Decimal = Decimal("0")
    cb_claimant_index: int = 0  # which adult holds the CB claim


def load_program(relative_path: str) -> Program:
    path = PROGRAMMES_ROOT / relative_path
    return Program.model_validate(yaml.safe_load(path.read_text()))


def decimal_value(record) -> Decimal:
    return Decimal(str(record.value.value))


def run_income_tax(client: RAC, program: Program, adult: Adult, tax_year: Period) -> dict[str, Any]:
    interval = Interval(start=tax_year.start, end=tax_year.end)
    dataset = Dataset(
        inputs=[
            InputRecord(
                name="employment_income",
                entity="Taxpayer",
                entity_id=adult.name,
                interval=interval,
                value=ScalarValue(kind="decimal", value=str(adult.annual_earnings)),
            ),
            InputRecord(
                name="country",
                entity="Taxpayer",
                entity_id=adult.name,
                interval=interval,
                value=ScalarValue(kind="text", value="rUK"),
            ),
        ]
    )
    response = client.execute(
        ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=adult.name,
                    period=tax_year,
                    outputs=["gross_income", "personal_allowance", "taxable_income", "income_tax", "net_income"],
                )
            ],
        )
    )
    outputs = response.results[0].outputs
    return {name: decimal_value(outputs[name]) for name in ["gross_income", "personal_allowance", "taxable_income", "income_tax", "net_income"]}


def run_nmw(client: RAC, program: Program, adult: Adult, month: Period) -> dict[str, Any]:
    interval = Interval(start=month.start, end=month.end)
    dataset = Dataset(
        inputs=[
            InputRecord(name="is_worker", entity="Worker", entity_id=adult.name, interval=interval, value=ScalarValue(kind="bool", value=adult.is_worker)),
            InputRecord(name="works_in_uk", entity="Worker", entity_id=adult.name, interval=interval, value=ScalarValue(kind="bool", value=adult.works_in_uk)),
            InputRecord(name="above_compulsory_school_age", entity="Worker", entity_id=adult.name, interval=interval, value=ScalarValue(kind="bool", value=True)),
            InputRecord(name="current_age_years", entity="Worker", entity_id=adult.name, interval=interval, value=ScalarValue(kind="integer", value=adult.age_years)),
            InputRecord(name="is_apprentice_first_year", entity="Worker", entity_id=adult.name, interval=interval, value=ScalarValue(kind="bool", value=adult.is_apprentice_first_year)),
            InputRecord(name="remuneration_in_prp", entity="Worker", entity_id=adult.name, interval=interval, value=ScalarValue(kind="decimal", value=str(adult.monthly_earnings))),
            InputRecord(name="hours_worked_in_prp", entity="Worker", entity_id=adult.name, interval=interval, value=ScalarValue(kind="decimal", value=str(adult.monthly_hours))),
        ]
    )
    response = client.execute(
        ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=adult.name,
                    period=month,
                    outputs=["qualifies_for_nmw", "rate_owed", "effective_hourly", "is_compliant", "shortfall_total"],
                )
            ],
        )
    )
    outputs = response.results[0].outputs
    return {
        "qualifies": outputs["qualifies_for_nmw"].outcome,
        "rate_owed": decimal_value(outputs["rate_owed"]),
        "effective_hourly": decimal_value(outputs["effective_hourly"]),
        "compliant": outputs["is_compliant"].outcome,
        "shortfall": decimal_value(outputs["shortfall_total"]),
    }


def run_auto_enrolment(client: RAC, program: Program, adult: Adult, month: Period) -> dict[str, Any]:
    interval = Interval(start=month.start, end=month.end)
    dataset = Dataset(
        inputs=[
            InputRecord(name="current_age_years", entity="Jobholder", entity_id=adult.name, interval=interval, value=ScalarValue(kind="integer", value=adult.age_years)),
            InputRecord(name="pensionable_age_years", entity="Jobholder", entity_id=adult.name, interval=interval, value=ScalarValue(kind="integer", value=adult.pensionable_age_years)),
            InputRecord(name="earnings_this_prp", entity="Jobholder", entity_id=adult.name, interval=interval, value=ScalarValue(kind="decimal", value=str(adult.monthly_earnings))),
            InputRecord(name="prp_months", entity="Jobholder", entity_id=adult.name, interval=interval, value=ScalarValue(kind="decimal", value="1")),
            InputRecord(name="active_member_of_qualifying_scheme", entity="Jobholder", entity_id=adult.name, interval=interval, value=ScalarValue(kind="bool", value=adult.active_member_of_qualifying_scheme)),
            InputRecord(name="recently_opted_out", entity="Jobholder", entity_id=adult.name, interval=interval, value=ScalarValue(kind="bool", value=adult.recently_opted_out)),
        ]
    )
    response = client.execute(
        ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=adult.name,
                    period=month,
                    outputs=["employer_enrolment_duty", "earnings_trigger_for_prp"],
                )
            ],
        )
    )
    outputs = response.results[0].outputs
    return {
        "duty": outputs["employer_enrolment_duty"].outcome,
        "trigger": decimal_value(outputs["earnings_trigger_for_prp"]),
    }


def run_council_tax(client: RAC, program: Program, household: Household, fy: Period) -> dict[str, Any]:
    interval = Interval(start=fy.start, end=fy.end)
    inputs = [
        InputRecord(name="empty_home_override_applies", entity="Dwelling", entity_id=household.name, interval=interval, value=ScalarValue(kind="bool", value=household.empty_home_override_applies)),
    ]
    relations = []
    # Adults are non-disregarded residents. Children disregarded under Sch 1.
    residents = [(adult.name, False) for adult in household.adults] + [(child.name, True) for child in household.children]
    for person_id, is_disregarded in residents:
        inputs.append(
            InputRecord(
                name="is_disregarded", entity="Person", entity_id=person_id, interval=interval,
                value=ScalarValue(kind="bool", value=is_disregarded),
            )
        )
        relations.append(
            RelationRecord(name="resident_of", tuple=[person_id, household.name], interval=interval)
        )
    dataset = Dataset(inputs=inputs, relations=relations)
    response = client.execute(
        ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=household.name,
                    period=fy,
                    outputs=["num_non_disregarded_residents", "discount_fraction"],
                )
            ],
        )
    )
    outputs = response.results[0].outputs
    return {
        "non_disregarded": int(outputs["num_non_disregarded_residents"].value.value),
        "discount_fraction": decimal_value(outputs["discount_fraction"]),
    }


def run_universal_credit(client: RAC, program: Program, household: Household, ap: Period) -> dict[str, Any]:
    interval = Interval(start=ap.start, end=ap.end)
    is_couple = len(household.adults) >= 2
    household_monthly_earnings = sum((a.monthly_earnings for a in household.adults), Decimal("0"))
    has_housing = household.monthly_eligible_housing_costs > 0
    bu_id = household.name
    inputs = [
        InputRecord(name="is_couple", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="bool", value=is_couple)),
        InputRecord(name="has_housing_costs", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="bool", value=has_housing)),
        InputRecord(name="eligible_housing_costs", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value=str(household.monthly_eligible_housing_costs))),
        InputRecord(name="non_dep_deductions_total", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value=str(household.non_dep_deductions_total))),
        InputRecord(name="earned_income_monthly", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value=str(household_monthly_earnings))),
        InputRecord(name="unearned_income_monthly", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value="0")),
        InputRecord(name="capital_total", entity="BenefitUnit", entity_id=bu_id, interval=interval, value=ScalarValue(kind="decimal", value=str(household.capital_total))),
    ]
    relations = []
    for adult in household.adults:
        inputs.extend([
            InputRecord(name="age_25_or_over", entity="Adult", entity_id=adult.name, interval=interval, value=ScalarValue(kind="bool", value=adult.age_years >= 25)),
            InputRecord(name="has_lcwra", entity="Adult", entity_id=adult.name, interval=interval, value=ScalarValue(kind="bool", value=adult.has_lcwra)),
            InputRecord(name="is_carer", entity="Adult", entity_id=adult.name, interval=interval, value=ScalarValue(kind="bool", value=adult.is_carer)),
        ])
        relations.append(RelationRecord(name="adult_of_benefit_unit", tuple=[adult.name, bu_id], interval=interval))
    for child in household.children:
        inputs.extend([
            InputRecord(name="qualifies_for_child_element", entity="Child", entity_id=child.name, interval=interval, value=ScalarValue(kind="bool", value=child.qualifies_for_child_element)),
            InputRecord(name="is_higher_rate_first_child", entity="Child", entity_id=child.name, interval=interval, value=ScalarValue(kind="bool", value=child.is_higher_rate_first_child)),
            InputRecord(name="disability_level", entity="Child", entity_id=child.name, interval=interval, value=ScalarValue(kind="text", value=child.disability_level)),
        ])
        relations.append(RelationRecord(name="child_of_benefit_unit", tuple=[child.name, bu_id], interval=interval))
    dataset = Dataset(inputs=inputs, relations=relations)
    response = client.execute(
        ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=bu_id,
                    period=ap,
                    outputs=["standard_allowance", "child_element_total", "lcwra_element", "housing_element", "max_uc", "earnings_deduction", "uc_award"],
                )
            ],
        )
    )
    outputs = response.results[0].outputs
    return {name: decimal_value(outputs[name]) for name in ["standard_allowance", "child_element_total", "lcwra_element", "housing_element", "max_uc", "earnings_deduction", "uc_award"]}


def run_child_benefit_rate(client: RAC, program: Program, household: Household, week: Period) -> dict[str, Any]:
    if not household.children:
        return {"weekly_cb": Decimal("0"), "num_enhanced": 0, "num_standard": 0}
    claimant = household.adults[household.cb_claimant_index]
    interval = Interval(start=week.start, end=week.end)
    inputs = [
        InputRecord(name="is_voluntary_org", entity="Claimant", entity_id=claimant.name, interval=interval, value=ScalarValue(kind="bool", value=False)),
    ]
    relations = []
    for child in household.children:
        inputs.extend([
            InputRecord(name="is_eldest_in_household", entity="Child", entity_id=child.name, interval=interval, value=ScalarValue(kind="bool", value=child.is_eldest_in_household)),
            InputRecord(name="resides_with_parent", entity="Child", entity_id=child.name, interval=interval, value=ScalarValue(kind="bool", value=False)),
        ])
        relations.append(RelationRecord(name="child_of_claim", tuple=[child.name, claimant.name], interval=interval))
    dataset = Dataset(inputs=inputs, relations=relations)
    response = client.execute(
        ExecutionRequest(
            mode="explain",
            program=program,
            dataset=dataset,
            queries=[
                ExecutionQuery(
                    entity_id=claimant.name,
                    period=week,
                    outputs=["num_enhanced_rate", "num_standard_rate", "weekly_child_benefit"],
                )
            ],
        )
    )
    outputs = response.results[0].outputs
    return {
        "num_enhanced": int(outputs["num_enhanced_rate"].value.value),
        "num_standard": int(outputs["num_standard_rate"].value.value),
        "weekly_cb": decimal_value(outputs["weekly_child_benefit"]),
    }


def main() -> None:
    client = RAC(binary_path=str(ROOT / "target" / "debug" / "rac"))

    income_tax_program = load_program("ukpga/2007/3/rules.yaml")
    nmw_program = load_program("ukpga/1998/39/section/1/rules.yaml")
    auto_enrolment_program = load_program("ukpga/2008/30/section/3/rules.yaml")
    council_tax_program = load_program("ukpga/1992/14/section/11/rules.yaml")
    uc_program = load_program("uksi/2013/376/rules.yaml")
    cb_program = load_program("uksi/2006/965/regulation/2/rules.yaml")

    household = Household(
        name="household-fitzgerald",
        adults=[
            Adult(
                name="alice",
                age_years=35,
                annual_earnings=Decimal("22000"),
                monthly_earnings=Decimal("1833.33"),
                monthly_hours=Decimal("160"),
            ),
            Adult(
                name="bob",
                age_years=38,
                annual_earnings=Decimal("8000"),
                monthly_earnings=Decimal("666.67"),
                monthly_hours=Decimal("80"),
            ),
        ],
        children=[
            Child(name="charlie", is_eldest_in_household=True),
            Child(name="dana"),
        ],
        dwelling_band_number=2,
        monthly_eligible_housing_costs=Decimal("700"),
        capital_total=Decimal("1500"),
        cb_claimant_index=0,
    )

    tax_year = Period(period_kind="tax_year", start=date(2025, 4, 6), end=date(2026, 4, 5))
    ap_month = Period(period_kind="month", start=date(2025, 5, 1), end=date(2025, 5, 31))
    fy_ct = Period(period_kind="tax_year", start=date(2025, 4, 1), end=date(2026, 3, 31))
    cb_week = Period(period_kind="benefit_week", start=date(2025, 5, 5), end=date(2025, 5, 11))

    # --- per-adult outputs ---
    CONSOLE.rule("[bold blue]Household demo: Fitzgerald family")

    per_adult_table = Table(title="Per adult", show_lines=True)
    per_adult_table.add_column("adult")
    per_adult_table.add_column("age", justify="right")
    per_adult_table.add_column("annual earn", justify="right")
    per_adult_table.add_column("income tax", justify="right")
    per_adult_table.add_column("nmw compliant?")
    per_adult_table.add_column("nmw rate owed", justify="right")
    per_adult_table.add_column("ae duty?")

    adult_tax_totals = Decimal("0")

    for adult in household.adults:
        tax = run_income_tax(client, income_tax_program, adult, tax_year)
        nmw = run_nmw(client, nmw_program, adult, ap_month)
        ae = run_auto_enrolment(client, auto_enrolment_program, adult, ap_month)
        adult_tax_totals += tax["income_tax"]
        per_adult_table.add_row(
            adult.name,
            str(adult.age_years),
            f"£{tax['gross_income']:,.0f}",
            f"£{tax['income_tax']:,.0f}",
            nmw["compliant"] if nmw["qualifies"] == "holds" else "n/a",
            f"£{nmw['rate_owed']:.2f}" if nmw["qualifies"] == "holds" else "-",
            ae["duty"],
        )

    # --- household outputs ---
    uc = run_universal_credit(client, uc_program, household, ap_month)
    cb = run_child_benefit_rate(client, cb_program, household, cb_week)
    ct = run_council_tax(client, council_tax_program, household, fy_ct)

    per_household_table = Table(title="Per household (monthly unless noted)", show_lines=True)
    per_household_table.add_column("item")
    per_household_table.add_column("value", justify="right")

    monthly_uc = uc["uc_award"]
    monthly_cb = cb["weekly_cb"] * Decimal("52") / Decimal("12")
    monthly_earnings_total = sum((a.monthly_earnings for a in household.adults), Decimal("0"))
    monthly_income_tax = adult_tax_totals / Decimal("12")
    per_household_table.add_row("adults / children", f"{len(household.adults)} / {len(household.children)}")
    per_household_table.add_row("combined earnings", f"£{monthly_earnings_total:,.2f}")
    per_household_table.add_row("income tax (monthly-equivalent)", f"£{monthly_income_tax:,.2f}")
    per_household_table.add_row("UC standard allowance", f"£{uc['standard_allowance']:,.2f}")
    per_household_table.add_row("UC child element", f"£{uc['child_element_total']:,.2f}")
    per_household_table.add_row("UC housing element", f"£{uc['housing_element']:,.2f}")
    per_household_table.add_row("UC max (before deductions)", f"£{uc['max_uc']:,.2f}")
    per_household_table.add_row("UC earnings deduction", f"£{uc['earnings_deduction']:,.2f}")
    per_household_table.add_row("UC award", f"£{monthly_uc:,.2f}")
    per_household_table.add_row("child benefit weekly", f"£{cb['weekly_cb']:,.2f}")
    per_household_table.add_row("child benefit monthly-equivalent", f"£{monthly_cb:,.2f}")
    per_household_table.add_row("council tax discount fraction", f"{ct['discount_fraction']:.0%}")

    # net cashflow per month (pre-tax earnings + UC + CB - income tax - rent)
    monthly_net_cashflow = (
        monthly_earnings_total
        + monthly_uc
        + monthly_cb
        - monthly_income_tax
        - household.monthly_eligible_housing_costs
    )
    per_household_table.add_row(
        "[bold]net monthly cashflow (post rent & income tax)[/bold]",
        f"[bold]£{monthly_net_cashflow:,.2f}[/bold]",
    )

    CONSOLE.print(per_adult_table)
    CONSOLE.print()
    CONSOLE.print(per_household_table)
    CONSOLE.print()
    CONSOLE.print(
        Panel(
            "Five encoded programmes running against a single synthetic household: "
            "rUK income tax, NMW, auto-enrolment, council tax discount, Universal "
            "Credit, child benefit rates. Every derived output is traceable to the "
            "regulation it came from. None of the programmes needed DSL changes for "
            "this demo.",
            title="cross-programme household",
            border_style="green",
            expand=False,
        )
    )


if __name__ == "__main__":
    main()
