"""Filesystem-backed registry for RAC programmes.

Each ``rules.yaml`` under the scan root is a programme. Its identity is the
directory path relative to that root:
``programmes/uksi/2013/376/rules.yaml`` becomes ``uksi/2013/376``. Callers
ask for a subset by glob pattern over that identity
(``"ukpga/**"``, ``"uksi/2013/**"``) rather than enumerating individual files,
which keeps the taxonomy pinned to the filesystem layout — no separate tag
registry to drift.

``select()`` returns a new registry, so selections compose and the caller can
always introspect the chosen set with :meth:`ProgrammeRegistry.identities`.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable, Iterator

from pydantic import BaseModel, ConfigDict

from .loader import load_program
from .models import Program

RULES_FILE = "rules.yaml"


class ProgrammeEntry(BaseModel):
    """A single programme on disk, identified by its path relative to root."""

    model_config = ConfigDict(frozen=True)

    identity: str
    path: Path

    def load(self) -> Program:
        return load_program(self.path)


class ProgrammeRegistry:
    """Collection of programmes discovered under a filesystem root.

    Instances are immutable views over an ordered set of entries. Construct
    from a directory with :meth:`from_root`; narrow with :meth:`select`.
    """

    def __init__(
        self,
        entries: Iterable[ProgrammeEntry],
        root: Path | None = None,
    ) -> None:
        self._entries: dict[str, ProgrammeEntry] = {}
        for entry in entries:
            if entry.identity in self._entries:
                raise ValueError(f"duplicate programme identity `{entry.identity}`")
            self._entries[entry.identity] = entry
        self._root = root

    @classmethod
    def from_root(cls, root: str | Path) -> "ProgrammeRegistry":
        root_path = Path(root).resolve()
        if not root_path.exists():
            raise FileNotFoundError(f"programme root not found: {root_path}")
        if not root_path.is_dir():
            raise NotADirectoryError(f"programme root must be a directory: {root_path}")
        entries = [
            ProgrammeEntry(
                identity=program_path.parent.relative_to(root_path).as_posix(),
                path=program_path,
            )
            for program_path in sorted(root_path.rglob(RULES_FILE))
        ]
        return cls(entries, root=root_path)

    @property
    def root(self) -> Path | None:
        return self._root

    def identities(self) -> list[str]:
        return list(self._entries.keys())

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[ProgrammeEntry]:
        return iter(self._entries.values())

    def __contains__(self, identity: object) -> bool:
        return identity in self._entries

    def get(self, identity: str) -> ProgrammeEntry:
        if identity not in self._entries:
            raise KeyError(f"unknown programme identity `{identity}`")
        return self._entries[identity]

    def load(self, identity: str) -> Program:
        return self.get(identity).load()

    def select(self, *patterns: str) -> "ProgrammeRegistry":
        """Return a new registry of entries matching any of the given globs.

        Patterns are slash-separated glob expressions over the identity:
        ``*`` matches within a segment, ``**`` spans zero or more segments,
        ``?`` matches a single character. A pattern with no special
        characters and no slash separator is treated as a single-segment
        match — pass the full identity to pick one programme exactly.

        An empty pattern list returns an empty registry. Patterns that
        match nothing are not an error: the caller can inspect the result
        with :meth:`identities`.
        """
        if not patterns:
            return ProgrammeRegistry([], root=self._root)
        filtered = [
            entry
            for entry in self._entries.values()
            if any(_match(entry.identity, pattern) for pattern in patterns)
        ]
        return ProgrammeRegistry(filtered, root=self._root)


def _match(identity: str, pattern: str) -> bool:
    return _segments_match(identity.split("/"), pattern.split("/"))


def _segments_match(parts: list[str], pattern_parts: list[str]) -> bool:
    if not pattern_parts:
        return not parts
    head, *tail = pattern_parts
    if head == "**":
        for i in range(len(parts) + 1):
            if _segments_match(parts[i:], tail):
                return True
        return False
    if not parts:
        return False
    if not fnmatch.fnmatchcase(parts[0], head):
        return False
    return _segments_match(parts[1:], tail)
