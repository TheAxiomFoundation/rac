# Schema alignment with the deployed RAC DSL

This prototype's YAML surface and its Rust engine's spec are being aligned
with the deployed `.rac` DSL on `github.com/TheAxiomFoundation/rac` so our
work reads as **additions on top of** the deployed spec rather than a
parallel reinvention. The deployed DSL and its surrounding ecosystem —
`rac-compile`, `autorac`, `rac-uk`, `rac-us`, `rac-us-*`, `rac-ca`,
`rac-validators`, `atlas`, `atlas-viewer`, `akomize`, `statute-graph`,
`rac-syntax` — already do most of what a rules engine needs. Our Rust
runtime is kept, since it is genuinely useful for bulk execution; the DSL
is what re-aligns.

## What's aligned in this pass

**Dtype vocabulary.** The Rust `DTypeSpec` now accepts rac's PascalCase
names (`Judgment`, `Boolean`, `Integer`, `Decimal`, `Money`, `Rate`,
`Text`, `Date`) as aliases for the previous snake_case. `Money` and `Rate`
both map to the engine's `Decimal` at runtime — they preserve authoring
intent from the `.rac` surface but the engine does not distinguish them.
All 21 on-disk `rules.yaml` files are migrated.

**Optional `period:` field.** `DerivedSpec` now accepts an optional
`period:` value (e.g. `Month`, `Year`, `Day`) for parity with rac's
variable declarations. The engine does not use it yet — the query period
remains authoritative at runtime — but programmes can round-trip the
authoring convention.

## What's *not* aligned yet, deliberately

The following would require structural changes that go beyond vocabulary;
they're queued as follow-ups rather than done in this pass.

**File granularity.** rac's jurisdiction repos (`rac-uk`, `rac-us`, …)
encode one atomic leaf per `.rac` file with a `.rac.test` companion, laid
out under `legislation/<jurisdiction>/<act>/<section>/`. Our programmes
are integrated single-file encodings — e.g. UC's ~30 derived outputs live
in one `rules.yaml`. Splitting into atomic leaves is its own migration.

**Author surface.** rac's surface is `.rac`, parsed by its Python
recursive-descent parser into a `Module` AST. Our surface is YAML that
maps to the Rust engine's internal spec. The medium-term target is to
make `.rac` the author surface and have the Rust engine consume the rac
AST (as JSON from the Python parser or via a Rust port of the parser).
For now the YAML is a serialised form of the same conceptual AST, with
field names aligned where feasible.

**Expression AST shape.** rac tags expression nodes with `type:` and
uses `BinOp`/`Cond`/`Call`/`FieldAccess`/`Let`/`Match`. We tag ours with
`kind:` and inline the arithmetic operators (`add`, `mul`, `sub`, …) as
their own node kinds. The semantics map 1:1; the field name and shape
don't yet.

**Parameter / variable split.** rac treats a definition without `entity:`
as a parameter and with `entity:` as entity-scoped — one unified
declaration list. We keep two separate top-level lists (`parameters:`
and `derived:`). Merging into one is a follow-up.

**Entity / relation modelling.** rac uses typed `entity` declarations
with `fields`, `foreign_keys`, and `reverse_relations`. We declare
`relations` as flat N-ary tuples with arity. The two models express the
same facts, but ours is less constrained; aligning means re-expressing
our relations as reverse relations off typed entity declarations.

## Extensions we genuinely contribute

These are features the deployed DSL does not have today. They are the
additions we are trying to land on top of it:

1. **Three-valued judgments.** `dtype: Judgment` with outcomes `holds` /
   `not_holds` / `undetermined`, and judgment expressions built from
   `and` / `or` / `not` / comparison / derived-reference. The deployed
   DSL has `dtype: Boolean`; it does not have an `undetermined` outcome.
   Undetermined is load-bearing for real legal questions where the
   inputs don't let the engine decide (missing evidence, disputed facts).

2. **Filtered aggregation.** `count_related` and `sum_related` take an
   optional `where:` predicate, so "count notices served in the last 6
   months" is one expression rather than a pre-flattened boolean input.
   The deployed DSL supports `sum(members.field)` but has no predicate
   argument; filtering would require a list comprehension it doesn't
   parse.

3. **Date arithmetic built-ins.** `days_between(from, to)` and
   `date_add_days(date, n)` operate on arbitrary date values inside an
   expression. The deployed DSL supports `dtype: date` values but lacks
   arithmetic operators between two dates.

4. **YAML as a serialisation surface.** The deployed DSL uses `.rac`
   source. Our YAML is the engine's consumable form of the same AST;
   this lets callers skip the parser when they already have a compiled
   AST in hand. Not a capability claim — just a different medium.

Every other capability — entity scoping, temporal effectivity,
amendments, Rust codegen for speed, list-valued field access, `sum` /
`len` / `any` / `all` built-ins — exists in the deployed DSL today and
should not be re-pitched as new.

## Why this framing matters

The prior prototype PR (#23) was pitched as a rewrite demonstrating that
the deployed DSL could not express arbitrary law. That pitch overstated
the case: the deployed DSL already handles entities, relations
(via foreign keys and reverse relations), temporal values, amendments,
and list-scoped aggregation. The genuine additions fit in the four
bullets above; the rest is engineering (Rust runtime, YAML surface) that
is legitimately useful but does not need a new-spec framing to justify.

Treating this work as additions on top of the deployed DSL makes the
surface area honestly small, makes the pitch defensible, and keeps the
downstream tooling (`rac-compile`, `autorac`, `atlas-viewer`,
`rac-syntax`) interoperable. A random-legislation exercise across
non-tax-benefit domains — family, property, regulatory, procedural,
public law — is the fair test of whether the four extensions plus the
deployed spec cover enough ground, and whether further operators are
needed.
