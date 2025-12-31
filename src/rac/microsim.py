"""Cosilico Microsimulation Runner.

Loads microdata (CPS) and runs Cosilico rules to produce aggregate statistics.
"""

from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

from .vectorized_executor import VectorizedExecutor, EntityIndex
from .dsl_executor import get_default_parameters


def load_cps(path: Optional[Path] = None, year: int = 2024) -> pd.DataFrame:
    """Load CPS ASEC microdata.

    Args:
        path: Path to parquet file (default: auto-detect from cosilico-data-sources)
        year: Tax year

    Returns:
        DataFrame with person-level records
    """
    if path is None:
        # Try to find CPS data in sibling repo
        candidates = [
            Path(__file__).parents[4] / "cosilico-data-sources" / "micro" / "us" / f"cps_{year}.parquet",
            Path.home() / "CosilicoAI" / "cosilico-data-sources" / "micro" / "us" / f"cps_{year}.parquet",
        ]
        for p in candidates:
            if p.exists():
                path = p
                break
        if path is None:
            raise FileNotFoundError(f"Could not find CPS {year} data. Tried: {candidates}")

    return pd.read_parquet(path)


def construct_tax_units(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Construct tax units from CPS household structure.

    CPS contains person records within households. We identify tax units as:
    - Married couples (marital_status=1) = one joint tax unit
    - Unmarried adults (19+) = separate single tax units
    - Children (<19) = dependents, not separate tax units

    Per 26 USC §152(c) and §32(c)(3), qualifying children:
    - Age under 19 at end of year (general rule)
    - Must share principal place of abode (same household)

    Returns:
        is_primary_filer: Boolean array - True for primary filer of each tax unit
        tax_unit_earned_income: Earned income for the tax unit (combined for couples)
        tax_unit_n_children: Qualifying children count for the tax unit (capped at 3)
        tax_unit_filing_status: 'JOINT' or 'SINGLE'
    """
    age_limit = 19  # §152(c)(3)(A) - under 19 at end of year

    age = df["age"].values
    marital = df.get("marital_status", pd.Series(0, index=df.index)).fillna(0).values
    earned = (
        df.get("wage_salary_income", pd.Series(0, index=df.index)).fillna(0).values
        + df.get("self_employment_income", pd.Series(0, index=df.index)).fillna(0).values
    )
    household_id = df["household_id"].values

    # Initialize output arrays
    n = len(df)
    is_primary_filer = np.zeros(n, dtype=bool)
    tax_unit_earned_income = np.zeros(n)
    tax_unit_n_children = np.zeros(n, dtype=int)
    tax_unit_filing_status = np.array(["SINGLE"] * n, dtype=object)

    # Process each household
    for hh_id in df["household_id"].unique():
        hh_mask = household_id == hh_id
        hh_idx = np.where(hh_mask)[0]
        hh_ages = age[hh_mask]
        hh_married = marital[hh_mask]
        hh_earned = earned[hh_mask]

        # Count children in this household
        n_children_in_hh = int((hh_ages < age_limit).sum())

        # Identify adults
        adult_mask = hh_ages >= age_limit
        adult_idx = hh_idx[adult_mask]

        if len(adult_idx) == 0:
            continue

        # Check for married couples (marital_status=1 means married, spouse present)
        married_idx = [i for i in adult_idx if marital[i] == 1]

        if len(married_idx) >= 2:
            # Married couple: use oldest as primary filer, combine income
            married_ages = [(i, age[i]) for i in married_idx]
            married_ages.sort(key=lambda x: -x[1])  # Sort by age descending
            primary = married_ages[0][0]
            spouse = married_ages[1][0]

            is_primary_filer[primary] = True
            tax_unit_earned_income[primary] = earned[primary] + earned[spouse]
            tax_unit_n_children[primary] = min(n_children_in_hh, 3)
            tax_unit_filing_status[primary] = "JOINT"

            # Handle any additional unmarried adults in same household
            # (e.g., adult children, grandparents living with family)
            unmarried_idx = [i for i in adult_idx if marital[i] != 1]
            for i in unmarried_idx:
                is_primary_filer[i] = True
                tax_unit_earned_income[i] = earned[i]
                tax_unit_n_children[i] = 0  # Children assigned to married couple
                tax_unit_filing_status[i] = "SINGLE"
        else:
            # No married couple - each adult is own tax unit
            # Assign children to adult with highest earned income (most likely to claim)
            adult_earned = [earned[i] for i in adult_idx]
            primary_earner_idx = adult_idx[np.argmax(adult_earned)]
            for i in adult_idx:
                is_primary_filer[i] = True
                tax_unit_earned_income[i] = earned[i]
                if i == primary_earner_idx:
                    tax_unit_n_children[i] = min(n_children_in_hh, 3)
                else:
                    tax_unit_n_children[i] = 0
                tax_unit_filing_status[i] = "JOINT" if marital[i] == 1 else "SINGLE"

    return is_primary_filer, tax_unit_earned_income, tax_unit_n_children, tax_unit_filing_status


def derive_qualifying_children(df: pd.DataFrame) -> np.ndarray:
    """Derive qualifying children count from CPS household structure.

    Per 26 USC §152(c) and §32(c)(3):
    - Age under 19 at end of year (general rule)
    - Age under 24 if full-time student (we can't verify student status in CPS)
    - Must share principal place of abode (same household)

    This is a simplified version. Use construct_tax_units() for full tax unit modeling.

    Returns array of qualifying children count per person record.
    """
    _, _, n_children, _ = construct_tax_units(df)
    return n_children


def map_cps_to_inputs(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Map CPS columns to Cosilico input variables.

    CPS provides person-level records within households. We construct tax units
    and map income/demographic data to variables needed by Cosilico DSL formulas.
    """
    # Construct tax units from household structure
    is_primary_filer, tax_unit_earned, tax_unit_children, tax_unit_status = construct_tax_units(df)

    inputs = {}

    # Tax unit structure
    inputs["is_tax_unit_head"] = is_primary_filer.astype(float)

    # Income variables (individual level)
    inputs["wages"] = df.get("wage_salary_income", pd.Series(0, index=df.index)).fillna(0).values
    inputs["salaries"] = np.zeros(len(df))  # Included in wages
    inputs["tips"] = np.zeros(len(df))  # Not separately reported
    inputs["self_employment_income"] = df.get("self_employment_income", pd.Series(0, index=df.index)).fillna(0).values

    # Investment income
    inputs["interest_income"] = np.zeros(len(df))  # Not in simplified CPS extract
    inputs["dividend_income"] = np.zeros(len(df))
    inputs["capital_gains"] = np.zeros(len(df))
    inputs["other_income"] = np.zeros(len(df))

    # Tax unit level income (combined for married couples)
    inputs["tax_unit_earned_income"] = tax_unit_earned
    inputs["earned_income"] = inputs["wages"] + inputs["self_employment_income"]

    # Demographics
    inputs["age"] = df.get("age", pd.Series(30, index=df.index)).fillna(30).values

    # Qualifying children - from tax unit construction per §152(c)
    inputs["count_qualifying_children"] = tax_unit_children

    # Filing status from tax unit construction
    inputs["filing_status"] = tax_unit_status

    # Weights
    inputs["weight"] = df.get("weight", pd.Series(1.0, index=df.index)).fillna(1.0).values

    return inputs


def run_microsim(
    year: int = 2024,
    cps_path: Optional[Path] = None,
    variables: Optional[list[str]] = None,
    sample_size: Optional[int] = None,
) -> dict:
    """Run microsimulation on CPS data.

    Args:
        year: Tax year
        cps_path: Path to CPS parquet (default: auto-detect)
        variables: Variables to compute (default: AGI, EITC)
        sample_size: Limit to N records for testing

    Returns:
        Dict with aggregate statistics
    """
    # Load data
    df = load_cps(cps_path, year)
    if sample_size:
        df = df.head(sample_size)

    print(f"Loaded {len(df):,} person records")
    print(f"Weighted population: {df['weight'].sum():,.0f}")

    # Map to inputs
    inputs = map_cps_to_inputs(df)

    # Default variables
    if variables is None:
        variables = ["adjusted_gross_income"]

    # Load DSL code from cosilico-us (country-specific statutes)
    # NOT from cosilico-engine/statute (which should only have test fixtures)
    statute_candidates = [
        Path(__file__).parents[4] / "cosilico-us",  # From cosilico-engine/src/cosilico/
        Path.home() / "CosilicoAI" / "cosilico-us",
    ]
    statute_dir = None
    for p in statute_candidates:
        if p.exists():
            statute_dir = p
            break

    if statute_dir is None:
        raise FileNotFoundError(
            f"Could not find cosilico-us statute repo. Tried: {statute_candidates}\n"
            "Statute files must be in cosilico-us, NOT cosilico-engine."
        )

    dsl_code = ""

    # Load AGI formula from cosilico-us
    agi_path = statute_dir / "statute" / "26" / "62" / "a" / "adjusted_gross_income.rac"
    if agi_path.exists():
        dsl_code = agi_path.read_text()
    else:
        # Inline simplified formula as fallback (v2 syntax)
        dsl_code = """
variable adjusted_gross_income:
  entity Person
  period Year
  dtype Money

  formula: |
    return wages + salaries + tips + self_employment_income + interest_income + dividend_income + capital_gains + other_income
"""

    # Create executor
    executor = VectorizedExecutor(
        parameters=get_default_parameters(),
        n_workers=1,
    )

    # Execute
    import time
    start = time.time()

    results = executor.execute(
        code=dsl_code,
        inputs=inputs,
        output_variables=variables,
    )

    elapsed = time.time() - start

    # Compute aggregates
    weights = inputs["weight"]
    total_weight = weights.sum()

    aggregates = {
        "meta": {
            "year": year,
            "n_records": len(df),
            "weighted_population": float(total_weight),
            "elapsed_seconds": elapsed,
            "records_per_second": len(df) / elapsed,
        },
        "variables": {},
    }

    for var_name, values in results.items():
        weighted_total = float((values * weights).sum())
        weighted_mean = weighted_total / total_weight if total_weight > 0 else 0

        aggregates["variables"][var_name] = {
            "total": weighted_total,
            "mean": weighted_mean,
            "min": float(values.min()),
            "max": float(values.max()),
            "median": float(np.median(values)),
            "nonzero_count": int((values > 0).sum()),
            "nonzero_pct": float((values > 0).mean() * 100),
        }

    return aggregates


def main():
    """CLI entry point."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Run Cosilico microsimulation")
    parser.add_argument("--year", type=int, default=2024, help="Tax year")
    parser.add_argument("--sample", type=int, help="Sample size for testing")
    parser.add_argument("--variables", nargs="+", default=["adjusted_gross_income"], help="Variables to compute")
    args = parser.parse_args()

    results = run_microsim(
        year=args.year,
        sample_size=args.sample,
        variables=args.variables,
    )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
