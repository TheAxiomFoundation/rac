from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


PROGRAMMES_DIR = Path(__file__).parent / "programmes"


class Programme(BaseModel):
    name: str
    title: str
    statutory_reference: str
    summary: str
    programme_path: str
    query_entity: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    rates_effective_from: str | None = None
    out_of_scope: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)


class Catalogue:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self._programmes: dict[str, Programme] = {}
        for manifest_path in sorted(PROGRAMMES_DIR.glob("*.yaml")):
            data = yaml.safe_load(manifest_path.read_text())
            programme = Programme.model_validate(data)
            self._programmes[programme.name] = programme

    def list(self) -> list[Programme]:
        return list(self._programmes.values())

    def get(self, name: str) -> Programme:
        if name not in self._programmes:
            known = ", ".join(sorted(self._programmes)) or "(none)"
            raise KeyError(f"unknown programme {name!r}; known: {known}")
        return self._programmes[name]

    def programme_yaml_path(self, name: str) -> Path:
        programme = self.get(name)
        return self.repo_root / programme.programme_path
