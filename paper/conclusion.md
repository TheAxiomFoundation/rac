# Conclusion

We presented an AI system for automated rules-as-code encoding using reinforcement learning from implementation feedback. By using existing implementations (PolicyEngine, TAXSIM) as oracles, we create a closed-loop training signal that guides LLMs toward correct statutory encodings.

## Summary of Contributions

1. **Technical system**: An agentic loop using Claude with tool use that iteratively generates and tests code until accuracy thresholds are met.

2. **Empirical evaluation**: Preregistered study on 15 IRC provisions demonstrating feasibility, cost-effectiveness, and transfer learning.

3. **Failure taxonomy**: Categorization of systematic failures informing human oversight requirements.

## Key Takeaways

- **AI can read law and write code**: With the right feedback loop, LLMs achieve high accuracy on real statutory provisions.

- **Cost is low**: Encoding costs cents to dollars per provision, potentially orders of magnitude cheaper than manual encoding.

- **Humans remain essential**: For ambiguous statute, novel legislation, and edge cases, human judgment is irreplaceable.

- **Oracles are the constraint**: Where reference implementations exist, AI encoding works well; where they don't, new approaches are needed.

## Vision

We see AI-driven encoding as the foundation for computational law at scale. Rather than manually encoding each provision, AI does the heavy lifting while humans provide oversight and handle edge cases.

This shifts the bottleneck from implementation to validation—a more tractable problem when the AI's work is auditable and testable.

## Code and Data

All code, data, and analysis available at:
- **Repository**: https://github.com/CosilicoAI/rac
- **Documentation**: https://docs.rac.ai
- **Paper**: https://docs.rac.ai/paper
