"""Programme loader with `extends:` composition and .rac lowering.

Mirrors the logic in `rac::spec::ProgramSpec::from_yaml_file`: an amending
file's top-level `extends: <relative path>` is resolved relative to the file
itself, the base is loaded recursively, and parameter versions are merged by
name (amendment versions are concatenated onto the base's versions; units,
relations, and derived outputs are additive).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .models import Program

ROOT = Path(__file__).resolve().parents[2]


def _merge_parameters(
    base: list[dict[str, Any]], amendment: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {p["name"]: dict(p) for p in base}
    for amend in amendment:
        name = amend["name"]
        if name in by_name:
            merged = by_name[name]
            merged_versions = list(merged.get("versions", []))
            merged_versions.extend(amend.get("versions", []))
            merged["versions"] = merged_versions
        else:
            by_name[name] = dict(amend)
    return list(by_name.values())


def _merge_additive(
    base: list[dict[str, Any]],
    amendment: list[dict[str, Any]],
    key: str,
    kind: str,
) -> list[dict[str, Any]]:
    seen = {item[key] for item in base}
    merged = list(base)
    for item in amendment:
        if item[key] in seen:
            raise ValueError(
                f"duplicate {kind} `{item[key]}` when merging extended programme"
            )
        merged.append(item)
    return merged


def _load_raw(path: Path) -> dict[str, Any]:
    spec: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    extends = spec.pop("extends", None)
    if extends is None:
        return spec
    base_path = (path.parent / extends).resolve()
    base = _load_raw(base_path)
    merged: dict[str, Any] = {
        "units": _merge_additive(
            base.get("units", []), spec.get("units", []), "name", "unit"
        ),
        "relations": _merge_additive(
            base.get("relations", []),
            spec.get("relations", []),
            "name",
            "relation",
        ),
        "parameters": _merge_parameters(
            base.get("parameters", []), spec.get("parameters", [])
        ),
        "derived": _merge_additive(
            base.get("derived", []), spec.get("derived", []), "name", "derived"
        ),
    }
    return merged


def _load_rac(path: Path, binary_path: str | Path | None = None) -> Program:
    binary = Path(binary_path) if binary_path is not None else ROOT / "target" / "debug" / "rac"
    with tempfile.TemporaryDirectory(prefix="rac-program-") as temp_dir:
        artifact_path = Path(temp_dir) / "program.compiled.json"
        process = subprocess.run(
            [
                str(binary),
                "compile",
                "--program",
                str(path),
                "--output",
                str(artifact_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            stderr = process.stderr.strip() or "rac compile failed"
            raise RuntimeError(stderr)
        artifact = json.loads(artifact_path.read_text())
        return Program.model_validate(artifact["program"])


def load_program(path: str | Path, *, binary_path: str | Path | None = None) -> Program:
    """Load a programme from .rac or YAML, resolving any YAML `extends:` chain."""
    path = Path(path)
    if path.suffix == ".rac":
        return _load_rac(path, binary_path=binary_path)
    spec = _load_raw(path)
    return Program.model_validate(spec)
