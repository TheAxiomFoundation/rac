from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "python" / "examples"

FAILURE_MARKERS = (
    "differs from expected",
    "mismatch",
    "[fail]",
)


@dataclass(frozen=True)
class RunnerResult:
    name: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def failed(self) -> bool:
        return self.returncode != 0 or any(
            marker in self.stdout.lower() for marker in FAILURE_MARKERS
        )


def discover_case_runners(examples_dir: Path = EXAMPLES) -> list[Path]:
    return sorted(examples_dir.glob("run_*_cases.py"))


def run_case_runner(path: Path) -> RunnerResult:
    proc = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        cwd=ROOT,
        text=True,
    )
    return RunnerResult(path.name, proc.returncode, proc.stdout, proc.stderr)


def check_examples(args: argparse.Namespace) -> int:
    runners = discover_case_runners(Path(args.examples_dir))
    if args.only:
        selected = set(args.only)
        runners = [runner for runner in runners if runner.name in selected]

    if not runners:
        print("No case runners found.")
        return 1

    failures: list[RunnerResult] = []
    for runner in runners:
        result = run_case_runner(runner)
        status = "ok" if not result.failed else "FAIL"
        print(f"[{status}] {result.name}")
        if args.verbose or result.failed:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
        if result.failed:
            failures.append(result)

    if failures:
        print("\nExample case check failed:")
        for failure in failures:
            reason = (
                f"exit {failure.returncode}"
                if failure.returncode != 0
                else "output contains a failure marker"
            )
            print(f"  - {failure.name}: {reason}")
        return 1

    print(f"\nAll {len(runners)} case runners passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m axiom_rules.cli")
    subcommands = parser.add_subparsers(dest="command", required=True)

    check = subcommands.add_parser(
        "check-examples",
        help="Run every python/examples/run_*_cases.py runner and fail on mismatches.",
    )
    check.add_argument(
        "--examples-dir",
        default=str(EXAMPLES),
        help="Directory containing run_*_cases.py files.",
    )
    check.add_argument(
        "--only",
        action="append",
        help="Run only a named runner, e.g. --only run_snap_cases.py.",
    )
    check.add_argument(
        "--verbose",
        action="store_true",
        help="Print runner stdout/stderr even when the runner succeeds.",
    )
    check.set_defaults(func=check_examples)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
