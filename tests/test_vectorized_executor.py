"""Tests for vectorized DSL executor.

Following TDD principles - these tests define the expected behavior.
"""

import pytest
import numpy as np
from numpy.testing import assert_array_equal, assert_array_almost_equal

from src.cosilico.vectorized_executor import (
    VectorizedExecutor,
    VectorizedContext,
    EntityIndex,
    DependencyGraph,
    Scenario,
    evaluate_expression_vectorized,
    evaluate_formula_vectorized,
)
from src.cosilico.dsl_parser import parse_dsl


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


class TestPythonFormulaExecution:
    """Tests for executing Python-syntax formulas via PythonFormulaExecutor."""

    def test_python_syntax_detection(self):
        """Detect Python syntax in formula text."""
        from src.cosilico.vectorized_executor import is_python_syntax_formula

        # DSL syntax (not Python)
        assert not is_python_syntax_formula("return income * 0.25")
        assert not is_python_syntax_formula("if income > 50000: 0.25 else 0.15")
        assert not is_python_syntax_formula("let x = income * 0.5\nreturn x")

        # Python syntax (if-statements with blocks)
        assert is_python_syntax_formula("if income > 50000:\n    rate = 0.25")
        assert is_python_syntax_formula("if filing_status == 'JOINT':\n    threshold = 250000\nelse:\n    threshold = 200000")
        assert is_python_syntax_formula("if x:\n    y = 1\nelif z:\n    y = 2\nelse:\n    y = 3")

    def test_python_formula_with_explicit_syntax_field(self):
        """Execute Python formula with explicit syntax: python field."""
        code = """
variable niit:
  entity: TaxUnit
  period: Year
  dtype: Money
  syntax: python

  formula: |
    # Determine threshold based on filing status
    if filing_status == 'JOINT':
        threshold = threshold_joint
    elif filing_status == 'SEPARATE':
        threshold = threshold_separate
    else:
        threshold = threshold_other
    excess_magi = max(0, magi - threshold)
    return min(nii, excess_magi) * rate

"""
        executor = VectorizedExecutor(
            parameters={
                "threshold_joint": 250000,
                "threshold_separate": 125000,
                "threshold_other": 200000,
                "rate": 0.038,
            }
        )
        inputs = {
            "filing_status": np.array(["JOINT", "SEPARATE", "SINGLE", "JOINT", "SINGLE"]),
            "magi": np.array([300000, 150000, 250000, 200000, 180000]),
            "nii": np.array([50000, 30000, 40000, 10000, 20000]),
        }
        results = executor.execute(code, inputs)

        # JOINT: magi=300k, threshold=250k, excess=50k, nii=50k -> min(50k,50k)*0.038 = 1900
        # SEPARATE: magi=150k, threshold=125k, excess=25k, nii=30k -> min(30k,25k)*0.038 = 950
        # SINGLE: magi=250k, threshold=200k, excess=50k, nii=40k -> min(40k,50k)*0.038 = 1520
        # JOINT: magi=200k, threshold=250k, excess=0, nii=10k -> min(10k,0)*0.038 = 0
        # SINGLE: magi=180k, threshold=200k, excess=0, nii=20k -> min(20k,0)*0.038 = 0
        assert_array_almost_equal(results["niit"], [1900, 950, 1520, 0, 0])

    def test_python_formula_auto_detection(self):
        """Execute Python formula without explicit syntax field (auto-detect)."""
        code = """
variable threshold:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula: |
    if filing_status == 'JOINT':
        threshold = 250000
    else:
        threshold = 200000
    return threshold

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {
            "filing_status": np.array(["JOINT", "SINGLE", "JOINT"]),
        }
        results = executor.execute(code, inputs)

        assert_array_equal(results["threshold"], [250000, 200000, 250000])

    def test_python_formula_with_elif_chain(self):
        """Execute Python formula with if/elif/else chain."""
        code = """
variable threshold:
  entity: TaxUnit
  period: Year
  dtype: Money
  syntax: python

  formula: |
    if filing_status == 'JOINT':
        threshold = 250000
    elif filing_status == 'SURVIVING_SPOUSE':
        threshold = 250000
    elif filing_status == 'SEPARATE':
        threshold = 125000
    else:
        threshold = 200000
    return threshold

"""
        executor = VectorizedExecutor(parameters={})
        inputs = {
            "filing_status": np.array([
                "JOINT", "SEPARATE", "SINGLE", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE"
            ]),
        }
        results = executor.execute(code, inputs)

        assert_array_equal(
            results["threshold"],
            [250000, 125000, 200000, 200000, 250000]
        )

    def test_python_formula_with_parameters(self):
        """Execute Python formula using parameter values."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
  syntax: python

  formula: |
    if income < low_threshold:
        tax = income * low_rate
    elif income < high_threshold:
        tax = income * mid_rate
    else:
        tax = income * high_rate
    return tax

"""
        executor = VectorizedExecutor(
            parameters={
                "low_threshold": 20000,
                "high_threshold": 50000,
                "low_rate": 0.1,
                "mid_rate": 0.2,
                "high_rate": 0.3,
            }
        )
        inputs = {"income": np.array([10000, 30000, 60000])}
        results = executor.execute(code, inputs)

        # 10000 * 0.1 = 1000, 30000 * 0.2 = 6000, 60000 * 0.3 = 18000
        assert_array_equal(results["tax"], [1000, 6000, 18000])


class TestExecuteLazyEntityBroadcasting:
    """Tests for entity aggregation in execute_lazy method.

    When a TaxUnit-level variable imports Person-level variables,
    the executor must aggregate Person values to TaxUnit level.
    """

    def test_person_to_taxunit_aggregation(self):
        """Person-level variables should be summed to TaxUnit level.

        AGI scenario: wages (Person) + salaries (Person) -> AGI (TaxUnit)
        """
        import tempfile
        import os

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
  syntax: python
  formula: |
    return wages + salaries
'''
            with open(os.path.join(statute_dir, "agi.rac"), "w") as f:
                f.write(taxunit_rac)

            # Set up executor with statute root
            from pathlib import Path
            from src.cosilico.dependency_resolver import DependencyResolver

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
