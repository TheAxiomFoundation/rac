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
cargo run -- compile --program examples/snap_program.yaml --output /tmp/snap.compiled.json
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

- scalar and judgment derived outputs
- acyclic dependencies
- parameter lookups
- `if`
- `count_related`
- `sum_related` over related inputs

It is exercised on three YAML programmes:

- `examples/flat_tax_program.yaml`
- `examples/family_allowance_program.yaml`
- `examples/snap_program.yaml`

To run the release benchmark over `100,000` rows:

```bash
cargo run --release --example dense_bench -- 100000
```

This is the first proof in the repo that YAML-defined programmes beyond SNAP can
be compiled into a genuinely fast dense runtime. That same generic dense path is
now also exposed to Python through `CompiledDenseProgram`, so the Python
benchmark no longer needs to measure JSON/subprocess overhead to exercise the
real fast path.

## SNAP examples

The prototype SNAP law lives in [`examples/snap_program.yaml`](examples/snap_program.yaml).
The executable test cases live in [`examples/snap_cases.yaml`](examples/snap_cases.yaml).

## Running tests

```bash
cargo test
```
