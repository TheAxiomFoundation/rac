"""Cosilico AI Rules Engine.

RAC (Rules as Code) provides tools for encoding tax and benefit law
as executable code.

Example usage:
    from rac import RACRegistry, load_statute

    # Quick lookup
    var = load_statute("us:statute/26/21#child_and_dependent_care_credit")
    print(var.label)  # "Child and Dependent Care Credit"

    # Full registry for batch operations
    registry = RACRegistry()
    registry.load_jurisdiction("us", "/path/to/rac-us")

    for var in registry.list_variables("us:statute/26"):
        print(f"{var.ref}: {var.label}")
"""

__version__ = "0.1.0"

from .registry import (
    RACRegistry,
    RACFile,
    VariableInfo,
    ParameterInfo,
    InputInfo,
    load_statute,
)

from .dsl_parser import (
    Module,
    VariableDef,
    ParameterDef,
    InputDef,
    parse_dsl,
    parse_file,
)

__all__ = [
    # Registry
    "RACRegistry",
    "RACFile",
    "VariableInfo",
    "ParameterInfo",
    "InputInfo",
    "load_statute",
    # Parser
    "Module",
    "VariableDef",
    "ParameterDef",
    "InputDef",
    "parse_dsl",
    "parse_file",
]
