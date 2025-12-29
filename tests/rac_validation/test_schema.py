"""Tests for entity, period, dtype validation."""

import pytest
import re
from .conftest import get_all_rac_files


class TestSchemaValidation:
    """entity, period, dtype must be valid values."""

    VALID_ENTITIES = {
        "Person", "TaxUnit", "Household", "State", "SPMUnit",
        "TanfUnit", "Corporation", "Asset", "Family", "Business"
    }
    VALID_PERIODS = {"Year", "Month", "Week", "Eternity"}
    VALID_DTYPES = {"Money", "Rate", "Boolean", "Integer", "Enum", "String", "Count", "Decimal"}

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_valid_entity(self, rac_file):
        """entity: must be a valid entity type."""
        content = rac_file.read_text()
        match = re.search(r'entity:\s*(\w+)', content)
        if match:
            entity = match.group(1)
            if entity not in self.VALID_ENTITIES:
                pytest.fail(f"Invalid entity '{entity}'. Must be one of: {self.VALID_ENTITIES}")

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_valid_period(self, rac_file):
        """period: must be a valid period type."""
        content = rac_file.read_text()
        match = re.search(r'^  period:\s*(\w+)', content, re.MULTILINE)
        if match:
            period = match.group(1)
            if period not in self.VALID_PERIODS:
                pytest.fail(f"Invalid period '{period}'. Must be one of: {self.VALID_PERIODS}")

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_valid_dtype(self, rac_file):
        """dtype: must be a valid data type."""
        content = rac_file.read_text()
        match = re.search(r'dtype:\s*(\w+)', content)
        if match:
            dtype = match.group(1)
            if dtype == "Enum":
                return
            if dtype not in self.VALID_DTYPES:
                pytest.fail(f"Invalid dtype '{dtype}'. Must be one of: {self.VALID_DTYPES}")


class TestValidAttributes:
    """Only spec-defined attributes are allowed."""

    PARAMETER_ATTRS = {'description', 'unit', 'indexed_by', 'values'}
    VARIABLE_ATTRS = {
        'imports', 'entity', 'period', 'dtype', 'unit', 'label',
        'description', 'default', 'formula', 'tests', 'syntax', 'versions'
    }
    INPUT_ATTRS = {'entity', 'period', 'dtype', 'unit', 'label', 'description', 'default'}

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_no_invalid_attributes(self, rac_file):
        """Attributes must be in the spec. No source/reference (filepath is citation)."""
        content = rac_file.read_text()
        errors = []

        for match in re.finditer(r'^parameter\s+\w+:\s*\n((?:  \w+:.*\n)*)', content, re.MULTILINE):
            block = match.group(1)
            attrs = set(re.findall(r'^  (\w+):', block, re.MULTILINE))
            invalid = attrs - self.PARAMETER_ATTRS
            if invalid:
                errors.append(f"parameter has invalid attrs: {invalid}")

        for match in re.finditer(r'^variable\s+\w+:\s*\n((?:  \w+:.*\n)*)', content, re.MULTILINE):
            block = match.group(1)
            attrs = set(re.findall(r'^  (\w+):', block, re.MULTILINE))
            invalid = attrs - self.VARIABLE_ATTRS
            if invalid:
                errors.append(f"variable has invalid attrs: {invalid}")

        for match in re.finditer(r'^input\s+\w+:\s*\n((?:  \w+:.*\n)*)', content, re.MULTILINE):
            block = match.group(1)
            attrs = set(re.findall(r'^  (\w+):', block, re.MULTILINE))
            invalid = attrs - self.INPUT_ATTRS
            if invalid:
                errors.append(f"input has invalid attrs: {invalid}")

        if errors:
            pytest.fail(f"Invalid attributes:\n" + "\n".join(errors[:5]))
