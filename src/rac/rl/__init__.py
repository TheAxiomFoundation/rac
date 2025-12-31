"""RL Training for Cosilico DSL Generation.

This package implements an outer RL loop that learns from trajectories
to improve the system prompt for future runs.
"""

# Import reward functions (no heavy dependencies)
from .reward import (
    EncodingRewardFunction,
    StructuralRewardFunction,
    CombinedRewardFunction,
    Oracle,
    PolicyEngineOracle,
    TaxsimOracle,
    IRSTableOracle,
    RewardResult,
)

from .state import LearningState, TrajectoryExample, FailurePattern

# Lazy imports for components that need anthropic
def __getattr__(name):
    if name == "RLTrainer":
        from .trainer import RLTrainer
        return RLTrainer
    elif name == "run_rl_experiment":
        from .trainer import run_rl_experiment
        return run_rl_experiment
    elif name == "PromptEvolver":
        from .prompt_evolver import PromptEvolver
        return PromptEvolver
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "RLTrainer",
    "run_rl_experiment",
    "LearningState",
    "TrajectoryExample",
    "FailurePattern",
    "PromptEvolver",
    "EncodingRewardFunction",
    "StructuralRewardFunction",
    "CombinedRewardFunction",
    "Oracle",
    "PolicyEngineOracle",
    "TaxsimOracle",
    "IRSTableOracle",
    "RewardResult",
]
