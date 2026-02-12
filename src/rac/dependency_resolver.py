"""Dependency resolver for cross-file statute references.

Resolves references between .rac files, builds a dependency graph,
and provides execution order via topological sort.

Example:
    resolver = DependencyResolver(statute_root=Path("rac-us"))
    modules = resolver.resolve_all("statute/26/32/a/1/earned_income_credit")
    # modules is ordered: dependencies before dependents
"""

from dataclasses import dataclass, field
from pathlib import Path

from .dsl_parser import Module, parse_file


class ModuleNotFoundError(Exception):
    """Raised when a referenced module cannot be found."""

    pass


class CircularDependencyError(Exception):
    """Raised when circular dependencies are detected."""

    pass


class PackageNotFoundError(Exception):
    """Raised when a referenced package cannot be found in the registry."""

    pass


class PackageRegistry:
    """Registry mapping package names to their root directories.

    Enables cross-package imports like:
        rac-us:statute/26/62/a#adjusted_gross_income

    Example:
        registry = PackageRegistry.from_workspace(Path("/Users/me/RulesFoundation"))
        registry.set_default("rac-us-ca")

        resolver = DependencyResolver(registry=registry)
        modules = resolver.resolve_all("statute/ca/rtc/17041/tax")
    """

    def __init__(self, default: str | None = None):
        """Initialize registry with optional default package.

        Args:
            default: Default package name for unqualified imports
        """
        self._packages: dict[str, Path] = {}
        self._default = default

    def register(self, name: str, root: Path) -> None:
        """Register a package with its root directory.

        Args:
            name: Package name (e.g., "rac-us")
            root: Root directory path for the package
        """
        self._packages[name] = root

    def get_root(self, name: str | None) -> Path:
        """Get the root directory for a package.

        Args:
            name: Package name, or None to get default

        Returns:
            Root directory path

        Raises:
            PackageNotFoundError: If package not registered
        """
        if name is None:
            name = self._default
            if name is None:
                raise PackageNotFoundError("No default package set")

        if name not in self._packages:
            raise PackageNotFoundError(f"Package not found: {name}")

        return self._packages[name]

    def set_default(self, name: str) -> None:
        """Set the default package for unqualified imports.

        Args:
            name: Package name to use as default
        """
        self._default = name

    @classmethod
    def from_workspace(cls, workspace: Path) -> "PackageRegistry":
        """Create registry from workspace directory containing sibling repos.

        Scans for directories matching "rac-*" pattern.

        Args:
            workspace: Parent directory containing rac repos

        Returns:
            Registry with all found packages registered
        """
        registry = cls()

        for path in workspace.iterdir():
            if path.is_dir() and path.name.startswith("rac-"):
                registry.register(path.name, path)

        return registry


def extract_dependencies(module: Module) -> list[tuple[str | None, str]]:
    """Extract dependency paths from a module's references and variable imports.

    Args:
        module: Parsed DSL module

    Returns:
        List of (package, file_path) tuples for all dependencies
    """
    deps: list[tuple[str | None, str]] = []

    # From module-level imports block
    if module.imports:
        for ref in module.imports.references:
            deps.append((ref.package, ref.file_path or ref.statute_path))

    # From variable-level imports
    for var in module.variables:
        if var.imports:
            for imp in var.imports:
                # imp is a VariableImport with package, file_path
                deps.append((imp.package, imp.file_path))

    return deps


@dataclass
class DependencyGraph:
    """Directed acyclic graph of module dependencies.

    Supports:
    - Adding modules with their dependencies
    - Querying dependencies
    - Topological sorting for execution order
    - Circular dependency detection
    """

    _adjacency: dict[str, list[str]] = field(default_factory=dict)

    def add_module(self, name: str, dependencies: list[str]) -> None:
        """Add a module and its dependencies to the graph.

        Args:
            name: Module identifier (usually statute path)
            dependencies: List of modules this one depends on
        """
        self._adjacency[name] = dependencies
        # Ensure all dependencies are in the graph
        for dep in dependencies:
            if dep not in self._adjacency:
                self._adjacency[dep] = []

    def get_dependencies(self, name: str) -> list[str]:
        """Get direct dependencies of a module.

        Args:
            name: Module identifier

        Returns:
            List of dependency module names
        """
        return self._adjacency.get(name, [])

    def topological_sort(self) -> list[str]:
        """Return modules in topological order (dependencies first).

        Returns:
            List of module names, ordered so dependencies come before dependents

        Raises:
            CircularDependencyError: If circular dependencies exist
        """
        # Kahn's algorithm
        # Calculate in-degrees
        in_degree = {node: 0 for node in self._adjacency}
        for node, deps in self._adjacency.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[node] += 0  # node depends on dep, not the reverse
                # Actually we need reverse: if A depends on B, B must come first
                # So we need to track who depends on each node

        # Rebuild: for each node, who depends on it?
        dependents = {node: [] for node in self._adjacency}
        for node, deps in self._adjacency.items():
            for dep in deps:
                if dep in dependents:
                    dependents[dep].append(node)

        # Recalculate in-degrees (number of unprocessed dependencies)
        in_degree = {node: len(self._adjacency.get(node, [])) for node in self._adjacency}

        # Start with nodes that have no dependencies
        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            # For each node that depends on this one, decrement its in-degree
            for dependent in dependents.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(self._adjacency):
            # Not all nodes processed = cycle exists
            remaining = set(self._adjacency.keys()) - set(result)
            raise CircularDependencyError(f"Circular dependency detected involving: {remaining}")

        return result


class ModuleResolver:
    """Resolves statute reference paths to filesystem paths."""

    def __init__(self, statute_root: Path):
        """Initialize resolver with statute root directory.

        Args:
            statute_root: Root directory for statute files (e.g., rac-us)
        """
        self.statute_root = statute_root

    def resolve(self, statute_path: str) -> Path:
        """Resolve a statute path to a filesystem path.

        Args:
            statute_path: Path like "26/32/c/2/A" or "statute/26/32/c/2/A"

        Returns:
            Absolute path to the .rac file

        Raises:
            ModuleNotFoundError: If file doesn't exist
        """
        # Try paths in order of preference
        paths_to_try = [statute_path]

        # If path doesn't start with "statute/", also try with that prefix
        # This handles imports like "26/32/c/2/A" -> "statute/26/32/c/2/A"
        if not statute_path.startswith("statute/"):
            paths_to_try.append(f"statute/{statute_path}")

        for clean_path in paths_to_try:
            # Try with .rac extension
            file_path = self.statute_root / f"{clean_path}.rac"
            if file_path.exists():
                return file_path

            # Try as directory with same-named file inside
            dir_path = self.statute_root / clean_path
            if dir_path.is_dir():
                # Look for a .rac file with the last component name
                name = Path(clean_path).name
                candidate = dir_path / f"{name}.rac"
                if candidate.exists():
                    return candidate

        raise ModuleNotFoundError(f"Cannot resolve '{statute_path}' from {self.statute_root}")


@dataclass
class ResolvedModule:
    """A parsed module with its path and dependencies resolved."""

    path: str
    file_path: Path
    module: Module
    dependencies: list[str]


class DependencyResolver:
    """Full dependency resolver: finds, parses, and orders modules.

    Supports both single-root (statute_root) and multi-root (registry) modes.
    """

    def __init__(self, statute_root: Path | None = None, registry: PackageRegistry | None = None):
        """Initialize with statute root or package registry.

        Args:
            statute_root: Root directory for statute files (single-package mode)
            registry: Package registry for multi-package resolution
        """
        if registry is not None:
            self.registry = registry
            self.module_resolver = None  # Use registry instead
        elif statute_root is not None:
            self.registry = None
            self.module_resolver = ModuleResolver(statute_root)
        else:
            raise ValueError("Must provide either statute_root or registry")

        self._cache: dict[str, ResolvedModule] = {}

    def resolve_all(self, entry_point: str) -> list[ResolvedModule]:
        """Resolve entry point and all its dependencies recursively.

        Args:
            entry_point: Starting statute path

        Returns:
            List of ResolvedModule in execution order (dependencies first)
        """
        # Clear cache for fresh resolution
        self._cache.clear()

        # Recursively load all modules (entry point uses default package)
        self._load_recursive(entry_point, package=None)

        # Build dependency graph
        graph = DependencyGraph()
        for path, resolved in self._cache.items():
            graph.add_module(path, resolved.dependencies)

        # Get execution order
        order = graph.topological_sort()

        # Return modules in order
        return [self._cache[path] for path in order if path in self._cache]

    def _resolve_file(self, package: str | None, file_path: str) -> Path:
        """Resolve a file path to filesystem path using registry or single root.

        Args:
            package: Package name (None for local/default package)
            file_path: Path within the package

        Returns:
            Absolute filesystem path to the .rac file
        """
        if self.registry is not None:
            # Multi-package mode: use registry
            root = self.registry.get_root(package)
            resolver = ModuleResolver(root)
            return resolver.resolve(file_path)
        else:
            # Single-package mode: use module_resolver
            if package is not None:
                raise ModuleNotFoundError(
                    f"Cross-package import to '{package}' not supported in single-root mode"
                )
            return self.module_resolver.resolve(file_path)

    def _make_cache_key(self, package: str | None, file_path: str) -> str:
        """Create a unique cache key for a module.

        Args:
            package: Package name (None for default)
            file_path: Path within the package

        Returns:
            Cache key string
        """
        if package:
            return f"{package}:{file_path}"
        return file_path

    def _load_recursive(self, file_path: str, package: str | None = None) -> None:
        """Load a module and its dependencies recursively.

        Args:
            file_path: File path within package
            package: Package name (None for default)
        """
        cache_key = self._make_cache_key(package, file_path)

        if cache_key in self._cache:
            return

        # Resolve and parse
        try:
            resolved_path = self._resolve_file(package, file_path)
        except (ModuleNotFoundError, PackageNotFoundError):
            # Module not found - might be a primitive input
            # Create a placeholder
            self._cache[cache_key] = ResolvedModule(
                path=cache_key, file_path=Path(), module=None, dependencies=[]
            )
            return

        # Try to parse, but handle errors gracefully
        try:
            module = parse_file(str(resolved_path))
            deps = extract_dependencies(module)
        except SyntaxError as e:
            # Parse error - treat as placeholder with warning
            import warnings

            warnings.warn(f"Parse error in {cache_key}: {e}")
            self._cache[cache_key] = ResolvedModule(
                path=cache_key, file_path=resolved_path, module=None, dependencies=[]
            )
            return

        # Convert deps to cache keys for dependency graph
        dep_keys = [self._make_cache_key(pkg, path) for pkg, path in deps]

        # Cache this module
        self._cache[cache_key] = ResolvedModule(
            path=cache_key, file_path=resolved_path, module=module, dependencies=dep_keys
        )

        # Recursively load dependencies
        for dep_pkg, dep_path in deps:
            self._load_recursive(dep_path, dep_pkg)
