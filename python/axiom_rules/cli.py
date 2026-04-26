from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .source_registry import validate_source_registries


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


def check_sources(args: argparse.Namespace) -> int:
    roots = [Path(root) for root in args.roots]
    if args.repo and len(roots) != 1:
        print("--repo can only be used with one root", file=sys.stderr)
        return 2
    total_entries = 0
    total_issues = 0
    for root in roots:
        try:
            report = validate_source_registries(
                root,
                repo=args.repo,
                bucket=args.bucket,
                verify_r2=args.verify_r2,
            )
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 2
        total_entries += len(report.entries)
        total_issues += len(report.issues)
        if report.issues:
            print(f"[FAIL] {root}")
            for issue in report.issues:
                try:
                    issue_path = issue.path.relative_to(root.resolve())
                except ValueError:
                    issue_path = issue.path
                print(f"  - {issue_path}: {issue.message}")
        elif args.verbose:
            print(f"[ok] {root}: {len(report.entries)} source registry file(s)")
            for entry in report.entries:
                print(f"  - {entry.source_id}")
                for artifact in entry.artifacts:
                    print(f"    {artifact.name}: {artifact.r2_path}")

    if total_issues:
        print(f"\nSource registry check failed with {total_issues} issue(s).")
        return 1
    print(f"\nValidated {total_entries} source registry file(s).")
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

    sources = subcommands.add_parser(
        "check-sources",
        help="Validate jurisdiction-repo sources/**/*.yaml registry files.",
    )
    sources.add_argument(
        "roots",
        nargs="+",
        help="Jurisdiction repository root(s) containing a sources/ tree.",
    )
    sources.add_argument(
        "--repo",
        help="Override the repo ID used for derived source IDs. Only valid with one root.",
    )
    sources.add_argument(
        "--bucket",
        default="axiom-sources",
        help="R2 bucket name used when deriving default artifact paths.",
    )
    sources.add_argument(
        "--verbose",
        action="store_true",
        help="Print derived source IDs and R2 paths for valid entries.",
    )
    sources.add_argument(
        "--verify-r2",
        action="store_true",
        help="Fetch derived R2 objects and verify their SHA-256 hashes.",
    )
    sources.set_defaults(func=check_sources)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
