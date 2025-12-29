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
        """Values >= 1000 should use _ separator (e.g., 5_000 not 5000)."""
        content = rac_file.read_text()

        bad_values = []
        lines = content.split('\n')
        in_text_block = False

        for i, line in enumerate(lines, 1):
            if '"""' in line:
                in_text_block = not in_text_block
                continue
            if in_text_block:
                continue
            if line.strip().startswith('#'):
                continue
            if re.search(r'\d{4}-\d{2}-\d{2}', line):
                continue
            if 'period:' in line or 'expect:' in line:
                continue
            if 'source:' in line.lower() or 'reference:' in line.lower():
                continue
            if 'imports:' in line or (line.strip().startswith('-') and '/' in line):
                continue

            matches = re.findall(r'(?<![_\d])(\d{4,})(?![_\d.])', line)
            for match in matches:
                if 1900 <= int(match) <= 2100:
                    continue
                if int(match) >= 1000:
                    bad_values.append(f"Line {i}: {match} (use {int(match):_})")

        if bad_values:
            pytest.fail(f"Large numbers without _ separator:\n" + "\n".join(bad_values[:10]))
