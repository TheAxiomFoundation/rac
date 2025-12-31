#!/usr/bin/env python3
"""Run the full experiment suite for the AI encoding paper.

This script runs the agentic loop on all 15 provisions and logs results.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from rac.agent import AgentTrainingLoop
from rac.oracles import MockOracle
from rac.types import Statute, TestCase


# ============================================================================
# PROVISION DEFINITIONS
# ============================================================================

PROVISIONS = {
    # Phase 1: Simple (complexity 1-3)
    "eitc_phase_in": {
        "citation": "26 USC § 32(a)(1)",
        "complexity": 2,
        "phase": 1,
        "text": """
(a) Allowance of credit
    (1) In general
    In the case of an eligible individual, there shall be allowed as a credit
    against the tax imposed by this subtitle for the taxable year an amount
    equal to the credit percentage of so much of the taxpayer's earned income
    for the taxable year as does not exceed the earned income amount.

Parameters (2024):
- 0 children: phase_in_rate=7.65%, earned_income_amount=$7,840
- 1 child: phase_in_rate=34%, earned_income_amount=$11,750
- 2 children: phase_in_rate=40%, earned_income_amount=$16,510
- 3+ children: phase_in_rate=45%, earned_income_amount=$16,510
        """,
    },
    "standard_deduction": {
        "citation": "26 USC § 63(c)",
        "complexity": 3,
        "phase": 1,
        "text": """
(c) Standard deduction
For purposes of this subtitle—
    (1) In general
    Except as otherwise provided in this subsection, the term "standard deduction" means the sum of—
        (A) the basic standard deduction, and
        (B) the additional standard deduction.
    (2) Basic standard deduction
    For purposes of paragraph (1), the basic standard deduction is—
        (A) 200 percent of the dollar amount in effect under subparagraph (C) for the taxable year in the case of—
            (i) a joint return, or
            (ii) a surviving spouse,
        (B) $12,950 in the case of a head of household, and
        (C) $6,500 in any other case.

Parameters (2024):
- Single: $14,600
- Married Filing Jointly: $29,200
- Married Filing Separately: $14,600
- Head of Household: $21,900
        """,
    },
    "ctc_base": {
        "citation": "26 USC § 24(a)",
        "complexity": 2,
        "phase": 1,
        "text": """
(a) Allowance of credit
There shall be allowed as a credit against the tax imposed by this chapter
for the taxable year with respect to each qualifying child of the taxpayer
an amount equal to $2,000.

Parameters (2024):
- Credit per qualifying child: $2,000
- Qualifying child must be under age 17
        """,
    },
    "salt_cap": {
        "citation": "26 USC § 164(b)(6)",
        "complexity": 2,
        "phase": 1,
        "text": """
(b)(6) Limitation on individual deductions for taxable years 2018 through 2025
In the case of an individual, for any taxable year beginning after December 31, 2017,
and before January 1, 2026—
    (A) the aggregate amount of taxes taken into account under paragraphs (1), (2), and (3)
    of subsection (a) and paragraph (5) of this subsection for any taxable year shall not
    exceed $10,000 ($5,000 in the case of a married individual filing a separate return).

Parameters (2024):
- Cap for Single/MFJ/HoH: $10,000
- Cap for MFS: $5,000
        """,
    },
    "savers_credit": {
        "citation": "26 USC § 25B",
        "complexity": 3,
        "phase": 1,
        "text": """
(a) Allowance of credit
In the case of an eligible individual, there shall be allowed as a credit
against the tax imposed by this subtitle an amount equal to the applicable
percentage of so much of the qualified retirement savings contributions of
the eligible individual for the taxable year as do not exceed $2,000.

(b) Applicable percentage
For purposes of this section—
    (1) Joint returns
    In the case of a joint return, the applicable percentage is—
        (A) 50% if AGI ≤ $46,000
        (B) 20% if AGI > $46,000 and ≤ $50,000
        (C) 10% if AGI > $50,000 and ≤ $76,500
        (D) 0% if AGI > $76,500

Parameters (2024, MFJ):
- 50% rate: AGI ≤ $46,000
- 20% rate: AGI $46,001-$50,000
- 10% rate: AGI $50,001-$76,500
- 0% rate: AGI > $76,500
- Max contribution: $2,000
        """,
    },

    # Phase 2: Medium (complexity 4-6)
    "eitc_full": {
        "citation": "26 USC § 32",
        "complexity": 6,
        "phase": 2,
        "text": """
26 USC § 32 - Earned Income Tax Credit (Full)

(a) Allowance of credit
    (1) In general - Credit = credit_percentage × min(earned_income, earned_income_amount)
    (2) Limitation - Credit cannot exceed: max_credit - phaseout_percentage × max(0, AGI - phaseout_start)

The credit has three regions:
1. Phase-in: Credit increases with earned income up to earned_income_amount
2. Plateau: Credit stays at maximum from earned_income_amount to phaseout_start
3. Phase-out: Credit decreases from phaseout_start to phaseout_end

Parameters (2024, Single):
- 0 children: rate=7.65%, earned_income_amount=$7,840, max_credit=$600,
              phaseout_start=$9,800, phaseout_end=$17,640, phaseout_rate=7.65%
- 1 child: rate=34%, earned_income_amount=$11,750, max_credit=$3,995,
           phaseout_start=$22,720, phaseout_end=$49,080, phaseout_rate=15.98%
- 2 children: rate=40%, earned_income_amount=$16,510, max_credit=$6,604,
              phaseout_start=$22,720, phaseout_end=$55,770, phaseout_rate=21.06%
- 3+ children: rate=45%, earned_income_amount=$16,510, max_credit=$7,430,
               phaseout_start=$22,720, phaseout_end=$59,900, phaseout_rate=21.06%

Formula:
  phase_in_credit = min(earned_income, earned_income_amount) × rate
  phase_out_reduction = max(0, max(AGI, earned_income) - phaseout_start) × phaseout_rate
  credit = max(0, min(phase_in_credit, max_credit) - phase_out_reduction)
        """,
    },
    "cdcc": {
        "citation": "26 USC § 21",
        "complexity": 5,
        "phase": 2,
        "text": """
(a) Allowance of credit
There shall be allowed as a credit against the tax the applicable percentage
of the employment-related expenses paid by such individual during the taxable year.

(b) Applicable percentage defined
The term "applicable percentage" means 35 percent reduced (but not below 20 percent)
by 1 percentage point for each $2,000 (or fraction thereof) by which the taxpayer's
adjusted gross income exceeds $15,000.

(c) Dollar limit on amount creditable
The amount of employment-related expenses which may be taken into account shall not exceed—
    (1) $3,000 if there is 1 qualifying individual, or
    (2) $6,000 if there are 2 or more qualifying individuals.

Parameters (2024):
- Base rate: 35%
- Minimum rate: 20%
- Rate reduction: 1% per $2,000 of AGI over $15,000
- Max expenses (1 qualifying individual): $3,000
- Max expenses (2+ qualifying individuals): $6,000
        """,
    },
    "ptc": {
        "citation": "26 USC § 36B",
        "complexity": 6,
        "phase": 2,
        "text": """
(a) In general
There shall be allowed as a credit the premium assistance credit amount.

(b) Premium assistance credit amount
The premium assistance credit amount is the sum of the premium assistance amounts
for all coverage months of the taxpayer.

(c) Premium assistance amount
The premium assistance amount for a coverage month is the lesser of:
    (A) the monthly premiums for such month for 1 or more qualified health plans
        in which the taxpayer enrolls, or
    (B) the excess of the adjusted monthly premium for the applicable second lowest
        cost silver plan less 1/12 of the product of the applicable percentage and
        household income.

The applicable percentage scales with income as a percentage of FPL:
- <150% FPL: 0%
- 150-200% FPL: 0% to 2%
- 200-250% FPL: 2% to 4%
- 250-300% FPL: 4% to 6%
- 300-400% FPL: 6% to 8.5%

Parameters (2024):
- FPL for single: $14,580
- Applicable percentages vary by income bracket
- Credit = max(0, SLCSP_premium - applicable_percentage × household_income / 12)
        """,
    },
    "adoption_credit": {
        "citation": "26 USC § 23",
        "complexity": 5,
        "phase": 2,
        "text": """
(a) Allowance of credit
    (1) In general
    There shall be allowed as a credit the amount of qualified adoption expenses
    paid or incurred by the taxpayer.

(b) Limitations
    (1) Dollar limitation
    The aggregate amount of qualified adoption expenses which may be taken into
    account under subsection (a) for all taxable years shall not exceed $15,950.

    (2) Income limitation
    The amount allowable as a credit under subsection (a) shall be reduced (but not
    below zero) by an amount which bears the same ratio to the amount so allowable
    as the amount by which the taxpayer's adjusted gross income exceeds $239,230
    bears to $40,000.

Parameters (2024):
- Maximum credit: $15,950
- Phaseout start: $239,230
- Phaseout range: $40,000
- Phaseout end: $279,230
- Formula: credit = min(expenses, $15,950) × max(0, 1 - (AGI - $239,230) / $40,000)
        """,
    },
    "amt_exemption": {
        "citation": "26 USC § 55(d)",
        "complexity": 5,
        "phase": 2,
        "text": """
(d) Exemption amount
For purposes of this section—
    (1) Exemption amount for taxpayers other than corporations
    In the case of a taxpayer other than a corporation, the term "exemption amount" means—
        (A) $81,300 in the case of a joint return or surviving spouse,
        (B) $52,800 in the case of an individual who is not married and is not a surviving spouse,
        (C) 50% of the dollar amount applicable under subparagraph (A) in the case of MFS.

    (2) Phase-out of exemption amount
    The exemption amount shall be reduced (but not below zero) by an amount equal to
    25 percent of the amount by which the alternative minimum taxable income exceeds—
        (A) $1,156,300 in the case of a joint return or surviving spouse,
        (B) $578,150 in the case of MFS,
        (C) $578,150 in all other cases.

Parameters (2024):
- Exemption (MFJ): $133,300, phaseout starts at $1,218,700
- Exemption (Single): $85,700, phaseout starts at $609,350
- Exemption (MFS): $66,650, phaseout starts at $609,350
- Phaseout rate: 25%
        """,
    },

    # Phase 3: Complex (complexity 7+)
    "ss_taxation": {
        "citation": "26 USC § 86",
        "complexity": 8,
        "phase": 3,
        "text": """
(a) In general
If the taxpayer's modified adjusted gross income plus one-half of social security
benefits exceeds the base amount, there shall be included in gross income the
lesser of:
    (1) one-half of the social security benefits, or
    (2) one-half of the excess of combined income over the base amount.

(b) 85% inclusion
If combined income exceeds the adjusted base amount:
    (1) 85% of benefits, or
    (2) the sum of:
        (A) the smaller of (a)(1) or (a)(2) above, plus
        (B) 85% of the excess of combined income over the adjusted base amount.

Combined income = MAGI + 0.5 × SS_benefits

Parameters (2024):
- Single: base_amount=$25,000, adjusted_base=$34,000
- MFJ: base_amount=$32,000, adjusted_base=$44,000
- MFS (living together): base_amount=$0

Taxable amount formula:
- If combined_income ≤ base_amount: $0
- If base_amount < combined_income ≤ adjusted_base: min(0.5 × benefits, 0.5 × (combined_income - base_amount))
- If combined_income > adjusted_base: min(0.85 × benefits, first_tier + 0.85 × (combined_income - adjusted_base))
        """,
    },
    "niit": {
        "citation": "26 USC § 1411",
        "complexity": 7,
        "phase": 3,
        "text": """
(a) In general
There is hereby imposed a tax equal to 3.8 percent of the lesser of—
    (1) the taxpayer's net investment income for such taxable year, or
    (2) the excess (if any) of—
        (A) the taxpayer's modified adjusted gross income for such taxable year, over
        (B) the threshold amount.

(b) Threshold amount
The term "threshold amount" means—
    (1) $250,000 in the case of a joint return or surviving spouse,
    (2) $125,000 in the case of a married individual filing separately, and
    (3) $200,000 in any other case.

Net investment income includes:
- Interest, dividends, capital gains
- Rental and royalty income
- Passive activity income

Parameters:
- Tax rate: 3.8%
- Threshold (MFJ): $250,000
- Threshold (Single): $200,000
- Threshold (MFS): $125,000
- Formula: tax = 0.038 × min(NII, max(0, MAGI - threshold))
        """,
    },
    "qbi_simple": {
        "citation": "26 USC § 199A (simplified)",
        "complexity": 7,
        "phase": 3,
        "text": """
(a) In general
There shall be allowed as a deduction an amount equal to the lesser of:
    (1) the combined qualified business income amount, or
    (2) 20 percent of taxable income minus net capital gain.

(b) Combined QBI amount
The sum of:
    (1) 20 percent of QBI from each qualified trade or business, plus
    (2) 20 percent of qualified REIT dividends and PTP income.

(d) Income threshold
For taxpayers above income thresholds, the deduction may be limited based on:
    (1) W-2 wages paid by the business, and
    (2) The unadjusted basis of qualified property.

Parameters (2024):
- Base deduction rate: 20%
- Threshold (MFJ): $364,200
- Threshold (Single): $182,100
- Phase-in range: $100,000 (MFJ), $50,000 (Single)

Simplified formula (below threshold):
- QBI_deduction = min(0.20 × QBI, 0.20 × (taxable_income - net_capital_gain))
        """,
    },
    "amt_full": {
        "citation": "26 USC § 55",
        "complexity": 10,
        "phase": 3,
        "text": """
(a) General rule
There is hereby imposed a tax equal to the excess (if any) of—
    (1) the tentative minimum tax for the taxable year, over
    (2) the regular tax for the taxable year.

(b) Tentative minimum tax
The tentative minimum tax for the taxable year is the sum of—
    (1) 26 percent of so much of the taxable excess as does not exceed $220,700
        ($110,350 in the case of MFS), plus
    (2) 28 percent of so much of the taxable excess as exceeds $220,700.

(c) Taxable excess
The taxable excess = AMTI - exemption_amount

AMTI = Regular taxable income + preference items + AMT adjustments

Exemption phases out at 25% rate above thresholds (see § 55(d)).

Parameters (2024):
- 26% bracket: $0 - $220,700 ($110,350 MFS)
- 28% bracket: above $220,700
- Exemption amounts and phaseouts per § 55(d)

Formula:
1. Calculate AMTI from taxable income + adjustments
2. Calculate exemption with phaseout
3. Calculate taxable_excess = max(0, AMTI - exemption)
4. Calculate tentative_min_tax using brackets
5. AMT = max(0, tentative_min_tax - regular_tax)
        """,
    },
    "foreign_tax_credit": {
        "citation": "26 USC § 27",
        "complexity": 9,
        "phase": 3,
        "text": """
(a) Allowance of credit
There shall be allowed as a credit the amount of foreign income taxes paid or accrued.

(b) Limitation
The credit shall not exceed the same proportion of the tax against which such credit
is taken which the taxpayer's taxable income from sources outside the United States
bears to his entire taxable income for the same taxable year.

Formula:
FTC_limit = US_tax × (foreign_source_income / worldwide_income)
Credit = min(foreign_taxes_paid, FTC_limit)

If foreign taxes paid > limit, excess can be carried back 1 year or forward 10 years.

Income must be separated into "baskets":
- General category income
- Passive category income
- Each basket has its own limitation

Parameters:
- Limitation formula applies separately to each basket
- Carryback: 1 year
- Carryforward: 10 years
        """,
    },
}


# ============================================================================
# TEST CASE GENERATORS
# ============================================================================

def generate_eitc_phase_in_cases() -> list[TestCase]:
    """Generate test cases for EITC phase-in only."""
    params = {
        0: {"rate": 0.0765, "ei_amt": 7840},
        1: {"rate": 0.34, "ei_amt": 11750},
        2: {"rate": 0.40, "ei_amt": 16510},
        3: {"rate": 0.45, "ei_amt": 16510},
    }

    cases = []
    incomes = [0, 1000, 5000, 7840, 10000, 11750, 15000, 16510, 20000]

    for i, income in enumerate(incomes):
        for n_children in [0, 1, 2, 3]:
            p = params[n_children]
            expected = min(income, p["ei_amt"]) * p["rate"]

            cases.append(TestCase(
                id=f"eitc_pi_{i}_{n_children}",
                inputs={
                    "earned_income": income,
                    "n_children": n_children,
                    "n_qualifying_children": n_children,
                    "filing_status": "SINGLE",
                },
                expected={"eitc_phase_in_credit": expected},
            ))
    return cases


def generate_standard_deduction_cases() -> list[TestCase]:
    """Generate test cases for standard deduction."""
    deductions = {
        "SINGLE": 14600,
        "JOINT": 29200,
        "MARRIED_FILING_SEPARATELY": 14600,
        "HEAD_OF_HOUSEHOLD": 21900,
    }

    cases = []
    for filing_status, expected in deductions.items():
        cases.append(TestCase(
            id=f"std_ded_{filing_status}",
            inputs={"filing_status": filing_status},
            expected={"standard_deduction": expected},
        ))
    return cases


def generate_ctc_cases() -> list[TestCase]:
    """Generate test cases for child tax credit base."""
    cases = []
    for n_children in [0, 1, 2, 3, 4, 5]:
        expected = n_children * 2000
        cases.append(TestCase(
            id=f"ctc_{n_children}",
            inputs={"n_qualifying_children": n_children},
            expected={"child_tax_credit_base": expected},
        ))
    return cases


def generate_salt_cap_cases() -> list[TestCase]:
    """Generate test cases for SALT cap."""
    cases = []
    salt_amounts = [0, 5000, 10000, 15000, 20000, 50000]

    for salt in salt_amounts:
        for filing_status in ["SINGLE", "JOINT", "MARRIED_FILING_SEPARATELY"]:
            cap = 5000 if filing_status == "MARRIED_FILING_SEPARATELY" else 10000
            expected = min(salt, cap)

            cases.append(TestCase(
                id=f"salt_{filing_status}_{salt}",
                inputs={
                    "state_and_local_taxes_paid": salt,
                    "filing_status": filing_status,
                },
                expected={"salt_deduction": expected},
            ))
    return cases


def generate_savers_credit_cases() -> list[TestCase]:
    """Generate test cases for saver's credit."""
    cases = []

    # AGI brackets for MFJ
    test_points = [
        (30000, 0.50),
        (46000, 0.50),
        (46001, 0.20),
        (50000, 0.20),
        (50001, 0.10),
        (76500, 0.10),
        (76501, 0.00),
        (100000, 0.00),
    ]

    contribution = 2000  # Max creditable contribution

    for agi, rate in test_points:
        expected = contribution * rate

        cases.append(TestCase(
            id=f"savers_{agi}",
            inputs={
                "adjusted_gross_income": agi,
                "retirement_contributions": contribution,
                "filing_status": "JOINT",
            },
            expected={"savers_credit": expected},
        ))
    return cases


def generate_eitc_full_cases() -> list[TestCase]:
    """Generate test cases for full EITC with phase-out."""
    params = {
        0: {"rate": 0.0765, "ei_amt": 7840, "max_credit": 600, "po_start": 9800, "po_end": 17640, "po_rate": 0.0765},
        1: {"rate": 0.34, "ei_amt": 11750, "max_credit": 3995, "po_start": 22720, "po_end": 49080, "po_rate": 0.1598},
        2: {"rate": 0.40, "ei_amt": 16510, "max_credit": 6604, "po_start": 22720, "po_end": 55770, "po_rate": 0.2106},
        3: {"rate": 0.45, "ei_amt": 16510, "max_credit": 7430, "po_start": 22720, "po_end": 59900, "po_rate": 0.2106},
    }

    def calc_eitc(income, n_children):
        p = params[min(n_children, 3)]
        phase_in = min(income, p["ei_amt"]) * p["rate"]
        reduction = max(0, income - p["po_start"]) * p["po_rate"]
        return max(0, min(phase_in, p["max_credit"]) - reduction)

    cases = []
    incomes = [0, 5000, 7840, 9800, 15000, 17640, 22720, 30000, 40000, 49080, 55770, 59900, 70000]

    for i, income in enumerate(incomes):
        for n_children in [0, 1, 2, 3]:
            expected = calc_eitc(income, n_children)
            cases.append(TestCase(
                id=f"eitc_full_{i}_{n_children}",
                inputs={
                    "earned_income": income,
                    "adjusted_gross_income": income,
                    "n_children": n_children,
                    "n_qualifying_children": n_children,
                    "filing_status": "SINGLE",
                },
                expected={"eitc": expected},
            ))
    return cases


def generate_cdcc_cases() -> list[TestCase]:
    """Generate test cases for child and dependent care credit."""
    cases = []

    def calc_rate(agi):
        if agi <= 15000:
            return 0.35
        reduction = min(15, (agi - 15000) // 2000 + 1)
        return max(0.20, 0.35 - reduction * 0.01)

    test_points = [
        (10000, 3000, 1),
        (15000, 3000, 1),
        (20000, 3000, 1),
        (43000, 3000, 1),  # Rate = 20%
        (50000, 6000, 2),
        (100000, 6000, 2),
    ]

    for agi, expenses, n_qualifying in test_points:
        max_exp = 3000 if n_qualifying == 1 else 6000
        rate = calc_rate(agi)
        expected = min(expenses, max_exp) * rate

        cases.append(TestCase(
            id=f"cdcc_{agi}_{n_qualifying}",
            inputs={
                "adjusted_gross_income": agi,
                "dependent_care_expenses": expenses,
                "n_qualifying_individuals": n_qualifying,
            },
            expected={"cdcc": expected},
        ))
    return cases


def generate_niit_cases() -> list[TestCase]:
    """Generate test cases for Net Investment Income Tax."""
    cases = []

    test_points = [
        ("SINGLE", 150000, 50000, 0),  # Below threshold
        ("SINGLE", 200000, 50000, 0),  # At threshold
        ("SINGLE", 250000, 50000, 1900),  # 0.038 * min(50000, 50000)
        ("SINGLE", 300000, 50000, 1900),
        ("JOINT", 200000, 100000, 0),
        ("JOINT", 250000, 100000, 0),
        ("JOINT", 300000, 100000, 1900),  # 0.038 * min(100000, 50000)
        ("JOINT", 400000, 100000, 3800),  # 0.038 * min(100000, 150000)
    ]

    for filing_status, magi, nii, expected in test_points:
        cases.append(TestCase(
            id=f"niit_{filing_status}_{magi}",
            inputs={
                "filing_status": filing_status,
                "modified_adjusted_gross_income": magi,
                "net_investment_income": nii,
            },
            expected={"niit": expected},
        ))
    return cases


def generate_ss_taxation_cases() -> list[TestCase]:
    """Generate test cases for Social Security benefit taxation."""
    cases = []

    def calc_ss_taxable(magi, benefits, filing_status):
        if filing_status == "JOINT":
            base, adjusted = 32000, 44000
        else:
            base, adjusted = 25000, 34000

        combined = magi + 0.5 * benefits

        if combined <= base:
            return 0
        elif combined <= adjusted:
            return min(0.5 * benefits, 0.5 * (combined - base))
        else:
            first_tier = min(0.5 * benefits, 0.5 * (adjusted - base))
            return min(0.85 * benefits, first_tier + 0.85 * (combined - adjusted))

    test_points = [
        ("SINGLE", 20000, 20000),  # Below base
        ("SINGLE", 30000, 20000),  # Between base and adjusted
        ("SINGLE", 50000, 20000),  # Above adjusted
        ("JOINT", 25000, 30000),
        ("JOINT", 40000, 30000),
        ("JOINT", 60000, 30000),
    ]

    for filing_status, magi, benefits in test_points:
        expected = calc_ss_taxable(magi, benefits, filing_status)
        cases.append(TestCase(
            id=f"ss_tax_{filing_status}_{magi}",
            inputs={
                "filing_status": filing_status,
                "modified_adjusted_gross_income": magi,
                "social_security_benefits": benefits,
            },
            expected={"taxable_social_security": expected},
        ))
    return cases


# Map provision IDs to their test case generators
TEST_GENERATORS = {
    "eitc_phase_in": generate_eitc_phase_in_cases,
    "standard_deduction": generate_standard_deduction_cases,
    "ctc_base": generate_ctc_cases,
    "salt_cap": generate_salt_cap_cases,
    "savers_credit": generate_savers_credit_cases,
    "eitc_full": generate_eitc_full_cases,
    "cdcc": generate_cdcc_cases,
    "niit": generate_niit_cases,
    "ss_taxation": generate_ss_taxation_cases,
    # Add more as implemented
}


# ============================================================================
# EXPERIMENT RUNNER
# ============================================================================

def run_experiment(
    provision_ids: list[str] | None = None,
    model: str = "claude-opus-4-5-20251101",
    max_iterations: int = 10,
    target_accuracy: float = 0.95,
    output_dir: str = "paper/data/runs",
    verbose: bool = True,
) -> dict:
    """Run experiments on specified provisions.

    Args:
        provision_ids: List of provision IDs to run (None = all available)
        model: Claude model to use
        max_iterations: Max iterations per provision
        target_accuracy: Target accuracy threshold
        output_dir: Directory to save results
        verbose: Print progress

    Returns:
        Dict with results for all provisions
    """
    if provision_ids is None:
        provision_ids = list(TEST_GENERATORS.keys())

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Timestamp for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results = {
        "timestamp": timestamp,
        "model": model,
        "max_iterations": max_iterations,
        "target_accuracy": target_accuracy,
        "provisions": {}
    }

    total_cost = 0.0

    for i, provision_id in enumerate(provision_ids):
        if provision_id not in PROVISIONS:
            print(f"Warning: Unknown provision {provision_id}, skipping")
            continue

        if provision_id not in TEST_GENERATORS:
            print(f"Warning: No test generator for {provision_id}, skipping")
            continue

        provision = PROVISIONS[provision_id]

        if verbose:
            print("\n" + "=" * 70)
            print(f"[{i+1}/{len(provision_ids)}] {provision['citation']}")
            print(f"Complexity: {provision['complexity']}, Phase: {provision['phase']}")
            print("=" * 70)

        # Create statute and test cases
        statute = Statute(
            citation=provision["citation"],
            text=provision["text"].strip(),
            jurisdiction="us",
        )

        test_cases = TEST_GENERATORS[provision_id]()

        if verbose:
            print(f"Test cases: {len(test_cases)}")

        # Run training loop
        loop = AgentTrainingLoop(
            model=model,
            max_iterations=max_iterations,
            target_accuracy=target_accuracy,
        )

        result = loop.train(statute, test_cases, verbose=verbose)

        # Store result
        provision_result = {
            "citation": provision["citation"],
            "complexity": provision["complexity"],
            "phase": provision["phase"],
            "n_test_cases": len(test_cases),
            "success": result["success"],
            "final_accuracy": result["final_accuracy"],
            "iterations": result["iterations"],
            "submitted": result["submitted"],
            "cost": result.get("cost", {}),
            "final_code": result.get("final_code", ""),
            "trajectory": result.get("trajectory", []),  # Full RL learning history
            "conversation": result.get("conversation", []),  # Full conversation for visualization
        }

        results["provisions"][provision_id] = provision_result
        total_cost += result.get("cost", {}).get("total_cost_usd", 0)

        if verbose:
            print(f"\nResult: {'SUCCESS' if result['success'] else 'FAILED'}")
            print(f"Accuracy: {result['final_accuracy']:.1%}")
            print(f"Iterations: {result['iterations']}")
            cost = result.get("cost", {})
            print(f"Cost: ${cost.get('total_cost_usd', 0):.4f}")

    # Summary
    results["summary"] = {
        "total_provisions": len(provision_ids),
        "successful": sum(1 for p in results["provisions"].values() if p["success"]),
        "total_cost_usd": total_cost,
        "mean_iterations": sum(p["iterations"] for p in results["provisions"].values()) / len(results["provisions"]) if results["provisions"] else 0,
    }

    # Save results
    results_file = output_path / f"experiment_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    if verbose:
        print("\n" + "=" * 70)
        print("EXPERIMENT COMPLETE")
        print("=" * 70)
        print(f"Provisions: {results['summary']['total_provisions']}")
        print(f"Successful: {results['summary']['successful']}")
        print(f"Total cost: ${results['summary']['total_cost_usd']:.4f}")
        print(f"Mean iterations: {results['summary']['mean_iterations']:.1f}")
        print(f"Results saved to: {results_file}")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run AI encoding experiments")
    parser.add_argument("--provisions", nargs="+", help="Specific provisions to run")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], help="Run all provisions from a phase")
    parser.add_argument("--model", default="claude-opus-4-5-20251101")
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--target-accuracy", type=float, default=0.95)
    parser.add_argument("--output-dir", default="paper/data/runs")
    args = parser.parse_args()

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set")
        return

    # Determine which provisions to run
    if args.provisions:
        provision_ids = args.provisions
    elif args.phase:
        provision_ids = [
            pid for pid, p in PROVISIONS.items()
            if p["phase"] == args.phase and pid in TEST_GENERATORS
        ]
    else:
        # Default: run all with test generators
        provision_ids = list(TEST_GENERATORS.keys())

    print(f"Running {len(provision_ids)} provisions: {provision_ids}")

    run_experiment(
        provision_ids=provision_ids,
        model=args.model,
        max_iterations=args.max_iterations,
        target_accuracy=args.target_accuracy,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
