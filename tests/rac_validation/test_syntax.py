"""Tests for YAML syntax and indentation."""

import pytest
import re
from .conftest import get_all_rac_files


class TestIndentation:
    """All .rac files must use 2-space indentation."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_two_space_indent(self, rac_file):
        """YAML structure must use 2-space indentation increments, not 4."""
        content = rac_file.read_text()
        lines = content.split('\n')

        bad_lines = []
        in_multiline_block = False
        multiline_marker = None
        prev_indent = 0

        for i, line in enumerate(lines, 1):
            if not line.strip() or line.strip().startswith('#'):
                continue

            if re.match(r'\s*(formula|syntax):\s*\|', line):
                in_multiline_block = True
                multiline_marker = 'pipe'
                continue
            if re.match(r'\s*text:\s*(\"\"\"|\'\'\'|\|)', line):
                in_multiline_block = True
                multiline_marker = 'triple' if '"""' in line or "'''" in line else 'pipe'
                continue

            if in_multiline_block:
                curr_indent = len(line) - len(line.lstrip())
                if multiline_marker == 'triple' and ('"""' in line or "'''" in line):
                    in_multiline_block = False
                    continue
                elif multiline_marker == 'pipe' and curr_indent <= 2 and re.match(r'\s*\w+:', line):
                    in_multiline_block = False
                else:
                    continue

            curr_indent = len(line) - len(line.lstrip())
            if curr_indent - prev_indent == 4 and prev_indent == 0:
                bad_lines.append(f"Line {i}: {line.strip()}")

            prev_indent = curr_indent

        if bad_lines:
            pytest.fail(f"4-space indentation found (should be 2):\n" + "\n".join(bad_lines[:5]))


class TestThousandsSeparator:
    """Numeric values >= 1000 should use underscore separator."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_large_numbers_use_separator(self, rac_file):
        """Values >= 1000 in parameter values should use _ separator."""
        content = rac_file.read_text()

        bad_values = []
        lines = content.split('\n')
        in_text_block = False
        in_values_block = False

        for i, line in enumerate(lines, 1):
            # Skip text blocks
            if '"""' in line:
                in_text_block = not in_text_block
                continue
            if in_text_block:
                continue
            if line.strip().startswith('#'):
                continue

            # Track values: blocks where parameter values live
            if re.match(r'\s*values:\s*$', line):
                in_values_block = True
                continue
            # Exit values block on new top-level key
            if in_values_block and re.match(r'\s{0,2}\w+:', line) and not re.match(r'\s{4,}', line):
                in_values_block = False

            # Only check lines in values blocks (date: value pairs)
            if not in_values_block:
                continue

            # Skip date lines and comments
            if re.search(r'\d{4}-\d{2}-\d{2}:', line):
                # Check the value part after the date
                value_match = re.search(r'\d{4}-\d{2}-\d{2}:\s*(\d+)', line)
                if value_match:
                    val = value_match.group(1)
                    if len(val) >= 4 and int(val) >= 1000 and '_' not in line.split(':')[-1]:
                        if not (1900 <= int(val) <= 2100):
                            bad_values.append(f"Line {i}: {val} (use {int(val):_})")

        if bad_values:
            pytest.fail(f"Large numbers without _ separator:\n" + "\n".join(bad_values[:10]))
