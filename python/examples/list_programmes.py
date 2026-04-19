#!/usr/bin/env python3
# ruff: noqa: E402
"""List programmes in the `programmes/` tree and show glob-selection in action.

Identity is the directory path of each `rules.yaml` relative to the scan
root: `programmes/uksi/2013/376/rules.yaml` → `uksi/2013/376`. No tags, no
separate registry — the filesystem layout *is* the taxonomy.

Usage:
    uv run python python/examples/list_programmes.py              # list all
    uv run python python/examples/list_programmes.py 'ukpga/**'   # filter
    uv run python python/examples/list_programmes.py 'uksi/2013/**' 'ssi/**'
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import ProgrammeRegistry

CONSOLE = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "patterns",
        nargs="*",
        help="Glob patterns to filter identities; no args = list all.",
    )
    parser.add_argument(
        "--root",
        default=str(ROOT / "programmes"),
        help="Root directory to scan for rules.yaml files.",
    )
    args = parser.parse_args()

    registry = ProgrammeRegistry.from_root(args.root)
    selected = registry.select(*args.patterns) if args.patterns else registry

    title = (
        f"Programmes matching {args.patterns}" if args.patterns else "All programmes"
    )
    table = Table(title=title, show_lines=False)
    table.add_column("identity", style="cyan", no_wrap=True)
    table.add_column("path", style="dim")

    for entry in selected:
        table.add_row(entry.identity, str(entry.path.relative_to(ROOT)))

    CONSOLE.print(table)
    CONSOLE.print(
        f"[bold]{len(selected)}[/bold] of {len(registry)} programmes selected."
    )


if __name__ == "__main__":
    main()
