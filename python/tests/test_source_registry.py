from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from axiom_rules.cli import main
from axiom_rules.source_registry import (
    default_r2_path,
    discover_source_files,
    source_id_for,
    source_path_for,
    validate_source_registries,
)

SHA_RAW = "a" * 64
SHA_AKN = "b" * 64
SHA_TEXT = "c" * 64


def write_source(root: Path, relative: str, body: str) -> Path:
    path = root / "sources" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def valid_default_body(extra: str = "") -> str:
    return f"""
publisher: Tennessee DHS
canonical_url: https://example.test/manual
retrieved_at: 2026-04-25T00:00:00Z
hashes:
  raw_sha256: {SHA_RAW}
  akn_sha256: {SHA_AKN}
  text_sha256: {SHA_TEXT}
{extra}
"""


def test_derives_source_identity_and_default_r2_paths(tmp_path: Path) -> None:
    root = tmp_path / "us-tn"
    source = write_source(
        root,
        "policy/dhs/snap/manual/23/L.yaml",
        valid_default_body(),
    )

    report = validate_source_registries(root)

    assert report.ok
    assert discover_source_files(root) == [source]
    assert source_path_for(root, source) == "policy/dhs/snap/manual/23/L"
    assert source_id_for(root, source) == "us-tn:policy/dhs/snap/manual/23/L"
    entry = report.entries[0]
    assert entry.source_id == "us-tn:policy/dhs/snap/manual/23/L"
    assert [artifact.name for artifact in entry.artifacts] == ["raw", "akn", "text"]
    assert [artifact.r2_path for artifact in entry.artifacts] == [
        "r2://axiom-sources/us-tn/policy/dhs/snap/manual/23/L/raw",
        "r2://axiom-sources/us-tn/policy/dhs/snap/manual/23/L/akn",
        "r2://axiom-sources/us-tn/policy/dhs/snap/manual/23/L/text",
    ]


def test_repo_and_bucket_can_be_overridden(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    source = write_source(root, "regulation/7-cfr/273/9.yaml", valid_default_body())

    report = validate_source_registries(root, repo="us", bucket="test-bucket")

    assert report.ok
    assert source_id_for(root, source, repo="us") == "us:regulation/7-cfr/273/9"
    assert report.entries[0].artifacts[0].r2_path == (
        "r2://test-bucket/us/regulation/7-cfr/273/9/raw"
    )
    assert default_r2_path(
        repo="us",
        source_path="regulation/7-cfr/273/9",
        artifact="raw",
        bucket="test-bucket",
    ) == "r2://test-bucket/us/regulation/7-cfr/273/9/raw"


def test_explicit_artifacts_replace_default_hashes(tmp_path: Path) -> None:
    root = tmp_path / "us-tn"
    write_source(
        root,
        "policy/dhs/snap/manual/23/L.yaml",
        f"""
publisher: Tennessee DHS
canonical_url: https://example.test/manual
retrieved_at: 2026-04-25T00:00:00Z
artifacts:
  raw:
    path: manual.pdf
    sha256: {SHA_RAW}
    media_type: application/pdf
  akn:
    storage: akn.xml
    sha256: {SHA_AKN}
    media_type: application/akn+xml
""",
    )

    report = validate_source_registries(root)

    assert report.ok
    assert [artifact.r2_path for artifact in report.entries[0].artifacts] == [
        "r2://axiom-sources/us-tn/policy/dhs/snap/manual/23/L/manual.pdf",
        "r2://axiom-sources/us-tn/policy/dhs/snap/manual/23/L/akn.xml",
    ]


def test_rejects_redundant_identity_storage_bad_hash_and_relative_edges(
    tmp_path: Path,
) -> None:
    root = tmp_path / "us-tn"
    write_source(
        root,
        "policy/dhs/snap/manual/23/L.yaml",
        """
id: us-tn:policy/dhs/snap/manual/23/L
publisher: Tennessee DHS
canonical_url: https://example.test/manual
retrieved_at: 2026-04-25T00:00:00Z
storage: r2://axiom-sources/us-tn/policy/dhs/snap/manual/23/L
sets:
  - statute/7/2014/e/6/A
hashes:
  raw_sha256: not-a-hash
  akn_sha256: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
""",
    )

    report = validate_source_registries(root)
    messages = [issue.message for issue in report.issues]

    assert not report.ok
    assert any("`id:` is redundant" in message for message in messages)
    assert any("`storage:` is redundant at top level" in message for message in messages)
    assert any("`sets:` target" in message for message in messages)
    assert any("hashes.raw_sha256" in message for message in messages)
    assert any("hashes.text_sha256" in message for message in messages)


def test_rejects_source_paths_outside_taxonomy(tmp_path: Path) -> None:
    root = tmp_path / "us"
    write_source(root, "other/manual.yaml", valid_default_body())

    report = validate_source_registries(root)

    assert not report.ok
    assert any("source path must start with" in issue.message for issue in report.issues)


def test_rejects_hashes_and_artifacts_together(tmp_path: Path) -> None:
    root = tmp_path / "us"
    write_source(
        root,
        "statute/7/2014/e/6/A.yaml",
        valid_default_body(
            extra=f"""
artifacts:
  raw:
    path: raw.pdf
    sha256: {SHA_RAW}
"""
        ),
    )

    report = validate_source_registries(root)

    assert not report.ok
    assert any("use either default `hashes:`" in issue.message for issue in report.issues)


def test_missing_root_is_an_error(tmp_path: Path) -> None:
    report = validate_source_registries(tmp_path / "missing")

    assert not report.ok
    assert report.issues[0].message == "jurisdiction repository root not found"


def test_cli_check_sources_reports_failures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "us"
    write_source(
        root,
        "statute/7/2014/e/6/A.yaml",
        """
publisher: USDA
canonical_url: https://example.test/statute
retrieved_at: 2026-04-25T00:00:00Z
hashes:
  raw_sha256: bad
""",
    )

    rc = main(["check-sources", str(root)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "[FAIL]" in captured.out
    assert "Source registry check failed" in captured.out


def test_cli_check_sources_verbose_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "us"
    write_source(root, "statute/7/2014/e/6/A.yaml", valid_default_body())

    rc = main(["check-sources", str(root), "--verbose"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "us:statute/7/2014/e/6/A" in captured.out
    assert "Validated 1 source registry file" in captured.out
