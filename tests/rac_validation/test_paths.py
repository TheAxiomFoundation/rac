"""Tests for filepath conventions - filepath IS the citation."""

import pytest
import re
from .conftest import get_all_rac_files, get_statute_dir


class TestFilenameIsCitation:
    """Filename must be citation identifier, not descriptive name."""

    VALID_PATTERNS = [
        r'^[a-z]$',           # Single letter: a, b, c
        r'^[1-9][0-9]*$',     # Number: 1, 2, 10
        r'^[1-9][0-9]*[A-Z]$', # Section with letter: 25A, 36B, 30D
        r'^[ivxlcdm]+$',      # Roman numeral: i, ii, iii, iv
        r'^[A-Z]$',           # Capital letter: A, B, C
    ]

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_filename_is_citation(self, rac_file):
        """Filename should be subsection identifier (a, 1, A, i), not descriptive."""
        filename = rac_file.stem

        is_valid = any(re.match(p, filename) for p in self.VALID_PATTERNS)

        if not is_valid:
            pytest.fail(
                f"Filename '{filename}' is not a valid citation identifier. "
                f"Must be: single letter (a-z), number (1, 2, ...), roman numeral (i, ii, ...), "
                f"or capital letter (A-Z). Path: {rac_file}"
            )


class TestNoRedundantHeader:
    """First line should be text:, not a citation comment."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_no_citation_comment(self, rac_file):
        """File should not start with citation comment (filepath is the citation)."""
        content = rac_file.read_text()
        first_line = content.split('\n')[0].strip()

        # Check for citation-style comments at start
        if re.match(r'^#\s*\d+\s*(USC|U\.S\.C\.)', first_line, re.IGNORECASE):
            pytest.fail(f"Redundant citation comment: '{first_line}'. Filepath is the citation.")


class TestRepealedSections:
    """Detect files at repealed statute sections."""

    # Known repealed IRC sections (add more as discovered)
    REPEALED_SECTIONS = {
        '26/225',  # Repealed 1976 - was corporate trade/business expenses
        '26/226',  # Repealed 1976
        '26/227',  # Repealed 1976
    }

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_not_repealed_section(self, rac_file):
        """File should not be at a known repealed section path."""
        statute_dir = get_statute_dir()

        try:
            rel_path = rac_file.relative_to(statute_dir)
            path_str = str(rel_path.parent)

            for repealed in self.REPEALED_SECTIONS:
                if path_str.startswith(repealed):
                    pytest.fail(
                        f"File at repealed section {repealed}! "
                        f"This statute was repealed and should not be encoded."
                    )
        except ValueError:
            pytest.skip("File not under statute directory")
