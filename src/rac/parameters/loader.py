"""Parameter loader for YAML files.

Loads parameters from YAML files following the Cosilico parameter syntax.
Supports:
- Simple time-varying parameters
- Bracket parameters indexed by numeric value
- Filing status parameters
- Combined filing status + brackets
- Auto-resolution of index variables from context
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional, Union

import yaml


# Filing status keys recognized as dimension selectors
FILING_STATUS_KEYS = {
    "SINGLE",
    "JOINT",
    "SEPARATE",
    "HEAD_OF_HOUSEHOLD",
    "SURVIVING_SPOUSE",
    "MARRIED_FILING_JOINTLY",
    "MARRIED_FILING_SEPARATELY",
}


@dataclass
class ParameterDefinition:
    """A loaded parameter definition."""

    path: str
    description: str
    unit: str
    index_paths: list[str] = field(default_factory=list)
    # Raw data for value lookup
    _data: dict = field(default_factory=dict)

    def get_value(
        self,
        as_of: date,
        filing_status: Optional[str] = None,
        index_value: Optional[Union[int, float]] = None,
    ) -> Any:
        """Get parameter value for given date and indices."""
        data = self._data

        # Handle filing status dimension
        if filing_status and filing_status in data:
            data = data[filing_status]

        # Handle brackets
        if "brackets" in data:
            return self._resolve_bracket(data["brackets"], as_of, index_value or 0)

        # Handle simple values
        if "values" in data:
            return self._resolve_time(data["values"], as_of)

        # Might be filing status keys at top level without explicit selection
        for key in FILING_STATUS_KEYS:
            if key in data:
                raise ValueError(
                    f"Parameter {self.path} requires filing_status but none provided"
                )

        raise ValueError(f"Cannot resolve value for {self.path}")

    def _resolve_time(self, values: dict, as_of: date) -> Any:
        """Find value for given date (most recent <= as_of)."""
        # Parse date strings to date objects
        dated_values = []
        for date_key, value in values.items():
            if isinstance(date_key, str):
                d = date.fromisoformat(date_key)
            elif isinstance(date_key, date):
                d = date_key
            else:
                continue
            dated_values.append((d, value))

        # Sort by date descending
        dated_values.sort(key=lambda x: x[0], reverse=True)

        # Find most recent <= as_of
        for d, value in dated_values:
            if d <= as_of:
                return value

        raise ValueError(f"No value found for date {as_of}")

    def _resolve_bracket(
        self, brackets: list[dict], as_of: date, index_value: Union[int, float]
    ) -> Any:
        """Find value in bracket structure."""
        # Sort brackets by threshold descending
        sorted_brackets = sorted(
            brackets, key=lambda b: b.get("threshold", 0), reverse=True
        )

        # Find highest threshold <= index_value
        for bracket in sorted_brackets:
            threshold = bracket.get("threshold", 0)
            if threshold <= index_value:
                return self._resolve_time(bracket["values"], as_of)

        # Fallback to first bracket
        if brackets:
            return self._resolve_time(brackets[0]["values"], as_of)

        raise ValueError(f"No bracket found for index {index_value}")


@dataclass
class ParameterStore:
    """Collection of loaded parameters."""

    parameters: dict[str, ParameterDefinition] = field(default_factory=dict)

    def __contains__(self, path: str) -> bool:
        return path in self.parameters

    def get_definition(self, path: str) -> ParameterDefinition:
        """Get the parameter definition object."""
        if path not in self.parameters:
            raise KeyError(f"Unknown parameter: {path}")
        return self.parameters[path]

    def get(
        self,
        path: str,
        as_of: Optional[date] = None,
        filing_status: Optional[str] = None,
        index_value: Optional[Union[int, float]] = None,
    ) -> Any:
        """Get a parameter value by path.

        Args:
            path: Parameter path (e.g., "statute/26/32/b/1/A/credit_percentage")
            as_of: Effective date (defaults to today)
            filing_status: Filing status key (SINGLE, JOINT, etc.)
            index_value: Numeric index for bracket lookup

        Returns:
            The parameter value
        """
        if as_of is None:
            as_of = date.today()

        param = self.get_definition(path)
        return param.get_value(as_of, filing_status, index_value)

    def get_with_context(
        self,
        path: str,
        as_of: Optional[date] = None,
        context: Optional[dict[str, Any]] = None,
        filing_status: Optional[str] = None,
        index_value: Optional[Union[int, float]] = None,
    ) -> Any:
        """Get parameter value, auto-resolving indices from context.

        Args:
            path: Parameter path
            as_of: Effective date
            context: Dict mapping variable paths to values
            filing_status: Explicit filing status (overrides context)
            index_value: Explicit index value (overrides context)

        Returns:
            The parameter value
        """
        if as_of is None:
            as_of = date.today()
        if context is None:
            context = {}

        param = self.get_definition(path)

        # Auto-resolve from context if not explicitly provided
        resolved_filing_status = filing_status
        resolved_index_value = index_value

        for idx_path in param.index_paths:
            if idx_path in context:
                value = context[idx_path]
                # Detect if this is a filing status or numeric index
                if isinstance(value, str) and value in FILING_STATUS_KEYS:
                    if resolved_filing_status is None:
                        resolved_filing_status = value
                elif isinstance(value, (int, float)):
                    if resolved_index_value is None:
                        resolved_index_value = value

        return param.get_value(as_of, resolved_filing_status, resolved_index_value)

    def add(self, param: ParameterDefinition):
        """Add a parameter definition."""
        self.parameters[param.path] = param


class ParameterLoader:
    """Loads parameters from YAML files."""

    def __init__(self, root_dir: Union[str, Path]):
        """Initialize loader.

        Args:
            root_dir: Root directory containing parameter YAML files.
        """
        self.root_dir = Path(root_dir)
        self.store = ParameterStore()

    def load_all(self) -> ParameterStore:
        """Load all parameter YAML files from root directory."""
        if not self.root_dir.exists():
            return self.store

        for yaml_file in self.root_dir.rglob("*.yaml"):
            self._load_file(yaml_file)

        for yml_file in self.root_dir.rglob("*.yml"):
            self._load_file(yml_file)

        return self.store

    def _load_file(self, filepath: Path):
        """Load parameters from a YAML file."""
        try:
            with open(filepath, "r") as f:
                data = yaml.safe_load(f)

            if not data or not isinstance(data, dict):
                return

            # Derive parameter path from file path
            rel_path = filepath.relative_to(self.root_dir)
            param_path = str(rel_path.with_suffix(""))  # Remove .yaml

            # Extract metadata
            description = data.pop("description", "")
            unit = data.pop("unit", "")

            # Extract index paths
            index = data.pop("index", [])
            if isinstance(index, str):
                index_paths = [index]
            elif isinstance(index, list):
                index_paths = index
            else:
                index_paths = []

            # Remaining data is the values structure
            param = ParameterDefinition(
                path=param_path,
                description=description,
                unit=unit,
                index_paths=index_paths,
                _data=data,
            )
            self.store.add(param)

        except Exception as e:
            print(f"Warning: Failed to load {filepath}: {e}")


def load_parameters(root_dir: Union[str, Path]) -> ParameterStore:
    """Convenience function to load all parameters."""
    loader = ParameterLoader(root_dir)
    return loader.load_all()
