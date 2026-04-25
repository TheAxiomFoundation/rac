#!/usr/bin/env python3
"""AutoRAC YAML encoder.

Given a statute citation, its text, and a cases.yaml of inputs + expected
outputs (from an oracle such as PolicyEngine), emit a rules.yaml that the
Axiom Rules Engine computes to the expected values. Runs a validation-feedback loop
with Claude until cases pass or max attempts exhausted.

cases.yaml format (flat, single-entity):

    program_entity: TaxUnit              # required
    cases:
      - name: single_below
        entity_id: tu-1
        period: {period_kind: tax_year, start: 2026-01-01, end: 2026-12-31}
        inputs:                          # ScalarValue dicts, keyed by input name
          filing_status: {kind: integer, value: 0}
          wages: {kind: decimal, value: "150000"}
        expected:                        # keyed by derived-output name
          additional_medicare_tax: {kind: decimal, value: "0"}
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import anthropic
import yaml

ROOT = Path(__file__).resolve().parent.parent
EXEMPLAR_PATH = ROOT / "programmes" / "other" / "family_allowance" / "rules.yaml"
BINARY = ROOT / "target" / "debug" / "axiom-rules"
MODEL = "claude-opus-4-7"


def build_system_prompt() -> str:
    exemplar = EXEMPLAR_PATH.read_text()
    return f"""You encode statutes into rules.yaml for the Axiom Rules Engine.

The Axiom Rules Engine evaluates a temporal-relational programme over typed entities,
relations, parameters, and derived outputs. Your job: read the statute, read
the cases (inputs + expected outputs from an authoritative oracle), and emit a
rules.yaml whose derived outputs compute the expected values from the inputs.

# Schema

Top-level keys: `units`, `relations`, `parameters`, `derived`.

## units
  - name: USD
    kind: currency       # currency | count | ratio | custom
    minor_units: 2       # for currency
  - name: person
    kind: count

## relations (optional; only if the programme needs cross-entity aggregation)
  - name: member_of_tax_unit
    arity: 2             # slot 0 = Person, slot 1 = TaxUnit

## parameters (effective-dated, integer-indexed tables)
  - name: my_threshold
    unit: USD
    versions:
      - effective_from: 2026-01-01
        values:
          0: {{ kind: decimal, value: "200000" }}
          1: {{ kind: decimal, value: "250000" }}
          2: {{ kind: decimal, value: "125000" }}
          3: {{ kind: decimal, value: "200000" }}

## derived outputs
Each derived output:
    name: foo
    entity: TaxUnit              # entity name
    dtype: decimal               # bool | integer | decimal | text | date
    unit: USD
    source: "IRC §..."           # optional but recommended
    source_url: "https://..."    # optional
    semantics: scalar            # scalar | judgment
    expr: <ScalarExpr or JudgmentExpr>

# Expression kinds

ScalarExpr (use when semantics: scalar):
  literal         -> {{kind: literal, value: {{kind: decimal|integer|bool|text|date, value: ...}}}}
  input           -> {{kind: input, name: <input_name>}}
  derived         -> {{kind: derived, name: <another_derived_name>}}
  parameter_lookup-> {{kind: parameter_lookup, parameter: <name>, index: <ScalarExpr>}}
  add             -> {{kind: add, items: [<ScalarExpr>, ...]}}
  sub             -> {{kind: sub, left: <ScalarExpr>, right: <ScalarExpr>}}
  mul             -> {{kind: mul, left: <ScalarExpr>, right: <ScalarExpr>}}
  div             -> {{kind: div, left: <ScalarExpr>, right: <ScalarExpr>}}
  max             -> {{kind: max, items: [...]}}
  min             -> {{kind: min, items: [...]}}
  ceil            -> {{kind: ceil, value: <ScalarExpr>}}
  floor           -> {{kind: floor, value: <ScalarExpr>}}
  period_start    -> {{kind: period_start}}
  period_end      -> {{kind: period_end}}
  date_add_days   -> {{kind: date_add_days, date: <ScalarExpr>, days: <ScalarExpr>}}
  days_between    -> {{kind: days_between, from: <ScalarExpr>, to: <ScalarExpr>}}
  count_related   -> {{kind: count_related, relation: <name>, current_slot: <int>,
                       related_slot: <int>, where: <JudgmentExpr>?}}
  sum_related     -> {{kind: sum_related, relation: <name>, current_slot: <int>,
                       related_slot: <int>, value: <RelatedValueRef>, where: <JudgmentExpr>?}}
  if              -> {{kind: if, condition: <JudgmentExpr>, then_expr: <ScalarExpr>, else_expr: <ScalarExpr>}}

JudgmentExpr (use when semantics: judgment OR inside `if.condition` / `where`):
  comparison      -> {{kind: comparison, left: <ScalarExpr>, op: eq|ne|lt|lte|gt|gte, right: <ScalarExpr>}}
  derived         -> {{kind: derived, name: <judgment_derived_name>}}
  and             -> {{kind: and, items: [<JudgmentExpr>, ...]}}
  or              -> {{kind: or, items: [<JudgmentExpr>, ...]}}
  not             -> {{kind: not, item: <JudgmentExpr>}}

# Value rules

* Decimal literals must be **quoted strings**, never floats. Example: `value: "0.009"`.
* Integer literals are unquoted. Example: `value: 65`.
* Boolean literals are `true` / `false` unquoted.
* Date literals are `YYYY-MM-DD` unquoted.
* `kind:` tags are snake_case.

# Evaluation order

The engine resolves derived outputs in dependency order. A derived output may
only reference derived outputs declared earlier in the file.

# Exemplar (a complete working programme)

```yaml
{exemplar}
```

# Your task

Given the statute text and the cases, emit a `rules.yaml` that:
1. Declares only the units, parameters, and derived outputs needed.
2. For each derived output named in any case's `expected`, includes a
   declaration with matching dtype.
3. For each input name used in any case's `inputs`, the programme implicitly
   treats it as a typed input on the `program_entity` (no declaration needed;
   just reference it via `{{kind: input, name: ...}}`).
4. Uses `source` / `source_url` to cite the statute.

Return the YAML only — no markdown fences, no prose, no commentary. Your
entire response must be a valid parseable YAML document.
"""


def build_user_prompt(citation: str, statute_text: str, cases_yaml: str) -> str:
    return f"""Citation: {citation}

Statute text:
\"\"\"
{statute_text}
\"\"\"

cases.yaml:
```yaml
{cases_yaml}
```

Emit rules.yaml now.
"""


def extract_yaml(text: str) -> str:
    """Strip ```yaml ... ``` fences if the model used them despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        t = t[first_nl + 1 :]
        if t.endswith("```"):
            t = t[: -3]
    return t.strip() + "\n"


def build_request(case: dict, program_entity: str, program_text: str) -> dict:
    interval = {"start": str(case["period"]["start"]), "end": str(case["period"]["end"])}
    inputs = []
    for name, value in case["inputs"].items():
        inputs.append({
            "name": name,
            "entity": program_entity,
            "entity_id": case["entity_id"],
            "interval": interval,
            "value": value,
        })
    return {
        "mode": "explain",
        "program": yaml.safe_load(program_text),
        "dataset": {"inputs": inputs, "relations": case.get("relations", [])},
        "queries": [{
            "entity_id": case["entity_id"],
            "period": case["period"],
            "outputs": list(case["expected"].keys()),
        }],
    }


def decimal_eq(a: str, b: str) -> bool:
    try:
        return Decimal(a) == Decimal(b)
    except Exception:
        return a == b


def value_matches(actual: dict, expected: dict) -> bool:
    if actual.get("kind") != expected.get("kind"):
        return False
    if actual["kind"] == "decimal":
        return decimal_eq(str(actual["value"]), str(expected["value"]))
    return str(actual["value"]) == str(expected["value"])


def run_validation(program_path: Path, cases_path: Path) -> tuple[bool, str]:
    """Run each case through the engine; return (ok, feedback)."""
    program_text = program_path.read_text()
    cases_doc = yaml.safe_load(cases_path.read_text())
    program_entity = cases_doc["program_entity"]

    failures: list[str] = []
    engine_errors: list[str] = []

    for case in cases_doc["cases"]:
        request = build_request(case, program_entity, program_text)
        payload = json.dumps(request, default=str)
        try:
            proc = subprocess.run(
                [str(BINARY)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            engine_errors.append(f"[{case['name']}] engine timeout")
            continue

        if proc.returncode != 0:
            engine_errors.append(f"[{case['name']}] engine error: {proc.stderr.strip()}")
            continue

        try:
            response = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            engine_errors.append(f"[{case['name']}] invalid engine output: {e}")
            continue

        outputs = response["results"][0]["outputs"]
        for out_name, expected in case["expected"].items():
            if out_name not in outputs:
                failures.append(f"[{case['name']}] missing output `{out_name}`")
                continue
            actual_block = outputs[out_name]
            actual_value = actual_block.get("value") or actual_block
            if actual_value.get("kind") is None and "outcome" in actual_block:
                actual_value = {"kind": "text", "value": actual_block["outcome"]}
            if not value_matches(actual_value, expected):
                failures.append(
                    f"[{case['name']}] `{out_name}`: "
                    f"engine={json.dumps(actual_value)} expected={json.dumps(expected)}"
                )

    if engine_errors:
        return False, "Engine rejected the programme:\n" + "\n".join(engine_errors)
    if failures:
        return False, "Case mismatches:\n" + "\n".join(failures)
    return True, ""


def encode(
    citation: str,
    statute_text: str,
    cases_path: Path,
    out_path: Path,
    max_attempts: int = 4,
) -> None:
    client = anthropic.Anthropic()
    system_prompt = build_system_prompt()
    cases_yaml = cases_path.read_text()
    user_prompt = build_user_prompt(citation, statute_text, cases_yaml)

    messages: list[dict] = [{"role": "user", "content": user_prompt}]

    for attempt in range(1, max_attempts + 1):
        print(f"[attempt {attempt}/{max_attempts}] calling {MODEL}...")
        resp = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
        )
        usage = resp.usage
        print(f"  tokens: input={usage.input_tokens} "
              f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)} "
              f"cache_write={getattr(usage, 'cache_creation_input_tokens', 0)} "
              f"output={usage.output_tokens}")

        response_text = resp.content[0].text
        yaml_text = extract_yaml(response_text)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml_text)
        print(f"  wrote {out_path} ({len(yaml_text.splitlines())} lines)")

        ok, feedback = run_validation(out_path, cases_path)
        if ok:
            print(f"  VALIDATION PASSED on attempt {attempt}")
            return

        print(f"  validation failed; feeding back:")
        print("  " + feedback.replace("\n", "\n  "))
        messages.append({"role": "assistant", "content": response_text})
        messages.append({
            "role": "user",
            "content": (
                "Your rules.yaml did not match the expected outputs.\n\n"
                f"{feedback}\n\n"
                "Emit a corrected rules.yaml. Return only the YAML, no prose."
            ),
        })

    raise SystemExit(f"failed after {max_attempts} attempts")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--citation", required=True)
    parser.add_argument("--statute", required=True, help="path to statute text file")
    parser.add_argument("--cases", required=True, help="path to cases.yaml")
    parser.add_argument("--output", required=True, help="path to write rules.yaml")
    parser.add_argument("--max-attempts", type=int, default=4)
    args = parser.parse_args()

    statute_text = Path(args.statute).read_text()
    encode(
        citation=args.citation,
        statute_text=statute_text,
        cases_path=Path(args.cases),
        out_path=Path(args.output),
        max_attempts=args.max_attempts,
    )


if __name__ == "__main__":
    main()
