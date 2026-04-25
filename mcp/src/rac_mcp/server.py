"""MCP server exposing the Axiom Rules Engine and pre-encoded UK legislation.

Four tools:
  * list_programmes — what's in the catalogue
  * describe_programme — case schema + outputs + statutory reference for one
  * evaluate — run a case, return outputs + rule-by-rule trace
  * counterfactual — run baseline and alternative cases, return deltas
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from rac_api import AxiomRulesEngine
from rac_api.models import (
    ExecutionRequest,
    ExecutionResponse,
    Program,
)

from rac_mcp.catalogue import Catalogue
from rac_mcp.translate import translate


def _repo_root() -> Path:
    override = os.environ.get("RAC_REPO_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[3]


def _rac_binary(repo_root: Path) -> Path:
    override = os.environ.get("RAC_BINARY")
    if override:
        return Path(override).resolve()
    return repo_root / "target" / "debug" / "rac"


REPO_ROOT = _repo_root()
CATALOGUE = Catalogue(REPO_ROOT)
BINARY_PATH = _rac_binary(REPO_ROOT)
CLIENT = AxiomRulesEngine(binary_path=BINARY_PATH)


@lru_cache(maxsize=16)
def _load_program(programme_name: str) -> Program:
    path = CATALOGUE.programme_yaml_path(programme_name)
    return Program.model_validate(yaml.safe_load(path.read_text()))


def _run(programme_name: str, case: dict[str, Any], mode: str) -> ExecutionResponse:
    dataset, query = translate(programme_name, case)
    program = _load_program(programme_name)
    request = ExecutionRequest(
        mode=mode, program=program, dataset=dataset, queries=[query]
    )
    return CLIENT.execute(request)


def _output_summary(response: ExecutionResponse) -> dict[str, Any]:
    result = response.results[0]
    outputs: dict[str, Any] = {}
    for name, value in result.outputs.items():
        if value.kind == "scalar":
            outputs[name] = {"value": value.value.value, "dtype": value.dtype}
        else:
            outputs[name] = {"outcome": value.outcome, "dtype": "judgment"}
    return outputs


def _trace_summary(response: ExecutionResponse) -> list[dict[str, Any]]:
    result = response.results[0]
    trace: list[dict[str, Any]] = []
    for name, node in result.trace.items():
        entry: dict[str, Any] = {
            "name": name,
            "dtype": "judgment" if node.kind == "judgment" else node.dtype,
            "source": node.source,
            "source_url": node.source_url,
            "dependencies": list(node.dependencies),
        }
        if node.kind == "judgment":
            entry["outcome"] = node.outcome
        else:
            entry["value"] = node.value.value
        trace.append(entry)
    return trace


mcp = FastMCP("rac")


@mcp.tool()
def list_programmes() -> list[dict[str, Any]]:
    """List pre-encoded legislation available in this engine instance.

    Call describe_programme(name) to see a given programme's case schema before
    attempting to evaluate it.
    """
    return [
        {
            "name": p.name,
            "title": p.title,
            "statutory_reference": p.statutory_reference,
            "summary": p.summary.strip(),
            "rates_effective_from": p.rates_effective_from,
            "query_entity": p.query_entity,
        }
        for p in CATALOGUE.list()
    ]


@mcp.tool()
def describe_programme(name: str) -> dict[str, Any]:
    """Return the case schema, outputs, and legal citation for a programme.

    Use this before calling evaluate: it tells you which fields the user needs
    to supply, their types, what the engine returns, and what's explicitly out
    of scope for this encoding.
    """
    programme = CATALOGUE.get(name)
    return programme.model_dump()


@mcp.tool()
def evaluate(
    name: str,
    case: dict[str, Any],
    mode: str = "explain",
    include_trace: bool = True,
) -> dict[str, Any]:
    """Run a case through a programme and return outputs plus a rule trace.

    Arguments:
      name: programme name, e.g. "universal_credit".
      case: a dict matching the schema returned by describe_programme.
      mode: "explain" for full rule-by-rule trace (default), "fast" for the
        dense compiled path when supported.
      include_trace: whether to include the per-rule trace with citations.
        Set false for a lighter response when only outputs are needed.

    Returns a dict with keys: programme, statutory_reference, outputs, and
    (if include_trace) trace. Each trace entry carries source + source_url so
    you can cite the legislation directly.
    """
    programme = CATALOGUE.get(name)
    response = _run(name, case, mode)
    payload: dict[str, Any] = {
        "programme": programme.name,
        "statutory_reference": programme.statutory_reference,
        "mode": {
            "requested": response.metadata.requested_mode,
            "actual": response.metadata.actual_mode,
            "fallback_reason": response.metadata.fallback_reason,
        },
        "outputs": _output_summary(response),
    }
    if include_trace:
        payload["trace"] = _trace_summary(response)
    return payload


@mcp.tool()
def counterfactual(
    name: str,
    baseline_case: dict[str, Any],
    alternative_case: dict[str, Any],
    mode: str = "explain",
) -> dict[str, Any]:
    """Run a baseline and an alternative case, return the deltas for each output.

    Useful for "what if I worked 5 more hours" / "what if my partner moved out"
    style questions. Scalar outputs get a numeric delta; judgment outputs flip
    between holds/not_holds/undetermined.
    """
    programme = CATALOGUE.get(name)
    baseline = _run(name, baseline_case, mode)
    alternative = _run(name, alternative_case, mode)
    baseline_outputs = _output_summary(baseline)
    alternative_outputs = _output_summary(alternative)

    deltas: dict[str, Any] = {}
    for key in sorted(set(baseline_outputs) | set(alternative_outputs)):
        b = baseline_outputs.get(key)
        a = alternative_outputs.get(key)
        if b is None or a is None:
            deltas[key] = {"baseline": b, "alternative": a}
            continue
        if "value" in b and "value" in a:
            try:
                from decimal import Decimal

                delta = str(Decimal(str(a["value"])) - Decimal(str(b["value"])))
            except Exception:
                delta = None
            deltas[key] = {
                "baseline": b["value"],
                "alternative": a["value"],
                "delta": delta,
            }
        else:
            deltas[key] = {
                "baseline": b.get("outcome"),
                "alternative": a.get("outcome"),
                "changed": b.get("outcome") != a.get("outcome"),
            }
    return {
        "programme": programme.name,
        "statutory_reference": programme.statutory_reference,
        "deltas": deltas,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
