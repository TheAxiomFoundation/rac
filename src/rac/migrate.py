"""Strip a keyword prefix from all .rac files across statute repos.

Usage:
    rac-migrate variable
    rac-migrate variable --apply
    rac-migrate variable --repos rac-us rac-ca --apply
"""

import argparse
import re
import sys
from pathlib import Path

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
    for candidate in [cwd.parent, cwd, Path.home() / "RulesFoundation"]:
        if any((candidate / repo).exists() for repo in STATUTE_REPOS):
            return candidate
    return cwd.parent


def strip_keyword(content: str, keyword: str) -> tuple[str, int]:
    """Strip keyword prefix from lines. Returns (new_content, count)."""
    pattern = re.compile(rf"^{re.escape(keyword)}\s+", re.MULTILINE)
    new_content, count = pattern.subn("", content)
    return new_content, count


def main():
    parser = argparse.ArgumentParser(description="Strip keyword prefix from .rac files")
    parser.add_argument("keyword", help="Keyword to strip (e.g. 'variable')")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Parent directory containing all repos (auto-detected if omitted)",
    )
    parser.add_argument("--repos", nargs="+", default=STATUTE_REPOS)
    parser.add_argument(
        "--apply", action="store_true", help="Actually write changes (default: dry run)"
    )
    args = parser.parse_args()

    root = args.root or _default_root()
    total_files = 0
    total_replacements = 0

    for repo_name in args.repos:
        repo_path = root / repo_name
        if not repo_path.exists():
            print(f"  SKIP  {repo_name} (not found)")
            continue

        repo_files = 0
        repo_replacements = 0

        for f in sorted(repo_path.rglob("*.rac")):
            content = f.read_text()
            new_content, count = strip_keyword(content, args.keyword)
            if count > 0:
                repo_files += 1
                repo_replacements += count
                if args.apply:
                    f.write_text(new_content)

        if repo_replacements > 0:
            status = "WRITE" if args.apply else "DRY"
            print(f"  {status:5s}  {repo_name}: {repo_replacements} in {repo_files} files")

        total_files += repo_files
        total_replacements += repo_replacements

    print()
    print(f"  Total: {total_replacements} replacements in {total_files} files")
    if not args.apply and total_replacements > 0:
        print("  Run with --apply to write changes.")


if __name__ == "__main__":
    main()
