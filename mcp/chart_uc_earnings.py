"""Plot UC monthly award against monthly earnings for a fixed household profile.

Runs the Axiom Rules Engine once per £100/month earnings step and charts the result.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import matplotlib.pyplot as plt

from axiom_rules_mcp.server import evaluate

OUTPUT = Path(__file__).parent / "uc_chart.png"


def run(earned: int) -> tuple[Decimal, Decimal]:
    response = evaluate(
        "universal_credit",
        {
            "period": {"start": "2025-05-01", "end": "2025-05-31"},
            "is_couple": False,
            "has_housing_costs": True,
            "eligible_housing_costs": "1200",
            "non_dep_deductions_total": "0",
            "earned_income_monthly": str(earned),
            "unearned_income_monthly": "0",
            "capital_total": "0",
            "adults": [
                {"age_25_or_over": False, "has_lcwra": False, "is_carer": False}
            ],
            "children": [],
        },
        include_trace=False,
    )
    outputs = response["outputs"]
    return Decimal(outputs["max_uc"]["value"]), Decimal(outputs["uc_award"]["value"])


def main() -> None:
    earnings = list(range(0, 3001, 100))
    max_uc: list[Decimal] = []
    award: list[Decimal] = []
    for e in earnings:
        m, a = run(e)
        max_uc.append(m)
        award.append(a)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(earnings, [float(x) for x in max_uc], label="Max UC (before income)",
            linestyle="--", color="#888")
    ax.plot(earnings, [float(x) for x in award], label="UC award", linewidth=2.2,
            color="#0b5fa5")
    ax.fill_between(earnings, [float(x) for x in award], alpha=0.15, color="#0b5fa5")
    ax.set_xlabel("Monthly earnings (£)")
    ax.set_ylabel("Monthly UC (£)")
    ax.set_title("UC award vs earnings — 24-yr-old single, London, £1,200 rent")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    ax.set_xlim(0, 3000)
    ax.set_ylim(0, max(float(x) for x in max_uc) * 1.1)

    # annotate: taper-off point (first earnings where award == 0)
    taper_off = next((e for e, a in zip(earnings, award) if a == 0), None)
    if taper_off is not None:
        ax.axvline(taper_off, color="#aa3333", linewidth=1, linestyle=":")
        ax.annotate(
            f"Tapered to zero at £{taper_off:,}/month",
            xy=(taper_off, 0), xytext=(taper_off + 40, max(float(x) for x in max_uc) * 0.4),
            color="#aa3333", fontsize=9,
            arrowprops=dict(arrowstyle="->", color="#aa3333"),
        )

    fig.tight_layout()
    fig.savefig(OUTPUT, dpi=150)
    print(f"saved: {OUTPUT}")

    # Print a compact table too
    print(f"{'earnings':>10} {'max_uc':>10} {'award':>10}")
    for e, m, a in zip(earnings, max_uc, award):
        print(f"{e:>10} {str(m):>10} {str(a):>10}")


if __name__ == "__main__":
    main()
