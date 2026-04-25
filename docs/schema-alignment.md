# Schema Alignment

The current direction is:

1. RuleSpec YAML/JSON is the canonical AutoRAC output and jurisdiction-repo
   source format.
2. `ProgramSpec` is the Rust engine IR and compiled-artifact input.
3. `.rac` is a compatibility/review projection and a temporary expression-parser
   bridge, not the long-term authoring surface.

This supersedes the earlier framing that tried to make `.rac` the medium-term
author surface. The user constraint is stronger now: nobody depends on this PR
yet, backwards compatibility is not required, and Atlas visualisers can carry
human readability. The author schema should therefore optimise for AutoRAC
accuracy, validation, provenance, and lossless normalisation.

## Current Bridge

`src/rulespec.rs` deserializes RuleSpec, emits an equivalent in-memory `.rac`
declaration for formula-bearing rules, and lowers it through `crate::rac_dsl` into
`ProgramSpec`. This is intentionally an adapter:

- It avoids duplicating formula parsing and precedence while RuleSpec lands.
- It lets RuleSpec fixtures compare to existing `.rac` fixtures by compiled
  artifact equality.
- It should be replaced by direct formula parsing/normalisation once RuleSpec
  becomes the only generation target.

The bridge inherits `.rac` limits. The most important ones are latest-only
derived temporal formulas, inferred relation slot orientation, no direct
relation-output rules, and no richer cumulative/fold/counterfactual operators.
Those should be explicit RuleSpec and `ProgramSpec` gaps, not hidden constraints
on the canonical schema.

## Alignment Points

RuleSpec should retain the semantic gains from the deployed DSL and this Rust
prototype:

- Temporal versions on each rule.
- Typed scalar and judgment outputs.
- Relation facts separate from scalar outputs.
- Effective-dated parameters.
- Provenance fields that can carry source citations and source URLs.
- Formula strings for compact expressions such as `if`, `match`, arithmetic,
  date operations, and relation aggregations.

RuleSpec should go beyond `.rac` where AutoRAC needs structure:

- Explicit rule kind: `parameter`, `derived`, `relation`, and eventually
  `derived_relation`.
- Explicit relation arity and, in a follow-up, slot names/orientation.
- Multi-source provenance and Atlas/AKN anchors.
- Graph-level metadata such as `sets` and `amends` in sidecar documents rather
  than overloaded formula declarations.

## Tests Added In This Pass

The Rust tests now cover:

- RuleSpec-to-compiled-artifact equality against equivalent `.rac` for a
  SNAP-like formula set with parameters, `match`, nested `if`, `sum`, and
  provenance.
- RuleSpec-to-compiled-artifact equality for a housing-style judgment with date
  arithmetic, `count_where`, derived judgment references, and `not`.
- Rejection of `derived_relation` until relation outputs are modelled.
- Rejection of ambiguous YAML with `rules:` but no RuleSpec discriminator.
