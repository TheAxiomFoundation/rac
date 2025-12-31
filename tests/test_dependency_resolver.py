"""Tests for dependency resolution across statute files.

Following TDD - these tests define expected behavior for resolving
cross-file references in cosilico statute encodings.

The dependency resolver must:
1. Parse referenced statute files
2. Build a dependency graph
3. Execute in topological order
4. Pass outputs from dependencies as inputs to dependents
"""

import pytest
import tempfile
from pathlib import Path

from src.rac.dsl_parser import parse_dsl


class TestDependencyGraph:
    """Test building dependency graphs from references."""

    def test_extract_dependencies_from_references(self):
        """Extract dependency paths from a module's references block."""
        from src.rac.dependency_resolver import extract_dependencies

        code = """
imports:
  earned_income: statute/26/32/c/2/A#earned_income
  filing_status: statute/26/1#filing_status

variable credit:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return earned_income * 0.1 }
"""
        module = parse_dsl(code)
        deps = extract_dependencies(module)

        # extract_dependencies returns (package, file_path) tuples
        dep_paths = [path for pkg, path in deps]
        assert "statute/26/32/c/2/A" in dep_paths
        assert "statute/26/1" in dep_paths

    def test_no_dependencies_without_references(self):
        """Module without references has no dependencies."""
        from src.rac.dependency_resolver import extract_dependencies

        code = """
variable simple:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return income * 0.1 }
"""
        module = parse_dsl(code)
        deps = extract_dependencies(module)

        assert deps == []

    def test_build_dependency_graph(self):
        """Build graph from multiple modules with dependencies."""
        from src.rac.dependency_resolver import DependencyGraph

        # A depends on B, B depends on C, C has no deps
        graph = DependencyGraph()
        graph.add_module("A", dependencies=["B"])
        graph.add_module("B", dependencies=["C"])
        graph.add_module("C", dependencies=[])

        assert graph.get_dependencies("A") == ["B"]
        assert graph.get_dependencies("B") == ["C"]
        assert graph.get_dependencies("C") == []

    def test_topological_sort(self):
        """Topological sort produces valid execution order."""
        from src.rac.dependency_resolver import DependencyGraph

        graph = DependencyGraph()
        graph.add_module("A", dependencies=["B", "C"])
        graph.add_module("B", dependencies=["C"])
        graph.add_module("C", dependencies=[])

        order = graph.topological_sort()

        # C must come before B, B must come before A
        assert order.index("C") < order.index("B")
        assert order.index("B") < order.index("A")

    def test_detect_circular_dependency(self):
        """Detect and report circular dependencies."""
        from src.rac.dependency_resolver import DependencyGraph, CircularDependencyError

        graph = DependencyGraph()
        graph.add_module("A", dependencies=["B"])
        graph.add_module("B", dependencies=["A"])  # Circular!

        with pytest.raises(CircularDependencyError) as exc_info:
            graph.topological_sort()

        assert "circular" in str(exc_info.value).lower()


class TestModuleResolver:
    """Test resolving reference paths to actual files."""

    def test_resolve_statute_path(self):
        """Resolve statute path to filesystem path."""
        from src.rac.dependency_resolver import ModuleResolver

        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            # Create nested structure with statute/ prefix
            (root_dir / "statute/26/32/c/2/A").mkdir(parents=True)
            earned_income_file = root_dir / "statute/26/32/c/2/A/earned_income.rac"
            earned_income_file.write_text("""
variable earned_income:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return wages + self_employment_income }
""")

            resolver = ModuleResolver(statute_root=root_dir)
            path = resolver.resolve("statute/26/32/c/2/A/earned_income")

            assert path == earned_income_file

    def test_resolve_missing_file_raises(self):
        """Raise error for unresolvable reference."""
        from src.rac.dependency_resolver import ModuleResolver, ModuleNotFoundError

        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = ModuleResolver(statute_root=Path(tmpdir))

            with pytest.raises(ModuleNotFoundError):
                resolver.resolve("statute/99/999/nonexistent")


class TestDependencyResolver:
    """Integration tests for full dependency resolution."""

    def test_resolve_and_load_all_dependencies(self):
        """Load all dependencies recursively."""
        from src.rac.dependency_resolver import DependencyResolver

        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)

            # Create dependency chain: credit -> earned_income -> wages
            (root_dir / "statute/26/32").mkdir(parents=True)
            (root_dir / "statute/26/61").mkdir(parents=True)

            # wages (no deps)
            (root_dir / "statute/26/61/wages.rac").write_text("""
variable wages:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return wage_salary_income
""")

            # earned_income (depends on wages)
            (root_dir / "statute/26/32/earned_income.rac").write_text("""
imports:
  wages: statute/26/61/wages#wages

variable earned_income:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return wages + self_employment_income
""")

            # credit (depends on earned_income)
            (root_dir / "statute/26/32/credit.rac").write_text("""
imports:
  earned_income: statute/26/32/earned_income#earned_income

variable credit:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return earned_income * 0.1
""")

            resolver = DependencyResolver(statute_root=root_dir)
            modules = resolver.resolve_all("statute/26/32/credit")

            # Should have all 3 modules
            assert len(modules) == 3

            # Check execution order (deps before dependents)
            paths = [m.path for m in modules]
            assert paths.index("statute/26/61/wages") < paths.index("statute/26/32/earned_income")
            assert paths.index("statute/26/32/earned_income") < paths.index("statute/26/32/credit")


class TestExecutorWithDependencies:
    """Test executor handles cross-file dependencies."""

    @pytest.mark.skip(reason="VectorizedExecutor.execute_with_dependencies not implemented")
    def test_execute_with_resolved_dependencies(self):
        """Execute formula with resolved dependency values."""
        from src.rac.dependency_resolver import DependencyResolver
        from src.rac.vectorized_executor import VectorizedExecutor
        import numpy as np

        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)

            # Simple chain: credit = earned_income * 0.1
            (root_dir / "statute/income").mkdir(parents=True)
            (root_dir / "statute/credit").mkdir(parents=True)

            (root_dir / "statute/income/earned.rac").write_text("""
variable earned_income:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return wages
""")

            (root_dir / "statute/credit/eitc.rac").write_text("""
imports:
  earned_income: statute/income/earned#earned_income

variable eitc:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return earned_income * 0.1
""")

            # Resolve dependencies
            resolver = DependencyResolver(statute_root=root_dir)

            # Execute with dependency resolution
            executor = VectorizedExecutor(
                dependency_resolver=resolver,
                n_workers=1
            )

            inputs = {
                "wages": np.array([10000, 20000, 30000]),
                "weight": np.array([1.0, 1.0, 1.0]),
            }

            results = executor.execute_with_dependencies(
                entry_point="statute/credit/eitc",
                inputs=inputs,
                output_variables=["eitc"]
            )

            # credit = earned_income * 0.1 = wages * 0.1
            expected = np.array([1000, 2000, 3000])
            np.testing.assert_array_almost_equal(results["eitc"], expected)


class TestEITCWithDependencies:
    """Test EITC calculation with real cosilico-us files."""

    @pytest.fixture
    def cosilico_us_path(self):
        """Get path to cosilico-us if available."""
        candidates = [
            Path.home() / "CosilicoAI" / "cosilico-us",
            Path(__file__).parents[2] / "cosilico-us",
        ]
        for path in candidates:
            if path.exists():
                return path
        pytest.skip("cosilico-us not found")

    def test_eitc_resolves_all_dependencies(self, cosilico_us_path):
        """EITC formula resolves all its referenced dependencies."""
        # Skip: EITC file uses per-variable imports format that parser doesn't support yet
        pytest.skip("Parser needs enhancement for per-variable imports format")
        from src.rac.dependency_resolver import DependencyResolver

        resolver = DependencyResolver(statute_root=cosilico_us_path)
        modules = resolver.resolve_all("statute/26/32/a/1/earned_income_credit")

        # Should resolve multiple dependencies (some may be placeholders for missing files)
        assert len(modules) >= 1

        # Entry point should have parsed successfully
        eitc_modules = [m for m in modules if "earned_income_credit" in m.path]
        assert len(eitc_modules) == 1
        assert eitc_modules[0].module is not None

        # Count how many actually parsed vs placeholders
        parsed = [m for m in modules if m.module is not None]
        placeholders = [m for m in modules if m.module is None]
        print(f"Parsed: {len(parsed)}, Placeholders: {len(placeholders)}")

        # At least the entry point and some dependencies should parse
        assert len(parsed) >= 3
