"""Code generator using LLMs."""

import os

from .types import Failure, GeneratedCode, Statute

# DSL specification for prompts
DSL_SPEC = """
# RAC DSL Specification

## Variable Definition

```rac
variable <name>:
  entity: Person | TaxUnit | Household
  period: Year | Month
  dtype: Money | Rate | Boolean | Integer
  label: "Human readable description"
  citation: "<legal citation>"

  references:
    <alias>: <path>
    ...

  formula:
    <expression>
```

## Formula Syntax

- Arithmetic: +, -, *, /
- Comparison: ==, !=, <, <=, >, >=
- Logic: and, or, not
- Conditionals: if <cond> then <expr> else <expr>
- Functions: min(a, b), max(a, b), clip(x, lo, hi)
- References: Use aliases defined in references block

## Parameter Access

Parameters are time-varying values from statute (rates, thresholds).
Access via: param.<path>

Example: param.irs.eitc.phase_in_rate[n_children]

## Example

```rac
variable eitc_phase_in_credit:
  entity: TaxUnit
  period: Year
  dtype: Money
  label: "EITC phase-in credit amount"
  citation: "26 USC § 32(a)(1)"

  references:
    earned_income: us/irs/income/earned_income
    phase_in_rate: param.irs.eitc.phase_in_rate
    earned_income_amount: param.irs.eitc.earned_income_amount

  formula:
    min(earned_income, earned_income_amount) * phase_in_rate
```
"""


class CodeGenerator:
    """Generates RAC DSL code from statute using LLMs."""

    def __init__(
        self,
        model: str = "claude-opus-4-5-20251101",
        api_key: str | None = None,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    @property
    def client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def generate(
        self,
        statute: Statute,
        context: list[str] | None = None,
        failures: list[Failure] | None = None,
        temperature: float = 0.0,
    ) -> GeneratedCode:
        """Generate RAC DSL code for a statute.

        Args:
            statute: The statutory provision to encode
            context: Previously encoded related rules
            failures: Failures from previous iteration
            temperature: LLM temperature (0 = deterministic)

        Returns:
            Generated code with metadata
        """
        prompt = self._build_prompt(statute, context or [], failures or [])

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract code from response
        code_text = self._extract_code(response.content[0].text)

        return GeneratedCode(
            source=code_text,
            citation=statute.citation,
            model=self.model,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )

    def _build_prompt(
        self,
        statute: Statute,
        context: list[str],
        failures: list[Failure],
    ) -> str:
        """Build the prompt for code generation."""
        prompt_parts = [
            "You are encoding tax law into executable RAC DSL code.",
            "",
            "# DSL SPECIFICATION",
            DSL_SPEC,
            "",
        ]

        if context:
            prompt_parts.extend(
                [
                    "# CONTEXT (already encoded rules)",
                    "```rac",
                    "\n\n".join(context),
                    "```",
                    "",
                ]
            )

        if failures:
            prompt_parts.extend(
                [
                    "# PREVIOUS FAILURES",
                    "Your previous attempt had these issues:",
                    "",
                ]
            )
            for f in failures[:5]:  # Limit to 5 most relevant
                if f.type == "value_mismatch":
                    prompt_parts.append(
                        f"- Case {f.case_id}: Expected {f.expected}, got {f.actual}"
                    )
                    prompt_parts.append(f"  {f.message}")
                else:
                    prompt_parts.append(f"- {f.type}: {f.message}")
            prompt_parts.append("")

        prompt_parts.extend(
            [
                "# STATUTE TO ENCODE",
                f"Citation: {statute.citation}",
                f"Jurisdiction: {statute.jurisdiction}",
                "",
                "Text:",
                statute.text,
                "",
                "# INSTRUCTIONS",
                "Produce RAC DSL code for this provision. Include:",
                "1. Variable definition with proper entity (TaxUnit for tax credits) and period (Year)",
                "2. Formula implementing the statutory calculation",
                "3. References block for any inputs (use absolute paths)",
                "4. Citation in metadata",
                "",
                "For EITC specifically:",
                "- The phase-in credit = min(earned_income, earned_income_amount) * phase_in_rate",
                "- phase_in_rate and earned_income_amount vary by number of qualifying children",
                "- Access parameters via: param.irs.eitc.phase_in_rate[n_qualifying_children]",
                "",
                "Output ONLY the RAC DSL code in a code block. No explanation.",
            ]
        )

        return "\n".join(prompt_parts)

    def _extract_code(self, response: str) -> str:
        """Extract code from LLM response."""
        # Look for code blocks
        if "```rac" in response:
            start = response.find("```rac") + len("```rac")
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()

        if "```" in response:
            start = response.find("```") + 3
            # Skip language identifier if present
            newline = response.find("\n", start)
            if newline > start and newline - start < 20:
                start = newline + 1
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()

        # No code block, return as-is
        return response.strip()


class MockGenerator:
    """Mock generator for testing without API calls."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.call_count = 0

    def generate(
        self,
        statute: Statute,
        context: list[str] | None = None,
        failures: list[Failure] | None = None,
        temperature: float = 0.0,
    ) -> GeneratedCode:
        """Return mock code."""
        self.call_count += 1

        # Check for pre-defined response
        if statute.citation in self.responses:
            code = self.responses[statute.citation]
        else:
            # Default EITC implementation
            code = """
variable eitc_phase_in_credit:
  entity: TaxUnit
  period: Year
  dtype: Money
  label: "EITC phase-in credit amount"
  citation: "26 USC § 32(a)(1)"

  references:
    earned_income: us/irs/income/earned_income
    n_qualifying_children: us/irs/eitc/n_qualifying_children
    phase_in_rate: param.irs.eitc.phase_in_rate
    earned_income_amount: param.irs.eitc.earned_income_amount

  formula:
    min(earned_income, earned_income_amount[n_qualifying_children]) * phase_in_rate[n_qualifying_children]
""".strip()

        return GeneratedCode(
            source=code,
            citation=statute.citation,
            iteration=self.call_count,
            model="mock",
        )
