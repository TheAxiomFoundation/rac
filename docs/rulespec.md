# RuleSpec

RuleSpec is the canonical authoring and interchange schema for Axiom Rules
Engine rules.
AutoRAC should emit RuleSpec YAML/JSON from Atlas source documents; the Rust
engine normalises it into `ProgramSpec` before compilation. `ProgramSpec` is the
runtime IR. `.rac` is a compatibility/review projection and, for now, a formula
parser bridge.

## Shape

Every RuleSpec YAML file must declare an explicit discriminator:

```yaml
format: rulespec/v1
module:
  id: us.snap.tx
  title: Texas SNAP overlay
relations:
  - name: member_of_household
    arity: 2
rules:
  - name: medical_deduction
    kind: derived
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    sources:
      - citation: 7 CFR 273.9(d)(3)(x)
        url: https://www.ecfr.gov/current/title-7/section-273.9
    versions:
      - effective_from: 2025-10-01
        formula: |
          if has_elderly_or_disabled_member:
              if total_medical_expenses > snap_medical_deduction_threshold:
                  snap_state_sme_flat_amount
              else: 0
          else: 0
```

`schema: axiom.rules.*` is also accepted as a discriminator. YAML with a
top-level `rules:` key and no discriminator is rejected, because otherwise a
wrong-shaped document can deserialize as an empty legacy engine spec.

## Semantics

Supported rule kinds in the current Rust loader:

- `parameter`: no entity-scoped output; literal versions lower to indexed scalar
  parameters through the existing bridge.
- `derived`: entity-scoped scalar or judgment outputs.
- `relation`: explicit relation declarations with `arity`.

Known hard gaps:

- `derived_relation` is represented in the schema direction but intentionally
  rejected until relation outputs are modelled in `ProgramSpec`.
- Formula strings are currently parsed by generating an equivalent `.rac`
  declaration and lowering through `crate::rac_dsl`. This preserves existing
  expression precedence and functions, but it also inherits `.rac` bridge limits
  such as latest-only derived temporal formulas and inferred relation slots.
- The next implementation step is direct RuleSpec formula parsing and
  normalisation into `ProgramSpec`, with `.rac` generated only as a projection.

## Why This Instead Of Direct `ProgramSpec` YAML

Direct `ProgramSpec` YAML is useful as an engine IR/debug format, but it is not
the right AutoRAC target. RuleSpec keeps metadata and provenance structured while
leaving formulas concise enough for generation and review. Atlas should provide
the human-readable visualisation layer; raw source readability is secondary to
schema validity, provenance fidelity, and avoiding silent lossy translation.
