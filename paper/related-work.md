# Related Work

Our approach combines ideas from several active research areas: LLM-based agent systems, automated workflow optimization, and self-evolving AI architectures.

## LLM Agent Architectures

Recent work has established foundations for multi-agent LLM systems. AutoGen {cite}`wu2023autogen` and MetaGPT {cite}`hong2023metagpt` pioneered structured orchestration of multiple LLM agents through predefined workflows. These systems demonstrate that decomposing complex tasks across specialized agents improves performance, but rely on manually designed architectures.

Our work differs by allowing the agent to construct its own subagent network through reinforcement learning, rather than specifying the architecture upfront.

## Automated Workflow Optimization

**AFLOW** {cite}`zhang2024aflow` uses Monte Carlo Tree Search to automatically discover optimal agent workflows, defining reusable "operators" (e.g., Ensemble, Review & Revise) as building blocks. The framework outperforms manually designed methods by 5.7% and existing automated approaches by 19.5%.

**DSPy** {cite}`khattab2023dspy` represents workflows as graphs where sub-prompts are jointly tuned for a global objective. **TextGrad** {cite}`yuksekgonul2024textgrad` extends this with "textual gradients" propagated backward through workflows.

Our approach is most similar to AFLOW in using search over architecture space, but we:
1. Focus on the specific domain of statutory encoding
2. Use PolicyEngine/TAXSIM as oracles rather than general benchmarks
3. Introduce prediction-elicited improvement (H7) as a novel mechanism

## Self-Evolving Agent Systems

Several recent works explore agents that improve their own capabilities:

- **Agent-Pro** {cite}`zhang2024agentpro` (ACL 2024): Policy-level reflection and optimization via dynamic belief processes
- **EvoMAC** {cite}`hu2024evomac`: Combines RL with evolutionary algorithms for agent decision-making
- **MorphAgent** {cite}`lu2024morphagent`: Self-evolving agent profiles that dynamically optimize individual expertise
- **Richelieu** {cite}`fan2024richelieu` (NeurIPS 2024): Self-evolving LLM agent using self-play for autonomous evolution without human intervention
- **CORY** {cite}`ma2024cory` (NeurIPS 2024): Multi-agent coevolution framework, potentially superior to PPO for real-world refinement

The **STOP** framework {cite}`zelikman2024stop` proposes recursive self-improvement where agents optimize their own prompts.

## RL + LLM Multi-Agent Systems

**LGC-MARL** {cite}`chen2025lgcmarl` decomposes tasks into subtasks using graph-based coordination between an LLM planner and MARL meta-policy. **CoMAS** {cite}`li2024comas` generates intrinsic rewards from inter-agent discussions, optimized via RL without external supervision.

**DERL** {cite}`faldor2024derl` introduces differentiable evolutionary RL for autonomous reward discovery, using a Meta-Optimizer that evolves reward functions.

## Prediction-Elicited Improvement

Our H7 hypothesis—that requiring agents to predict reward components before proposing changes improves proposal quality—appears novel. The closest analogues are:

1. **Model-based RL**: Agents learn world models to predict outcomes, but this is typically applied to action selection rather than architecture search
2. **Bayesian optimization**: Uses surrogate models to predict objective values, but typically with separate acquisition functions rather than integrated prediction requirements
3. **Neuroscience of reward prediction errors**: Dopamine neurons encode the difference between expected and actual rewards, driving reinforcement learning {cite}`schultz1997dopamine`. We hypothesize that forcing explicit prediction may similarly improve learning

## Rules-as-Code and Legal AI

Prior work on automated legal reasoning includes:

- **Catala** {cite}`merigoux2021catala`: A domain-specific language for encoding legislation with formal semantics
- **Blawx** {cite}`morris2021blawx`: Visual programming for legal rules
- **PolicyEngine** {cite}`policyengine2023`: Tax-benefit microsimulation used as our oracle

These systems require manual encoding. Our contribution is automating the encoding process using LLMs with oracle feedback.

## References

```{bibliography}
:filter: docname in docnames
```
