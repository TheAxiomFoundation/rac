# Decisions

Short decision log for the architecture choices in PR #23. Publicly and
internally, this is the Axiom Rules Engine; the Rust crate and executable are
`axiom-rules`. One entry per decision, most recent first.

## 2026-04-24 — RuleSpec YAML/JSON is canonical; `.rac` is a bridge

**Decision.** The canonical authoring and interchange surface is RuleSpec
YAML/JSON: structured rule metadata with concise formula strings. AutoRAC
writes RuleSpec, Atlas visualises RuleSpec and compiled traces, and the
Rust engine normalises RuleSpec into `ProgramSpec` before compilation.
`ProgramSpec` is the engine IR, not the author schema. `.rac` remains a
compatibility/review projection and a temporary expression-parser bridge,
not the source of truth.

**Why.**

- Humans are not the primary authors. AutoRAC needs an unambiguous,
  schema-valid target more than a pretty hand-written DSL.
- Atlas can provide human visualisers for rule graphs, provenance, and
  traces, so source readability is secondary to faithful generation and
  validation.
- A structured schema can represent provenance, source-document anchors,
  jurisdiction/repo ownership, temporal versions, rule kind, relation
  orientation, and future hard gaps without overloading formula syntax.
- Concise formula strings keep common calculations compact while the
  surrounding YAML/JSON keeps metadata machine-checkable.
- Tests on SNAP-like and housing/date/relation formulas show RuleSpec can
  round-trip through the current `.rac` bridge to the same compiled
  artifacts; harder operators remain explicit schema gaps rather than
  hidden DSL constraints.

**Consequences.**

- `axiom-rules compile` accepts RuleSpec YAML when it has an explicit
  discriminator (`format: rulespec/v1` or `schema: axiom.rules.*`).
  Ambiguous YAML with a top-level `rules:` key is rejected.
- The first Rust implementation lowers formula strings through the
  existing `.rac` parser to avoid duplicating precedence and expression
  semantics. This is an adapter to delete, not the architecture.
- Follow-up work should replace the `.rac` bridge with direct RuleSpec
  formula parsing/normalisation into `ProgramSpec`.
- Existing `.rac` fixtures remain regression and migration fixtures until
  AutoRAC emits RuleSpec for those programmes.

## 2026-04-19 — Retire direct `ProgramSpec` YAML as the author surface

**Decision.** Direct YAML matching `src/spec.rs` is retained as an engine
IR/debug format, but not as the authoring contract for AutoRAC or
jurisdiction repos.

**Why.**

- The old `ProgramSpec` YAML is structurally faithful to the runtime but
  too verbose for reliable AutoRAC generation at scale.
- It lacks a stable place for source-document provenance, authoring
  status, rule kinds, and future relation-output constructs.
- Human readability of raw YAML is less important because Atlas will
  provide dedicated visualisers.

**Consequences.**

- New canonical examples and jurisdiction outputs should use RuleSpec,
  not direct `ProgramSpec` YAML.
- The engine can keep deserialising direct `ProgramSpec` YAML for tests
  and low-level debugging while no downstream consumers depend on it.

## 2026-04-19 — `programmes/` migrates to jurisdiction repos

**Decision.** The `programmes/` directory in this engine repo is a proof
of concept. In production, encodings live in the jurisdiction repo they
belong to:

- `rac-us/programmes/usda/snap/federal/` — federal baseline
- `rac-us-tx/programmes/snap/` — Texas overlay (`extends:` crosses repo
  boundaries via path)
- `rac-uk/programmes/...` — UK jurisdiction
- etc.

The engine resolves `extends:` by filesystem path; any mounted layout
works.

**Why.**

- Keeps the engine repo focused on runtime and schema, not content.
- Per-jurisdiction repos already exist and have their own release
  cadence, reviewers, and license boundaries.
- Matches the existing structure of `rac-us-*` and `rac-us-tx`.

**Consequences.**

- The programmes currently under `programmes/` in this repo move out
  post-merge. The engine ships a small set of canonical examples
  (SNAP generic, UC, UK income tax) for tests and docs.

## 2026-04-19 — `sets` / `amends` stay graph-level sidecar metadata

**Decision.** State-delegation (`relation: sets`) and regulation-amends-
statute (`relation: amends`) edges stay in sidecar `*.meta.yaml` files
alongside atlas AKN archives, not inside RuleSpec. The engine reads
merged RuleSpec / `ProgramSpec`; the graph-level facts are consumed by
tooling (validators, atlas viewer, explain-mode trace renderer).

**Why.**

- Overloading RuleSpec with graph metadata makes it harder to diff
  and harder to review.
- The existing `rac-us-tx/sources/targets/.../*.meta.yaml` files port
  forward as-is — no migration.
- Multi-source citations on a derived output (statute + reg + manual)
  are a valuable engine feature (array-shaped `source` and `source_url`)
  but that's a programme-internal change, not the same thing as the
  graph-level `sets` / `amends` edges.

**Consequences.**

- No engine execution change for `sets` / `amends` in the initial landing.
- A follow-up can teach the explain trace to pull sidecar metadata for
  rendering; separate PR.
- The `source` / `source_url` fields on derived outputs become arrays
  (follow-up PR) to support multi-document provenance.
