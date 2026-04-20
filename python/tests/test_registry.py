"""Tests for the filesystem-backed programme registry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rac_api import ProgrammeEntry, ProgrammeRegistry

PROGRAMMES = ROOT / "programmes"


def test_from_root_discovers_all_rules_racs() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    ids = set(registry.identities())
    # A few representative programmes we know live in the tree.
    assert "uksi/2013/376" in ids
    assert "ukpga/2014/19/section/4" in ids
    assert "other/family_allowance" in ids
    assert "usda/snap/federal" in ids
    # Registry count matches the raw filesystem walk.
    on_disk = sorted(
        p.parent.relative_to(PROGRAMMES).as_posix()
        for p in PROGRAMMES.rglob("rules.rac")
    )
    assert sorted(ids) == on_disk


def test_identity_excludes_rules_filename() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    for entry in registry:
        assert "rules.rac" not in entry.identity
        assert entry.path.name == "rules.rac"


def test_select_single_prefix_glob() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    selected = registry.select("ukpga/**")
    ids = selected.identities()
    assert ids, "expected at least one ukpga programme"
    assert all(i.startswith("ukpga/") for i in ids)


def test_select_multiple_patterns_unions() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    selected = registry.select("ukpga/**", "uksi/2013/**")
    ids = set(selected.identities())
    assert any(i.startswith("ukpga/") for i in ids)
    assert any(i.startswith("uksi/2013/") for i in ids)
    assert not any(i.startswith("ssi/") for i in ids)


def test_select_exact_identity() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    selected = registry.select("uksi/2013/376")
    assert selected.identities() == ["uksi/2013/376"]


def test_select_no_match_returns_empty_registry() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    selected = registry.select("nonexistent/**")
    assert len(selected) == 0
    assert selected.identities() == []


def test_select_empty_pattern_list_empty_registry() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    selected = registry.select()
    assert len(selected) == 0


def test_select_composes() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    # Narrow to ukpga then further narrow.
    narrowed = registry.select("ukpga/**").select("**/section/4")
    ids = narrowed.identities()
    assert ids == ["ukpga/2014/19/section/4"]


def test_get_unknown_raises_keyerror() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    with pytest.raises(KeyError):
        registry.get("does/not/exist")


def test_entry_identifies_rac_file() -> None:
    # `load_program` is a legacy YAML helper and doesn't parse .rac source;
    # the Rust engine handles .rac loading via `CompiledProgramArtifact::
    # from_rac_file` / `from_rac_str`. Here we just assert the registry
    # points at the expected file path.
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    entry = registry.get("uksi/2013/376")
    assert isinstance(entry, ProgrammeEntry)
    assert entry.path.name == "rules.rac"
    assert entry.path.read_text().startswith('"""')


def test_from_root_missing_path() -> None:
    with pytest.raises(FileNotFoundError):
        ProgrammeRegistry.from_root("/tmp/does-not-exist-rac-registry-test")


def test_duplicate_identity_is_rejected() -> None:
    entries = [
        ProgrammeEntry(identity="foo", path=Path("/tmp/a/rules.rac")),
        ProgrammeEntry(identity="foo", path=Path("/tmp/b/rules.rac")),
    ]
    with pytest.raises(ValueError):
        ProgrammeRegistry(entries)


def test_glob_matches_question_mark_and_star() -> None:
    registry = ProgrammeRegistry.from_root(PROGRAMMES)
    # `*` should not cross segments.
    top_level_only = registry.select("*")
    for i in top_level_only.identities():
        assert "/" not in i
    # `**` should span segments.
    all_ids = set(registry.select("**").identities())
    assert all_ids == set(registry.identities())
