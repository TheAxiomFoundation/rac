"""Parameter resolver with three-tier precedence.

Resolves indexed parameter values using:
1. PUBLISHED - Official government values (highest priority)
2. PROJECTED - Our calculations with forecast vintage
3. CALCULATED - On-the-fly from base year + index
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

from .index_store import IndexStore


class ValueTier(Enum):
    """Tier indicating the source of a parameter value."""
    PUBLISHED = "published"    # Official government source
    PROJECTED = "projected"    # Our calculation with forecast
    CALCULATED = "calculated"  # On-the-fly calculation


@dataclass
class IndexedValue:
    """A resolved parameter value with full provenance."""
    value: float
    tier: ValueTier
    source: str  # e.g., "Rev. Proc. 2023-34" or "Calculated via §32(j)"
    year: int
    vintage: Optional[str] = None  # For projections: forecast vintage
    base_year: Optional[int] = None  # For calculations: the base year used
    index_used: Optional[str] = None  # For calculations: which index
    raw_indexed: Optional[float] = None  # Before rounding


class ParameterResolver:
    """Resolves indexed parameter values with proper precedence.

    Implements the three-tier resolution:
    1. Published values from official government sources
    2. Projected values using forecasts
    3. Calculated values on-the-fly from base + index

    Example:
        resolver = ParameterResolver()

        # 2024 EITC earned income amount (uses published Rev. Proc. value)
        val = resolver.get("gov.irs.eitc.earned_income_amount", 2024, n_children=1)
        # Returns: IndexedValue(value=12390, tier=PUBLISHED, source="Rev. Proc. 2023-34")

        # 2025 value (not yet published, uses projected)
        val = resolver.get("gov.irs.eitc.earned_income_amount", 2025, n_children=1)
        # Returns: IndexedValue(value=12720, tier=PROJECTED, ...)

        # 2030 value (calculated from base + forecasted index)
        val = resolver.get("gov.irs.eitc.earned_income_amount", 2030, n_children=1)
        # Returns: IndexedValue(value=14200, tier=CALCULATED, ...)
    """

    def __init__(
        self,
        index_store: IndexStore = None,
        rules_dir: str | Path = None
    ):
        """Initialize resolver.

        Args:
            index_store: Store for index values. If None, creates default.
            rules_dir: Path to us/ directory with statute-organized rules.
        """
        self.index_store = index_store or IndexStore()

        if rules_dir is None:
            rules_dir = Path(__file__).parent.parent.parent.parent / "us"
        self.rules_dir = Path(rules_dir)

        self._param_cache: dict[str, dict] = {}
        self._indexing_rules: dict[str, dict] = {}

    def get(
        self,
        path: str,
        year: int,
        tier: str = "auto",
        vintage: str = None,
        **indices
    ) -> IndexedValue:
        """Resolve a parameter value for a given year.

        Args:
            path: Parameter path (e.g., "gov.irs.eitc.earned_income_amount")
            year: Tax year to get value for
            tier: Which tier to use ("published", "projected", "calculated", "auto")
            vintage: Forecast vintage for projected/calculated (e.g., "2024_06")
            **indices: Index values (e.g., n_children=2, filing_status="JOINT")

        Returns:
            IndexedValue with resolved value and provenance
        """
        param_data = self._load_parameter(path)

        # Auto: try tiers in order
        if tier == "auto":
            # Tier 1: Published
            published = self._try_published(param_data, year, indices)
            if published is not None:
                return published

            # Tier 2: Projected
            projected = self._try_projected(param_data, year, vintage, indices)
            if projected is not None:
                return projected

            # Tier 3: Calculate
            return self._calculate(param_data, year, vintage, indices)

        elif tier == "published":
            result = self._try_published(param_data, year, indices)
            if result is None:
                raise ValueError(f"No published value for {path} in {year}")
            return result

        elif tier == "projected":
            result = self._try_projected(param_data, year, vintage, indices)
            if result is None:
                raise ValueError(f"No projected value for {path} in {year}")
            return result

        elif tier == "calculated":
            return self._calculate(param_data, year, vintage, indices)

        else:
            raise ValueError(f"Unknown tier: {tier}")

    def _load_parameter(self, path: str) -> dict:
        """Load parameter definition from YAML."""
        if path in self._param_cache:
            return self._param_cache[path]

        # Convert path to file location
        # e.g., "gov.irs.eitc.earned_income_amount" ->
        #       "us/irc/.../§32/b/2/A/amounts.yaml"

        # For now, use simple lookup from known parameters
        # TODO: Implement proper path-to-file resolution

        # Try to find in us/irc structure
        yaml_path = self._find_parameter_file(path)
        if yaml_path and yaml_path.exists():
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
                # Find the parameter in the file
                param_name = path.split(".")[-1]
                if param_name in data:
                    self._param_cache[path] = data[param_name]
                    return data[param_name]

        raise ValueError(f"Parameter not found: {path}")

    def _find_parameter_file(self, path: str) -> Optional[Path]:
        """Find the YAML file containing a parameter.

        Maps gov.irs.* paths to us/irc/... file locations.
        """
        # Map of known parameter paths to file locations
        # TODO: Make this dynamic based on indexing_rule.applies_to
        known_paths = {
            "gov.irs.eitc.earned_income_amount": (
                "irc/subtitle_a/chapter_1/subchapter_a/part_iv/subpart_c/§32/b/2/A/amounts.yaml"
            ),
            "gov.irs.eitc.phaseout_amount": (
                "irc/subtitle_a/chapter_1/subchapter_a/part_iv/subpart_c/§32/b/2/A/amounts.yaml"
            ),
            "gov.irs.eitc.phase_in_rate": (
                "irc/subtitle_a/chapter_1/subchapter_a/part_iv/subpart_c/§32/b/1/credit_percentage.yaml"
            ),
            "gov.irs.eitc.disqualified_income_limit": (
                "irc/subtitle_a/chapter_1/subchapter_a/part_iv/subpart_c/§32/i/1/disqualified_income_limit.yaml"
            ),
        }

        if path in known_paths:
            return self.rules_dir / known_paths[path]

        return None

    def _try_published(
        self,
        param_data: dict,
        year: int,
        indices: dict
    ) -> Optional[IndexedValue]:
        """Try to get published (official) value."""
        published = param_data.get("published", param_data.get("values", []))

        if isinstance(published, list):
            # Find applicable value
            for entry in published:
                effective = entry.get("effective_from", "1900-01-01")
                if isinstance(effective, str):
                    effective_year = int(effective.split("-")[0])
                else:
                    effective_year = effective.year if hasattr(effective, 'year') else effective

                if effective_year == year or (effective_year < year and not entry.get("effective_to")):
                    # Check if status is unknown
                    if entry.get("status") == "unknown":
                        return None

                    # Extract value with indices
                    value = self._extract_indexed_value(entry, indices)
                    if value is not None:
                        return IndexedValue(
                            value=value,
                            tier=ValueTier.PUBLISHED,
                            source=entry.get("source", "published"),
                            year=year
                        )

        return None

    def _try_projected(
        self,
        param_data: dict,
        year: int,
        vintage: str,
        indices: dict
    ) -> Optional[IndexedValue]:
        """Try to get projected value from our calculations."""
        projected = param_data.get("projected", [])

        if isinstance(projected, list):
            for entry in projected:
                entry_vintage = entry.get("vintage")
                if vintage and entry_vintage != vintage:
                    continue

                effective = entry.get("effective_from", "1900-01-01")
                if isinstance(effective, str):
                    effective_year = int(effective.split("-")[0])
                else:
                    effective_year = effective.year if hasattr(effective, 'year') else effective

                if effective_year == year:
                    value = self._extract_indexed_value(entry, indices)
                    if value is not None:
                        return IndexedValue(
                            value=value,
                            tier=ValueTier.PROJECTED,
                            source=f"Calculated via {param_data.get('indexing_rule', 'indexing')}",
                            year=year,
                            vintage=entry_vintage
                        )

        return None

    def _calculate(
        self,
        param_data: dict,
        year: int,
        vintage: str,
        indices: dict
    ) -> IndexedValue:
        """Calculate value on-the-fly from base year + index."""
        # Get base values
        base_data = param_data.get("base", {})
        base_year = base_data.get("year", 2015)
        base_values = base_data.get("values", base_data)

        # Get base value for indices
        base_value = self._extract_indexed_value({"values": base_values}, indices)
        if base_value is None:
            # Try from first published value
            published = param_data.get("published", param_data.get("values", []))
            if published:
                first_entry = published[0] if isinstance(published, list) else published
                base_value = self._extract_indexed_value(first_entry, indices)
                base_year_str = first_entry.get("effective_from", "2015-01-01")
                if isinstance(base_year_str, str):
                    base_year = int(base_year_str.split("-")[0])

        if base_value is None:
            raise ValueError(f"No base value found for calculation")

        # Get index ratio
        # Determine which index to use based on year
        if year < 2018:
            index_name = "cpi_u"
        else:
            index_name = "chained_cpi_u"

        ratio = self.index_store.get_ratio(index_name, base_year, year, vintage)

        # Calculate raw indexed value
        raw_value = base_value * ratio

        # Apply rounding (default: nearest $10)
        rounding = param_data.get("rounding", 10)
        final_value = round(raw_value / rounding) * rounding

        return IndexedValue(
            value=final_value,
            tier=ValueTier.CALCULATED,
            source=f"Calculated: {base_value} × ({index_name} {year}/{base_year})",
            year=year,
            vintage=vintage,
            base_year=base_year,
            index_used=index_name,
            raw_indexed=raw_value
        )

    def _extract_indexed_value(self, entry: dict, indices: dict) -> Optional[float]:
        """Extract value from entry using provided indices."""
        # Try direct value
        if "value" in entry:
            return entry["value"]

        # Try indexed values
        for key in ["by_num_qualifying_children", "by_n_children", "by_filing_status"]:
            if key in entry:
                indexed = entry[key]
                # Determine which index to use
                if "n_children" in key or "qualifying" in key:
                    idx = indices.get("n_children", indices.get("num_qualifying_children", 0))
                elif "filing" in key:
                    idx = indices.get("filing_status", "SINGLE")
                else:
                    continue

                if isinstance(indexed, dict):
                    # Handle nested (e.g., by_n_children -> by_filing_status)
                    val = indexed.get(idx, indexed.get(str(idx)))
                    if isinstance(val, dict):
                        # Second level of indexing
                        filing_status = indices.get("filing_status", "SINGLE")
                        return val.get(filing_status)
                    return val

        return None
