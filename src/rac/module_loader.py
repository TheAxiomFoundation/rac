"""Load .rac modules together with their local imports."""

from __future__ import annotations

from pathlib import Path

from . import ast
from .parser import parse

ROOT_TOKENS = ("legislation", "statute", "regulation")


def infer_repo_root(path: str | Path) -> Path:
    """Infer the RAC repo root from a file path."""
    resolved = Path(path).resolve()
    for parent in resolved.parents:
        if parent.name in ROOT_TOKENS:
            return parent.parent
    return resolved.parent


def resolve_import_path(import_path: str, repo_root: Path) -> Path | None:
    """Resolve a local import path to a file or directory under *repo_root*."""
    candidates = [import_path]
    if import_path == repo_root.name:
        candidates.append("")
    elif import_path.startswith(f"{repo_root.name}/"):
        candidates.append(import_path[len(repo_root.name) + 1 :])

    for normalized in candidates:
        direct_file = repo_root / f"{normalized}.rac"
        if direct_file.exists():
            return direct_file

        dir_path = repo_root / normalized
        if dir_path.is_dir():
            for candidate in [dir_path / "index.rac", dir_path.parent / f"{dir_path.name}.rac"]:
                if candidate.exists():
                    return candidate
            return dir_path

    return None


def load_modules_with_imports(
    *paths: str | Path,
    repo_root: str | Path | None = None,
) -> list[ast.Module]:
    """Load entry modules and all resolvable local imports in dependency order."""
    if not paths:
        return []

    root = Path(repo_root).resolve() if repo_root is not None else infer_repo_root(paths[0])
    seen: dict[Path, ast.Module] = {}
    ordered: list[Path] = []

    def visit(path: Path) -> None:
        resolved_path = path.resolve()
        if resolved_path in seen:
            return

        source = resolved_path.read_text()
        module = parse(source, str(resolved_path))
        seen[resolved_path] = module

        for import_decl in module.imports:
            if ":" in import_decl.path and not import_decl.path.startswith(("legislation/", "statute/", "regulation/")):
                continue
            target = resolve_import_path(import_decl.path, root)
            if target is None:
                continue
            if target.is_dir():
                for rac_file in sorted(target.rglob("*.rac")):
                    visit(rac_file)
            else:
                visit(target)

        ordered.append(resolved_path)

    for path in paths:
        visit(Path(path))

    return [seen[path] for path in ordered]
