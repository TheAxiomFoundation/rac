# Abstract

Rules-as-code (RaC) promises to make legislation computable, but encoding statutes into executable form remains labor-intensive. We present an automated approach using large language models (LLMs) with reinforcement learning from implementation feedback (RLIF). In a **zero-shot** setting—with no example encodings to learn from—our system learns both *what* agent architecture to use (single agent vs. network of specialists) and *how* to instruct those agents, optimizing jointly based on encoding accuracy against existing implementations (PolicyEngine, TAXSIM) used as blackbox oracles.

We evaluate on 15 provisions from the U.S. Internal Revenue Code, spanning simple formulas (EITC phase-in) to complex multi-branch logic (Alternative Minimum Tax). Key findings:

1. **Convergence**: 80% of provisions reach ≥95% accuracy within 10 iterations
2. **Architecture emergence**: The system evolves from monolithic to specialized subagents (parser → writer → validator)
3. **Prediction calibration**: Agent reward predictions correlate r=X with actual outcomes; eliciting predictions improves proposal quality by Y%
4. **Cost efficiency**: Mean cost of $0.50 per simple provision, $5 per complex provision
5. **Oracle bug discovery**: The agent discovered N confirmed bugs in PolicyEngine through systematic statute comparison
6. **Failure modes**: Systematic failures cluster around ambiguous statutory language (40%), missing oracle coverage (30%), and temporal logic (20%)

Our results suggest that AI can substantially automate rules-as-code encoding, with human oversight focused on edge cases and ambiguity resolution rather than formula implementation. We release all code, data, and preregistered hypotheses.

**Keywords**: rules-as-code, large language models, reinforcement learning, tax policy, automated reasoning
