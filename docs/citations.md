# Citation metadata propagation

Every rac variable can carry a statutory citation via the `source:` metadata
field. This document describes how that citation travels from the source
`.rac` file through the parse → compile → execute pipeline, and the
guarantees callers can rely on.

## Surface syntax

```
gov/irs/standard_deduction:
    source: "26 USC 63(c)"
    label: "Standard deduction"
    from 2024-01-01: 14600
```

`source` is a free-form string. The convention is a statutory citation
("26 USC 32"), but the engine does not parse or validate the format —
downstream tooling is free to interpret it.

## Propagation contract

The pipeline preserves `source` at every stage:

1. **Parse** (`rac.parser`) — the string is stored on
   `ast.VariableDecl.source`.
2. **Compile** (`rac.compiler`) — `Compiler._collect_variables` copies it
   onto `TemporalLayer`, and `_resolve_temporal` emits it on the
   per-variable `ResolvedVar.source` in the produced `IR`.
3. **Execute** (`rac.executor`) — `Executor.execute` populates
   `Result.citations[path] = source` for every `ResolvedVar` that carries
   a non-empty `source`. Variables without a citation are **omitted**
   from the map (not set to `None` or `""`) to keep the map compact.

```python
result = run(ir, data)
result.citations            # dict[str, str]: path -> citation
result.citations.get("gov/rate")   # e.g. "26 USC 1"
```

## Amendments

Amendments (`amend path:`) do not currently carry their own `source:`
field. A variable's citation is the one declared on its original
`VariableDecl`; amendments stack temporal values on top without
overriding the citation. If a future change introduces a
`source:` on `AmendDecl`, the intended semantics are that the amendment's
citation applies only for dates it effectively covers — but that is a
future extension, and today the original declaration's citation wins for
all dates.

## Repeals

Repealed variables (`repeal`) drop out of the IR entirely for dates past
the effective repeal, so they also drop out of `Result.citations`. This
is consistent with the rest of the execution envelope.

## Rust / native backend

The Python executor is the canonical reference implementation for
citation propagation. The Rust `CompiledBinary` path
(`rac.native` / `rac.model.Model.run`) currently returns raw arrays and
does not expose a `citations` map. Plumbing citations through the native
backend is tracked as future work; callers that need citations today
should use the Python executor (`rac.executor.run`).

## Stability

`Result.citations` is a stable field of the execution envelope. Adding
new keys (as more statute files annotate `source:`) is backward
compatible. Renaming or removing the field is not.
