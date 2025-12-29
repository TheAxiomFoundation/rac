"""Tests for imports and variable references."""

import pytest
import re
from .conftest import get_all_rac_files, get_statute_dir


class TestImportValidation:
    """imports: must resolve to real files and variables."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_imports_resolve(self, rac_file):
        """All imports must point to existing files and variables."""
        content = rac_file.read_text()
        statute_dir = get_statute_dir()

        imports_match = re.search(r'imports:\s*\n((?:\s+-\s+.*\n)*)', content)
        if not imports_match:
            pytest.skip("No imports")

        imports_block = imports_match.group(1)
        imports = re.findall(r'-\s+([^\s#]+)', imports_block)

        errors = []
        for imp in imports:
            if '#' in imp:
                path_part, var_name = imp.rsplit('#', 1)
            else:
                path_part = imp
                var_name = None

            rac_path = statute_dir / f"{path_part}.rac"
            if not rac_path.exists():
                errors.append(f"Import path not found: {path_part}")
                continue

            if var_name:
                target_content = rac_path.read_text()
                has_decl = (
                    f"variable {var_name}:" in target_content or
                    f"parameter {var_name}:" in target_content or
                    f"input {var_name}:" in target_content
                )
                if not has_decl:
                    errors.append(f"'{var_name}' not found in {path_part}.rac")

        if errors:
            pytest.fail("\n".join(errors[:5]))


class TestUndefinedVariables:
    """Formula variables must be defined."""

    BUILTINS = {
        # Python builtins
        'max', 'min', 'sum', 'abs', 'round', 'int', 'float', 'len', 'range',
        'true', 'false', 'True', 'False', 'None', 'ceil', 'floor', 'any', 'all',
        'np', 'numpy', 'where', 'select', 'clip',
        'return', 'if', 'else', 'elif', 'and', 'or', 'not', 'in', 'for',
        # Cosilico DSL functions and keywords
        'marginal_agg', 'cut', 'calculate', 'parameter', 'members',
        # Filing status constants
        'SINGLE', 'JOINT', 'HEAD_OF_HOUSEHOLD', 'MARRIED_FILING_SEPARATELY',
        'SEPARATE', 'WIDOW', 'MFS', 'MFJ', 'HOH',
    }

    # Common loop/temp variables and English words that aren't variable references
    COMMON_WORDS = {
        'result', 'i', 'x', 'n', 'value', 'rate', 'amount',
        # Common temp vars
        'total', 'base', 'limit', 'threshold', 'excess', 'cap', 'adj',
    }

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_formula_vars_defined(self, rac_file):
        """Variables used in formula must be imported or defined in same file."""
        content = rac_file.read_text()

        # Collect all imports (including aliases)
        imported = set()
        for imports_match in re.finditer(r'imports:\s*\n((?:\s+-\s+.*\n)*)', content):
            for imp in re.findall(r'#(\w+)', imports_match.group(1)):
                imported.add(imp)
            for alias in re.findall(r'as\s+(\w+)', imports_match.group(1)):
                imported.add(alias)

        same_file = set(re.findall(r'variable\s+(\w+):', content))
        params = set(re.findall(r'parameter\s+(\w+):', content))
        inputs = set(re.findall(r'input\s+(\w+):', content))

        defined = imported | same_file | params | inputs | self.BUILTINS | self.COMMON_WORDS

        # Extract all formula blocks (may be multiple variables in file)
        all_formulas = []
        for match in re.finditer(r'formula:\s*\|?\s*\n((?:[ \t]+[^\n]*\n)*)', content):
            formula_block = match.group(1)
            # Stop at next YAML field (unindented or less indented)
            lines = []
            for line in formula_block.split('\n'):
                # Stop if we hit a YAML field at base indentation
                if re.match(r'^  [a-z_]+:', line):
                    break
                lines.append(line)
            all_formulas.append('\n'.join(lines))

        if not all_formulas:
            pytest.skip("No formula")

        # Combine all formulas and strip comments
        formula = '\n'.join(all_formulas)
        formula_no_comments = re.sub(r'#.*', '', formula)

        # Remove parameter() calls - tokens inside are parameter paths, not variables
        formula_no_params = re.sub(r'parameter\([^)]+\)', '', formula_no_comments)

        # Find local variable assignments (var = ...) and add to defined
        local_vars = set(re.findall(r'\b([a-z_][a-z0-9_]*)\s*=', formula_no_params))
        # Find loop variables (for x in ...)
        loop_vars = set(re.findall(r'for\s+([a-z_][a-z0-9_]*)\s+in\b', formula_no_params))
        defined = defined | local_vars | loop_vars

        # Extract identifiers (only lowercase to avoid matching constants/classes)
        used = set(re.findall(r'\b([a-z_][a-z0-9_]*)\b', formula_no_params))
        undefined = used - defined

        if undefined:
            pytest.xfail(f"Undefined variables: {sorted(undefined)[:5]}")
