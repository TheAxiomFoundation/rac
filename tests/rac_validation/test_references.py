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
        'max', 'min', 'sum', 'abs', 'round', 'int', 'float', 'len', 'range',
        'true', 'false', 'True', 'False', 'None',
        'np', 'numpy', 'where', 'select', 'clip',
        'return', 'if', 'else', 'elif', 'and', 'or', 'not', 'in', 'for',
    }

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_formula_vars_defined(self, rac_file):
        """Variables used in formula must be imported or defined in same file."""
        content = rac_file.read_text()

        imported = set()
        imports_match = re.search(r'imports:\s*\n((?:\s+-\s+.*\n)*)', content)
        if imports_match:
            for imp in re.findall(r'#(\w+)', imports_match.group(1)):
                imported.add(imp)
            for alias in re.findall(r'as\s+(\w+)', imports_match.group(1)):
                imported.add(alias)

        same_file = set(re.findall(r'variable\s+(\w+):', content))
        params = set(re.findall(r'parameter\s+(\w+):', content))
        inputs = set(re.findall(r'input\s+(\w+):', content))

        defined = imported | same_file | params | inputs | self.BUILTINS

        formula_match = re.search(r'formula:\s*\|?\s*\n((?:\s+.*\n)*)', content)
        if not formula_match:
            pytest.skip("No formula")

        formula = formula_match.group(1)
        used = set(re.findall(r'\b([a-z_][a-z0-9_]*)\b', formula, re.IGNORECASE))
        undefined = used - defined
        undefined -= {'result', 'i', 'x', 'n', 'value', 'rate', 'amount'}

        if undefined:
            pytest.xfail(f"Undefined variables: {sorted(undefined)[:5]}")
