# Prototype plan

## Goal

Build a Rust prototype that demonstrates the right semantic centre for the
Axiom Rules Engine:

- temporal
- relational
- typed
- judgment-aware
- still natural for ordinary tax and benefit calculations

The prototype should be small enough to understand quickly and strong enough to
show why the current formula-first design is too narrow.

## Why the current design is too narrow

The current prototype materials are good at:

- dated parameters
- dated formulas
- entity-scoped calculations

They are not yet native for:

- legal conclusions that hold or do not hold for a statutory purpose
- absence conditions such as "no person satisfies X"
- derived relations such as household membership or attribution
- named legal periods such as benefit weeks and tax years
- partial-period reasoning
- legal fictions such as "treated as" or "treated as if not entitled"

That is the core reason to move the runtime.

## Design decisions

### 1. Use a unified `derived` surface

The user-facing model should not split the world into separate "judgment" and
"value" declarations.

The cleaner model is:

- `derived ... dtype: Judgment`
- `derived ... dtype: Decimal`
- `derived ... dtype: Bool`
- `derived ... dtype: Integer`

This keeps tax calculations natural while still allowing legal conclusions.

### 2. Keep `relation` separate

A relation is not a scalar dtype. It is a set of tuples over time.

That matters for:

- household membership
- child benefit relationships
- company-arrangement relationships
- attribution links

### 3. Treat `Judgment` as a special dtype

`Judgment` is not special because it is binary. It is special because it has
legal inference semantics.

A plain `Bool` is an ordinary value.

A `Judgment` may need:

- `holds`
- `not_holds`
- `undetermined`
- scope
- provenance
- defeat in later versions of the engine

### 4. Make units user-defined

We should not hardcode `Money` as a primitive type.

The more general model is:

- `dtype: Decimal`
- `unit: USD`

or:

- `dtype: Integer`
- `unit: person`

This prototype therefore supports user-defined units and treats currency as one
kind of unit rather than the only quantitative domain.

### 5. Keep time native

Time is not metadata. It is part of the model.

The prototype includes:

- periods
- intervals
- effective-dated parameter versions
- relation facts that cover a period

This is a smaller but faithful step towards a full temporal legal engine.

## Prototype scope

This spike implements:

- a small in-memory execution engine
- typed scalar expressions
- judgment expressions
- relation-aware aggregations
- a serialisable executable interface
- a thin Python wrapper over the compiled binary
- SNAP as a DSL-driven conformance test rather than product code

It does not yet implement:

- Arrow or Parquet I/O
- a full fixed-point planner
- defeat priority
- scoped statutory purposes beyond the metadata model

## Executable interface

The prototype should be usable as an engine, not just as a Rust library.

The execution boundary is therefore:

- a serialisable program document
- a serialisable dataset document
- a list of entity-period queries
- JSON over stdin/stdout for the compiled executable

Python then stays thin. It should validate request and response envelopes with
Pydantic and shell out to the compiled binary rather than reimplementing engine
logic in Python.

## SNAP slice

The SNAP slice is intentionally modest but real. It covers part of the monthly
benefit calculation for the 48 states and DC, and it lives as a program fixture
plus tests rather than Rust engine code:

- household size from the `member_of_household(person, household)` relation
- earned and unearned income aggregated across members
- earned income deduction
- standard deduction lookup by household size
- gross income limit lookup by household size
- net income limit lookup by household size
- maximum allotment lookup by household size
- monthly allotment calculation

The tests use FY 2026 figures from USDA Food and Nutrition Service guidance and
the worked household example on the SNAP eligibility page:

- <https://www.fns.usda.gov/snap/recipient/eligibility>
- <https://www.fns.usda.gov/snap/allotment/cola>

## Why this is enough to be persuasive

The prototype forces three important questions into code:

1. Can one engine handle judgments and ordinary calculations?
2. Can the runtime aggregate over relations rather than only row-local fields?
3. Can time and units be part of the model rather than comments and host logic?

If the answer to all three is yes, then the repo should move in this direction.
