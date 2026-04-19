# Decisions

Short decision log for the architecture choices that the PR #23
"build a Rust temporal-relational RAC prototype" commits to. One entry
per decision, most recent first.

## 2026-04-19 — Retire the `.rac` DSL; YAML is the single surface

**Decision.** The `.rac` DSL and its Python parser / compiler / runtime
are retired. Programmes are authored (by AutoRAC, not humans) in the YAML
format defined by `src/spec.rs`. That YAML is both the author surface and
the engine's IR; there is no lowering step.

**Why.**

- Humans do not author encodings. AutoRAC writes them from atlas source.
  A DSL pays off in author ergonomics; if the author is an LLM, it does
  not pay off.
- Two formats plus a transpiler is more to maintain than one format.
  `rac-compile`, `rac-syntax`, and the `.rac` parser all go.
- The YAML form expresses what the new engine needs — units, relations,
  judgments, temporal periods, effective-dated parameters — natively. The
  `.rac` form does not, and a mechanical transpile would silently lose
  these fields.
- Tested against three worked examples (IRC §63(c), §3101(b)(2),
  §63(c)(5)) and a Texas SNAP overlay demo, all generated against the
  YAML schema and matching PolicyEngine US.

**Consequences.**

- Jurisdiction repos (`rac-us`, `rac-us-*`, `rac-uk`, `rac-ca`) re-encode
  from atlas rather than transpile. No forced flag day. Tier 1 is
  everything with a PolicyEngine oracle; Tier 2 is homepage and grant
  deliverables; the long tail stays on the old stack until there is a
  reason to move.
- `rac-compile` and `rac-syntax` get archived once downstream stops
  depending on them.
- Existing `.rac` files in jurisdiction repos remain the source of record
  for their encodings until superseded by an AutoRAC-generated
  `program.yaml`. No attempt to keep the two formats in sync.

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
alongside atlas AKN archives, not inside `program.yaml`. The engine reads
merged YAML; the graph-level facts are consumed by tooling (validators,
atlas viewer, explain-mode trace renderer).

**Why.**

- Overloading `program.yaml` with graph metadata makes it harder to diff
  and harder to review.
- The existing `rac-us-tx/sources/targets/.../*.meta.yaml` files port
  forward as-is — no migration.
- Multi-source citations on a derived output (statute + reg + manual)
  are a valuable engine feature (array-shaped `source` and `source_url`)
  but that's a programme-internal change, not the same thing as the
  graph-level `sets` / `amends` edges.

**Consequences.**

- No engine change for `sets` / `amends` in the initial landing.
- A follow-up can teach the explain trace to pull sidecar metadata for
  rendering; separate PR.
- The `source` / `source_url` fields on derived outputs become arrays
  (follow-up PR) to support multi-document provenance.
