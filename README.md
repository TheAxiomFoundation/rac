# rac

Prototype Rust rewrite of RAC around a temporal-relational core.

This prototype is intentionally opinionated. It resets the repository around one
claim:

> the current RAC surface handles dated formulas well, but arbitrary law needs a
> runtime that treats time, relations, legal judgments, and typed values as
> first-class.

The prototype therefore does four things:

1. keeps a unified `derived + dtype + unit` surface for outputs
2. treats `Judgment` as a dtype with legal inference semantics, not as a plain
   boolean
3. keeps `relation` separate because relations are tuple sets over time, not
   scalar values
4. exposes a compiled executable interface that can be wrapped from Python
5. proves the direction with a SNAP law fixture and conformance tests rather
   than product-specific engine code

The detailed plan and justification live in
[`docs/prototype-plan.md`](docs/prototype-plan.md).

## What is implemented

- user-defined units
- typed derived outputs
- temporal periods and intervals
- relation facts
- scalar expressions
- judgment expressions with `holds`, `not_holds`, and `undetermined`
- serialisable program and dataset documents
- explicit `explain` and `fast` execution modes over the same semantics
- a general `rac compile` command that turns any current YAML programme into a reusable compiled artefact
- a generic dense compiled executor for an acyclic scalar/judgment subset, proven on multiple YAML programmes
- a CLI that reads a JSON execution request from stdin and writes JSON results
- a Python wrapper over the compiled executable using Pydantic models
- a SNAP DSL fixture for the 48 states and DC monthly rules:
  - household size from relations
  - earned and unearned income aggregation across household members
  - standard deduction lookup by household size
  - gross and net income tests as judgments
  - maximum allotment lookup by household size
  - monthly allotment calculation

## Why this is a prototype

The engine is intentionally small. It does not yet parse RAC source, emit Arrow,
or implement the full fixed-point legal runtime. It is a working spike for the
semantic centre of gravity.

## Python wrapper

The thin Python wrapper lives under `python/rac_api/`. It exposes `Program`,
`Dataset`, and `RAC`, uses Pydantic models for the request and response
envelope, and shells out to the compiled `rac` binary for the reference and
generic compiled-artefact flows.

There is also now a separate generic dense Python binding,
`CompiledDenseProgram`, which loads a YAML programme directly into the generic
dense compiler path and executes it in-process over NumPy arrays.

Requests now choose a mode explicitly:

- `explain`: always run the reference executor
- `fast`: try the bulk compiled path first, then fall back to explain mode if the
  requested programme uses a feature the fast path does not support yet

To compile a YAML programme into a reusable artefact:

```bash
cargo run -- compile --program programmes/other/snap/program.yaml --output /tmp/snap.compiled.json
```

To execute that compiled artefact:

```bash
cargo run -- run-compiled --artifact /tmp/snap.compiled.json < request.json
```

The compiled artefact is currently an analysed execution package:

- resolved `ProgramSpec`
- dependency-ordered derived outputs
- fast-path compatibility metadata

That means the generic compile pipeline is now real and reusable. The repo no
longer contains a SNAP-specific Rust execution kernel; the remaining fast proof is
the generic dense compiler path below.

To run the SNAP demo end to end from Python:

```bash
python3 python/examples/run_snap_cases.py
```

To run the reg 15 child-benefit responsibility demo (explain mode), and then its
fast-mode benchmark over a million children:

```bash
python3 python/examples/run_child_benefit_cases.py
/Users/nikhilwoodruff/policyengine/.venv/bin/python python/examples/run_child_benefit_benchmark.py --children 1000000
```

To run the rUK income tax 2025-26 demo (eight HMRC-validated cases in explain
mode), and then its fast-mode benchmark over a million taxpayers:

```bash
python3 python/examples/run_uk_income_tax_cases.py
/Users/nikhilwoodruff/policyengine/.venv/bin/python python/examples/run_uk_income_tax_benchmark.py --taxpayers 1000000
```

The benchmark reports between 2 and 3 million taxpayers per second through the
in-process dense runtime on commodity hardware.

To run the Universal Credit demo (eight cases rendered in explain mode with
the legislation citation trace), and then its fast-mode benchmark over a
million synthetic benefit units:

```bash
python3 python/examples/run_universal_credit_cases.py
/Users/nikhilwoodruff/policyengine/.venv/bin/python python/examples/run_universal_credit_benchmark.py --benefit-units 1000000
```

The UC benchmark reports around 1.2 million benefit units per second in fast
mode; every derived output in explain mode is annotated with its UC Regs 2013
citation so the trace is readable as a legal explanation of the award.

To install the in-process dense Python binding into your virtualenv:

```bash
PATH=/Users/nikhilwoodruff/.cargo/bin:$PATH \
  /Users/nikhilwoodruff/policyengine/.venv/bin/maturin develop --release \
  --manifest-path python-ext/Cargo.toml
```

To run the fast Python benchmark over random SNAP households:

```bash
/Users/nikhilwoodruff/policyengine/.venv/bin/python python/examples/run_snap_benchmark.py
```

That path now reports:

- compile time for the generic dense programme
- generation time in Python
- execution time through the in-process generic dense runtime

To compare against the slower CLI boundary explicitly:

```bash
/Users/nikhilwoodruff/policyengine/.venv/bin/python python/examples/run_snap_benchmark.py --engine cli
```

The CLI path is still useful as a correctness boundary, but it is no longer the
performance benchmark that matters.

## Generic dense proof

There is now also a generic dense compiled path in Rust for a substantial subset:

- scalar and judgment derived outputs (bool, integer, decimal, text, date)
- acyclic dependencies
- parameter lookups (effective-dated, integer-indexed)
- `if` / and / or / not
- `count_related` with optional `where` predicate
- `sum_related` over related inputs, with optional `where` predicate
- `ceil`, `floor`, `date_add_days`
- source citations on derived outputs, surfaced as a tree-shaped trace in
  explain mode with every intermediate value and regulation reference

It is exercised on seven YAML programmes:

- `programmes/other/flat_tax/program.yaml`
- `programmes/other/family_allowance/program.yaml`
- `programmes/other/snap/program.yaml`
- `programmes/uksi/1987/1967/regulation/15/program.yaml` (SI 1987/1967 reg 15: child benefit responsibility with an absence condition, encoded as `count_related(cb_receipt) == 0`)
- `programmes/ukpga/2007/3/program.yaml` (rUK income tax 2025-26: personal allowance with £100k taper, basic/higher/additional rate bands, effective-dated parameters)
- `programmes/ssi/2021/249/regulation/71/program.yaml` (SSI 2021/249 reg 71: Scottish CTR notional capital, uses a filtered `sum_related` with a where-clause)
- `programmes/uksi/2013/376/program.yaml` (UC Regs 2013 core monthly calculation: standard allowance, child element with two-child limit, disabled child addition, LCWRA, carer, housing net of non-dep deductions, capital tariff, unearned and earned income taper with work allowance, capital disentitlement — every derived output cites the underlying regulation)

The dense path is exercised from Python via `CompiledDenseProgram` — the
`python/examples/run_*_benchmark.py` scripts are the honest measure of
in-process throughput over the real consumer entry point, no subprocess or
JSON overhead.

## SNAP examples

The prototype SNAP law lives in [`programmes/other/snap/program.yaml`](programmes/other/snap/program.yaml).
The executable test cases live in [`programmes/other/snap/cases.yaml`](programmes/other/snap/cases.yaml).

## Generality audit

Whenever a new operator lands, the DSL gets stress-tested against ten randomly
sampled UK legislation sections from Lex to catch over-fitting. The first audit
is at [`docs/generality-audit-001.md`](docs/generality-audit-001.md); the
sample itself is at
[`diverse-uk-legislation-sample.md`](diverse-uk-legislation-sample.md).
Filtered aggregation (`count_related` / `sum_related` with a `where` predicate)
came out of the first audit — it converted the Scottish CTR notional-capital
rule from a partial fit to a clean fit. Date arithmetic and the `floor`
operator went in next, alongside source citations and the explain-mode trace.
The remaining headline gaps from the first audit are counterfactual
evaluation, cross-entity (pair-keyed) derivation, and full interval output /
arithmetic.

## Running tests

```bash
cargo test
```

## Local tooling

This repo does not track issue-tracker or visualiser state. `.beads/` and
`viz/` are gitignored. Do not install pre-commit or pre-push hooks that
auto-flush bd (beads) JSONL into commits or block pushes on uncommitted
bd state. If `examples/git-hooks/install.sh` (or equivalent) has already
been run locally, remove `.git/hooks/pre-commit` and `.git/hooks/pre-push`.
