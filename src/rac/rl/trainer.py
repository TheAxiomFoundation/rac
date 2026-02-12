"""Main RL training loop for DSL generation."""

import json
import os
from datetime import datetime
from typing import Any

from ..dsl_agent import DSLAgentTrainingLoop
from ..dsl_experiment import STATUTES, TEST_GENERATORS
from .prompt_evolver import PromptEvolver
from .state import LearningState


class RLTrainer:
    """Main RL training loop for DSL generation.

    Implements the outer loop that:
    1. Runs the agent on multiple provisions
    2. Analyzes trajectories to extract successful patterns
    3. Updates the system prompt with learned examples
    4. Iterates to improve overall performance
    """

    def __init__(
        self,
        model: str = "claude-opus-4-5-20251101",
        max_iterations_per_provision: int = 5,
        target_accuracy: float = 0.95,
        output_dir: str = "paper/data/rl_runs",
    ):
        self.model = model
        self.max_iterations_per_provision = max_iterations_per_provision
        self.target_accuracy = target_accuracy
        self.output_dir = output_dir

        self.prompt_evolver = PromptEvolver()
        self.state = LearningState()

        os.makedirs(output_dir, exist_ok=True)

    def train(
        self,
        provisions: list[str] | None = None,
        n_outer_iterations: int = 3,
        verbose: bool = True,
    ) -> LearningState:
        """Run the full RL training loop.

        Args:
            provisions: List of provision keys to train on
            n_outer_iterations: Number of outer loop iterations
            verbose: Print progress

        Returns:
            Final learning state with accumulated examples
        """
        if provisions is None:
            provisions = list(STATUTES.keys())

        for outer_iter in range(n_outer_iterations):
            self.state.iteration = outer_iter + 1

            if verbose:
                print(f"\n{'=' * 60}")
                print(f"RL OUTER ITERATION {outer_iter + 1}/{n_outer_iterations}")
                print(f"{'=' * 60}")
                print(f"Accumulated examples: {len(self.state.successful_examples)}")
                print(f"Current success rate: {self.state.success_rate():.1%}")

            # Build evolved prompt with learnings
            evolved_prompt = self.prompt_evolver.build_prompt(self.state)

            if verbose and outer_iter > 0:
                print(f"Prompt evolved with {len(self.state.successful_examples)} examples")

            # Run on all provisions
            iteration_results = {
                "iteration": outer_iter + 1,
                "provisions": {},
                "successes": 0,
                "total": len(provisions),
            }

            for provision in provisions:
                if provision not in STATUTES:
                    continue

                if verbose:
                    print(f"\n--- {provision} ---")

                result = self._run_provision(
                    provision,
                    evolved_prompt,
                    verbose=verbose,
                )

                cost = result.get("cost", {})
                iteration_results["provisions"][provision] = {
                    "success": result["success"],
                    "accuracy": result["accuracy"],
                    "iterations": result["iterations"],
                    "cost_usd": cost.get("total_cost_usd", 0),
                }

                if result["success"]:
                    iteration_results["successes"] += 1

                self.state.total_provisions_attempted += 1
                if result["success"]:
                    self.state.total_successes += 1

                # Track costs
                self.state.total_input_tokens += cost.get("input_tokens", 0)
                self.state.total_output_tokens += cost.get("output_tokens", 0)
                self.state.total_cost_usd += cost.get("total_cost_usd", 0)

            # Record iteration results
            iteration_results["success_rate"] = (
                iteration_results["successes"] / iteration_results["total"]
            )
            self.state.iteration_history.append(iteration_results)

            if verbose:
                print(f"\nIteration {outer_iter + 1} complete:")
                print(f"  Pass rate: {iteration_results['successes']}/{iteration_results['total']}")
                print(f"  Cumulative success rate: {self.state.success_rate():.1%}")
                print(f"  Total cost so far: ${self.state.total_cost_usd:.4f}")

            # Save checkpoint
            self._save_checkpoint(outer_iter + 1)

        return self.state

    def _run_provision(
        self,
        provision: str,
        evolved_prompt: str,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """Run the agent on a single provision with evolved prompt."""

        statute = STATUTES[provision]
        test_cases = TEST_GENERATORS[provision]()

        # Create agent with evolved prompt
        agent = DSLAgentTrainingLoop(
            model=self.model,
            max_iterations=self.max_iterations_per_provision,
            target_accuracy=self.target_accuracy,
            system_prompt=evolved_prompt,  # Inject RL-evolved prompt
        )

        # Run training
        result = agent.train(statute, test_cases, verbose=verbose)

        # Analyze trajectory and extract learnings
        examples, patterns = self.prompt_evolver.analyze_trajectory(
            provision=provision,
            statute=statute,
            trajectory=result.get("trajectory", []),
            final_code=result.get("final_code", ""),
            success=result.get("success", False),
            accuracy=result.get("final_accuracy", 0),
        )

        # Add to state
        self.state.successful_examples.extend(examples)
        self.state.failure_patterns.extend(patterns)

        return {
            "success": result.get("success", False),
            "accuracy": result.get("final_accuracy", 0),
            "iterations": result.get("iterations", 0),
            "cost": result.get("cost", {}),
        }

    def _save_checkpoint(self, iteration: int):
        """Save current learning state to disk."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rl_checkpoint_iter{iteration}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)

        data = {
            "state": self.state.to_dict(),
            "examples": [
                {
                    "provision": ex.provision,
                    "citation": ex.statute_citation,
                    "code": ex.final_code,
                    "accuracy": ex.accuracy,
                    "iterations": ex.iterations,
                    "success_factors": ex.success_factors,
                }
                for ex in self.state.successful_examples
            ],
            "failure_patterns": [
                {
                    "provision": p.provision,
                    "error_type": p.error_type,
                    "description": p.description,
                }
                for p in self.state.failure_patterns
            ],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Checkpoint saved: {filepath}")


def run_rl_experiment(
    provisions: list[str] | None = None,
    n_outer_iterations: int = 3,
    model: str = "claude-opus-4-5-20251101",
    verbose: bool = True,
) -> LearningState:
    """Run the full RL experiment."""
    trainer = RLTrainer(model=model)
    return trainer.train(
        provisions=provisions,
        n_outer_iterations=n_outer_iterations,
        verbose=verbose,
    )


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="RL Training for DSL Generation")
    parser.add_argument("--provisions", nargs="+", help="Provisions to train on")
    parser.add_argument("--iterations", type=int, default=3, help="Outer loop iterations")
    parser.add_argument("--model", default="claude-opus-4-5-20251101")
    args = parser.parse_args()

    state = run_rl_experiment(
        provisions=args.provisions,
        n_outer_iterations=args.iterations,
        model=args.model,
    )

    print(f"\n{'=' * 60}")
    print("FINAL RESULTS")
    print(f"{'=' * 60}")
    print(f"Total attempts: {state.total_provisions_attempted}")
    print(f"Total successes: {state.total_successes}")
    print(f"Overall success rate: {state.success_rate():.1%}")
    print(f"Accumulated examples: {len(state.successful_examples)}")
    print(f"Total cost: ${state.total_cost_usd:.4f}")


if __name__ == "__main__":
    main()
