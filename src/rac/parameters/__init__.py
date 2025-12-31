"""Parameter management for Cosilico DSL.

Parameters are stored in YAML files organized by statute location:
  rules/us/federal/irs/credits/eitc/parameters.yaml

And referenced in DSL code by path:
  parameter(gov.irs.eitc.phase_in_rate[n_children])
"""

from .loader import ParameterLoader, load_parameters
from .schema import ParameterDefinition, ParameterValue

__all__ = [
    "ParameterLoader",
    "load_parameters",
    "ParameterDefinition",
    "ParameterValue",
]
