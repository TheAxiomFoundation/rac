"""Main training loop for the AI rules engine."""

from .executor import Executor
from .generator import CodeGenerator, MockGenerator
from .oracles import Oracle, PolicyEngineOracle
from .scorer import FailureDiagnoser, Scorer
from .types import (
    GeneratedCode,
    IterationRecord,
    Statute,
    TestCase,
    TrainingResult,
)


class TrainingLoop:
    """Main training loop: statute → code → test → iterate."""

    def __init__(
        self,
        generator: CodeGenerator | MockGenerator | None = None,
        executor: Executor | None = None,
        oracles: list[Oracle] | None = None,
        scorer: Scorer | None = None,
        diagnoser: FailureDiagnoser | None = None,
        max_iterations: int = 10,
        target_accuracy: float = 0.95,
    ):
        self.generator = generator or CodeGenerator()
        self.executor = executor or Executor()
        self.oracles = oracles or []
        self.scorer = scorer or Scorer()
        self.diagnoser = diagnoser or FailureDiagnoser()
        self.max_iterations = max_iterations
        self.target_accuracy = target_accuracy

    def train(
        self,
        statute: Statute,
        test_cases: list[TestCase],
        context: list[str] | None = None,
        verbose: bool = False,
    ) -> TrainingResult:
        """Run training loop for a statute.

        Args:
            statute: The statutory provision to encode
            test_cases: Test cases with inputs and expected outputs
            context: Previously encoded related rules
            verbose: Print progress

        Returns:
            TrainingResult with success status and final code
        """
        failures = []
        history = []
        context = context or []

        for i in range(self.max_iterations):
            if verbose:
                print(f"\n=== Iteration {i + 1} ===")

            # Generate code
            code = self.generator.generate(
                statute=statute,
                context=context,
                failures=failures,
            )
            code.iteration = i

            if verbose:
                print(f"Generated code:\n{code.source[:200]}...")

            # Execute against test cases
            results = self.executor.execute(code, test_cases)

            # Score
            score = self.scorer.score(results)

            if verbose:
                print(f"Score: accuracy={score.accuracy:.2%}, MAE=${score.mean_absolute_error:.2f}")

            # Record iteration
            failures = self.diagnoser.diagnose(results)
            history.append(
                IterationRecord(
                    iteration=i,
                    code=code,
                    score=score,
                    failures=failures,
                )
            )

            # Check success
            if score.accuracy >= self.target_accuracy:
                if verbose:
                    print(f"\nSuccess! Achieved {score.accuracy:.2%} accuracy in {i + 1} iterations.")
                return TrainingResult(
                    success=True,
                    final_code=code,
                    iterations=i + 1,
                    history=history,
                )

            if verbose:
                print(f"Failures: {len(failures)}")
                for f in failures[:3]:
                    print(f"  - {f.type}: {f.message[:80]}")

        # Max iterations reached
        if verbose:
            print(f"\nMax iterations reached. Best accuracy: {history[-1].score.accuracy:.2%}")

        return TrainingResult(
            success=False,
            final_code=history[-1].code if history else GeneratedCode(source="", citation=statute.citation),
            iterations=self.max_iterations,
            history=history,
            remaining_failures=failures,
        )


class TestCaseGenerator:
    """Generates test cases using oracles."""

    def __init__(self, oracle: Oracle | None = None):
        self.oracle = oracle or PolicyEngineOracle()

    def generate_eitc_cases(self, n_cases: int = 100) -> list[TestCase]:
        """Generate test cases for EITC.

        Covers:
        - Different income levels (phase-in, plateau, phase-out)
        - Different filing statuses
        - Different numbers of children
        """
        cases = []
        case_id = 0

        # Income levels to test
        incomes = [0, 1000, 5000, 7840, 10000, 11750, 15000, 16510, 20000, 25000, 30000, 40000, 50000]

        # Filing statuses
        statuses = ["SINGLE", "JOINT"]

        # Number of children
        n_children_options = [0, 1, 2, 3]

        for income in incomes:
            for status in statuses:
                for n_children in n_children_options:
                    inputs = {
                        "earned_income": income,
                        "filing_status": status,
                        "n_children": n_children,
                        "n_qualifying_children": n_children,
                    }

                    # Get expected from oracle
                    try:
                        expected = self.oracle.evaluate(inputs)
                    except Exception as e:
                        print(f"Warning: Oracle failed for {inputs}: {e}")
                        continue

                    cases.append(
                        TestCase(
                            id=f"case_{case_id}",
                            inputs=inputs,
                            expected=expected,
                            description=f"income=${income}, status={status}, children={n_children}",
                        )
                    )
                    case_id += 1

                    if len(cases) >= n_cases:
                        return cases

        return cases

    def generate_boundary_cases(self) -> list[TestCase]:
        """Generate boundary/edge cases for EITC."""
        cases = []

        # 2024 EITC parameters
        boundaries = {
            0: {"phase_in_end": 7840, "phase_out_start": 9800, "phase_out_end": 17640},
            1: {"phase_in_end": 11750, "phase_out_start": 22720, "phase_out_end": 49080},
            2: {"phase_in_end": 16510, "phase_out_start": 22720, "phase_out_end": 55770},
            3: {"phase_in_end": 16510, "phase_out_start": 22720, "phase_out_end": 59900},
        }

        for n_children, bounds in boundaries.items():
            for key, value in bounds.items():
                # Test at boundary and just above/below
                for offset in [-1, 0, 1]:
                    income = value + offset
                    if income < 0:
                        continue

                    inputs = {
                        "earned_income": income,
                        "filing_status": "SINGLE",
                        "n_children": n_children,
                        "n_qualifying_children": n_children,
                    }

                    try:
                        expected = self.oracle.evaluate(inputs)
                    except Exception:
                        continue

                    cases.append(
                        TestCase(
                            id=f"boundary_{n_children}_{key}_{offset}",
                            inputs=inputs,
                            expected=expected,
                            description=f"{key} boundary for {n_children} children",
                        )
                    )

        return cases
