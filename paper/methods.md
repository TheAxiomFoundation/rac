# Methods

## System Architecture

Our system uses reinforcement learning to jointly optimize **agent architecture** and **agent instructions**. Unlike fixed multi-agent systems, the agent starts from scratch and constructs its own network of subagents as it learns what works.

### Two-Level Optimization

**Outer loop** (architecture + instruction optimization):
```
config₀ ──▶ encode(batch) ──▶ reward ──▶ predict ──▶ propose ──▶ test ──┐
   ▲                                                                     │
   └──────────────────── accept if actual > baseline ◀───────────────────┘
```

**Degrees of freedom** (all learned, not predefined):
1. Whether to use subagents at all (single agent vs. network)
2. Number and roles of subagents
3. Each subagent's instructions
4. Routing policy (when to invoke which agent)
5. Information flow between agents

### Prediction-Elicited Improvement

Before proposing any change, the agent must predict expected reward:

| Step | Agent action |
|------|--------------|
| 1 | Observe current reward |
| 2 | **Predict** reward under proposed change |
| 3 | Propose the change |
| 4 | We measure actual reward |
| 5 | Log (predicted, actual) for calibration |

**Hypothesis (H7):** Eliciting predictions improves proposal quality. We test this via ablation:
- *Control*: Propose change directly
- *Treatment*: Predict reward first, then propose

If prediction-elicitation acts as a form of chain-of-thought reasoning, treatment should produce higher-quality improvements.

### Architecture Evolution

The system might evolve from monolithic to specialized:

**Early iterations** (single agent):
```
provision ──▶ [encoder] ──▶ code
```

**Later iterations** (subagent network emerges):
```
provision ──▶ [parser] ──▶ [writer] ──▶ [validator] ──┐
                 ▲            ▲                        │
           [params]           └──── [debugger] ◀───────┘
```

We log full architecture at each iteration to track emergence.

### Implementation: Claude SDK with Tool Use

The system is implemented using the Anthropic Claude SDK with agentic tool use. Unlike single API calls, the agent runs in a loop, calling tools as needed until convergence.

**Data access** (all local, no web):
| Repository | Contents | Access |
|------------|----------|--------|
| `cosilico-lawarchive/` | USC statutes (SQLite DB), IRS guidance (Rev Proc, Pub 17) | Read |
| `rac/` | DSL specification, parser, executor | Read + Execute |
| `cosilico-data-sources/` | CPS microdata, IRS indexed parameters | Read |

**Zero-shot setup**: The agent starts with no existing .rac encodings—`rac-us/` is empty. It must learn the encoding format purely from the DSL specification in `rac/`, without few-shot examples. This tests whether the agent can generalize from specification to implementation.

**Tools available:**
```python
tools = [
    # Codebase exploration
    "read_file",        # Read statutes, .rac files, parameters
    "search_code",      # Find provisions by keyword/pattern
    "list_directory",   # Explore repo structure

    # Execution and validation
    "execute_dsl",      # Run generated code against test cases
    "validate_oracle",  # Compare to PolicyEngine/TAXSIM
    "run_microsim",     # Aggregate validation across CPS

    # Architecture control (outer loop)
    "spawn_subagent",   # Create specialized agent with instructions
    "send_to_agent",    # Route task to existing subagent
    "propose_change",   # Suggest architecture/instruction modification
    "predict_reward",   # Forecast expected reward (for H7)

    # Oracle arbitration (Round 2 only)
    "inspect_oracle_code",  # Read PolicyEngine implementation
    "file_oracle_issue",    # Submit GitHub issue
]
```

The agent controls its own workflow—it can explore, delegate to subagents it creates, iterate on failures, and propose improvements to its own architecture.

### Inner Loop

Given a fixed architecture, the inner loop encodes a single provision:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Statute   │────▶│   Claude    │────▶│  Generated  │
│    Text     │     │   Agent     │     │    Code     │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                           │                    │
                           │    ┌───────────────┘
                           │    │
                    ┌──────▼────▼──────┐
                    │     Executor     │
                    │   (DSL Parser)   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   Test Cases     │
                    │  (from Oracles)  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │     Scorer       │
                    │  (Accuracy, MAE) │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │    Diagnoser     │──────▶ Feedback to Agent
                    │ (Failure Analysis)│
                    └──────────────────┘
```

### Claude Agent

We use Claude 4.5 models with tool use. The level of agent autonomy varies by provision complexity:

**Level 1 (Simple provisions)** - Minimal agency, all context provided:
- `execute_dsl`: Run code against test cases
- `submit_final_code`: Signal completion

**Level 2 (Medium provisions)** - Can query for related context:
- Above tools, plus:
- `search_provisions`: Find related .rac files by keyword
- `read_parameters`: Query IRS indexed values

**Level 3 (Complex provisions)** - Full exploration capability:
- Above tools, plus:
- `fetch_statute`: Read USC text from lawarchive
- `search_definitions`: Find term definitions across code

**Oracle Arbitration (Round 2 only)** - For provisions that fail to converge in Round 1:
- `inspect_oracle_code`: Read PolicyEngine implementation (costs -0.05 reward)
- `file_oracle_issue`: Submit GitHub issue with test case (costs -0.10 reward)
- If issue is confirmed as bug: +0.20 reward bonus
- If issue is rejected: -0.05 additional penalty

Round 1 uses a pure blackbox oracle—no code access. This establishes baseline encoding capability. Only provisions that fail to converge (<95% accuracy after max iterations) proceed to Round 2 with arbitration tools enabled.

This separation lets us measure: (1) encoding capability without peeking, (2) what fraction of failures are oracle bugs vs agent bugs, (3) whether code inspection helps resolution.

The system prompt provides:
- DSL specification (entity types, formula syntax, reference format)
- Available parameters (rates, thresholds from IRS publications)
- Instructions for iteration

We track tool usage to measure how much exploration is required—provisions needing more context queries are genuinely harder.

### Author-Evaluator Collaborative Workflow

Beyond the single-agent loop, we introduce a **two-agent collaborative workflow** for encoding improvement. This mirrors code review processes and enables systematic tracking of how review feedback improves encoding quality.

**Two Agents with Different Access Levels:**

| Agent | Access | Role |
|-------|--------|------|
| Author | Minimal prompt, no oracle code | Generates encodings from statute text |
| Evaluator | Full oracle code, statute archives, internet | Reviews, diagnoses issues, suggests improvements |

The Author operates under "AlphaLaw" constraints—minimal instruction, learning primarily from reward signals. The Evaluator has full access to ground truth for verification.

**Model Choice:**

Both agents use Claude 4.5 models, with flexibility to trade off cost vs. quality:
- **Haiku 4.5**: Lower cost ($1/$5 per 1M tokens)
- **Sonnet 4.5**: Balanced ($3/$15 per 1M tokens)
- **Opus 4.5**: Highest quality ($5/$25 per 1M tokens)

Default: Sonnet 4.5 for both. We track cost separately to measure cost-effectiveness.

**Collaborative Iteration Cycle:**

```
┌─────────────┐                    ┌─────────────┐
│   Author    │───── creates PR ──▶│   GitHub    │
│ (4.5 model) │                    │     PR      │
└─────────────┘                    └──────┬──────┘
                                          │
                    ┌─────────────────────┘
                    ▼
            ┌─────────────┐
            │  Evaluator  │◀──── full oracle access
            │ (4.5 model) │
            └──────┬──────┘
                   │
         ┌─────────▼─────────┐
         │  Initial Review   │
         │  - Scores         │
         │  - Issues         │
         │  - Prediction₁    │──────▶ tracks prediction BEFORE author input
         └─────────┬─────────┘
                   │
         ┌─────────▼─────────┐
         │  Author Response  │
         │  - Agrees/disagrees│
         │  - Proposed fixes │
         └─────────┬─────────┘
                   │
         ┌─────────▼─────────┐
         │  Post-Author      │
         │  Prediction₂      │──────▶ tracks prediction AFTER author input
         │  (measures shift) │
         └─────────┬─────────┘
                   │
              ┌────▼────┐
              │ Iterate │◀──── until accuracy ≥ target
              └────┬────┘
                   │
         ┌─────────▼─────────┐
         │  Record Learnings │──────▶ feeds back into agent prompts
         │  - What fixed it  │
         │  - System improve │
         └───────────────────┘
```

**Prediction Tracking:**

The Evaluator makes two predictions per review cycle:
1. **Initial prediction** (before seeing Author's response)
2. **Post-author prediction** (after seeing Author's response)

We track the **prediction shift** to measure how Author input influences Evaluator's assessment:

```
shift = prediction₂.total - prediction₁.total
```

This enables analysis of:
- Does Author input improve Evaluator's predictions? (positive shift)
- How often does Author change Evaluator's mind?
- Which types of issues show largest prediction shifts?

**Learning Capture:**

When an encoding successfully converges, we record what worked:

| Learning Field | Description |
|----------------|-------------|
| issue_type | Category (missing_logic, wrong_parameter, text_hallucination) |
| fix_description | What specifically fixed it |
| accuracy_before | Score before fix |
| accuracy_after | Score after fix |
| proposed_prompt_change | How to improve agent prompts for future |

These learnings accumulate and feed back into the agent's instructions, enabling systematic improvement of the encoding system itself—not just individual encodings.

**Cost Tracking:**

Separate cost tracking for each agent:
- Author cost (typically Haiku at $0.80/$4.00 per 1M tokens)
- Evaluator cost (typically Sonnet at $3/$15 per 1M tokens)

This enables cost-effectiveness analysis of the collaborative approach vs. single-agent encoding.

### Domain-Specific Language

Our Cosilico DSL captures:
- **Variables**: Named calculations with entity scope (Person, TaxUnit, Household)
- **Formulas**: Arithmetic expressions with conditionals and functions
- **References**: Pointers to other variables and parameters
- **Citations**: Links to statutory sections

Example:
```
variable eitc_phase_in_credit:
  entity: TaxUnit
  period: Year
  dtype: Money
  citation: "26 USC § 32(a)(1)"

  references:
    earned_income: us/irs/income/earned_income
    phase_in_rate: param.irs.eitc.phase_in_rate

  formula:
    min(earned_income, earned_income_amount) * phase_in_rate
```

### Oracles (Blackbox Only)

Critically, the agent has **no access to oracle source code**—only output comparisons. This prevents trivial copying and ensures the agent must learn statutory logic from the text itself.

**PolicyEngine-US** serves as primary oracle:
- Comprehensive federal tax implementation
- Validated against IRS examples
- API access for automated testing
- Agent sees only: (input, expected_output) pairs

**TAXSIM** (NBER) provides secondary validation:
- Independent implementation
- Flags disagreements for investigation
- Cross-oracle agreement increases confidence

### Hard Constraints vs. Soft Rewards

We distinguish between **hard constraints** (binary pass/fail) and **soft rewards** (continuous optimization targets):

**Hard Constraints** (must pass, not in reward function):
| Constraint | Enforcement | Rationale |
|------------|-------------|-----------|
| No hardcoded values | CI linter: only 0, 1, -1 allowed in formulas | Forces parameterization |
| Inline tests pass | DSL executor validates | Catches syntax and basic logic errors |
| Valid DSL syntax | Parser rejects invalid code | Agent must produce parseable output |
| Entity/period consistency | Type checker | Prevents dimensional errors |

**Soft Rewards** (continuous, optimized via RL):
| Reward Component | Weight | Metric |
|------------------|--------|--------|
| Oracle accuracy | 0.40 | Match rate against PolicyEngine/TAXSIM |
| Text fidelity | 0.20 | Statute text in `text:` field matches lawarchive |
| Sourcing score | 0.20 | All parameter values traceable to statute text |
| Granularity score | 0.20 | Encoding is at leaf subsection level |

The non-oracle components ensure encodings are **legally grounded**:
- **Text fidelity** prevents hallucinated statute language
- **Sourcing** ensures parameters come from the actual law, not model priors
- **Granularity** enforces atomic subsection encoding (the path IS the citation)

These are evaluated by dedicated **evaluator subagents** with full access to statute archives.

This separation ensures that failing a hard constraint is not a "low reward" but a rejection—the agent must retry until constraints pass. The soft rewards then guide toward optimal solutions among valid candidates.

### Hyperparameters

Beyond model choice, key hyperparameters affect convergence:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Max iterations | 10 | Hard cap on encode-validate cycles |
| Target accuracy | 0.95 | Early stop if achieved |
| Batch size | 50 | Test cases per validation round |
| Feedback limit | 10 | Max failing cases shown to agent |
| Temperature | 0.0 | Deterministic generation |

**Batch size** trades off signal vs. cost: larger batches catch more errors per iteration but increase API calls. We found 50 cases per round balances convergence speed with cost, increasing to 200 for aggregate microsim validation.

**Feedback limit** prevents prompt overflow—showing 10 representative failures is sufficient for diagnosis.

### Test Case Generation

For each provision, we generate test cases covering:
- Income distribution (log-uniform from $0 to $1M)
- Family structures (0-4 children, various filing statuses)
- Boundary values (exactly at thresholds)
- Edge cases (zero income, maximum values)

Typical test suite: 100-500 cases per provision.

## Pilot Phase Learnings

Before the formal experiment, we conducted pilot encoding runs on select provisions to validate our infrastructure and refine the experimental design. These runs are not included in the main results but informed key methodological choices.

### Key Discovery: Phase-In vs Phase-Out Rate Confusion

During pilot encoding of the Earned Income Tax Credit, we discovered a subtle bug pattern. The EITC has **different rates** for phase-in (34% for 1 child) and phase-out (15.98% for 1 child), but the agent initially used the phase-out rate for both regions—producing a systematic $9.2B aggregate underestimate vs PolicyEngine.

This error was only caught by **record-by-record comparison** across the full CPS microdata (200K+ records), not by unit test cases. The fix was straightforward once identified:

```diff
- phase_in_credit = earned_income * phaseout_rate  # WRONG
+ phase_in_credit = earned_income * phase_in_rate  # CORRECT
```

**Implications for experiment design:**
1. Validation must include aggregate microsimulation, not just unit tests
2. Parameters with similar names (phase_in_rate vs phaseout_rate) are high-confusion risk
3. The agent benefits from explicit rate derivation checks in feedback

### Infrastructure Validated

- **Encoder RL loop**: Converged to 100% accuracy on standard deduction within 3 iterations
- **Validator integration**: PolicyEngine API successfully returns test case results
- **No-hardcodes linter**: Correctly rejects formulas like `if age >= 65` (must use parameters)
- **Experiment tracking**: Run metadata saved to `optimization/runs/`

## Provision Selection

We encode 15 provisions from the Internal Revenue Code, stratified by complexity:

| Phase | Provisions | Complexity | Examples |
|-------|-----------|------------|----------|
| 1 | 5 | Simple (1-3) | EITC phase-in, Standard deduction |
| 2 | 5 | Medium (4-6) | Full EITC, Child care credit |
| 3 | 5 | Complex (7+) | AMT, NIIT, QBI deduction |

Complexity score = conditionals + parameters + references + 2×nesting

## Metrics

**Primary:**
- **Accuracy**: Proportion of test cases passing (within $1 tolerance)
- **Iterations**: Generate-test cycles to reach 95%
- **Tokens**: API usage (input + output)
- **Cost**: Tokens × rate ($3/M input, $15/M output for Sonnet)

**Secondary:**
- Time to convergence
- Error type distribution
- Human interventions required

## Analysis Plan

All hypotheses preregistered (see Appendix A):

- **H1 (Convergence)**: Bootstrap CI for convergence rate
- **H2 (Complexity)**: Regression of iterations on complexity score
- **H3 (Transfer)**: Paired comparison of early vs. late provisions
- **H4 (Cost)**: Trend analysis and comparison to manual estimates
- **H5 (Failures)**: Chi-square test for failure category distribution
