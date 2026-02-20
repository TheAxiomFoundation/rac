"""Cross-repo validation: parse every .rac file across all statute repos.

Usage:
    rac-validate-all
    rac-validate-all --root ~/RulesFoundation
    rac-validate-all --repos rac-us rac-ca -v
"""

import argparse
import sys
from pathlib import Path

from .parser import ParseError, parse_file

STATUTE_REPOS = [
    "rac-us",
    "rac-us-ny",
    "rac-us-tx",
    "rac-us-ca",
    "rac-ca",
]


def _default_root() -> Path:
    """Walk up from cwd looking for a directory containing statute repos."""
    cwd = Path.cwd()
    # If we're inside the rac repo, parent is the org directory
    for candidate in [cwd.parent, cwd, Path.home() / "RulesFoundation"]:
        if any((candidate / repo).exists() for repo in STATUTE_REPOS):
            return candidate
    return cwd.parent


def validate_repo(repo_path: Path) -> tuple[int, int, list[tuple[Path, str]]]:
    """Validate all .rac files in a repo. Returns (ok, err, errors)."""
    files = sorted(repo_path.rglob("*.rac"))
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
        default=None,
        help="Parent directory containing all repos (auto-detected if omitted)",
    )
    parser.add_argument(
        "--repos",
        nargs="+",
        default=STATUTE_REPOS,
        help=f"Repos to validate (default: {STATUTE_REPOS})",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    root = args.root or _default_root()

    total_ok = 0
    total_err = 0
    all_errors: list[tuple[Path, str]] = []

    for repo_name in args.repos:
        repo_path = root / repo_name
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
