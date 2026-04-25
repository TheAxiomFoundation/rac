"""Direct smoke test — invokes the tool callables the MCP server registers.

Runs list_programmes, describe_programme("universal_credit"), then evaluates a
single-adult no-income UC case and a £30k income tax case. Validates the
expected output matches the reference from the cases YAML.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from axiom_rules_mcp.server import (
    counterfactual,
    describe_programme,
    evaluate,
    list_programmes,
)


def _show(label: str, value: object) -> None:
    print(f"\n==== {label} ====")
    print(json.dumps(value, indent=2, default=str))


def main() -> int:
    catalogue = list_programmes()
    _show("list_programmes", catalogue)
    assert {p["name"] for p in catalogue} >= {
        "universal_credit",
        "uk_income_tax",
        "child_benefit_responsibility",
    }, "catalogue missing expected programmes"

    uc_description = describe_programme("universal_credit")
    assert "inputs" in uc_description
    assert "adults" in uc_description["inputs"]
    print("\ndescribe_programme('universal_credit') ok — input keys:",
          sorted(uc_description["inputs"]))

    uc_result = evaluate(
        "universal_credit",
        {
            "period": {"start": "2025-05-01", "end": "2025-05-31"},
            "is_couple": False,
            "has_housing_costs": False,
            "eligible_housing_costs": "0",
            "non_dep_deductions_total": "0",
            "earned_income_monthly": "0",
            "unearned_income_monthly": "0",
            "capital_total": "0",
            "adults": [
                {"age_25_or_over": True, "has_lcwra": False, "is_carer": False}
            ],
            "children": [],
        },
    )
    _show("evaluate universal_credit (single, 25+, no income)", uc_result)
    uc_award = uc_result["outputs"]["uc_award"]["value"]
    assert str(uc_award) == "400.14", f"expected 400.14 got {uc_award!r}"

    tax_result = evaluate(
        "uk_income_tax",
        {
            "period": {"start": "2025-04-06", "end": "2026-04-05"},
            "employment_income": "30000",
            "self_employment_income": "0",
            "pension_income": "0",
            "property_income": "0",
            "savings_income": "0",
        },
        include_trace=False,
    )
    _show("evaluate uk_income_tax (£30k employment)", tax_result)
    tax_due = tax_result["outputs"]["income_tax"]["value"]
    assert str(tax_due) == "3486", f"expected 3486 got {tax_due!r}"

    cf = counterfactual(
        "uk_income_tax",
        baseline_case={
            "period": {"start": "2025-04-06", "end": "2026-04-05"},
            "employment_income": "30000",
            "self_employment_income": "0",
            "pension_income": "0",
            "property_income": "0",
            "savings_income": "0",
        },
        alternative_case={
            "period": {"start": "2025-04-06", "end": "2026-04-05"},
            "employment_income": "35000",
            "self_employment_income": "0",
            "pension_income": "0",
            "property_income": "0",
            "savings_income": "0",
        },
    )
    _show("counterfactual £30k -> £35k", cf)
    assert cf["deltas"]["income_tax"]["delta"] == "1000"

    print("\nall assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
