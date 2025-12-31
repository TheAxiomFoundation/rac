"""Tests for the Cosilico parameter loader.

TDD tests defining expected behavior for:
1. Simple time-varying parameters
2. Bracket parameters with auto-resolution
3. Filing status parameters
4. Combined filing status + brackets
5. Explicit index passing
"""

import pytest
from datetime import date
from pathlib import Path
import tempfile
import yaml


class TestParameterLoader:
    """Tests for loading parameters from YAML files."""

    @pytest.fixture
    def temp_param_dir(self):
        """Create a temporary directory with test parameter files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def write_yaml(self, path: Path, content: dict):
        """Helper to write YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(content, f)

    # =========================================
    # 1. Simple Time-Varying Parameters
    # =========================================

    def test_load_simple_parameter(self, temp_param_dir):
        """Load a simple parameter with time-varying values."""
        from src.rac.parameters.loader import ParameterLoader

        # Create parameter file
        self.write_yaml(
            temp_param_dir / "statute/26/3101/b/1/rate.yaml",
            {
                "description": "Medicare tax rate",
                "unit": "/1",
                "values": {
                    "2013-01-01": 0.0145,
                    "1986-01-01": 0.0145,
                },
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        # Get value for 2024
        value = store.get("statute/26/3101/b/1/rate", as_of=date(2024, 1, 1))
        assert value == 0.0145

    def test_time_resolution_uses_most_recent(self, temp_param_dir):
        """Time resolution picks most recent value <= requested date."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/fica/cap.yaml",
            {
                "description": "Social Security wage base",
                "unit": "currency-USD",
                "values": {
                    "2024-01-01": 168600,
                    "2023-01-01": 160200,
                    "2022-01-01": 147000,
                },
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        # 2024 date gets 2024 value
        assert store.get("statute/26/fica/cap", as_of=date(2024, 6, 15)) == 168600
        # 2023 date gets 2023 value
        assert store.get("statute/26/fica/cap", as_of=date(2023, 6, 15)) == 160200
        # Mid-2022 gets 2022 value
        assert store.get("statute/26/fica/cap", as_of=date(2022, 6, 15)) == 147000

    # =========================================
    # 2. Bracket Parameters
    # =========================================

    def test_load_bracket_parameter(self, temp_param_dir):
        """Load a parameter with brackets indexed by numeric value."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/32/b/1/A/credit_percentage.yaml",
            {
                "description": "EITC credit percentage",
                "unit": "/1",
                "index": "statute/26/32/c/1/num_qualifying_children",
                "brackets": [
                    {"threshold": 0, "values": {"2024-01-01": 0.0765}},
                    {"threshold": 1, "values": {"2024-01-01": 0.34}},
                    {"threshold": 2, "values": {"2024-01-01": 0.40}},
                    {"threshold": 3, "values": {"2024-01-01": 0.45}},
                ],
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        # Get value with explicit index
        assert store.get(
            "statute/26/32/b/1/A/credit_percentage",
            as_of=date(2024, 1, 1),
            index_value=0,
        ) == 0.0765

        assert store.get(
            "statute/26/32/b/1/A/credit_percentage",
            as_of=date(2024, 1, 1),
            index_value=2,
        ) == 0.40

        assert store.get(
            "statute/26/32/b/1/A/credit_percentage",
            as_of=date(2024, 1, 1),
            index_value=3,
        ) == 0.45

    def test_bracket_uses_highest_matching_threshold(self, temp_param_dir):
        """Bracket lookup uses highest threshold <= index value."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/32/b/1/A/credit_percentage.yaml",
            {
                "description": "EITC credit percentage",
                "unit": "/1",
                "index": "statute/26/32/c/1/num_qualifying_children",
                "brackets": [
                    {"threshold": 0, "values": {"2024-01-01": 0.0765}},
                    {"threshold": 1, "values": {"2024-01-01": 0.34}},
                    {"threshold": 2, "values": {"2024-01-01": 0.40}},
                    {"threshold": 3, "values": {"2024-01-01": 0.45}},
                ],
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        # 5 children should use threshold 3 (highest <= 5)
        assert store.get(
            "statute/26/32/b/1/A/credit_percentage",
            as_of=date(2024, 1, 1),
            index_value=5,
        ) == 0.45

    def test_bracket_parameter_has_index_path(self, temp_param_dir):
        """Bracket parameter stores its index path for auto-resolution."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/32/b/1/A/credit_percentage.yaml",
            {
                "description": "EITC credit percentage",
                "unit": "/1",
                "index": "statute/26/32/c/1/num_qualifying_children",
                "brackets": [
                    {"threshold": 0, "values": {"2024-01-01": 0.0765}},
                ],
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        param = store.get_definition("statute/26/32/b/1/A/credit_percentage")
        assert param.index_paths == ["statute/26/32/c/1/num_qualifying_children"]

    # =========================================
    # 3. Filing Status Parameters
    # =========================================

    def test_load_filing_status_parameter(self, temp_param_dir):
        """Load a parameter that varies by filing status."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/1411/a/1/threshold.yaml",
            {
                "description": "NIIT threshold",
                "unit": "currency-USD",
                "index": "statute/26/1/filing_status",
                "SINGLE": {"values": {"2013-01-01": 200000}},
                "JOINT": {"values": {"2013-01-01": 250000}},
                "SEPARATE": {"values": {"2013-01-01": 125000}},
                "HEAD_OF_HOUSEHOLD": {"values": {"2013-01-01": 200000}},
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        assert store.get(
            "statute/26/1411/a/1/threshold",
            as_of=date(2024, 1, 1),
            filing_status="SINGLE",
        ) == 200000

        assert store.get(
            "statute/26/1411/a/1/threshold",
            as_of=date(2024, 1, 1),
            filing_status="JOINT",
        ) == 250000

        assert store.get(
            "statute/26/1411/a/1/threshold",
            as_of=date(2024, 1, 1),
            filing_status="SEPARATE",
        ) == 125000

    # =========================================
    # 4. Combined: Filing Status + Brackets
    # =========================================

    def test_load_combined_parameter(self, temp_param_dir):
        """Load a parameter with both filing status and brackets."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/32/b/2/A/phase_out_start.yaml",
            {
                "description": "EITC phase-out start",
                "unit": "currency-USD",
                "index": [
                    "statute/26/1/filing_status",
                    "statute/26/32/c/1/num_qualifying_children",
                ],
                "SINGLE": {
                    "brackets": [
                        {"threshold": 0, "values": {"2024-01-01": 10330}},
                        {"threshold": 1, "values": {"2024-01-01": 22720}},
                    ]
                },
                "JOINT": {
                    "brackets": [
                        {"threshold": 0, "values": {"2024-01-01": 17250}},
                        {"threshold": 1, "values": {"2024-01-01": 29640}},
                    ]
                },
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        # Single, 0 children
        assert store.get(
            "statute/26/32/b/2/A/phase_out_start",
            as_of=date(2024, 1, 1),
            filing_status="SINGLE",
            index_value=0,
        ) == 10330

        # Single, 1 child
        assert store.get(
            "statute/26/32/b/2/A/phase_out_start",
            as_of=date(2024, 1, 1),
            filing_status="SINGLE",
            index_value=1,
        ) == 22720

        # Joint, 0 children
        assert store.get(
            "statute/26/32/b/2/A/phase_out_start",
            as_of=date(2024, 1, 1),
            filing_status="JOINT",
            index_value=0,
        ) == 17250

    def test_combined_parameter_has_multiple_index_paths(self, temp_param_dir):
        """Combined parameter stores multiple index paths."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/32/b/2/A/phase_out_start.yaml",
            {
                "description": "EITC phase-out start",
                "unit": "currency-USD",
                "index": [
                    "statute/26/1/filing_status",
                    "statute/26/32/c/1/num_qualifying_children",
                ],
                "SINGLE": {
                    "brackets": [
                        {"threshold": 0, "values": {"2024-01-01": 10330}},
                    ]
                },
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        param = store.get_definition("statute/26/32/b/2/A/phase_out_start")
        assert param.index_paths == [
            "statute/26/1/filing_status",
            "statute/26/32/c/1/num_qualifying_children",
        ]

    # =========================================
    # 5. Path Resolution
    # =========================================

    def test_path_from_filename(self, temp_param_dir):
        """Parameter path derived from file path relative to root."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/3101/b/1/rate.yaml",
            {
                "description": "Medicare rate",
                "unit": "/1",
                "values": {"2024-01-01": 0.0145},
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        # Path should be statute/26/3101/b/1/rate (without .yaml)
        assert "statute/26/3101/b/1/rate" in store

    def test_unknown_parameter_raises(self, temp_param_dir):
        """Requesting unknown parameter raises KeyError."""
        from src.rac.parameters.loader import ParameterLoader

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        with pytest.raises(KeyError):
            store.get("nonexistent/parameter")


class TestParameterAutoResolution:
    """Tests for auto-resolution of index variables."""

    @pytest.fixture
    def temp_param_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def write_yaml(self, path: Path, content: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(content, f)

    def test_auto_resolve_single_index(self, temp_param_dir):
        """Auto-resolve index from context when not explicitly passed."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/32/b/1/A/credit_percentage.yaml",
            {
                "description": "EITC credit percentage",
                "unit": "/1",
                "index": "statute/26/32/c/1/num_qualifying_children",
                "brackets": [
                    {"threshold": 0, "values": {"2024-01-01": 0.0765}},
                    {"threshold": 1, "values": {"2024-01-01": 0.34}},
                    {"threshold": 2, "values": {"2024-01-01": 0.40}},
                ],
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        # Provide context with the variable value
        context = {"statute/26/32/c/1/num_qualifying_children": 2}

        value = store.get_with_context(
            "statute/26/32/b/1/A/credit_percentage",
            as_of=date(2024, 1, 1),
            context=context,
        )
        assert value == 0.40

    def test_auto_resolve_filing_status(self, temp_param_dir):
        """Auto-resolve filing status from context."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/1411/a/1/threshold.yaml",
            {
                "description": "NIIT threshold",
                "unit": "currency-USD",
                "index": "statute/26/1/filing_status",
                "SINGLE": {"values": {"2013-01-01": 200000}},
                "JOINT": {"values": {"2013-01-01": 250000}},
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        context = {"statute/26/1/filing_status": "JOINT"}

        value = store.get_with_context(
            "statute/26/1411/a/1/threshold",
            as_of=date(2024, 1, 1),
            context=context,
        )
        assert value == 250000

    def test_auto_resolve_combined(self, temp_param_dir):
        """Auto-resolve both filing status and numeric index from context."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/32/b/2/A/phase_out_start.yaml",
            {
                "description": "EITC phase-out start",
                "unit": "currency-USD",
                "index": [
                    "statute/26/1/filing_status",
                    "statute/26/32/c/1/num_qualifying_children",
                ],
                "SINGLE": {
                    "brackets": [
                        {"threshold": 0, "values": {"2024-01-01": 10330}},
                        {"threshold": 1, "values": {"2024-01-01": 22720}},
                    ]
                },
                "JOINT": {
                    "brackets": [
                        {"threshold": 0, "values": {"2024-01-01": 17250}},
                        {"threshold": 1, "values": {"2024-01-01": 29640}},
                    ]
                },
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        context = {
            "statute/26/1/filing_status": "JOINT",
            "statute/26/32/c/1/num_qualifying_children": 1,
        }

        value = store.get_with_context(
            "statute/26/32/b/2/A/phase_out_start",
            as_of=date(2024, 1, 1),
            context=context,
        )
        assert value == 29640

    def test_explicit_index_overrides_auto_resolve(self, temp_param_dir):
        """Explicitly passed index takes precedence over auto-resolution."""
        from src.rac.parameters.loader import ParameterLoader

        self.write_yaml(
            temp_param_dir / "statute/26/32/b/1/A/credit_percentage.yaml",
            {
                "description": "EITC credit percentage",
                "unit": "/1",
                "index": "statute/26/32/c/1/num_qualifying_children",
                "brackets": [
                    {"threshold": 0, "values": {"2024-01-01": 0.0765}},
                    {"threshold": 1, "values": {"2024-01-01": 0.34}},
                    {"threshold": 2, "values": {"2024-01-01": 0.40}},
                ],
            },
        )

        loader = ParameterLoader(temp_param_dir)
        store = loader.load_all()

        # Context says 2 children, but we explicitly pass 0
        context = {"statute/26/32/c/1/num_qualifying_children": 2}

        value = store.get_with_context(
            "statute/26/32/b/1/A/credit_percentage",
            as_of=date(2024, 1, 1),
            context=context,
            index_value=0,  # Explicit override
        )
        assert value == 0.0765  # Should use explicit 0, not context's 2
