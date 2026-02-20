#!/usr/bin/env python3
"""Migrate .rac files from old syntax to new engine syntax.

Old format (bare declarations with metadata):
    earned_income_credit:
      entity: TaxUnit
      description: "..."
      from 2024-01-01:
        adjusted = base * (1 + cola)
        return adjusted

New format (no keyword prefix, expression-based):
    earned_income_credit:
        entity: TaxUnit
        from 2024-01-01: base * (1 + cola)

Strips: description, period, dtype, unit, label, indexed_by, default,
        imports, tests, enum blocks, triple-quoted statute text.
Keeps: entity, from/to temporal values, comments.
Converts: multi-line formulas to single expressions (inlines return).
"""

import re
import sys
from pathlib import Path


# Metadata fields to strip (not supported by new parser)
STRIP_FIELDS = {
    "description",
    "period",
    "dtype",
    "unit",
    "label",
    "indexed_by",
    "default",
    "imports",
    "source",
    "tests",
}


def migrate_rac(source: str) -> str:
    """Migrate old .rac syntax to new engine syntax."""
    lines = source.split("\n")
    output: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip blank lines (preserve them)
        if not stripped:
            output.append("")
            i += 1
            continue

        # Convert triple-quoted statute text to comments
        if stripped.startswith('"""'):
            if stripped.endswith('"""') and len(stripped) > 6:
                # Single-line triple-quote
                text = stripped[3:-3].strip()
                if text:
                    output.append(f"# {text}")
            else:
                # Multi-line triple-quote block
                i += 1
                while i < len(lines):
                    inner = lines[i].strip()
                    if inner.endswith('"""'):
                        text = inner[:-3].strip()
                        if text:
                            output.append(f"# {text}")
                        break
                    if inner:
                        output.append(f"# {inner}")
                    else:
                        output.append("")
                    i += 1
            i += 1
            continue

        # Pass through comments
        if stripped.startswith("#"):
            output.append(line)
            i += 1
            continue

        # Skip enum blocks entirely
        if stripped.startswith("enum "):
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith(" ")):
                i += 1
            continue

        # Detect top-level declaration (name: at column 0, no leading space)
        decl_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*$", line)
        if decl_match:
            name = decl_match.group(1)
            i += 1
            entity, temporals = _parse_declaration_body(lines, i)
            i = _skip_declaration_body(lines, i)

            # Build new declaration
            output.append(f"{name}:")
            if entity:
                output.append(f"    entity: {entity.lower()}")
            for start_date, expr in temporals:
                output.append(f"    from {start_date}: {expr}")

            # If no temporals, add a placeholder
            if not temporals and not entity:
                output.append(f"    from 2024-01-01: 0")
            elif not temporals and entity:
                output.append(f"    from 2024-01-01: 0")

            output.append("")
            continue

        # Non-declaration line at top level (e.g., "status: obsolete")
        # Convert to comment
        if re.match(r"^[a-zA-Z_]\w*:\s+\S", line):
            output.append(f"# {stripped}")
            i += 1
            continue

        # Anything else: pass through
        output.append(line)
        i += 1

    # Clean up trailing blank lines
    while output and output[-1] == "":
        output.pop()
    output.append("")

    return "\n".join(output)


def _parse_declaration_body(
    lines: list[str], start: int
) -> tuple[str | None, list[tuple[str, str]]]:
    """Parse the indented body of an old-style declaration.

    Returns (entity, [(date, expression), ...]).
    """
    entity = None
    temporals: list[tuple[str, str]] = []
    i = start

    while i < len(lines):
        line = lines[i]
        if not line.strip() or (not line.startswith(" ") and not line.startswith("\t")):
            break
        stripped = line.strip()

        # Entity field
        entity_match = re.match(r"entity:\s*(.+)", stripped)
        if entity_match:
            entity = entity_match.group(1).strip()
            i += 1
            continue

        # Strip metadata fields
        field_match = re.match(r"(\w+):", stripped)
        if field_match and field_match.group(1) in STRIP_FIELDS:
            i += 1
            # Skip indented content under this field (e.g., imports list, tests block)
            while i < len(lines) and lines[i].strip() and _indent_level(lines[i]) > _indent_level(line):
                i += 1
            continue

        # Temporal value: from DATE: expression_or_block
        temporal_match = re.match(r"from\s+(\d{4}-\d{2}-\d{2}):\s*(.*)", stripped)
        if temporal_match:
            date_str = temporal_match.group(1)
            rest = temporal_match.group(2).strip()
            i += 1

            if rest:
                # Single-line temporal value — clean up return statements
                rest = _clean_inline_expr(rest)
                temporals.append((date_str, rest))
            else:
                # Multi-line formula block — collect all indented lines
                # (including blank lines between them)
                formula_lines = []
                base_indent = _indent_level(line)
                while i < len(lines):
                    if not lines[i].strip():
                        # Blank line — check if next non-blank is still indented
                        j = i + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines) and _indent_level(lines[j]) > base_indent:
                            i = j  # Skip blank lines, continue collecting
                            continue
                        break
                    if _indent_level(lines[i]) <= base_indent:
                        break
                    formula_lines.append(lines[i].strip())
                    i += 1
                expr = _convert_formula(formula_lines)
                if expr:
                    temporals.append((date_str, expr))
            continue

        # Anything else in the body: skip
        i += 1

    return entity, temporals


def _skip_declaration_body(lines: list[str], start: int) -> int:
    """Skip past the indented body of a declaration, return next line index."""
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            # Blank line might be inside or after the block
            # Check if next non-blank line is still indented
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and (lines[j].startswith(" ") or lines[j].startswith("\t")):
                i = j
                continue
            break
        if not line.startswith(" ") and not line.startswith("\t"):
            break
        i += 1
    return i


def _indent_level(line: str) -> int:
    """Count leading spaces."""
    return len(line) - len(line.lstrip())


def _clean_inline_expr(expr: str) -> str:
    """Clean up inline expressions: remove 'return', fix if-return patterns."""
    # "if cond: return val" -> just "val" (incomplete conditional, use as-is for now)
    m = re.match(r"if\s+(.+?):\s*return\s+(.+)", expr)
    if m:
        # Single if-return with no else: treat the condition as a guard
        # "if is_dependent: return 0" -> "if is_dependent: 0 else: 1"
        # But we don't know the else value, so we need to check if there's more context
        # For now, just strip the return
        return f"if {m.group(1)}: {m.group(2)} else: 0"
    if expr.startswith("return "):
        return expr[7:]
    return expr


def _convert_formula(lines: list[str]) -> str:
    """Convert multi-line formula to single expression.

    Handles patterns like:
        adjusted = base * (1 + cola)
        return adjusted
    ->  base * (1 + cola)

    And simpler:
        return some_expression
    ->  some_expression
    """
    if not lines:
        return ""

    # Strip comments
    lines = [l for l in lines if not l.startswith("#")]

    if not lines:
        return ""

    # Simple case: single return statement
    if len(lines) == 1:
        line = lines[0]
        if line.startswith("return "):
            return line[7:].strip()
        # Single assignment: var = expr -> expr
        assign_match = re.match(r"\w+\s*=\s*(.+)", line)
        if assign_match:
            return assign_match.group(1).strip()
        # Single expression (no return)
        return line.strip()

    # Multi-line: collect assignments and find return
    assignments: dict[str, str] = {}
    return_expr = ""

    for line in lines:
        # Skip comments
        if line.startswith("#"):
            continue

        assign_match = re.match(r"(\w+)\s*=\s*(.+)", line)
        if assign_match:
            var_name = assign_match.group(1)
            var_expr = assign_match.group(2).strip()
            assignments[var_name] = var_expr
            continue

        if line.startswith("return "):
            return_expr = line[7:].strip()
            continue

    # If return expression is just a variable name that was assigned, inline it
    if return_expr and return_expr in assignments:
        return assignments[return_expr]

    # If return expression references assigned variables, substitute
    if return_expr:
        result = return_expr
        for var_name, var_expr in assignments.items():
            # Simple substitution (word boundary)
            result = re.sub(rf"\b{var_name}\b", f"({var_expr})", result)
        return result

    # No return: use last assignment's expression
    if assignments:
        last_var = list(assignments.keys())[-1]
        return assignments[last_var]

    # Handle if/return patterns:
    # "if cond: return val1" + "return val2" -> "if cond: val1 else: val2"
    if_returns = []
    final_return = None
    remaining_assignments: dict[str, str] = {}
    for line in lines:
        if_ret = re.match(r"if\s+(.+?):\s*return\s+(.+)", line)
        if if_ret:
            if_returns.append((if_ret.group(1), if_ret.group(2)))
            continue
        if line.startswith("return "):
            final_return = line[7:].strip()
            continue
        assign_m = re.match(r"(\w+)\s*=\s*(.+)", line)
        if assign_m:
            remaining_assignments[assign_m.group(1)] = assign_m.group(2).strip()

    if if_returns and final_return is not None:
        # Substitute any assigned variables in conditions and values
        def sub_vars(expr: str) -> str:
            for var_name, var_expr in remaining_assignments.items():
                expr = re.sub(rf"\b{var_name}\b", f"({var_expr})", expr)
            return expr

        # Build nested if/else
        result = sub_vars(final_return)
        for cond, val in reversed(if_returns):
            result = f"if {sub_vars(cond)}: {sub_vars(val)} else: {result}"
        return result

    # Fallback: join all lines
    return " ".join(lines)


def migrate_file(path: Path) -> str:
    """Migrate a single .rac file. Returns the migrated content."""
    source = path.read_text()
    return migrate_rac(source)


def migrate_repo(repo_path: Path, dry_run: bool = False) -> list[Path]:
    """Migrate all .rac files in a repo."""
    rac_files = sorted(repo_path.rglob("*.rac"))
    migrated = []

    for path in rac_files:
        original = path.read_text()
        migrated_content = migrate_rac(original)

        if migrated_content != original:
            if not dry_run:
                path.write_text(migrated_content)
            migrated.append(path)
            print(f"  {'[dry-run] ' if dry_run else ''}migrated: {path}")

    return migrated


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate .rac files to new engine syntax")
    parser.add_argument("paths", nargs="+", help="Files or directories to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--validate", action="store_true", help="Validate output with new parser")
    args = parser.parse_args()

    total = 0
    errors = 0

    for p in args.paths:
        path = Path(p)
        if path.is_dir():
            files = migrate_repo(path, dry_run=args.dry_run)
            total += len(files)
        elif path.suffix == ".rac":
            result = migrate_rac(path.read_text())
            if not args.dry_run:
                path.write_text(result)
            print(f"  migrated: {path}")
            total += 1

            if args.validate:
                try:
                    from rac import parse
                    parse(result)
                    print(f"  validated: {path}")
                except Exception as e:
                    print(f"  VALIDATION ERROR: {path}: {e}")
                    errors += 1

    print(f"\n{total} files migrated, {errors} validation errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
