"""Per-programme translators: user-facing case dict -> engine Dataset/Query.

Each translator takes the case dict shape documented in the programme manifest
and returns the pair (Dataset, ExecutionQuery) the Axiom Rules Engine consumes. This is
the layer that insulates the LLM (and any other caller) from internal entity
IDs and relation wiring.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from axiom_rules.models import (
    Dataset,
    ExecutionQuery,
    InputRecord,
    Interval,
    Period,
    RelationRecord,
    ScalarValue,
)


def _period(case: dict[str, Any], kind: str) -> tuple[Period, Interval]:
    period_dict = case["period"]
    start = _as_date(period_dict["start"])
    end = _as_date(period_dict["end"])
    return Period(period_kind=kind, start=start, end=end), Interval(start=start, end=end)


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _decimal(value: Any) -> ScalarValue:
    return ScalarValue(kind="decimal", value=str(value))


def _bool(value: Any) -> ScalarValue:
    return ScalarValue(kind="bool", value=bool(value))


def _integer(value: Any) -> ScalarValue:
    return ScalarValue(kind="integer", value=int(value))


def _text(value: Any) -> ScalarValue:
    return ScalarValue(kind="text", value=str(value))


# ---------------------------------------------------------------------------
# Universal Credit
# ---------------------------------------------------------------------------

UC_OUTPUTS = [
    "standard_allowance",
    "child_element_total",
    "lcwra_element",
    "carer_element",
    "housing_element",
    "max_uc",
    "uc_award",
]


def translate_universal_credit(case: dict[str, Any]) -> tuple[Dataset, ExecutionQuery]:
    period, interval = _period(case, "month")
    benefit_unit_id = case.get("benefit_unit_id", "bu-1")

    adults = case.get("adults") or []
    children = case.get("children") or []

    inputs: list[InputRecord] = []
    relations: list[RelationRecord] = []

    bu_decimals = [
        ("eligible_housing_costs", _decimal),
        ("non_dep_deductions_total", _decimal),
        ("earned_income_monthly", _decimal),
        ("unearned_income_monthly", _decimal),
        ("capital_total", _decimal),
    ]
    bu_bools = [
        ("is_couple", _bool),
        ("has_housing_costs", _bool),
    ]
    for name, coerce in bu_bools + bu_decimals:
        inputs.append(
            InputRecord(
                name=name,
                entity="BenefitUnit",
                entity_id=benefit_unit_id,
                interval=interval,
                value=coerce(case[name]),
            )
        )

    for index, adult in enumerate(adults, start=1):
        adult_id = adult.get("id", f"adult-{index}")
        for name, coerce in [
            ("age_25_or_over", _bool),
            ("has_lcwra", _bool),
            ("is_carer", _bool),
        ]:
            inputs.append(
                InputRecord(
                    name=name,
                    entity="Adult",
                    entity_id=adult_id,
                    interval=interval,
                    value=coerce(adult[name]),
                )
            )
        relations.append(
            RelationRecord(
                name="adult_of_benefit_unit",
                tuple=[adult_id, benefit_unit_id],
                interval=interval,
            )
        )

    for index, child in enumerate(children, start=1):
        child_id = child.get("id", f"child-{index}")
        inputs.append(
            InputRecord(
                name="qualifies_for_child_element",
                entity="Child",
                entity_id=child_id,
                interval=interval,
                value=_bool(child["qualifies_for_child_element"]),
            )
        )
        inputs.append(
            InputRecord(
                name="disability_level",
                entity="Child",
                entity_id=child_id,
                interval=interval,
                value=_text(child.get("disability_level", "none")),
            )
        )
        relations.append(
            RelationRecord(
                name="child_of_benefit_unit",
                tuple=[child_id, benefit_unit_id],
                interval=interval,
            )
        )

    dataset = Dataset(inputs=inputs, relations=relations)
    query = ExecutionQuery(entity_id=benefit_unit_id, period=period, outputs=list(UC_OUTPUTS))
    return dataset, query


# ---------------------------------------------------------------------------
# UK income tax
# ---------------------------------------------------------------------------

INCOME_TAX_OUTPUTS = [
    "gross_income",
    "personal_allowance",
    "taxable_income",
    "income_tax",
    "net_income",
]


def translate_uk_income_tax(case: dict[str, Any]) -> tuple[Dataset, ExecutionQuery]:
    period, interval = _period(case, "tax_year")
    taxpayer_id = case.get("taxpayer_id", "taxpayer-1")

    income_fields = [
        "employment_income",
        "self_employment_income",
        "pension_income",
        "property_income",
        "savings_income",
    ]
    inputs = [
        InputRecord(
            name=name,
            entity="Taxpayer",
            entity_id=taxpayer_id,
            interval=interval,
            value=_decimal(case[name]),
        )
        for name in income_fields
    ]
    dataset = Dataset(inputs=inputs)
    query = ExecutionQuery(entity_id=taxpayer_id, period=period, outputs=list(INCOME_TAX_OUTPUTS))
    return dataset, query


# ---------------------------------------------------------------------------
# Child benefit responsibility (SI 1987/1967 reg 15)
# ---------------------------------------------------------------------------

CB_RESPONSIBILITY_OUTPUTS = [
    "cb_recipient_count",
    "has_cb_recipient",
    "needs_fallback",
    "sole_claim_fallback",
    "usual_residence_fallback",
    "responsible_person",
]


def translate_child_benefit_responsibility(
    case: dict[str, Any],
) -> tuple[Dataset, ExecutionQuery]:
    period, interval = _period(case, "week")
    child_id = case.get("child_id", "child-1")

    inputs = [
        InputRecord(
            name="cb_claim_count",
            entity="Child",
            entity_id=child_id,
            interval=interval,
            value=_integer(case["cb_claim_count"]),
        ),
        InputRecord(
            name="cb_recipient_id",
            entity="Child",
            entity_id=child_id,
            interval=interval,
            value=_text(case["cb_recipient_id"]),
        ),
        InputRecord(
            name="sole_claimant_id",
            entity="Child",
            entity_id=child_id,
            interval=interval,
            value=_text(case["sole_claimant_id"]),
        ),
        InputRecord(
            name="usual_resident_id",
            entity="Child",
            entity_id=child_id,
            interval=interval,
            value=_text(case["usual_resident_id"]),
        ),
    ]
    relations = [
        RelationRecord(
            name="cb_receipt",
            tuple=[recipient, child_id],
            interval=interval,
        )
        for recipient in case.get("cb_recipients", [])
    ]
    dataset = Dataset(inputs=inputs, relations=relations)
    query = ExecutionQuery(
        entity_id=child_id, period=period, outputs=list(CB_RESPONSIBILITY_OUTPUTS)
    )
    return dataset, query


TRANSLATORS: dict[str, Callable[[dict[str, Any]], tuple[Dataset, ExecutionQuery]]] = {
    "universal_credit": translate_universal_credit,
    "uk_income_tax": translate_uk_income_tax,
    "child_benefit_responsibility": translate_child_benefit_responsibility,
}


def translate(programme_name: str, case: dict[str, Any]) -> tuple[Dataset, ExecutionQuery]:
    if programme_name not in TRANSLATORS:
        known = ", ".join(sorted(TRANSLATORS))
        raise KeyError(f"no translator for programme {programme_name!r}; have: {known}")
    return TRANSLATORS[programme_name](case)
