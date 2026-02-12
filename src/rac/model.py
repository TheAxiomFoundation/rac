"""High-level Python interface for RAC models."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from .compiler import IR, Compiler
from .executor import Context, evaluate
from .native import CompiledBinary, compile_to_binary
from .parser import parse
from .schema import Data


@dataclass
class RunResult:
    """Result of running a model on data."""

    arrays: dict[str, np.ndarray]
    output_names: dict[str, list[str]]

    def __getitem__(self, entity: str) -> np.ndarray:
        return self.arrays[entity]

    def to_dict(self, entity: str) -> list[dict[str, float]]:
        arr = self.arrays[entity]
        names = self.output_names[entity]
        return [{name: arr[i, j] for j, name in enumerate(names)} for i in range(len(arr))]


@dataclass
class CompareResult:
    """Result of comparing baseline vs reform."""

    baseline: RunResult
    reform: RunResult
    n_rows: dict[str, int]

    def gain(self, entity: str, variable: str) -> np.ndarray:
        b_names = self.baseline.output_names[entity]
        r_names = self.reform.output_names[entity]
        b_idx = b_names.index(variable)
        r_idx = r_names.index(variable)
        return self.reform.arrays[entity][:, r_idx] - self.baseline.arrays[entity][:, b_idx]

    def summary(self, entity: str, variable: str, income_col: np.ndarray | None = None) -> dict:
        gain = self.gain(entity, variable)
        n = len(gain)

        result = {
            "n": n,
            "total_annual": float(gain.sum() * 12),
            "mean_monthly": float(gain.mean()),
            "winners": int((gain > 1).sum()),
            "losers": int((gain < -1).sum()),
            "winners_pct": float(100 * (gain > 1).sum() / n),
            "losers_pct": float(100 * (gain < -1).sum() / n),
        }

        if income_col is not None:
            deciles = np.percentile(income_col, np.arange(10, 101, 10))
            decile_idx = np.digitize(income_col, deciles)
            result["by_decile"] = []
            for d in range(10):
                mask = decile_idx == d
                if mask.sum() == 0:
                    continue
                result["by_decile"].append(
                    {
                        "decile": d + 1,
                        "avg_income": float(income_col[mask].mean()),
                        "avg_gain": float(gain[mask].mean()),
                        "pct_winners": float(100 * (gain[mask] > 1).sum() / mask.sum()),
                    }
                )

        return result


class Model:
    """A compiled RAC model ready for execution."""

    def __init__(self, ir: IR, binary: CompiledBinary):
        self._ir = ir
        self._binary = binary

    @classmethod
    def from_source(cls, *sources: str, as_of: date) -> Model:
        modules = [parse(s) for s in sources]
        ir = Compiler(modules).compile(as_of)
        binary = compile_to_binary(ir)
        return cls(ir, binary)

    @classmethod
    def from_file(cls, *paths: str | Path, as_of: date) -> Model:
        sources = [Path(p).read_text() for p in paths]
        return cls.from_source(*sources, as_of=as_of)

    @property
    def entities(self) -> list[str]:
        return list(self._binary.entity_outputs.keys())

    @property
    def scalars(self) -> dict[str, float]:
        ctx = Context(data=Data(tables={}))
        for path in self._ir.order:
            var = self._ir.variables[path]
            if var.entity is None:
                ctx.computed[path] = evaluate(var.expr, ctx)
        return dict(ctx.computed)

    def outputs(self, entity: str) -> list[str]:
        return self._binary.entity_outputs.get(entity, [])

    def inputs(self, entity: str) -> list[str]:
        return self._binary.entity_schemas.get(entity, [])

    def run(self, data: dict[str, list[dict] | np.ndarray]) -> RunResult:
        arrays = self._binary.run(data)
        return RunResult(
            arrays=arrays,
            output_names={e: self._binary.entity_outputs[e] for e in arrays},
        )

    def compare(self, reform: Model, data: dict[str, list[dict] | np.ndarray]) -> CompareResult:
        with ThreadPoolExecutor(max_workers=2) as executor:
            baseline_future = executor.submit(self.run, data)
            reform_future = executor.submit(reform.run, data)
            baseline_result = baseline_future.result()
            reform_result = reform_future.result()

        return CompareResult(
            baseline=baseline_result,
            reform=reform_result,
            n_rows={e: len(arr) for e, arr in baseline_result.arrays.items()},
        )
