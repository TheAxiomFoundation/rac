#!/usr/bin/env python3
"""CI wrapper for case runners under python/examples/.

The standard runners print per-case "matches expected" / "differs from
expected" lines but do not `sys.exit(1)` on mismatch, so a green CI
return code can hide failing cases. This wrapper runs each listed runner
and fails CI if any runner exits non-zero or prints a failure marker.

Excludes:
  * run_*_benchmark.py — require maturin-built in-process bindings
  * run_household_demo.py — informational demo, no expected-output check
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "python" / "examples"

RUNNERS = [
    # Keep CI on runners whose fixtures and input builders are migrated to RuleSpec.
    # Restore the stale/missing-fixture runners as those examples are repaired.
    "run_snap_cases.py",
    "run_child_benefit_cases.py",
    "run_ated_cases.py",
    "run_auto_enrolment_cases.py",
    "run_ct_marginal_relief_cases.py",
]

FAILURE_MARKERS = (
    "differs from expected",
    "mismatch",
    "[fail]",
)


def main() -> None:
    failures: list[str] = []
    for runner in RUNNERS:
        path = EXAMPLES / runner
        if not path.exists():
            print(f"[skip] {runner} not present")
            continue
        print(f"\n=== {runner} ===")
        proc = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
        )
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            failures.append(f"{runner}: exit {proc.returncode}")
        elif any(m in proc.stdout.lower() for m in FAILURE_MARKERS):
            failures.append(f"{runner}: output contains a failure marker")

    print()
    if failures:
        print("CI FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"All {len(RUNNERS)} runners passed.")


if __name__ == "__main__":
    main()
