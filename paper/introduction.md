# Introduction

## The Rules-as-Code Challenge

Legislation governs trillions of dollars in tax collection and benefit distribution, yet remains encoded primarily in natural language. Converting statutes to executable code—rules-as-code (RaC)—enables:

- **Simulation**: Model policy changes before enactment
- **Automation**: Streamline benefit delivery and tax filing
- **Transparency**: Make calculations auditable and reproducible
- **Accessibility**: Let citizens understand how rules affect them

But encoding is expensive. A single tax provision can take days of expert effort, and the full U.S. tax code contains thousands of interacting rules. Organizations like PolicyEngine and NBER's TAXSIM have encoded major provisions, but coverage remains incomplete and maintenance is ongoing.

## AI as Encoder

Recent advances in large language models (LLMs) suggest a different approach: rather than humans reading statute and writing code, have AI do both. The key insight is that existing implementations can serve as **oracles**—ground truth for training.

This is analogous to reinforcement learning from human feedback (RLHF), but with deterministic feedback from code execution. Critically, we use **agentic AI**—not single API calls, but agents with tool use that can:

1. Explore the codebase to find related provisions
2. Look up parameter values from IRS documents
3. Execute generated code and observe results
4. Iterate based on validation feedback
5. Spawn specialized subagents for subtasks
6. Propose improvements to their own architecture

We call this **reinforcement learning from implementation feedback (RLIF)**. The agent learns both *how to encode* (instructions) and *what architecture to use* (single agent vs. specialist network).

## Contributions

This paper makes four contributions:

1. **Architecture learning**: We show that an agent can learn its own multi-agent architecture from scratch, evolving from monolithic to specialized subagent networks based on task performance.

2. **Prediction-elicited improvement**: We demonstrate that requiring agents to predict reward before proposing changes improves proposal quality (H7), suggesting prediction acts as chain-of-thought reasoning.

3. **Empirical evaluation**: We test on 15 IRC provisions with 7 preregistered hypotheses, measuring convergence, architecture emergence, prediction calibration, and oracle bug discovery.

4. **Open infrastructure**: We release all code, data, agent trajectories, and the evolved agent architecture for replication and extension.

## Roadmap

- **Methods**: System architecture, provision selection, metrics
- **Results**: Accuracy, cost, transfer learning, failure modes
- **Discussion**: Implications for RaC, limitations, future work
- **Appendices**: Full preregistration, provision details, code listings
