"""Tests for vectorized DSL executor.

Following TDD principles - these tests define the expected behavior.
"""

import numpy as np
import pytest
from numpy.testing import assert_array_almost_equal, assert_array_equal

from src.rac.vectorized_executor import (
    DependencyGraph,
    EntityIndex,
    Scenario,
    VectorizedContext,
    VectorizedExecutor,
)


class TestDependencyGraph:
    """Tests for dependency graph and parallel execution planning."""

    def test_empty_graph(self):
        """Empty graph should return empty results."""
        graph = DependencyGraph()
        assert graph.topological_order() == []
        assert graph.parallel_groups() == []

    def test_single_variable_no_deps(self):
        """Single variable with no dependencies."""
        graph = DependencyGraph()
        graph.add_variable("a", [])
        assert graph.topological_order() == ["a"]
        assert graph.parallel_groups() == [["a"]]

    def test_linear_chain(self):
        """Linear dependency chain: a -> b -> c."""
        graph = DependencyGraph()
        graph.add_variable("a", [])
        graph.add_variable("b", ["a"])
        graph.add_variable("c", ["b"])

        topo = graph.topological_order()
        assert topo.index("a") < topo.index("b") < topo.index("c")

        groups = graph.parallel_groups()
        assert len(groups) == 3  # Each in its own group
        assert ["a"] in groups
        assert ["b"] in groups
        assert ["c"] in groups

    def test_diamond_pattern(self):
        """Diamond: a -> b, a -> c, b -> d, c -> d."""
        graph = DependencyGraph()
        graph.add_variable("a", [])
        graph.add_variable("b", ["a"])
        graph.add_variable("c", ["a"])
        graph.add_variable("d", ["b", "c"])

        topo = graph.topological_order()
        assert topo.index("a") < topo.index("b")
        assert topo.index("a") < topo.index("c")
        assert topo.index("b") < topo.index("d")
        assert topo.index("c") < topo.index("d")

        groups = graph.parallel_groups()
        # a first, then b and c can be parallel, then d
        assert ["a"] in groups
        assert sorted(["b", "c"]) in [sorted(g) for g in groups]
        assert ["d"] in groups

    def test_multiple_roots(self):
        """Multiple independent variables can run in parallel."""
        graph = DependencyGraph()
        graph.add_variable("a", [])
        graph.add_variable("b", [])
        graph.add_variable("c", [])

        groups = graph.parallel_groups()
        # All three should be in the same group (can run in parallel)
        assert len(groups) == 1
        assert sorted(groups[0]) == ["a", "b", "c"]


class TestScenario:
    """Tests for copy-on-write scenario semantics."""

    def test_empty_scenario(self):
        """Empty scenario returns None for missing variables."""
        scenario = Scenario()
        assert scenario.get("nonexistent") is None

    def test_override(self):
        """Overrides take precedence."""
        scenario = Scenario()
        scenario.set("income", np.array([1000, 2000]))
        result = scenario.get("income")
        assert_array_equal(result, [1000, 2000])

    def test_cache(self):
        """Cached results are returned."""
        scenario = Scenario()
        scenario.cache_result("computed", np.array([100, 200]))
        result = scenario.get("computed")
        assert_array_equal(result, [100, 200])

    def test_override_clears_cache(self):
        """Setting override clears the cache."""
        scenario = Scenario()
        scenario.cache_result("computed", np.array([100, 200]))
        scenario.set("income", np.array([1000, 2000]))
        # Cache should be cleared
        assert "computed" not in scenario.cache

    def test_fork_inherits_base(self):
        """Forked scenario inherits from base."""
        base = Scenario()
        base.set("income", np.array([1000, 2000]))
        base.cache_result("tax", np.array([100, 200]))

        child = base.fork()
        assert_array_equal(child.get("income"), [1000, 2000])
        assert_array_equal(child.get("tax"), [100, 200])

    def test_fork_override_doesnt_affect_base(self):
        """Child override doesn't affect base scenario."""
        base = Scenario()
        base.set("income", np.array([1000, 2000]))

        child = base.fork()
        child.set("income", np.array([5000, 6000]))

        assert_array_equal(base.get("income"), [1000, 2000])
        assert_array_equal(child.get("income"), [5000, 6000])


class TestEntityIndex:
    """Tests for entity relationship mapping."""

    def test_entity_index_creation(self):
        """Create entity index for a household structure."""
        # 2 tax units, 4 persons total
        # TaxUnit 0: persons 0, 1
        # TaxUnit 1: persons 2, 3
        index = EntityIndex(
            person_to_tax_unit=np.array([0, 0, 1, 1]),
            tax_unit_to_household=np.array([0, 0]),
            n_persons=4,
            n_tax_units=2,
            n_households=1,
        )
        assert index.n_persons == 4
        assert index.n_tax_units == 2


class TestVectorizedContext:
    """Tests for execution context."""

    def test_get_input_variable(self):
        """Get variable from inputs."""
        ctx = VectorizedContext(
            inputs={"income": np.array([1000, 2000, 3000])},
            parameters={},
            variables={},
        )
        result = ctx.get_variable("income")
        assert_array_equal(result, [1000, 2000, 3000])

    def test_get_missing_variable_returns_zeros(self):
        """Missing variable returns zeros."""
        ctx = VectorizedContext(
            inputs={"income": np.array([1000, 2000, 3000])},
            parameters={},
            variables={},
        )
        result = ctx.get_variable("nonexistent")
        assert_array_equal(result, [0, 0, 0])

    def test_parameter_broadcast(self):
        """Scalar parameter broadcasts to entity dimension."""
        ctx = VectorizedContext(
            inputs={"income": np.array([1000, 2000, 3000])},
            parameters={"tax_rate": 0.25},
            variables={},
        )
        result = ctx.get_parameter("tax_rate")
        assert_array_equal(result, [0.25, 0.25, 0.25])

    def test_indexed_parameter(self):
        """Indexed parameter lookup."""
        ctx = VectorizedContext(
            inputs={
                "income": np.array([1000, 2000, 3000]),
                "n_children": np.array([0, 1, 2]),
            },
            parameters={"rate": {0: 0.0765, 1: 0.34, 2: 0.40}},
            variables={},
        )
        result = ctx.get_parameter("rate", "n_children")
        assert_array_almost_equal(result, [0.0765, 0.34, 0.40])


class TestEntityAggregation:
    """Tests for entity-level aggregations."""

    def test_sum_persons_to_tax_unit(self):
        """Sum Person values to TaxUnit level."""
        # 2 tax units, 4 persons
        # TaxUnit 0: persons 0, 1 with incomes 1000, 2000
        # TaxUnit 1: persons 2, 3 with incomes 3000, 4000
        index = EntityIndex(
            person_to_tax_unit=np.array([0, 0, 1, 1]),
            tax_unit_to_household=np.array([0, 0]),
            n_persons=4,
            n_tax_units=2,
            n_households=1,
        )
        ctx = VectorizedContext(
            inputs={"person_income": np.array([1000, 2000, 3000, 4000])},
            parameters={},
            variables={},
            entity_index=index,
        )

        result = ctx.aggregate_to_parent(
            ctx.inputs["person_income"],
            from_entity="Person",
            to_entity="TaxUnit",
            agg_func="sum"
        )
        assert_array_equal(result, [3000, 7000])

    def test_count_persons_in_tax_unit(self):
        """Count persons per tax unit."""
        index = EntityIndex(
            person_to_tax_unit=np.array([0, 0, 0, 1, 1]),  # 3 in TU0, 2 in TU1
            tax_unit_to_household=np.array([0, 0]),
            n_persons=5,
            n_tax_units=2,
            n_households=1,
        )
        ctx = VectorizedContext(
            inputs={},
            parameters={},
            variables={},
            entity_index=index,
        )

        ones = np.ones(5)
        result = ctx.aggregate_to_parent(ones, "Person", "TaxUnit", "sum")
        assert_array_equal(result, [3, 2])

    def test_any_aggregation(self):
        """Any aggregation (boolean OR)."""
        index = EntityIndex(
            person_to_tax_unit=np.array([0, 0, 1, 1]),
            tax_unit_to_household=np.array([0, 0]),
            n_persons=4,
            n_tax_units=2,
            n_households=1,
        )
        ctx = VectorizedContext(
            inputs={},
            parameters={},
            variables={},
            entity_index=index,
        )

        # TU0: False, True -> True
        # TU1: False, False -> False
        values = np.array([False, True, False, False])
        result = ctx.aggregate_to_parent(values, "Person", "TaxUnit", "any")
        assert_array_equal(result, [True, False])

    def test_broadcast_tax_unit_to_person(self):
        """Broadcast TaxUnit value to Person level."""
        index = EntityIndex(
            person_to_tax_unit=np.array([0, 0, 1, 1]),
            tax_unit_to_household=np.array([0, 0]),
            n_persons=4,
            n_tax_units=2,
            n_households=1,
        )
        ctx = VectorizedContext(
            inputs={},
            parameters={},
            variables={},
            entity_index=index,
        )

        tu_values = np.array([100, 200])  # TU0=100, TU1=200
        result = ctx.broadcast_to_child(tu_values, "TaxUnit", "Person")
        assert_array_equal(result, [100, 100, 200, 200])


class TestVectorizedExecutor:
    """Tests for the main executor."""

    def test_simple_formula(self):
        """Execute simple formula."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"income": np.array([10000, 20000, 30000])}
        results = executor.execute(code, inputs)

        assert "tax" in results
        assert_array_equal(results["tax"], [2500, 5000, 7500])

    def test_formula_with_max(self):
        """Formula using max function."""
        code = """
variable credit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return max(0, 1000 - income * 0.1)

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"income": np.array([5000, 10000, 15000])}
        results = executor.execute(code, inputs)

        # 1000 - 500 = 500, 1000 - 1000 = 0, max(0, 1000 - 1500) = 0
        assert_array_equal(results["credit"], [500, 0, 0])

    def test_formula_with_min(self):
        """Formula using min function."""
        code = """
variable capped_income:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return min(income, 50000)

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"income": np.array([30000, 50000, 70000])}
        results = executor.execute(code, inputs)

        assert_array_equal(results["capped_income"], [30000, 50000, 50000])

    def test_formula_with_let_binding(self):
        """Formula with let bindings."""
        code = """
variable eitc:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let phase_in = income * 0.34
    let max_credit = 6960
    return min(phase_in, max_credit)

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"income": np.array([10000, 20000, 30000])}
        results = executor.execute(code, inputs)

        # 10000*0.34=3400, 20000*0.34=6800, min(30000*0.34, 6960)=6960
        assert_array_almost_equal(results["eitc"], [3400, 6800, 6960])

    def test_conditional_formula(self):
        """Formula with if/else expression."""
        code = """
variable benefit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    if income < 20000: 1000 else 0

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"income": np.array([15000, 20000, 25000])}
        results = executor.execute(code, inputs)

        assert_array_equal(results["benefit"], [1000, 0, 0])

    def test_scenario_caching(self):
        """Scenario caches computed results."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"income": np.array([10000, 20000])}
        scenario = Scenario()

        # First execution
        results1 = executor.execute(code, inputs, scenario=scenario)
        assert "tax" in scenario.cache

        # Second execution uses cache
        results2 = executor.execute(code, inputs, scenario=scenario)
        assert_array_equal(results1["tax"], results2["tax"])

    def test_multiple_variables(self):
        """Execute multiple dependent variables."""
        code = """
variable gross_income:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return wages + interest


variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return gross_income * 0.25

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {
            "wages": np.array([50000, 60000]),
            "interest": np.array([1000, 2000]),
        }
        results = executor.execute(code, inputs)

        assert_array_equal(results["gross_income"], [51000, 62000])
        assert_array_equal(results["tax"], [12750, 15500])


class TestEITCCalculation:
    """Integration tests for EITC-like calculations."""

    def test_eitc_phase_in(self):
        """EITC phase-in calculation."""
        code = """
variable eitc_phase_in:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let rate = 0.34
    let cap = 11750
    return rate * min(earned_income, cap)

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"earned_income": np.array([5000, 11750, 20000])}
        results = executor.execute(code, inputs)

        # 5000 * 0.34 = 1700
        # 11750 * 0.34 = 3995
        # min(20000, 11750) * 0.34 = 3995
        assert_array_almost_equal(results["eitc_phase_in"], [1700, 3995, 3995])

    def test_eitc_with_children_index(self):
        """EITC with indexed parameters by number of children."""
        code = """
variable eitc:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let rate = credit_rate[count_children]
    return earned_income * rate

"""
        executor = VectorizedExecutor(
            parameters={"credit_rate": {0: 0.0765, 1: 0.34, 2: 0.40, 3: 0.45}}
        )
        inputs = {
            "earned_income": np.array([10000, 10000, 10000, 10000]),
            "count_children": np.array([0, 1, 2, 3]),
        }
        results = executor.execute(code, inputs)

        assert_array_almost_equal(
            results["eitc"],
            [765, 3400, 4000, 4500]
        )


class TestPerformance:
    """Performance regression tests."""

    def test_million_entities_under_10ms(self):
        """1M entities should execute in under 10ms for simple formula."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return max(0, income * 0.25 - 1000)

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"income": np.random.uniform(0, 100000, 1_000_000)}

        import time
        start = time.perf_counter()
        executor.execute(code, inputs)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.010, f"Execution took {elapsed*1000:.1f}ms, expected <10ms"


class TestEnumSupport:
    """Tests for enum declaration and comparison support."""

    def test_enum_comparison_without_quotes(self):
        """Enum values can be used without quotes in comparisons."""
        code = """
enum FilingStatus:
  SINGLE
  JOINT
  HEAD_OF_HOUSEHOLD

variable threshold:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return if filing_status == JOINT: 250000 else 200000

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"filing_status": np.array(["JOINT", "SINGLE", "JOINT"])}
        results = executor.execute(code, inputs)

        # JOINT gets $250k, SINGLE gets $200k
        assert_array_equal(results["threshold"], [250000, 200000, 250000])

    def test_enum_multiple_values(self):
        """Test multiple enum values in if/else chain."""
        code = """
enum FilingStatus:
  SINGLE
  JOINT
  SEPARATE
  HEAD_OF_HOUSEHOLD
  SURVIVING_SPOUSE

variable niit_threshold:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return if filing_status == JOINT: 250000
      else if filing_status == SURVIVING_SPOUSE: 250000
      else if filing_status == SEPARATE: 125000
      else 200000

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {
            "filing_status": np.array([
                "JOINT", "SINGLE", "SEPARATE", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE"
            ])
        }
        results = executor.execute(code, inputs)

        assert_array_equal(
            results["niit_threshold"],
            [250000, 200000, 125000, 200000, 250000]
        )

    def test_string_literals_still_work(self):
        """String literals continue to work alongside enum support."""
        code = """
enum FilingStatus:
  SINGLE
  JOINT

variable threshold:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return if filing_status == "JOINT": 250000 else 200000

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"filing_status": np.array(["JOINT", "SINGLE"])}
        results = executor.execute(code, inputs)

        assert_array_equal(results["threshold"], [250000, 200000])


class TestMatchExpression:
    """Tests for match expression with value comparison."""

    def test_match_on_value(self):
        """Match expression should compare against the match value."""
        code = """
variable test_rate:
  entity: TaxUnit
  period: Year
  dtype: Rate

  formula:
    let n_children = min(num_qualifying_children, 3)
    return match n_children {
      case 0 => 0.0765
      case 1 => 0.34
      case 2 => 0.40
      case 3 => 0.45
    }
"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"num_qualifying_children": np.array([2, 0, 1, 3])}
        results = executor.execute(code, inputs)

        # n_children=2 -> 0.40, n_children=0 -> 0.0765, etc.
        assert_array_almost_equal(
            results["test_rate"],
            [0.40, 0.0765, 0.34, 0.45]
        )

    def test_match_with_else(self):
        """Match expression with else clause for unmatched values."""
        code = """
variable category:
  entity: TaxUnit
  period: Year
  dtype: Rate

  formula:
    return match count {
      case 0 => 1.0
      case 1 => 2.0
      else => 9.0
    }
"""
        executor = VectorizedExecutor(parameters={})
        inputs = {"count": np.array([0, 1, 5, 100])}
        results = executor.execute(code, inputs)

        assert_array_equal(results["category"], [1.0, 2.0, 9.0, 9.0])


# NOTE: TestPythonFormulaExecution removed - syntax: python is now rejected
# by the parser as a security risk (arbitrary code execution).
# See test_dsl_parser.py::TestParserErrors::test_syntax_python_rejected


class TestExecuteLazyEntityBroadcasting:
    """Tests for entity aggregation in execute_lazy method.

    When a TaxUnit-level variable imports Person-level variables,
    the executor must aggregate Person values to TaxUnit level.
    """

    def test_person_to_taxunit_aggregation(self):
        """Person-level variables should be summed to TaxUnit level.

        AGI scenario: wages (Person) + salaries (Person) -> AGI (TaxUnit)
        """
        import os
        import tempfile

        # Create a temporary statute directory with test .rac files
        with tempfile.TemporaryDirectory() as tmpdir:
            statute_dir = os.path.join(tmpdir, "statute", "test")
            os.makedirs(statute_dir)

            # Person-level inputs file
            person_rac = '''
variable wages:
  entity: Person
  period: Year
  dtype: Money
  label: "Wages"
  description: "Person-level wages"

variable salaries:
  entity: Person
  period: Year
  dtype: Money
  label: "Salaries"
  description: "Person-level salaries"
'''
            with open(os.path.join(statute_dir, "inputs.rac"), "w") as f:
                f.write(person_rac)

            # TaxUnit-level AGI file that imports Person-level variables
            taxunit_rac = '''
variable total_income:
  imports:
    - test/inputs#wages
    - test/inputs#salaries
  entity: TaxUnit
  period: Year
  dtype: Money
  label: "Total Income"
  description: "Sum of all income"
  formula: |
    return wages + salaries
'''
            with open(os.path.join(statute_dir, "agi.rac"), "w") as f:
                f.write(taxunit_rac)

            # Set up executor with statute root
            from pathlib import Path

            from src.rac.dependency_resolver import DependencyResolver

            dep_resolver = DependencyResolver(statute_root=Path(tmpdir))
            executor = VectorizedExecutor(parameters={}, dependency_resolver=dep_resolver)

            # Entity structure: 2 tax units, 4 persons
            # TaxUnit 0: persons 0, 1 with wages [1000, 2000], salaries [100, 200]
            # TaxUnit 1: persons 2, 3 with wages [3000, 4000], salaries [300, 400]
            entity_index = EntityIndex(
                person_to_tax_unit=np.array([0, 0, 1, 1]),
                tax_unit_to_household=np.array([0, 0]),
                n_persons=4,
                n_tax_units=2,
                n_households=1,
            )

            # Person-level inputs (4 persons)
            inputs = {
                "wages": np.array([1000, 2000, 3000, 4000]),
                "salaries": np.array([100, 200, 300, 400]),
            }

            results = executor.execute_lazy(
                entry_point="test/agi",
                inputs=inputs,
                output_variables=["total_income"],
                entity_index=entity_index,
            )

            # TaxUnit 0: (1000+2000) + (100+200) = 3300
            # TaxUnit 1: (3000+4000) + (300+400) = 7700
            assert_array_equal(results["total_income"], [3300, 7700])


class TestDataFrameExecution:
    """Tests for DataFrame execution support."""

    @pytest.fixture(autouse=True)
    def _require_pandas(self):
        pytest.importorskip("pandas")

    @pytest.fixture
    def simple_dsl(self):
        """Simple DSL code for testing."""
        return """
variable doubled_income:
  entity: Person
  period: Year
  dtype: Money
  formula:
    return earned_income * 2
"""

    @pytest.fixture
    def executor(self):
        """Create executor for testing."""
        return VectorizedExecutor(parameters={})

    def test_execute_dataframe_flat(self, executor, simple_dsl):
        """Test execute_dataframe with flat (non-hierarchical) DataFrame."""
        import pandas as pd

        df = pd.DataFrame({
            "earned_income": [10000, 20000, 30000, 40000],
            "age": [25, 35, 45, 55],
        })

        result = executor.execute_dataframe(
            code=simple_dsl,
            df=df,
        )

        # Should add computed column
        assert "doubled_income" in result.columns
        assert_array_equal(result["doubled_income"], [20000, 40000, 60000, 80000])

        # Original columns preserved
        assert "earned_income" in result.columns
        assert "age" in result.columns

        # Should not modify original
        assert "doubled_income" not in df.columns

    def test_execute_dataframe_inplace(self, executor, simple_dsl):
        """Test execute_dataframe with inplace=True."""
        import pandas as pd

        df = pd.DataFrame({
            "earned_income": [10000, 20000],
        })

        result = executor.execute_dataframe(
            code=simple_dsl,
            df=df,
            inplace=True,
        )

        # Should modify original DataFrame
        assert "doubled_income" in df.columns
        assert result is df

    def test_execute_dataframe_with_entity_columns(self, executor):
        """Test execute_dataframe with hierarchical entity structure."""
        import pandas as pd

        dsl = """
variable eitc_eligible:
  entity: Person
  period: Year
  dtype: Boolean
  formula:
    return earned_income > 0
"""

        # DataFrame with person/tax_unit/household IDs
        df = pd.DataFrame({
            "person_id": [1, 2, 3, 4],
            "tax_unit_id": [100, 100, 101, 101],
            "household_id": [1000, 1000, 1000, 1000],
            "earned_income": [15000, 0, 25000, 30000],
        })

        result = executor.execute_dataframe(
            code=dsl,
            df=df,
            entity_columns={
                "person": "person_id",
                "tax_unit": "tax_unit_id",
                "household": "household_id",
            },
        )

        assert "eitc_eligible" in result.columns
        # Persons 0, 2, 3 have earned income > 0
        assert_array_equal(result["eitc_eligible"], [True, False, True, True])

    def test_execute_entity_dataframes_separate(self, executor):
        """Test execute_entity_dataframes with separate DataFrames per entity."""
        import pandas as pd

        dsl = """
variable income_doubled:
  entity: Person
  period: Year
  dtype: Money
  formula:
    return earned_income * 2
"""

        persons = pd.DataFrame({
            "person_id": [1, 2, 3, 4],
            "tax_unit_id": [100, 100, 101, 101],
            "earned_income": [10000, 20000, 30000, 40000],
        })

        tax_units = pd.DataFrame({
            "tax_unit_id": [100, 101],
            "household_id": [1000, 1000],
            "filing_status": ["joint", "single"],
        })

        households = pd.DataFrame({
            "household_id": [1000],
            "state": ["CA"],
        })

        results = executor.execute_entity_dataframes(
            code=dsl,
            persons=persons,
            tax_units=tax_units,
            households=households,
        )

        # Check person-level results
        assert "persons" in results
        assert "income_doubled" in results["persons"].columns
        assert_array_equal(
            results["persons"]["income_doubled"],
            [20000, 40000, 60000, 80000]
        )

        # Original DataFrames preserved
        assert "tax_units" in results
        assert "households" in results

    def test_execute_entity_dataframes_tax_unit_only(self, executor):
        """Test with only tax_units DataFrame (common for TaxSim comparison)."""
        import pandas as pd

        dsl = """
variable tax_base:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula:
    return wages * 0.1
"""

        tax_units = pd.DataFrame({
            "tax_unit_id": [1, 2, 3],
            "household_id": [1, 2, 3],
            "wages": [50000, 75000, 100000],
        })

        results = executor.execute_entity_dataframes(
            code=dsl,
            tax_units=tax_units,
        )

        assert "tax_units" in results
        assert "tax_base" in results["tax_units"].columns
        assert_array_almost_equal(
            results["tax_units"]["tax_base"],
            [5000, 7500, 10000]
        )

    def test_infer_entity_index_flat(self, executor):
        """Test _infer_entity_index with flat DataFrame."""
        import pandas as pd

        df = pd.DataFrame({
            "income": [100, 200, 300],
        })

        entity_index = executor._infer_entity_index(df, {})

        assert entity_index.n_persons == 3
        assert entity_index.n_tax_units == 3
        assert entity_index.n_households == 3
        assert_array_equal(entity_index.person_to_tax_unit, [0, 1, 2])
        assert_array_equal(entity_index.tax_unit_to_household, [0, 1, 2])

    def test_infer_entity_index_hierarchical(self, executor):
        """Test _infer_entity_index with full hierarchy."""
        import pandas as pd

        df = pd.DataFrame({
            "person_id": [1, 2, 3, 4, 5],
            "tax_unit_id": [100, 100, 101, 101, 102],
            "household_id": [1000, 1000, 1000, 1000, 1001],
            "income": [10, 20, 30, 40, 50],
        })

        entity_index = executor._infer_entity_index(
            df,
            {
                "person": "person_id",
                "tax_unit": "tax_unit_id",
                "household": "household_id",
            }
        )

        assert entity_index.n_persons == 5
        assert entity_index.n_tax_units == 3  # 100, 101, 102
        assert entity_index.n_households == 2  # 1000, 1001

    def test_build_entity_index_from_dataframes(self, executor):
        """Test _build_entity_index_from_dataframes."""
        import pandas as pd

        persons = pd.DataFrame({
            "person_id": [1, 2, 3, 4],
            "tax_unit_id": [100, 100, 101, 101],
        })

        tax_units = pd.DataFrame({
            "tax_unit_id": [100, 101],
            "household_id": [1000, 1000],
        })

        households = pd.DataFrame({
            "household_id": [1000],
        })

        entity_index = executor._build_entity_index_from_dataframes(
            persons, tax_units, households
        )

        assert entity_index.n_persons == 4
        assert entity_index.n_tax_units == 2
        assert entity_index.n_households == 1

        # Persons 0,1 -> TaxUnit 0, Persons 2,3 -> TaxUnit 1
        assert_array_equal(entity_index.person_to_tax_unit, [0, 0, 1, 1])
        # Both TaxUnits -> Household 0
        assert_array_equal(entity_index.tax_unit_to_household, [0, 0])

    def test_dataframe_to_inputs(self, executor):
        """Test _dataframe_to_inputs conversion."""
        import pandas as pd

        df = pd.DataFrame({
            "income": [100.0, 200.0, 300.0],
            "count": [1, 2, 3],
            "status": ["single", "joint", "single"],
        })

        inputs = executor._dataframe_to_inputs(df)

        assert "income" in inputs
        assert "count" in inputs
        assert "status" in inputs

        assert_array_equal(inputs["income"], [100.0, 200.0, 300.0])
        assert_array_equal(inputs["count"], [1, 2, 3])
        assert_array_equal(inputs["status"], ["single", "joint", "single"])
