#!/usr/bin/env python3
"""Convert legacy `rules.rac` programme files to RuleSpec `rules.yaml`.

This is intentionally a one-way source migration helper, not a general `.rac`
parser. The deployed grammar remains in Rust; this script handles the programme
block shape used by the repository fixtures and preserves formula text verbatim.
If a companion `rules.rac.test` file exists, it is renamed to
`rules.test.yaml`; the test-file body is already YAML-shaped.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class LiteralString(str):
    pass


class RuleSpecDumper(yaml.SafeDumper):
    def increase_indent(
        self, flow: bool = False, indentless: bool = False
    ) -> None:  # pragma: no cover - PyYAML formatting hook
        return super().increase_indent(flow, False)


def _represent_literal(dumper: RuleSpecDumper, data: LiteralString) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


RuleSpecDumper.add_representer(LiteralString, _represent_literal)

DOCSTRING_RE = re.compile(r'"""(.*?)"""', re.DOTALL)
DECL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_./-]*):\s*$")
FROM_RE = re.compile(
    r"^\s{4}from\s+(\d{4}-\d{2}-\d{2})(?:\s+to\s+(\d{4}-\d{2}-\d{2}))?:\s*(.*)$"
)
META_RE = re.compile(r"^\s{4}([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
METADATA_KEYS = {
    "entity",
    "dtype",
    "period",
    "unit",
    "source",
    "source_url",
    "label",
    "description",
    "default",
    "indexed_by",
    "status",
}


@dataclass
class Version:
    effective_from: str
    effective_to: str | None
    formula: str


@dataclass
class Rule:
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    versions: list[Version] = field(default_factory=list)


def _scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    try:
        loaded = yaml.safe_load(value)
    except yaml.YAMLError:
        return value
    if isinstance(loaded, (str, int, float, bool)) or loaded is None:
        return loaded
    return value


def _extract_summary(source: str) -> str | None:
    match = DOCSTRING_RE.search(source)
    if match is None:
        return None
    summary = match.group(1).strip()
    return summary or None


def _without_comments_and_docstrings(source: str) -> list[str]:
    source = DOCSTRING_RE.sub("", source)
    lines: list[str] = []
    for line in source.splitlines():
        if line.strip().startswith("#"):
            continue
        lines.append(line.rstrip())
    return lines


def parse_rac(source: str) -> tuple[str | None, list[Rule]]:
    summary = _extract_summary(source)
    lines = _without_comments_and_docstrings(source)
    rules: list[Rule] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        decl = DECL_RE.match(line)
        if decl is None:
            raise ValueError(f"unexpected top-level line {i + 1}: {line!r}")

        rule = Rule(name=decl.group(1))
        i += 1
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if DECL_RE.match(line):
                break

            from_match = FROM_RE.match(line)
            if from_match is not None:
                start, end, inline_formula = from_match.groups()
                i += 1
                if inline_formula.strip():
                    formula = inline_formula.strip()
                else:
                    formula_lines: list[str] = []
                    while i < len(lines):
                        next_line = lines[i]
                        if not next_line.strip():
                            formula_lines.append("")
                            i += 1
                            continue
                        if DECL_RE.match(next_line) or FROM_RE.match(next_line):
                            break
                        meta = META_RE.match(next_line)
                        if meta is not None and meta.group(1) in METADATA_KEYS:
                            break
                        formula_lines.append(
                            next_line[8:] if next_line.startswith(" " * 8) else next_line.strip()
                        )
                        i += 1
                    while formula_lines and formula_lines[-1] == "":
                        formula_lines.pop()
                    formula = "\n".join(formula_lines)
                rule.versions.append(Version(start, end, formula))
                continue

            meta = META_RE.match(line)
            if meta is None or meta.group(1) not in METADATA_KEYS:
                raise ValueError(f"unexpected rule line {i + 1}: {line!r}")
            key, value = meta.groups()
            if key == "status":
                # Top-level status was previously accepted as authoring metadata
                # but ignored by the Rust loader. Preserve rule status only if
                # it appears inside a rule block.
                rule.metadata[key] = _scalar(value)
            else:
                rule.metadata[key] = _scalar(value)
            i += 1

        if not rule.versions:
            raise ValueError(f"rule `{rule.name}` has no `from` versions")
        rules.append(rule)

    return summary, rules


def _module_id(path: Path, root: Path) -> str:
    try:
        parent = path.parent.relative_to(root)
    except ValueError:
        parent = path.parent
    return ".".join(parent.parts)


def _rule_to_yaml(rule: Rule) -> dict[str, Any]:
    output: dict[str, Any] = {"name": rule.name}
    entity = rule.metadata.get("entity")
    output["kind"] = "derived" if entity else "parameter"
    for key in [
        "entity",
        "dtype",
        "period",
        "unit",
        "label",
        "description",
        "default",
        "indexed_by",
        "status",
        "source",
        "source_url",
    ]:
        if key in rule.metadata and rule.metadata[key] not in (None, ""):
            output[key] = rule.metadata[key]

    versions: list[dict[str, Any]] = []
    for version in rule.versions:
        formula: str | LiteralString = version.formula
        if "\n" in formula:
            formula = LiteralString(formula)
        item: dict[str, Any] = {
            "effective_from": version.effective_from,
            "formula": formula,
        }
        if version.effective_to:
            item["effective_to"] = version.effective_to
        versions.append(item)
    output["versions"] = versions
    return output


def convert_file(path: Path, *, root: Path) -> tuple[Path, Path | None]:
    source = path.read_text()
    summary, rules = parse_rac(source)
    document: dict[str, Any] = {
        "format": "rulespec/v1",
        "module": {
            "id": _module_id(path, root),
        },
        "rules": [_rule_to_yaml(rule) for rule in rules],
    }
    if summary:
        document["module"]["summary"] = LiteralString(summary)

    output_path = path.with_suffix(".yaml")
    output_path.write_text(
        yaml.dump(
            document,
            Dumper=RuleSpecDumper,
            sort_keys=False,
            width=1000,
            allow_unicode=True,
        ),
    )
    companion_test = path.with_suffix(".rac.test")
    output_test = None
    if companion_test.exists():
        output_test = path.with_name("rules.test.yaml")
        output_test.write_text(companion_test.read_text())
    return output_path, output_test


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path("programmes"))
    args = parser.parse_args()

    paths = args.paths or sorted(args.root.rglob("rules.rac"))
    for path in paths:
        output_path, output_test = convert_file(path, root=args.root)
        print(f"{path} -> {output_path}")
        if output_test is not None:
            print(f"{path.with_suffix('.rac.test')} -> {output_test}")


if __name__ == "__main__":
    main()
