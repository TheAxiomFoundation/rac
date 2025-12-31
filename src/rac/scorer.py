"""Scoring and failure diagnosis for training loop."""

from .types import ExecutionResult, Failure, Score


class Scorer:
    """Computes metrics from execution results."""

    def score(self, results: list[ExecutionResult]) -> Score:
        """Compute aggregate score from execution results."""
        if not results:
            return Score()

        n_total = len(results)

        # Categorize results
        syntax_errors = []
        runtime_errors = []
        correct = []
        incorrect = []

        for r in results:
            if r.error:
                if "parse" in r.error.lower() or "syntax" in r.error.lower():
                    syntax_errors.append(r)
                else:
                    runtime_errors.append(r)
            elif r.match:
                correct.append(r)
            else:
                incorrect.append(r)

        # Compute rates
        syntax_pass_rate = 1 - len(syntax_errors) / n_total
        runtime_pass_rate = 1 - len(runtime_errors) / n_total

        # Accuracy only counts non-error cases
        n_executed = len(correct) + len(incorrect)
        accuracy = len(correct) / n_executed if n_executed > 0 else 0

        # Compute error metrics for incorrect cases
        mae, max_err = self._compute_error_metrics(incorrect)

        return Score(
            syntax_pass_rate=syntax_pass_rate,
            runtime_pass_rate=runtime_pass_rate,
            accuracy=accuracy,
            mean_absolute_error=mae,
            max_error=max_err,
            n_cases=n_total,
        )

    def _compute_error_metrics(
        self, incorrect: list[ExecutionResult]
    ) -> tuple[float, float]:
        """Compute MAE and max error from incorrect results."""
        if not incorrect:
            return 0.0, 0.0

        errors = []
        for r in incorrect:
            if r.output and r.expected:
                # Get the primary output value
                out_val = self._get_primary_value(r.output)
                exp_val = self._get_primary_value(r.expected)

                if out_val is not None and exp_val is not None:
                    errors.append(abs(out_val - exp_val))

        if not errors:
            return 0.0, 0.0

        mae = sum(errors) / len(errors)
        max_err = max(errors)

        return mae, max_err

    def _get_primary_value(self, d: dict) -> float | None:
        """Extract primary numerical value from output dict."""
        for key in ["eitc_phase_in_credit", "eitc", "output"]:
            if key in d and isinstance(d[key], (int, float)):
                return float(d[key])

        # Take first numerical value
        for v in d.values():
            if isinstance(v, (int, float)):
                return float(v)

        return None


class FailureDiagnoser:
    """Diagnoses failures to provide context for next iteration."""

    def diagnose(
        self,
        results: list[ExecutionResult],
    ) -> list[Failure]:
        """Extract structured failure information from results."""
        failures = []

        for r in results:
            if r.error:
                failure_type = "syntax" if "parse" in r.error.lower() else "runtime"
                failures.append(
                    Failure(
                        type=failure_type,
                        message=r.error,
                        case_id=r.case_id,
                    )
                )
            elif not r.match:
                # Value mismatch - provide analysis
                out_val = self._get_primary_value(r.output) if r.output else None
                exp_val = self._get_primary_value(r.expected) if r.expected else None

                analysis = self._analyze_mismatch(r, out_val, exp_val)

                failures.append(
                    Failure(
                        type="value_mismatch",
                        message=analysis,
                        case_id=r.case_id,
                        expected=exp_val,
                        actual=out_val,
                    )
                )

        # Cluster similar failures
        return self._cluster_failures(failures)

    def _get_primary_value(self, d: dict) -> float | None:
        """Extract primary numerical value from output dict."""
        for key in ["eitc_phase_in_credit", "eitc", "output"]:
            if key in d and isinstance(d[key], (int, float)):
                return float(d[key])
        for v in d.values():
            if isinstance(v, (int, float)):
                return float(v)
        return None

    def _analyze_mismatch(
        self,
        result: ExecutionResult,
        out_val: float | None,
        exp_val: float | None,
    ) -> str:
        """Produce human-readable analysis of value mismatch."""
        if out_val is None or exp_val is None:
            return "Unable to compare values"

        diff = out_val - exp_val
        pct_diff = abs(diff / exp_val) * 100 if exp_val != 0 else float("inf")

        if out_val == 0 and exp_val > 0:
            return f"Output is $0 but expected ${exp_val:.2f}. Check if formula is correctly accessing inputs."
        elif out_val > 0 and exp_val == 0:
            return f"Output is ${out_val:.2f} but expected $0. Check eligibility conditions."
        elif pct_diff > 100:
            return f"Output ${out_val:.2f} differs from expected ${exp_val:.2f} by {pct_diff:.0f}%. Check rate or threshold values."
        else:
            return f"Output ${out_val:.2f} differs from expected ${exp_val:.2f} by ${abs(diff):.2f} ({pct_diff:.1f}%)."

    def _cluster_failures(self, failures: list[Failure]) -> list[Failure]:
        """Cluster similar failures to reduce noise.

        For now, just return unique failures by type and message pattern.
        Future: Use embeddings for semantic clustering.
        """
        # Group by type
        by_type: dict[str, list[Failure]] = {}
        for f in failures:
            by_type.setdefault(f.type, []).append(f)

        clustered = []

        # For each type, keep representative failures
        for failure_type, type_failures in by_type.items():
            if failure_type in ("syntax", "runtime"):
                # Keep first error of each type (they're usually all the same)
                if type_failures:
                    clustered.append(type_failures[0])
            else:
                # For value mismatches, keep a sample
                # Sort by error magnitude if available
                sorted_failures = sorted(
                    type_failures,
                    key=lambda f: abs(f.expected - f.actual) if f.expected and f.actual else 0,
                    reverse=True,
                )
                # Keep top 5 worst mismatches
                clustered.extend(sorted_failures[:5])

        return clustered
