"""Prompt evolution based on learned examples and failure patterns."""

from ..dsl_agent import DSL_SYSTEM_PROMPT
from ..types import Statute
from .state import FailurePattern, LearningState, TrajectoryExample


class PromptEvolver:
    """Evolves the system prompt based on learned examples and patterns."""

    def __init__(self, base_prompt: str = DSL_SYSTEM_PROMPT):
        self.base_prompt = base_prompt

    def build_prompt(self, state: LearningState, max_examples: int = 3) -> str:
        """Build an evolved prompt with learned examples."""

        prompt_parts = [self.base_prompt]

        # Add successful examples as few-shot demonstrations
        if state.successful_examples:
            prompt_parts.append("\n\n## Successful Examples from Previous Runs\n")
            prompt_parts.append("Here are examples of correctly encoded provisions:\n")

            # Select most recent diverse examples
            examples = state.successful_examples[-max_examples:]

            for i, ex in enumerate(examples, 1):
                prompt_parts.append(f"""
### Example {i}: {ex.statute_citation}

**Statute excerpt:**
{ex.statute_text[:500]}...

**Correct DSL implementation:**
```rac
{ex.final_code}
```

**Key patterns:** {", ".join(ex.success_factors) if ex.success_factors else "Standard implementation"}
""")

        # Add learned failure patterns as warnings
        if state.failure_patterns:
            prompt_parts.append("\n\n## Common Mistakes to Avoid\n")
            for pattern in state.failure_patterns[-5:]:
                prompt_parts.append(f"""
**{pattern.error_type.upper()}:** {pattern.description}
- Bad: `{pattern.bad_code_snippet[:100]}...`
- Fix: {pattern.correction}
""")

        return "".join(prompt_parts)

    def analyze_trajectory(
        self,
        provision: str,
        statute: Statute,
        trajectory: list[dict],
        final_code: str,
        success: bool,
        accuracy: float,
    ) -> tuple[list[TrajectoryExample], list[FailurePattern]]:
        """Analyze a trajectory to extract learnings."""
        examples = []
        patterns = []

        if success and final_code:
            success_factors = self._identify_success_factors(trajectory, final_code)
            examples.append(
                TrajectoryExample(
                    provision=provision,
                    statute_citation=statute.citation,
                    statute_text=statute.text,
                    final_code=final_code,
                    accuracy=accuracy,
                    iterations=len(trajectory),
                    success_factors=success_factors,
                )
            )

        # Extract failure patterns from trajectory
        if len(trajectory) > 1:
            patterns.extend(self._extract_failure_patterns(provision, trajectory))

        return examples, patterns

    def _identify_success_factors(
        self,
        trajectory: list[dict],
        final_code: str,
    ) -> list[str]:
        """Identify what made this encoding successful."""
        factors = []

        # DSL structure patterns
        if "match {" in final_code:
            factors.append("Used match expression for conditionals")
        if "let " in final_code:
            factors.append("Used let bindings for clarity")
        if "min(" in final_code or "max(" in final_code:
            factors.append("Used min/max for clamping")
        if "variable(" in final_code:
            factors.append("Properly referenced input variables")
        if len(trajectory) == 1:
            factors.append("Correct on first attempt")

        # Statute-organized paths
        if "references {" in final_code:
            factors.append("Used references block for traceability")
        if "statute/" in final_code or "statute." in final_code:
            factors.append("Used statute-organized paths")

        # Indexing awareness
        if "indexing_rule" in final_code:
            factors.append("Identified indexing provision")
        if "indexed" in final_code.lower() or "cost_of_living" in final_code.lower():
            factors.append("Recognized indexed parameters")
        if "earned_income_amount[" in final_code:
            factors.append("Used indexed parameter correctly")

        # No hardcoding
        has_hardcoded = any(
            f"{x}:" in final_code or f"=> {x}" in final_code
            for x in ["7840", "12390", "17400", "14600", "29200", "21900"]
        )
        if not has_hardcoded:
            factors.append("Avoided hardcoding indexed values")

        return factors

    def _extract_failure_patterns(
        self,
        provision: str,
        trajectory: list[dict],
    ) -> list[FailurePattern]:
        """Extract failure patterns from iterations that didn't pass."""
        patterns = []

        for i, step in enumerate(trajectory[:-1]):
            if step.get("accuracy", 0) < 1.0:
                failures = step.get("failures", [])
                for failure in failures[:2]:
                    error_type = failure.get("type", "unknown")
                    message = failure.get("message", "")
                    if not message:
                        continue

                    code = step.get("code", "")
                    snippet = code[:200] if code else ""

                    correction = "Fixed in next iteration"
                    if i + 1 < len(trajectory):
                        if trajectory[i + 1].get("accuracy", 0) <= step.get("accuracy", 0):
                            correction = "Required multiple attempts"

                    patterns.append(
                        FailurePattern(
                            provision=provision,
                            error_type=error_type,
                            description=message[:200],
                            bad_code_snippet=snippet,
                            correction=correction,
                        )
                    )

        return patterns
