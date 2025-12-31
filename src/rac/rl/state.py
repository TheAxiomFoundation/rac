"""Learning state and data structures for RL training."""

from dataclasses import dataclass, field


@dataclass
class TrajectoryExample:
    """A successful trajectory that can be used as a few-shot example."""

    provision: str
    statute_citation: str
    statute_text: str
    final_code: str
    accuracy: float
    iterations: int
    success_factors: list[str] = field(default_factory=list)


@dataclass
class FailurePattern:
    """A pattern that led to failure - something to avoid."""

    provision: str
    error_type: str  # "syntax", "logic", "parameter"
    description: str
    bad_code_snippet: str
    correction: str


@dataclass
class LearningState:
    """Accumulated learnings from RL iterations."""

    successful_examples: list[TrajectoryExample] = field(default_factory=list)
    failure_patterns: list[FailurePattern] = field(default_factory=list)
    iteration: int = 0
    total_provisions_attempted: int = 0
    total_successes: int = 0
    iteration_history: list[dict] = field(default_factory=list)

    # Cost tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    def success_rate(self) -> float:
        if self.total_provisions_attempted == 0:
            return 0.0
        return self.total_successes / self.total_provisions_attempted

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "total_provisions_attempted": self.total_provisions_attempted,
            "total_successes": self.total_successes,
            "success_rate": self.success_rate(),
            "n_examples": len(self.successful_examples),
            "n_failure_patterns": len(self.failure_patterns),
            "iteration_history": self.iteration_history,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
        }
