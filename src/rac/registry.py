"""RAC Registry - index and query RAC files.

Provides a clean API for loading RAC files and accessing variable/parameter metadata.

Example usage:
    from rac import RACRegistry

    # Load a jurisdiction's statutes
    registry = RACRegistry()
    registry.load_jurisdiction("us", "/path/to/rac-us")

    # Get variable metadata
    var = registry.get_variable("us:statute/26/21#child_and_dependent_care_credit")
    print(var.label)  # "Child and Dependent Care Credit"
    print(var.entity)  # "TaxUnit"

    # List all variables in a section
    for var in registry.list_variables("us:statute/26/21"):
        print(f"{var.name}: {var.label}")
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .dsl_parser import InputDef, Module, ParameterDef, VariableDef, parse_file
from .test_runner import load_test_file


@dataclass
class RACFile:
    """A parsed RAC file with its location info."""

    jurisdiction: str
    path: str  # Relative path within statute/ (e.g., "26/21")
    filepath: Path  # Absolute filesystem path
    module: Module

    @property
    def ref_prefix(self) -> str:
        """Reference prefix for this file (e.g., 'us:statute/26/21')."""
        return f"{self.jurisdiction}:statute/{self.path}"

    def variable_ref(self, name: str) -> str:
        """Full reference for a variable (e.g., 'us:statute/26/21#child_and_dependent_care_credit')."""
        return f"{self.ref_prefix}#{name}"


@dataclass
class VariableInfo:
    """Variable metadata with full reference info."""

    ref: str  # Full reference (e.g., 'us:statute/26/21#child_and_dependent_care_credit')
    name: str
    jurisdiction: str
    statute_path: str
    definition: VariableDef
    source_file: Path

    @property
    def label(self) -> str | None:
        return self.definition.label

    @property
    def description(self) -> str | None:
        return self.definition.description

    @property
    def entity(self) -> str:
        return self.definition.entity

    @property
    def period(self) -> str:
        return self.definition.period

    @property
    def dtype(self) -> str:
        return self.definition.dtype

    @property
    def unit(self) -> str | None:
        return self.definition.unit

    @property
    def imports(self) -> list[str]:
        return self.definition.imports


@dataclass
class ParameterInfo:
    """Parameter metadata with full reference info."""

    ref: str  # Full reference (e.g., 'us:statute/26/21/c#one_qualifying_limit')
    name: str
    jurisdiction: str
    statute_path: str
    definition: ParameterDef
    source_file: Path

    @property
    def description(self) -> str | None:
        return self.definition.description

    @property
    def unit(self) -> str | None:
        return self.definition.unit

    @property
    def values(self) -> dict[str, any]:
        return self.definition.values


@dataclass
class InputInfo:
    """Input metadata with full reference info."""

    ref: str
    name: str
    jurisdiction: str
    statute_path: str
    definition: InputDef
    source_file: Path

    @property
    def label(self) -> str | None:
        return self.definition.label

    @property
    def description(self) -> str | None:
        return self.definition.description

    @property
    def entity(self) -> str:
        return self.definition.entity

    @property
    def dtype(self) -> str:
        return self.definition.dtype


class RACRegistry:
    """Registry for loading and querying RAC files.

    Provides indexed access to variables, parameters, and inputs across
    multiple jurisdictions.
    """

    def __init__(self):
        self._files: dict[str, RACFile] = {}  # ref_prefix -> RACFile
        self._variables: dict[str, VariableInfo] = {}  # full_ref -> VariableInfo
        self._parameters: dict[str, ParameterInfo] = {}  # full_ref -> ParameterInfo
        self._inputs: dict[str, InputInfo] = {}  # full_ref -> InputInfo
        self._load_errors: list[tuple[Path, str]] = []  # (filepath, error_message)

    def load_jurisdiction(self, jurisdiction: str, base_path: str | Path) -> int:
        """Load all RAC files from a jurisdiction.

        Args:
            jurisdiction: Jurisdiction code (e.g., "us", "uk")
            base_path: Path to the rac-{jurisdiction} directory

        Returns:
            Number of files loaded
        """
        base = Path(base_path)
        statute_dir = base / "statute"

        if not statute_dir.exists():
            raise FileNotFoundError(f"No statute/ directory in {base_path}")

        count = 0
        errors = []
        for rac_file in statute_dir.rglob("*.rac"):
            rel_path = rac_file.relative_to(statute_dir)
            # Convert path to statute reference (e.g., "26/21/c.rac" -> "26/21/c")
            statute_path = str(rel_path.with_suffix(""))

            try:
                self._load_file(jurisdiction, statute_path, rac_file)
                count += 1
            except Exception as e:
                errors.append((rac_file, str(e)))

        if errors:
            self._load_errors = errors

        return count

    def load_file(self, jurisdiction: str, statute_path: str, filepath: str | Path) -> RACFile:
        """Load a single RAC file.

        Args:
            jurisdiction: Jurisdiction code (e.g., "us")
            statute_path: Path within statute/ (e.g., "26/21")
            filepath: Path to the .rac file

        Returns:
            The loaded RACFile
        """
        return self._load_file(jurisdiction, statute_path, Path(filepath))

    def _load_file(self, jurisdiction: str, statute_path: str, filepath: Path) -> RACFile:
        """Internal file loading."""
        module = parse_file(str(filepath))

        # Check for companion .rac.test file
        test_file = filepath.with_suffix(".rac.test")
        if test_file.exists():
            try:
                external_tests = load_test_file(test_file)
                for var_def in module.variables:
                    if var_def.name in external_tests:
                        var_def.tests.extend(external_tests[var_def.name])
            except Exception:
                pass  # Don't fail loading on test file parse errors

        rac_file = RACFile(
            jurisdiction=jurisdiction,
            path=statute_path,
            filepath=filepath,
            module=module,
        )

        self._files[rac_file.ref_prefix] = rac_file

        # Index variables
        for var_def in module.variables:
            ref = rac_file.variable_ref(var_def.name)
            self._variables[ref] = VariableInfo(
                ref=ref,
                name=var_def.name,
                jurisdiction=jurisdiction,
                statute_path=statute_path,
                definition=var_def,
                source_file=filepath,
            )

        # Index parameters
        for param_def in module.parameters:
            ref = f"{rac_file.ref_prefix}#{param_def.name}"
            self._parameters[ref] = ParameterInfo(
                ref=ref,
                name=param_def.name,
                jurisdiction=jurisdiction,
                statute_path=statute_path,
                definition=param_def,
                source_file=filepath,
            )

        # Index inputs
        for input_def in module.inputs:
            ref = f"{rac_file.ref_prefix}#{input_def.name}"
            self._inputs[ref] = InputInfo(
                ref=ref,
                name=input_def.name,
                jurisdiction=jurisdiction,
                statute_path=statute_path,
                definition=input_def,
                source_file=filepath,
            )

        return rac_file

    def get_variable(self, ref: str) -> VariableInfo | None:
        """Get a variable by its full reference.

        Args:
            ref: Full reference (e.g., 'us:statute/26/21#child_and_dependent_care_credit')

        Returns:
            VariableInfo or None if not found
        """
        return self._variables.get(ref)

    def get_parameter(self, ref: str) -> ParameterInfo | None:
        """Get a parameter by its full reference."""
        return self._parameters.get(ref)

    def get_input(self, ref: str) -> InputInfo | None:
        """Get an input by its full reference."""
        return self._inputs.get(ref)

    def list_variables(self, prefix: str | None = None) -> Iterator[VariableInfo]:
        """List all variables, optionally filtered by prefix.

        Args:
            prefix: Optional prefix to filter by (e.g., 'us:statute/26/21')

        Yields:
            VariableInfo objects
        """
        for ref, var in self._variables.items():
            if prefix is None or ref.startswith(prefix):
                yield var

    def list_parameters(self, prefix: str | None = None) -> Iterator[ParameterInfo]:
        """List all parameters, optionally filtered by prefix."""
        for ref, param in self._parameters.items():
            if prefix is None or ref.startswith(prefix):
                yield param

    def list_inputs(self, prefix: str | None = None) -> Iterator[InputInfo]:
        """List all inputs, optionally filtered by prefix."""
        for ref, inp in self._inputs.items():
            if prefix is None or ref.startswith(prefix):
                yield inp

    @property
    def variable_count(self) -> int:
        return len(self._variables)

    @property
    def parameter_count(self) -> int:
        return len(self._parameters)

    @property
    def input_count(self) -> int:
        return len(self._inputs)

    @property
    def file_count(self) -> int:
        return len(self._files)


# Convenience function for quick access
def load_statute(ref: str, rac_us_path: str | None = None) -> VariableInfo | None:
    """Load a single statute variable by reference.

    Args:
        ref: Full reference (e.g., 'us:statute/26/21#child_and_dependent_care_credit')
        rac_us_path: Path to rac-us directory (defaults to ~/RulesFoundation/rac-us)

    Returns:
        VariableInfo or None
    """
    # Parse reference
    if ":" not in ref or "#" not in ref:
        raise ValueError(
            f"Invalid reference format: {ref}. Expected 'jurisdiction:statute/path#variable'"
        )

    jurisdiction, rest = ref.split(":", 1)
    if not rest.startswith("statute/"):
        raise ValueError(f"Invalid reference format: {ref}. Expected 'statute/' prefix")

    path_and_var = rest[8:]  # Remove "statute/"
    if "#" not in path_and_var:
        raise ValueError(f"Invalid reference format: {ref}. Missing #variable")

    statute_path, var_name = path_and_var.rsplit("#", 1)

    # Determine base path
    if rac_us_path:
        base = Path(rac_us_path)
    else:
        base = Path.home() / "RulesFoundation" / f"rac-{jurisdiction}"

    # Find and parse the file
    rac_file = base / "statute" / f"{statute_path}.rac"
    if not rac_file.exists():
        # Try as directory with subsections
        rac_dir = base / "statute" / statute_path
        if rac_dir.is_dir():
            # Look in all files in this directory
            registry = RACRegistry()
            for f in rac_dir.rglob("*.rac"):
                rel = f.relative_to(base / "statute")
                registry.load_file(jurisdiction, str(rel.with_suffix("")), f)
            return registry.get_variable(ref)
        return None

    registry = RACRegistry()
    registry.load_file(jurisdiction, statute_path, rac_file)
    return registry.get_variable(ref)
