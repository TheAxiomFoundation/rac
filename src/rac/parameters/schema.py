"""Schema definitions for Cosilico parameters."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class ParameterValue:
    """A single parameter value with effective date range."""

    value: Any
    effective_from: date
    effective_to: Optional[date] = None
    source: Optional[str] = None  # Citation or URL
    notes: Optional[str] = None


@dataclass
class ParameterDefinition:
    """A parameter definition with metadata and values over time.

    Example YAML:
    ```yaml
    gov.irs.eitc.phase_in_rate:
      description: EITC phase-in credit percentage
      unit: rate
      reference: "26 USC § 32(b)(1)"
      indexed_by: [n_children]
      values:
        - effective_from: 2024-01-01
          by_n_children:
            0: 0.0765
            1: 0.34
            2: 0.40
            3: 0.45
          source: "Rev. Proc. 2023-34"
    ```
    """

    path: str  # e.g., "gov.irs.eitc.phase_in_rate"
    description: str
    unit: str  # "USD", "rate", "percent", "count", "bool"
    reference: str  # Statute citation

    # Index dimensions (e.g., ["n_children", "filing_status"])
    indexed_by: list[str] = field(default_factory=list)

    # Values over time
    values: list[ParameterValue] = field(default_factory=list)

    def get_value(
        self,
        as_of: Optional[date] = None,
        **indices: Any,
    ) -> Any:
        """Get parameter value for a given date and index values.

        Args:
            as_of: Effective date (defaults to today)
            **indices: Index values (e.g., n_children=2, filing_status="SINGLE")

        Returns:
            The parameter value
        """
        if as_of is None:
            as_of = date.today()

        # Find applicable value by date
        applicable_value = None
        for pv in sorted(self.values, key=lambda v: v.effective_from, reverse=True):
            if pv.effective_from <= as_of:
                if pv.effective_to is None or pv.effective_to >= as_of:
                    applicable_value = pv
                    break

        if applicable_value is None:
            raise ValueError(f"No value found for {self.path} as of {as_of}")

        value = applicable_value.value

        # Handle indexed parameters
        if self.indexed_by and indices:
            for index_name in self.indexed_by:
                if index_name in indices:
                    index_val = indices[index_name]
                    if isinstance(value, dict):
                        # Try exact match first
                        if index_val in value:
                            value = value[index_val]
                        # Try string key
                        elif str(index_val) in value:
                            value = value[str(index_val)]
                        # Try int key
                        elif isinstance(index_val, str) and index_val.isdigit():
                            value = value.get(int(index_val), value)
                        else:
                            # Use max key as default for "3+" style parameters
                            max_key = max(k for k in value.keys() if isinstance(k, int))
                            value = value.get(max_key, list(value.values())[-1])

        return value


@dataclass
class ParameterStore:
    """Collection of parameters organized by path."""

    parameters: dict[str, ParameterDefinition] = field(default_factory=dict)

    def get(self, path: str, as_of: Optional[date] = None, **indices: Any) -> Any:
        """Get a parameter value by path.

        Args:
            path: Parameter path (e.g., "gov.irs.eitc.phase_in_rate")
            as_of: Effective date
            **indices: Index values

        Returns:
            The parameter value
        """
        if path not in self.parameters:
            raise KeyError(f"Unknown parameter: {path}")

        return self.parameters[path].get_value(as_of=as_of, **indices)

    def add(self, param: ParameterDefinition):
        """Add a parameter definition."""
        self.parameters[param.path] = param

    def __contains__(self, path: str) -> bool:
        return path in self.parameters
