"""Validation for jurisdiction-repo source registry files.

Source registries live under ``sources/`` and mirror the executable rule tree.
Their identity and default R2 object paths are derived from the repository name
and filepath, so registry YAML should only store metadata and expected hashes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

DEFAULT_BUCKET = "axiom-sources"
DEFAULT_ARTIFACTS = ("raw", "akn", "text")
HASH_KEYS = tuple(f"{artifact}_sha256" for artifact in DEFAULT_ARTIFACTS)
EDGE_KEYS = ("sets", "implements", "extends", "authority")
TAXONOMY_ROOTS = ("statute", "regulation", "policy")

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class SourceArtifact:
    name: str
    sha256: str
    r2_path: str
    media_type: str | None = None


@dataclass(frozen=True)
class SourceRegistryEntry:
    path: Path
    repo: str
    source_path: str
    source_id: str
    artifacts: tuple[SourceArtifact, ...]


@dataclass(frozen=True)
class SourceRegistryIssue:
    path: Path
    message: str


@dataclass(frozen=True)
class SourceRegistryReport:
    entries: tuple[SourceRegistryEntry, ...]
    issues: tuple[SourceRegistryIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def discover_source_files(root: str | Path) -> list[Path]:
    """Return all source-registry YAML files under ``root/sources``."""

    root_path = Path(root)
    sources_root = root_path / "sources"
    if not sources_root.exists():
        return []
    files = [*sources_root.rglob("*.yaml"), *sources_root.rglob("*.yml")]
    return sorted(path for path in files if path.is_file())


def source_path_for(root: str | Path, source_file: str | Path) -> str:
    """Derive the source identity path from a source-registry filepath."""

    root_path = Path(root).resolve()
    source_path = Path(source_file).resolve()
    relative = source_path.relative_to(root_path / "sources")
    return relative.with_suffix("").as_posix()


def source_id_for(root: str | Path, source_file: str | Path, repo: str | None = None) -> str:
    repo_name = repo or Path(root).resolve().name
    return f"{repo_name}:{source_path_for(root, source_file)}"


def default_r2_path(
    *,
    repo: str,
    source_path: str,
    artifact: str,
    bucket: str = DEFAULT_BUCKET,
) -> str:
    return f"r2://{bucket}/{repo}/{source_path}/{artifact}"


def validate_source_registries(
    root: str | Path,
    *,
    repo: str | None = None,
    bucket: str = DEFAULT_BUCKET,
) -> SourceRegistryReport:
    """Validate every source-registry YAML file under a jurisdiction repo root."""

    root_path = Path(root).resolve()
    repo_name = repo or root_path.name
    issues: list[SourceRegistryIssue] = []
    entries: list[SourceRegistryEntry] = []

    if not root_path.exists():
        return SourceRegistryReport(
            (),
            (SourceRegistryIssue(root_path, "jurisdiction repository root not found"),),
        )
    if not root_path.is_dir():
        return SourceRegistryReport(
            (),
            (SourceRegistryIssue(root_path, "jurisdiction repository root must be a directory"),),
        )

    if not _REPO_RE.fullmatch(repo_name):
        issues.append(
            SourceRegistryIssue(
                root_path,
                f"repo name `{repo_name}` must match {_REPO_RE.pattern}",
            )
        )

    for path in discover_source_files(root_path):
        entry, file_issues = validate_source_registry_file(
            root_path,
            path,
            repo=repo_name,
            bucket=bucket,
        )
        issues.extend(file_issues)
        if entry is not None:
            entries.append(entry)

    return SourceRegistryReport(tuple(entries), tuple(issues))


def validate_source_registry_file(
    root: str | Path,
    path: str | Path,
    *,
    repo: str,
    bucket: str = DEFAULT_BUCKET,
) -> tuple[SourceRegistryEntry | None, list[SourceRegistryIssue]]:
    root_path = Path(root).resolve()
    source_file = Path(path).resolve()
    issues: list[SourceRegistryIssue] = []

    try:
        source_path = source_path_for(root_path, source_file)
    except ValueError:
        return (
            None,
            [
                SourceRegistryIssue(
                    source_file,
                    f"source registry file must live under {root_path / 'sources'}",
                )
            ],
        )

    first_segment = source_path.split("/", 1)[0]
    if first_segment not in TAXONOMY_ROOTS:
        issues.append(
            SourceRegistryIssue(
                source_file,
                "source path must start with one of "
                f"{', '.join(TAXONOMY_ROOTS)}; got `{first_segment}`",
            )
        )

    try:
        document = yaml.safe_load(source_file.read_text())
    except yaml.YAMLError as error:
        return (None, [SourceRegistryIssue(source_file, f"YAML parse error: {error}")])

    if document is None:
        document = {}
    if not isinstance(document, dict):
        return (
            None,
            [SourceRegistryIssue(source_file, "source registry YAML must be a mapping")],
        )

    _validate_required_metadata(source_file, document, issues)
    _validate_forbidden_storage(source_file, document, issues)
    _validate_edges(source_file, document, issues)

    if "id" in document:
        issues.append(
            SourceRegistryIssue(
                source_file,
                "`id:` is redundant; source identity is derived from the filepath",
            )
        )
    if "storage" in document:
        issues.append(
            SourceRegistryIssue(
                source_file,
                "`storage:` is redundant at top level; R2 paths are derived from the filepath",
            )
        )

    artifacts = _validate_artifacts(
        source_file,
        document,
        repo=repo,
        source_path=source_path,
        bucket=bucket,
        issues=issues,
    )

    return (
        SourceRegistryEntry(
            path=source_file,
            repo=repo,
            source_path=source_path,
            source_id=f"{repo}:{source_path}",
            artifacts=tuple(artifacts),
        ),
        issues,
    )


def _validate_required_metadata(
    path: Path,
    document: dict[str, Any],
    issues: list[SourceRegistryIssue],
) -> None:
    for field in ("publisher", "canonical_url", "retrieved_at"):
        value = document.get(field)
        if value is None or str(value).strip() == "":
            issues.append(SourceRegistryIssue(path, f"`{field}:` is required"))


def _validate_forbidden_storage(
    path: Path,
    value: Any,
    issues: list[SourceRegistryIssue],
    key_path: tuple[str, ...] = (),
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            next_path = (*key_path, str(key))
            if key == "storage" and key_path and key_path[0] != "artifacts":
                issues.append(
                    SourceRegistryIssue(
                        path,
                        "`storage:` is only allowed inside explicit `artifacts:` overrides",
                    )
                )
            _validate_forbidden_storage(path, child, issues, next_path)
    elif isinstance(value, list):
        for child in value:
            _validate_forbidden_storage(path, child, issues, key_path)


def _validate_edges(
    path: Path,
    document: dict[str, Any],
    issues: list[SourceRegistryIssue],
) -> None:
    for key in EDGE_KEYS:
        if key not in document:
            continue
        for target in _edge_targets(document[key]):
            if not _is_absolute_canonical_path(target):
                issues.append(
                    SourceRegistryIssue(
                        path,
                        f"`{key}:` target `{target}` must be an absolute canonical path "
                        "like `us:statute/7/2014/e/6/A`",
                    )
                )


def _edge_targets(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item
            else:
                yield repr(item)
    else:
        yield repr(value)


def _is_absolute_canonical_path(value: str) -> bool:
    if "://" in value or value.endswith((".yaml", ".yml")):
        return False
    if ":" not in value:
        return False
    repo, path = value.split(":", 1)
    if not _REPO_RE.fullmatch(repo):
        return False
    return any(path.startswith(f"{root}/") for root in TAXONOMY_ROOTS)


def _validate_artifacts(
    path: Path,
    document: dict[str, Any],
    *,
    repo: str,
    source_path: str,
    bucket: str,
    issues: list[SourceRegistryIssue],
) -> list[SourceArtifact]:
    if "artifacts" in document:
        if "hashes" in document:
            issues.append(
                SourceRegistryIssue(
                    path,
                    "use either default `hashes:` or explicit `artifacts:`, not both",
                )
            )
        return _validate_explicit_artifacts(
            path,
            document.get("artifacts"),
            repo=repo,
            source_path=source_path,
            bucket=bucket,
            issues=issues,
        )
    return _validate_default_hashes(
        path,
        document.get("hashes"),
        repo=repo,
        source_path=source_path,
        bucket=bucket,
        issues=issues,
    )


def _validate_default_hashes(
    path: Path,
    hashes: Any,
    *,
    repo: str,
    source_path: str,
    bucket: str,
    issues: list[SourceRegistryIssue],
) -> list[SourceArtifact]:
    artifacts: list[SourceArtifact] = []
    if not isinstance(hashes, dict):
        issues.append(
            SourceRegistryIssue(
                path,
                "`hashes:` mapping with raw_sha256, akn_sha256, and text_sha256 is required",
            )
        )
        return artifacts

    for artifact, key in zip(DEFAULT_ARTIFACTS, HASH_KEYS, strict=True):
        sha = hashes.get(key)
        if not _is_sha256(sha):
            issues.append(
                SourceRegistryIssue(path, f"`hashes.{key}` must be a SHA-256 hex digest")
            )
            continue
        artifacts.append(
            SourceArtifact(
                name=artifact,
                sha256=str(sha),
                r2_path=default_r2_path(
                    repo=repo,
                    source_path=source_path,
                    artifact=artifact,
                    bucket=bucket,
                ),
            )
        )
    return artifacts


def _validate_explicit_artifacts(
    path: Path,
    artifacts: Any,
    *,
    repo: str,
    source_path: str,
    bucket: str,
    issues: list[SourceRegistryIssue],
) -> list[SourceArtifact]:
    parsed: list[SourceArtifact] = []
    if not isinstance(artifacts, dict) or not artifacts:
        issues.append(SourceRegistryIssue(path, "`artifacts:` must be a non-empty mapping"))
        return parsed

    for name, spec in artifacts.items():
        artifact_name = str(name)
        if not _ARTIFACT_NAME_RE.fullmatch(artifact_name):
            issues.append(
                SourceRegistryIssue(
                    path,
                    f"`artifacts.{artifact_name}` must use a simple artifact name",
                )
            )
        if not isinstance(spec, dict):
            issues.append(
                SourceRegistryIssue(path, f"`artifacts.{artifact_name}` must be a mapping")
            )
            continue
        sha = spec.get("sha256")
        if not _is_sha256(sha):
            issues.append(
                SourceRegistryIssue(
                    path,
                    f"`artifacts.{artifact_name}.sha256` must be a SHA-256 hex digest",
                )
            )
            continue
        path_override = spec.get("path", spec.get("storage", artifact_name))
        if not isinstance(path_override, str) or not path_override.strip():
            issues.append(
                SourceRegistryIssue(
                    path,
                    f"`artifacts.{artifact_name}.path` must be a non-empty relative path",
                )
            )
            continue
        if path_override.startswith("/") or ".." in Path(path_override).parts:
            issues.append(
                SourceRegistryIssue(
                    path,
                    f"`artifacts.{artifact_name}.path` must stay within the source identity path",
                )
            )
            continue
        r2_path = (
            path_override
            if path_override.startswith("r2://")
            else default_r2_path(
                repo=repo,
                source_path=source_path,
                artifact=path_override,
                bucket=bucket,
            )
        )
        parsed.append(
            SourceArtifact(
                name=artifact_name,
                sha256=str(sha),
                r2_path=r2_path,
                media_type=_optional_string(spec.get("media_type")),
            )
        )
    return parsed


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
