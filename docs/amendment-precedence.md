# Amendment precedence specification

This document formalizes how rac resolves competing definitions for a
single variable path across multiple source tiers. It is the reference
for compiler behavior in `src/rac/compiler.py` (`TemporalLayer`,
`_apply_amendments`, `_resolve_temporal`).

## Source tiers

A single variable (`path`) may be written or modified from several
distinct source tiers. When two tiers cover the same effective date,
higher-numbered tiers win:

| Tier | Name          | Origin                                            | Produces                |
|-----:|---------------|---------------------------------------------------|-------------------------|
|    1 | Statute       | Statute encoding (`.rac` files in `rac-us/`, etc.) | `VariableDecl`          |
|    2 | Projection    | Forecast / projection overlays for future periods | `AmendDecl` (by convention) |
|    3 | Legislation   | Enacted legislation applying an amendment         | `AmendDecl`             |
|    4 | Publication   | Published regulatory guidance / updated tables    | `AmendDecl`             |

Numerically: **statute (1) < projection (2) < legislation (3) <
publication (4)**. A publication-tier amendment overrides a
legislation-tier amendment for the same effective date; a legislation-
tier amendment overrides a projection; and so on.

Tiers 2–4 are all expressed as `amend` declarations in rac today — the
engine does not currently record the tier on the AST. The convention is
that higher-tier amendments appear **later** in the module load order,
because `TemporalLayer.resolve` applies the "later value wins" rule
(`src/rac/compiler.py`, `TemporalLayer.resolve`). This is a load-order
contract, not a parser-enforced invariant.

## Resolution algorithm

For a single variable path, resolution at a given `as_of` date proceeds:

1. Collect all `TemporalValue` entries for the path, in module load
   order. (Each `VariableDecl` and each `AmendDecl` contributes its
   `values`.)
2. Filter to entries that cover `as_of` (i.e. `start <= as_of` and
   `end is None or as_of <= end`).
3. Return the **last matching entry's expression**. "Last" is in
   collection order, which matches declaration order within a module and
   module order within the compiler's module list.
4. If the variable has been repealed (`RepealDecl`) with
   `effective <= as_of`, the variable is dropped from the resolved IR
   entirely (the expression is `None` and the path is not present in
   `Result.scalars` or `Result.entities`).

## Tie-breaking rules

When two or more temporal values cover the same `as_of` date:

1. **Later source tier wins.** By convention, higher-tier amendments are
   loaded later, so "later in the collected list" means "higher tier."
2. **Within the same tier**, later declarations win. This lets a
   statute file end with a corrective amendment that overrides earlier
   values in the same file.
3. **Replace-mode wins a whole segment.** An `AmendDecl` with
   `replace: True` (`TemporalLayer.add_values(..., replace=True)`)
   discards all previously accumulated values before adding its own.
   This is the hammer — use it sparingly. Replace-mode is intended for
   legislation that strikes and replaces an entire statutory provision
   rather than amending it incrementally.
4. **Repeal trumps everything.** If the path has been repealed with an
   effective date at or before `as_of`, no amendment can bring it back.
   A later "un-repeal" requires a fresh `VariableDecl` or a re-enactment
   modeled as a new module.

## Worked example

Consider `gov/irs/ctc/base_amount` with these sources:

> **Note:** The $2,000 statute value and the $2,200 OBBBA legislation value
> are real (26 USC 24 and the OBBBA as enacted). The $1,050 projection and
> $2,225 publication values are illustrative — chosen to show tier
> interleaving, not to represent actual CBO or IRS figures.

```
# statute/26/24.rac  (tier 1: statute)
gov/irs/ctc/base_amount:
    source: "26 USC 24(a)"
    from 2018-01-01: 2000
    from 2026-01-01: 1000   # statutory sunset back to pre-TCJA level

# projections/ctc_projection.rac  (tier 2: projection)
amend gov/irs/ctc/base_amount:
    from 2026-01-01: 1050   # CBO-style inflation projection

# legislation/obbba.rac  (tier 3: legislation)
amend gov/irs/ctc/base_amount:
    from 2026-01-01: 2200   # OBBBA sets CTC to $2,200 for 2026

# publications/irs_rev_proc_2026.rac  (tier 4: publication)
amend gov/irs/ctc/base_amount:
    from 2026-01-01: 2225   # hypothetical inflation-indexed update
```

Resolution at `as_of = 2026-06-01`:

| Step | Source                 | Contributes                     |
|------|------------------------|---------------------------------|
| 1    | statute                | `(2026-01-01, None) => 1000`    |
| 2    | projection             | `(2026-01-01, None) => 1050`    |
| 3    | legislation            | `(2026-01-01, None) => 2200`    |
| 4    | publication            | `(2026-01-01, None) => 2225`    |

All four match (`start <= 2026-06-01`, no end). The last collected
entry wins → **2225**.

If the publication module were removed, the result would be **2200**
(legislation). If legislation were removed too, **1050** (projection).
Without any amendments, **1000** (statute).

Resolution at `as_of = 2024-06-01`:

Only the statute's first segment (`from 2018-01-01: 2000`) matches. All
three amendments are effective only from 2026-01-01, so they do not
apply → **2000**.

## Divergence from rac-compile

`rac-compile` (the multi-target compiler) models amendments with a
different `override:` keyword on variable declarations rather than a
separate `amend` declaration. The two approaches are logically similar
but differ in three ways:

1. **Shape.** rac uses a separate `AmendDecl` node with its own
   `target` path; rac-compile attaches `override:` to the original
   variable declaration.
2. **Tier tagging.** Neither system records the source tier on the AST
   today; both rely on load order for precedence. A future change could
   add an explicit `tier:` field to both.
3. **Replace semantics.** rac's `replace: True` discards all prior
   values; rac-compile's `override:` semantics are declaration-scoped
   and the merge rule for multiple overrides of the same period is
   currently unspecified.

**These two models must be reconciled** before either can be treated as
the canonical rac-ecosystem amendment form. This document tracks the
rac engine's behavior; the rac-compile divergence is a known
inconsistency flagged for a future RFC.
