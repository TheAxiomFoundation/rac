"""Demonstrate RAC reform comparison.

Usage:
    python examples/run_reform.py
"""

from datetime import date
from pathlib import Path

from rac import compile, execute, parse_file

examples = Path(__file__).parent

# Load baseline and reform
baseline_module = parse_file(examples / "uk_tax_benefit.rac")
reform_module = parse_file(examples / "reform.rac")

# Compile both scenarios
as_of = date(2025, 6, 1)
baseline_ir = compile([baseline_module], as_of=as_of)
reform_ir = compile([baseline_module, reform_module], as_of=as_of)

# Sample population
data = {
    "person": [
        {"id": 1, "income": 20000.0, "age": 30, "has_children": 0},
        {"id": 2, "income": 35000.0, "age": 45, "has_children": 1},
        {"id": 3, "income": 60000.0, "age": 50, "has_children": 0},
    ]
}

baseline = execute(baseline_ir, data)
reform = execute(reform_ir, data)

print("=== Reform impact ===\n")
print(f"{'':>6} {'Baseline Tax':>14} {'Reform Tax':>12} {'Change':>10}  {'Baseline UC':>12} {'Reform UC':>10} {'Change':>10}")
print("-" * 80)

for i, person in enumerate(data["person"]):
    b_tax = baseline.entities["person"]["person/income_tax"][i]
    r_tax = reform.entities["person"]["person/income_tax"][i]
    b_uc = baseline.entities["person"]["person/universal_credit"][i]
    r_uc = reform.entities["person"]["person/universal_credit"][i]
    print(
        f"#{person['id']:>4}  "
        f"{b_tax:>13,.2f}  {r_tax:>11,.2f}  {r_tax - b_tax:>+9,.2f}  "
        f"{b_uc:>11,.2f}  {r_uc:>9,.2f}  {r_uc - b_uc:>+9,.2f}"
    )

print()
print(f"Personal allowance: {baseline.scalars['gov/tax/personal_allowance']:,.0f} -> {reform.scalars['gov/tax/personal_allowance']:,.0f}")
print(f"UC standard:        {baseline.scalars['gov/uc/standard_allowance']:,.2f} -> {reform.scalars['gov/uc/standard_allowance']:,.2f}")
