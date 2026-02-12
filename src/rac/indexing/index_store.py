"""Index store for loading and querying inflation indices.

Handles both historical (BLS published) and forecast (CBO/Fed projected) values
with proper separation of concerns.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class IndexValue:
    """A single index value with metadata."""

    year: int
    value: float
    source: str  # "historical" or forecast provider name
    vintage: str | None = None  # For forecasts: when the forecast was made


class IndexStore:
    """Store for inflation index values (historical and forecast).

    Separates historical (authoritative BLS data) from forecasts (CBO/Fed projections).
    This separation is critical for:
    1. Knowing what's "real" vs projected
    2. Tracking forecast accuracy over time
    3. Supporting multiple forecast vintages
    """

    def __init__(self, data_dir: str | Path = None):
        """Initialize index store.

        Args:
            data_dir: Path to data/indices/ directory
        """
        if data_dir is None:
            # Default: relative to this file
            data_dir = Path(__file__).parent.parent.parent.parent / "data" / "indices"
        self.data_dir = Path(data_dir)

        self._historical: dict[str, dict[int, float]] = {}
        self._forecasts: dict[str, dict[str, dict[int, float]]] = {}
        self._loaded = False

    def _ensure_loaded(self):
        """Load index data on first access."""
        if self._loaded:
            return

        self._load_index("cpi_u")
        self._load_index("chained_cpi_u")
        self._loaded = True

    def _load_index(self, index_name: str):
        """Load historical and forecast data for an index."""
        index_dir = self.data_dir / index_name

        # Load historical
        historical_path = index_dir / "historical.yaml"
        if historical_path.exists():
            with open(historical_path) as f:
                data = yaml.safe_load(f)
                # Extract annual average values
                index_data = data.get(index_name, data)
                self._historical[index_name] = index_data.get("annual_average", {})

        # Load forecasts
        self._forecasts[index_name] = {}
        forecast_dir = index_dir / "forecast"
        if forecast_dir.exists():
            for forecast_file in forecast_dir.glob("*.yaml"):
                with open(forecast_file) as f:
                    data = yaml.safe_load(f)
                    forecast_data = data.get("forecast", data)
                    vintage = forecast_data.get("vintage", forecast_file.stem)
                    self._forecasts[index_name][vintage] = forecast_data.get("values", {})

    def get_historical(self, index_name: str, year: int) -> float | None:
        """Get historical (authoritative) index value.

        Returns None if value not available (future year or not published yet).
        """
        self._ensure_loaded()

        if index_name not in self._historical:
            raise ValueError(f"Unknown index: {index_name}")

        return self._historical[index_name].get(year)

    def get_forecast(self, index_name: str, year: int, vintage: str = None) -> float | None:
        """Get forecast index value.

        Args:
            index_name: Name of index (cpi_u, chained_cpi_u)
            year: Year to get value for
            vintage: Forecast vintage (e.g., "2024_06"). If None, uses latest.

        Returns:
            Forecast value or None if not available
        """
        self._ensure_loaded()

        if index_name not in self._forecasts:
            return None

        forecasts = self._forecasts[index_name]

        if vintage is None:
            # Use latest vintage
            if not forecasts:
                return None
            vintage = sorted(forecasts.keys())[-1]

        if vintage not in forecasts:
            return None

        return forecasts[vintage].get(year)

    def get(
        self, index_name: str, year: int, vintage: str = None, prefer_historical: bool = True
    ) -> IndexValue:
        """Get index value with proper source selection.

        Args:
            index_name: Name of index
            year: Year to get value for
            vintage: Forecast vintage for future years
            prefer_historical: If True, use historical when available

        Returns:
            IndexValue with value and source metadata
        """
        self._ensure_loaded()

        # Try historical first if preferred
        if prefer_historical:
            historical = self.get_historical(index_name, year)
            if historical is not None:
                return IndexValue(year=year, value=historical, source="historical")

        # Try forecast
        forecast = self.get_forecast(index_name, year, vintage)
        if forecast is not None:
            return IndexValue(
                year=year,
                value=forecast,
                source="forecast",
                vintage=vintage or self._latest_vintage(index_name),
            )

        # No value available
        raise ValueError(f"No {index_name} value available for {year} (vintage={vintage})")

    def _latest_vintage(self, index_name: str) -> str | None:
        """Get the most recent forecast vintage for an index."""
        forecasts = self._forecasts.get(index_name, {})
        if not forecasts:
            return None
        return sorted(forecasts.keys())[-1]

    def get_ratio(
        self, index_name: str, from_year: int, to_year: int, vintage: str = None
    ) -> float:
        """Get ratio of index values between two years.

        This is the core calculation for inflation adjustment:
        ratio = index[to_year] / index[from_year]

        Args:
            index_name: Name of index
            from_year: Base year
            to_year: Target year
            vintage: Forecast vintage for future values

        Returns:
            Ratio of to_year index to from_year index
        """
        from_value = self.get(index_name, from_year, vintage)
        to_value = self.get(index_name, to_year, vintage)

        return to_value.value / from_value.value

    def available_years(self, index_name: str) -> tuple[int, int]:
        """Get range of years with historical data."""
        self._ensure_loaded()

        historical = self._historical.get(index_name, {})
        if not historical:
            return (0, 0)

        years = list(historical.keys())
        return (min(years), max(years))

    def list_vintages(self, index_name: str) -> list[str]:
        """List available forecast vintages for an index."""
        self._ensure_loaded()
        return sorted(self._forecasts.get(index_name, {}).keys())
