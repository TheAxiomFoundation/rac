#!/usr/bin/env python3
"""Cross-repo validation: parse every .rac file across all statute repos.

Run from the rac repo root:
    python scripts/validate_all.py

Or specify repo root:
    python scripts/validate_all.py --root ~/RulesFoundation

Exits 0 if all files parse, 1 if any fail.
"""

import argparse
import sys
from pathlib import Path

# Add src/ to path so we can import rac
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rac.parser import parse_file, ParseError

STATUTE_REPOS = [
    "rac-us",
    "rac-us-ny",
    "rac-us-tx",
    "rac-us-ca",
    "rac-ca",
]


def find_rac_files(repo_path: Path) -> list[Path]:
    return sorted(repo_path.rglob("*.rac"))


def validate_repo(repo_path: Path) -> tuple[int, int, list[tuple[Path, str]]]:
    """Validate all .rac files in a repo. Returns (ok, err, errors)."""
    files = find_rac_files(repo_path)
    ok = 0
    errors: list[tuple[Path, str]] = []
    for f in files:
        try:
            parse_file(f)
            ok += 1
        except (ParseError, Exception) as e:
            errors.append((f, str(e)))
    return ok, len(errors), errors


def main():
    parser = argparse.ArgumentParser(description="Validate .rac files across all statute repos")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent,
        help="Parent directory containing all repos (default: sibling of rac/)",
    )
    parser.add_argument(
        "--repos",
        nargs="+",
        default=STATUTE_REPOS,
        help=f"Repos to validate (default: {STATUTE_REPOS})",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    total_ok = 0
    total_err = 0
    all_errors: list[tuple[Path, str]] = []

    for repo_name in args.repos:
        repo_path = args.root / repo_name
        if not repo_path.exists():
            print(f"  SKIP  {repo_name} (not found at {repo_path})")
            continue

        ok, err, errors = validate_repo(repo_path)
        total_ok += ok
        total_err += err
        all_errors.extend(errors)

        status = "OK" if err == 0 else "FAIL"
        print(f"  {status:4s}  {repo_name}: {ok}/{ok + err} files parse")

        if args.verbose:
            for f, e in errors:
                print(f"        {f}: {e}")

    print()
    print(f"  Total: {total_ok}/{total_ok + total_err} files parse")

    if total_err > 0:
        print()
        print("  Errors:")
        for f, e in all_errors:
            print(f"    {f}: {e}")
        sys.exit(1)
    else:
        print("  All clear.")


if __name__ == "__main__":
    main()
