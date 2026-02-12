"""Structural validators for .rac files.

Provides schema validation (allowed attributes, entities, dtypes) and
import resolution / cycle detection. These are generic validators that
work on any jurisdiction's .rac files.

CLI usage:
    python -m rac.validate schema <statute_dir>
    python -m rac.validate imports <statute_dir>
    python -m rac.validate all <statute_dir>
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Schema validation constants
# ---------------------------------------------------------------------------

VALID_ENTITIES = {
    "Person",
    "TaxUnit",
    "Household",
    "Family",
    "TanfUnit",
    "SnapUnit",
    "SPMUnit",
    "Corporation",
    "Business",
    "Asset",
}
VALID_PERIODS = {"Year", "Month", "Week", "Day"}
VALID_DTYPES = {
    "Money",
    "Rate",
    "Boolean",
    "Integer",
    "Count",
    "String",
    "Decimal",
    "Float",
}

ALLOWED_ATTRIBUTES = {
    "entity",
    "period",
    "dtype",
    "unit",
    "label",
    "description",
    "formula",
    "default",
    "defined_for",
    "imports",
    "parameters",
    "exports",
    "examples",
    "variable",
    "input",
    "enum",
    "values",
    "parameter",
    "function",
    "text",
    "tests",
}

CODE_KEYWORDS = {
    "if",
    "else",
    "return",
    "for",
    "break",
    "and",
    "or",
    "not",
    "in",
}

ENTITY_PATTERN = re.compile(r"^\s*entity:\s*(\w+)")
PERIOD_PATTERN = re.compile(
    r"^\s*period:\s*(Year|Month|Week|Day|[A-Z][a-z]+)$"
)
DTYPE_PATTERN = re.compile(r"^\s*dtype:\s*(\w+)")
PARAMETER_PATTERN = re.compile(r"^parameter\s+(\w+):")
LEGISLATION_ANTIPATTERNS = [
    (r"pre_tcja|post_tcja|tcja_", "TCJA"),
    (r"pre_aca|post_aca|aca_", "ACA"),
    (r"pre_arpa|post_arpa|arpa_", "ARPA"),
    (r"pre_arra|post_arra|arra_", "ARRA"),
    (r"pre_tra|post_tra|tra97_|tra01_", "TRA"),
    (
        r"_2017_|_2018_|_2019_|_2020_|_2021_|_2022_|_2023_|_2024_",
        "year",
    ),
]
FORMULA_START = re.compile(r"^\s*formula:\s*\|")
FORMULA_LINE = re.compile(r"^\s{4,}")
TEMPORAL_ENTRY_PATTERN = re.compile(r"^\s+from\s+\d{4}-\d{2}-\d{2}:")
BARE_DEFINITION_PATTERN = re.compile(r"^([a-z_][a-z0-9_]*):\s*(?!\|)")

LITERAL_PATTERN = re.compile(
    r"""
    (?<![a-zA-Z_\d])  # Not preceded by identifier char or digit
    (
        \d+\.\d+      # Float like 0.075
        |
        [4-9]         # Single digit 4-9
        |
        [1-9]\d+      # Multi-digit starting with 1-9 (10+)
    )
    (?![a-zA-Z_\d])   # Not followed by identifier char or digit
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# Import validation constants
# ---------------------------------------------------------------------------

IMPORTS_BLOCK_PATTERN = re.compile(r"^\s*imports:\s*(.*)$")
IMPORTS_LIST_PATTERN = re.compile(r"^\s*-\s*(.+)$")
IMPORT_PATTERN = re.compile(r"([^#\s\[\]]+)#(\w+)(?:\s+as\s+\w+)?")

# Old syntax: "variable name:" / "input name:" / "parameter name:"
VARIABLE_DEF_PATTERN = re.compile(r"^(variable|input)\s+(\w+):")
PARAMETER_DEF_PATTERN = re.compile(r"^parameter\s+(\w+):")
# Unified syntax: bare "name:" at column 0
BARE_DEF_PATTERN = re.compile(r"^([a-z_][a-z0-9_]*):")
STRUCTURAL_KEYWORDS = {
    "imports",
    "text",
    "tests",
    "exports",
    "parameters",
    "enum",
    "function",
}


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def _validate_schema_file(filepath: Path) -> list[str]:
    """Validate a single .rac file against the schema."""
    errors: list[str] = []
    content = filepath.read_text()
    lines = content.split("\n")

    in_code_section = False
    in_formula = False
    in_multiline_string = False

    for lineno, line in enumerate(lines, 1):
        if '"""' in line:
            count = line.count('"""')
            if count == 1:
                in_multiline_string = not in_multiline_string
            continue
        if in_multiline_string:
            continue

        if FORMULA_START.match(line):
            in_formula = True
            continue
        elif in_formula and not FORMULA_LINE.match(line) and line.strip():
            in_formula = False

        if in_formula:
            code_line = re.sub(r"#.*$", "", line)
            code_line = re.sub(r"['\"].*?['\"]", "", code_line)

            for match in LITERAL_PATTERN.finditer(code_line):
                literal = match.group(1)
                try:
                    val = float(literal)
                    if val in {-1.0, 0.0, 1.0, 2.0, 3.0}:
                        continue
                except ValueError:  # pragma: no cover
                    pass  # regex only matches valid numeric patterns
                errors.append(
                    f"{filepath}:{lineno}: hardcoded literal '{literal}' "
                    f"- use a parameter instead"
                )

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if TEMPORAL_ENTRY_PATTERN.match(line):
            continue

        param_match = PARAMETER_PATTERN.match(stripped)
        if param_match:
            param_name = param_match.group(1)
            for pattern, legislation in LEGISLATION_ANTIPATTERNS:
                if re.search(pattern, param_name, re.IGNORECASE):
                    errors.append(
                        f"{filepath}:{lineno}: parameter '{param_name}' "
                        f"references {legislation} - use time-varying values "
                        f"instead (e.g., 2017-12-15: new_value)"
                    )

        entity_match = ENTITY_PATTERN.match(line)
        if entity_match:
            entity = entity_match.group(1)
            if entity not in VALID_ENTITIES:
                errors.append(
                    f"{filepath}:{lineno}: invalid entity '{entity}' "
                    f"(must be one of: {sorted(VALID_ENTITIES)})"
                )

        period_match = PERIOD_PATTERN.match(line)
        if period_match:
            period = period_match.group(1)
            if period not in VALID_PERIODS:
                errors.append(
                    f"{filepath}:{lineno}: invalid period '{period}' "
                    f"(must be one of: {sorted(VALID_PERIODS)})"
                )

        dtype_match = DTYPE_PATTERN.match(line)
        if dtype_match:
            dtype = dtype_match.group(1)
            if dtype not in VALID_DTYPES and not dtype.startswith("Enum"):
                errors.append(
                    f"{filepath}:{lineno}: invalid dtype '{dtype}' "
                    f"(must be one of: {sorted(VALID_DTYPES)} or Enum[...])"
                )

        indent = len(line) - len(line.lstrip())
        if indent > 0:
            continue

        named_match = re.match(
            r"^(variable|input|function|enum)\s+([a-z_][a-z0-9_]*)", stripped
        )
        if named_match:
            if named_match.group(1) == "function":
                in_code_section = True
            continue

        match = re.match(r"^([a-z_]+)(:|\s|$)", stripped)
        if not match:
            if in_code_section:
                continue
            if re.match(r"^[a-z_]+\s*=", stripped):
                errors.append(
                    f"{filepath}:{lineno}: assignment outside code block"
                )
            continue

        attr = match.group(1)

        if attr in CODE_KEYWORDS:
            if not in_code_section:
                errors.append(
                    f"{filepath}:{lineno}: code keyword '{attr}' "
                    f"outside code block"
                )
            continue

        if attr in {"formula", "function", "defined_for"}:
            in_code_section = True
            continue

        if attr in ALLOWED_ATTRIBUTES:
            in_code_section = False
            continue

        # Bare definition name in unified syntax (e.g. "snap_allotment:")
        if BARE_DEFINITION_PATTERN.match(line):
            in_code_section = False
            continue

        if in_code_section:
            continue

        errors.append(f"{filepath}:{lineno}: forbidden attribute '{attr}'")

    return errors


def validate_schema(statute_dir: Path) -> list[str]:
    """Validate all .rac files in *statute_dir* against the schema.

    Returns a list of error strings (empty means success).
    """
    errors: list[str] = []

    for rac_file in sorted(statute_dir.rglob("*.rac")):
        errors.extend(_validate_schema_file(rac_file))

    return errors


# ---------------------------------------------------------------------------
# Import validation helpers
# ---------------------------------------------------------------------------


def _extract_exports(filepath: Path) -> set[str]:
    """Extract all variable/input/parameter names defined in a file."""
    exports: set[str] = set()
    try:
        content = filepath.read_text()
        for line in content.split("\n"):
            match = VARIABLE_DEF_PATTERN.match(line)
            if match:
                exports.add(match.group(2))
                continue
            match = PARAMETER_DEF_PATTERN.match(line)
            if match:
                exports.add(match.group(1))
                continue
            match = BARE_DEF_PATTERN.match(line)
            if match:
                name = match.group(1)
                if name not in STRUCTURAL_KEYWORDS:
                    exports.add(name)
    except Exception as exc:
        print(
            f"Warning: Could not read {filepath}: {exc}", file=sys.stderr
        )
    return exports


def _resolve_import_path(import_path: str, statute_dir: Path) -> Path | None:
    """Resolve an import path to a .rac file or directory.

    Import path like ``26/1/j/2`` could resolve to:
    - ``statute/26/1/j/2.rac`` (file)
    - ``statute/26/1/j/2/index.rac`` (directory with index)
    """
    direct_file = statute_dir / f"{import_path}.rac"
    if direct_file.exists():
        return direct_file

    dir_path = statute_dir / import_path
    if dir_path.is_dir():
        for candidate in [
            dir_path / "index.rac",
            dir_path.parent / f"{dir_path.name}.rac",
        ]:
            if candidate.exists():
                return candidate
        return dir_path

    return None


def _find_variable_in_path(
    import_path: str, variable: str, statute_dir: Path
) -> tuple[bool, str]:
    """Check whether *variable* is exported from *import_path*.

    Returns ``(found, error_message)``.
    """
    resolved = _resolve_import_path(import_path, statute_dir)

    if resolved is None:
        return False, f"path '{import_path}' does not exist"

    if resolved.is_file():
        exports = _extract_exports(resolved)
        if variable in exports:
            return True, ""
        return (
            False,
            f"variable '{variable}' not found in {resolved.name} "
            f"(exports: {sorted(exports) if exports else 'none'})",
        )

    if resolved.is_dir():
        all_exports: set[str] = set()
        for rac_file in resolved.rglob("*.rac"):
            exports = _extract_exports(rac_file)
            if variable in exports:
                return True, ""
            all_exports.update(exports)

        truncated = sorted(all_exports)[:10]
        suffix = "..." if len(all_exports) > 10 else ""
        return (
            False,
            f"variable '{variable}' not found in {import_path}/ directory "
            f"(exports: {truncated}{suffix})",
        )

    return False, f"path '{import_path}' is neither file nor directory"


def _extract_imports(filepath: Path) -> list[tuple[int, str, str]]:
    """Extract all imports from a file.

    Returns a list of ``(line_number, import_path, variable_name)`` tuples.
    """
    imports: list[tuple[int, str, str]] = []
    content = filepath.read_text()
    lines = content.split("\n")

    in_imports_block = False

    for lineno, line in enumerate(lines, 1):
        block_match = IMPORTS_BLOCK_PATTERN.match(line)
        if block_match:
            rest = block_match.group(1).strip()

            if rest.startswith("["):
                in_imports_block = False
                for m in IMPORT_PATTERN.finditer(rest):
                    imports.append((lineno, m.group(1), m.group(2)))
            elif not rest or rest == "|":
                in_imports_block = True
            continue

        if in_imports_block:
            list_match = IMPORTS_LIST_PATTERN.match(line)
            if list_match:
                import_str = list_match.group(1).strip()
                import_match = IMPORT_PATTERN.match(import_str)
                if import_match:
                    imports.append(
                        (lineno, import_match.group(1), import_match.group(2))
                    )
            elif line.strip() and not line.strip().startswith("#"):
                if not line[0].isspace():
                    in_imports_block = False

    return imports


def _build_dependency_graph(
    statute_dir: Path,
) -> dict[str, list[str]]:
    """Build a dependency graph for cycle detection."""
    graph: dict[str, list[str]] = defaultdict(list)

    for rac_file in statute_dir.rglob("*.rac"):
        rel_path = rac_file.relative_to(statute_dir)
        node = str(rel_path.with_suffix(""))

        imports = _extract_imports(rac_file)
        for _, import_path, _ in imports:
            graph[node].append(import_path)

    return graph


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Find all cycles in the dependency graph using DFS."""
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])

        path.pop()
        rec_stack.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node)

    return cycles


# ---------------------------------------------------------------------------
# Import validation (public API)
# ---------------------------------------------------------------------------


def validate_imports(statute_dir: Path) -> list[str]:
    """Validate that all imports in .rac files resolve and have no cycles.

    Returns a list of error strings (empty means success).
    """
    errors: list[str] = []

    for rac_file in sorted(statute_dir.rglob("*.rac")):
        try:
            imports = _extract_imports(rac_file)
        except Exception as exc:
            errors.append(f"{rac_file}: failed to parse imports: {exc}")
            continue

        for lineno, import_path, variable in imports:
            # Skip cross-repo imports (e.g. "rac-us:statute/26/1")
            if ":" in import_path:
                continue
            found, error_msg = _find_variable_in_path(
                import_path, variable, statute_dir
            )
            if not found:
                errors.append(
                    f"{rac_file}:{lineno}: broken import "
                    f"'{import_path}#{variable}' - {error_msg}"
                )

    # Cycle detection
    graph = _build_dependency_graph(statute_dir)
    cycles = _find_cycles(graph)
    for cycle in cycles:
        cycle_str = " -> ".join(cycle)
        errors.append(f"Circular dependency detected: {cycle_str}")

    return errors


# ---------------------------------------------------------------------------
# Combined validation
# ---------------------------------------------------------------------------


def validate_all(statute_dir: Path) -> list[str]:
    """Run both schema and import validation.

    Returns a list of error strings (empty means success).
    """
    errors = validate_schema(statute_dir)
    errors.extend(validate_imports(statute_dir))
    return errors


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for ``python -m rac.validate``."""
    args = argv if argv is not None else sys.argv[1:]

    usage = (
        "Usage: python -m rac.validate {schema|imports|all} <statute_dir>"
    )

    if len(args) != 2:
        print(usage, file=sys.stderr)
        sys.exit(2)

    command, statute_path = args
    statute_dir = Path(statute_path)

    if command not in {"schema", "imports", "all"}:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(usage, file=sys.stderr)
        sys.exit(2)

    if not statute_dir.exists():
        print(f"Error: {statute_dir} not found", file=sys.stderr)
        sys.exit(1)

    if command == "schema":
        errors = validate_schema(statute_dir)
        label = "schema"
    elif command == "imports":
        errors = validate_imports(statute_dir)
        label = "import"
    else:
        errors = validate_all(statute_dir)
        label = "validation"

    files_checked = len(list(statute_dir.rglob("*.rac")))
    print(f"Checked {files_checked} .rac files")

    if errors:
        print(f"\nFound {len(errors)} {label} errors:\n")
        for error in sorted(errors):
            print(f"  {error}")
        sys.exit(1)
    else:
        print(f"\nAll files pass {label}")
        sys.exit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
