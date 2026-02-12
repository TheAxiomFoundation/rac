"""Tests for cross-package imports (e.g., rac-us-ca importing from rac-us).

TDD tests for state jurisdiction repos importing federal variables.

Use case: California R&TC § 17071 starts with federal AGI (26 USC § 62),
then makes California-specific adjustments.

Import syntax: package:path#variable
  - package: source package name (e.g., rac-us)
  - path: file path within package (e.g., statute/26/62/a)
  - variable: variable name within file (e.g., adjusted_gross_income)

Example: rac-us:statute/26/62/a#adjusted_gross_income
"""

import tempfile
from pathlib import Path

import pytest

from src.rac.dsl_parser import parse_dsl


class TestCrossPackageImportSyntax:
    """Test parsing of cross-package import syntax."""

    def test_parse_external_package_import(self):
        """Parse import with package prefix: rac-us:statute/26/62/a#agi"""
        code = """
variable ca_agi:
  imports:
    - rac-us:statute/26/62/a#adjusted_gross_income
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return adjusted_gross_income
"""
        module = parse_dsl(code)
        var = module.variables[0]

        # Should have one import with package prefix
        assert len(var.imports) == 1
        imp = var.imports[0]

        # Import should identify external package
        assert imp.package == "rac-us"
        assert imp.file_path == "statute/26/62/a"
        assert imp.variable_name == "adjusted_gross_income"

    def test_parse_module_level_external_import(self):
        """Parse module-level import with package prefix."""
        code = """
imports:
  federal_agi: rac-us:statute/26/62/a#adjusted_gross_income
  federal_std_ded: rac-us:statute/26/63/c#standard_deduction

variable ca_taxable_income:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return federal_agi - ca_adjustments
"""
        module = parse_dsl(code)

        # Module-level imports should capture package prefix
        refs = module.imports.references

        fed_agi = next(r for r in refs if r.alias == "federal_agi")
        assert fed_agi.package == "rac-us"
        assert fed_agi.variable_name == "adjusted_gross_income"

        fed_std = next(r for r in refs if r.alias == "federal_std_ded")
        assert fed_std.package == "rac-us"

    def test_parse_local_import_no_package(self):
        """Local imports (same package) should have no package prefix."""
        code = """
variable some_var:
  imports:
    - statute/ca/rtc/17024#ca_exemption
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return ca_exemption
"""
        module = parse_dsl(code)
        var = module.variables[0]
        imp = var.imports[0]

        # Local import - no package
        assert imp.package is None
        assert imp.file_path == "statute/ca/rtc/17024"
        assert imp.variable_name == "ca_exemption"

    def test_parse_aliased_external_import(self):
        """Parse aliased external import: rac-us:path#var as alias"""
        code = """
variable ca_agi:
  imports:
    - rac-us:statute/26/62/a#adjusted_gross_income as fed_agi
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return fed_agi + ca_additions - ca_subtractions
"""
        module = parse_dsl(code)
        var = module.variables[0]
        imp = var.imports[0]

        assert imp.package == "rac-us"
        assert imp.variable_name == "adjusted_gross_income"
        assert imp.alias == "fed_agi"


class TestPackageRegistry:
    """Test package registry for multi-root resolution."""

    def test_create_registry_with_multiple_packages(self):
        """Create registry mapping package names to roots."""
        from src.rac.dependency_resolver import PackageRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            us_root = Path(tmpdir) / "rac-us"
            ca_root = Path(tmpdir) / "rac-us-ca"
            us_root.mkdir()
            ca_root.mkdir()

            registry = PackageRegistry()
            registry.register("rac-us", us_root)
            registry.register("rac-us-ca", ca_root)

            assert registry.get_root("rac-us") == us_root
            assert registry.get_root("rac-us-ca") == ca_root

    def test_registry_unknown_package_raises(self):
        """Unknown package should raise PackageNotFoundError."""
        from src.rac.dependency_resolver import PackageNotFoundError, PackageRegistry

        registry = PackageRegistry()

        with pytest.raises(PackageNotFoundError) as exc:
            registry.get_root("nonexistent-package")

        assert "nonexistent-package" in str(exc.value)

    def test_registry_from_workspace(self):
        """Create registry from workspace directory (sibling repos)."""
        from src.rac.dependency_resolver import PackageRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create sibling repos
            (workspace / "rac-us" / "statute").mkdir(parents=True)
            (workspace / "rac-us-ca" / "statute").mkdir(parents=True)
            (workspace / "rac-us-ny" / "statute").mkdir(parents=True)

            registry = PackageRegistry.from_workspace(workspace)

            assert registry.get_root("rac-us") == workspace / "rac-us"
            assert registry.get_root("rac-us-ca") == workspace / "rac-us-ca"
            assert registry.get_root("rac-us-ny") == workspace / "rac-us-ny"

    def test_registry_default_package(self):
        """Registry can have a default package for unqualified imports."""
        from src.rac.dependency_resolver import PackageRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            ca_root = Path(tmpdir) / "rac-us-ca"
            ca_root.mkdir()

            registry = PackageRegistry(default="rac-us-ca")
            registry.register("rac-us-ca", ca_root)

            # Unqualified path should resolve to default
            assert registry.get_root(None) == ca_root


class TestMultiRootResolver:
    """Test dependency resolver with multiple package roots."""

    def test_resolve_cross_package_reference(self):
        """Resolve import from external package."""
        from src.rac.dependency_resolver import DependencyResolver, PackageRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Set up federal (rac-us)
            us_root = workspace / "rac-us"
            (us_root / "statute/26/62").mkdir(parents=True)
            (us_root / "statute/26/62/a.rac").write_text("""
variable adjusted_gross_income:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula:
    return gross_income - above_the_line_deductions
""")

            # Set up California (rac-us-ca)
            ca_root = workspace / "rac-us-ca"
            (ca_root / "statute/ca/rtc").mkdir(parents=True)
            (ca_root / "statute/ca/rtc/17071.rac").write_text("""
variable ca_adjusted_gross_income:
  imports:
    - rac-us:statute/26/62/a#adjusted_gross_income
  entity: TaxUnit
  period: Year
  dtype: Money
  formula:
    # CA starts with federal AGI
    return adjusted_gross_income + ca_additions - ca_subtractions
""")

            # Create registry
            registry = PackageRegistry.from_workspace(workspace)
            registry.set_default("rac-us-ca")

            # Resolve with multi-root
            resolver = DependencyResolver(registry=registry)
            modules = resolver.resolve_all("statute/ca/rtc/17071")

            # Should load both CA and federal modules
            paths = [m.path for m in modules]
            assert any("17071" in p for p in paths)
            assert any("62/a" in p for p in paths)

            # Federal should come before CA (dependency order)
            fed_idx = next(i for i, m in enumerate(modules) if "62/a" in m.path)
            ca_idx = next(i for i, m in enumerate(modules) if "17071" in m.path)
            assert fed_idx < ca_idx

    def test_resolve_mixed_local_and_external(self):
        """Resolve imports from both local and external packages."""
        from src.rac.dependency_resolver import DependencyResolver, PackageRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Federal package
            us_root = workspace / "rac-us"
            (us_root / "statute/26/62").mkdir(parents=True)
            (us_root / "statute/26/62/a.rac").write_text("""
variable adjusted_gross_income:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return gross_income
""")

            # California package
            ca_root = workspace / "rac-us-ca"

            # CA exemption (local)
            (ca_root / "statute/ca/rtc").mkdir(parents=True)
            (ca_root / "statute/ca/rtc/17054.rac").write_text("""
variable ca_personal_exemption:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return n_exemptions * exemption_amount
""")

            # CA tax (depends on both federal AGI and local exemption)
            (ca_root / "statute/ca/rtc/17041.rac").write_text("""
variable ca_income_tax:
  imports:
    - rac-us:statute/26/62/a#adjusted_gross_income
    - statute/ca/rtc/17054#ca_personal_exemption
  entity: TaxUnit
  period: Year
  dtype: Money
  formula:
    let taxable = adjusted_gross_income - ca_personal_exemption
    return taxable * ca_tax_rate
""")

            registry = PackageRegistry.from_workspace(workspace)
            registry.set_default("rac-us-ca")

            resolver = DependencyResolver(registry=registry)
            modules = resolver.resolve_all("statute/ca/rtc/17041")

            # Should have 3 modules
            assert len(modules) == 3

            # Check all resolved
            module_vars = [m.path for m in modules if m.module]
            assert len(module_vars) == 3


class TestStateRepoStructure:
    """Test recommended structure for state repos."""

    def test_ca_repo_follows_rtc_structure(self):
        """California repo follows Revenue and Taxation Code structure."""
        # This documents the expected structure for rac-us-ca

        expected_structure = {
            "statute/ca/rtc/17024": "Personal exemption credits",
            "statute/ca/rtc/17041": "Tax imposed on individuals",
            "statute/ca/rtc/17054": "Exemption credits",
            "statute/ca/rtc/17071": "Gross income (starts with IRC 61)",
            "statute/ca/rtc/17073": "Adjusted gross income (starts with IRC 62)",
            "statute/ca/rtc/17201": "Itemized deductions",
        }

        # Verify naming convention follows: statute/{state}/{code}/{section}
        for path in expected_structure:
            parts = path.split("/")
            assert parts[0] == "statute"
            assert parts[1] == "ca"  # state abbreviation
            assert parts[2] == "rtc"  # code abbreviation (Revenue & Taxation Code)
            assert parts[3].isdigit()  # section number

    def test_ny_repo_follows_tax_law_structure(self):
        """New York repo follows Tax Law structure."""
        expected_structure = {
            "statute/ny/tax/601": "Imposition of tax",
            "statute/ny/tax/611": "New York adjusted gross income",
            "statute/ny/tax/612": "New York deductions",
            "statute/ny/tax/615": "New York itemized deduction",
        }

        for path in expected_structure:
            parts = path.split("/")
            assert parts[0] == "statute"
            assert parts[1] == "ny"
            assert parts[2] == "tax"  # Tax Law


class TestExecutionWithCrossPackage:
    """Test executing formulas with cross-package dependencies."""

    @pytest.mark.skip(reason="VectorizedExecutor integration pending")
    def test_execute_ca_tax_with_federal_agi(self):
        """Execute California tax calculation using federal AGI."""
        import numpy as np

        from src.rac.dependency_resolver import DependencyResolver, PackageRegistry
        from src.rac.vectorized_executor import VectorizedExecutor

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Federal AGI
            us_root = workspace / "rac-us"
            (us_root / "statute/26/62/a").mkdir(parents=True)
            (us_root / "statute/26/62/a/agi.rac").write_text("""
variable adjusted_gross_income:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return gross_income
""")

            # CA tax (10% of federal AGI for simplicity)
            ca_root = workspace / "rac-us-ca"
            (ca_root / "statute/ca/rtc/17041").mkdir(parents=True)
            (ca_root / "statute/ca/rtc/17041/tax.rac").write_text("""
parameter ca_flat_rate:
  values:
    2024-01-01: 0.10

variable ca_income_tax:
  imports:
    - rac-us:statute/26/62/a#adjusted_gross_income
  entity: TaxUnit
  period: Year
  dtype: Money
  formula:
    return adjusted_gross_income * ca_flat_rate
""")

            registry = PackageRegistry.from_workspace(workspace)
            registry.set_default("rac-us-ca")

            resolver = DependencyResolver(registry=registry)
            executor = VectorizedExecutor(dependency_resolver=resolver)

            inputs = {
                "gross_income": np.array([50000, 100000, 150000]),
                "weight": np.array([1.0, 1.0, 1.0]),
            }

            results = executor.execute_with_dependencies(
                entry_point="statute/ca/rtc/17041/tax",
                inputs=inputs,
                output_variables=["ca_income_tax"],
                tax_year=2024,
            )

            # 10% of gross_income (which flows through federal AGI)
            expected = np.array([5000, 10000, 15000])
            np.testing.assert_array_almost_equal(results["ca_income_tax"], expected)
