# Preregistration: AI-Driven Rules-as-Code Encoding

**Study Title:** Reinforcement Learning from Implementation Feedback for Automated Statutory Encoding

**Authors:** Cosilico AI

**Date:** December 2024 (Updated December 2024)

**Registration:** This document serves as the preregistration for our empirical study on AI-driven rules-as-code encoding. The hypotheses, methods, and analysis plans below were specified before the experimental phase of data collection.

**Live Dashboard:** Progress tracked at https://cosilico.ai/validation

---

## 1. Research Questions

### Primary Question
Can large language models (LLMs) automatically encode statutory provisions into executable code by using existing implementations as oracles for reinforcement learning?

### Secondary Questions
1. Does transfer learning occur—after learning federal tax rules and early state systems, can the model encode later states more efficiently?
2. How does accuracy vary across provision complexity (simple formulas vs. multi-branch logic)?
3. What is the cost-effectiveness compared to manual encoding?
4. Where do LLMs systematically fail, and what human oversight is required?

---

## 2. Experimental Design

### 2.1 Two-Phase Approach

Our study employs a two-phase design that separates capability development from experimental evaluation:

**Phase 1: Federal Development (Non-Experimental)**
We first build the complete federal individual income tax system, tracking accuracy against PolicyEngine at each step. This phase establishes:
- Baseline encoding capabilities
- Iterative refinement methodology
- Tool and process maturation

**Phase 2: State Tax Systems (Experimental)**
After federal completion, we use the 50 state income tax systems plus DC as our research experiment. State systems provide:
- **Natural variation**: Different complexity levels, structures, and edge cases
- **Controlled conditions**: Same tooling and approach across all states
- **Novel provisions**: Cannot be memorized from training data
- **Independent validation**: Both PolicyEngine-US and TAXSIM cover all 50 states + DC

### 2.2 Why States as the Experiment

State income tax systems offer an ideal natural experiment for several reasons:

1. **Sample size**: 50 states + DC provides sufficient statistical power
2. **Variation**: States range from no income tax (TX, FL) to complex progressive systems (CA, NY)
3. **Independence**: State rules are less represented in LLM training data than federal
4. **Dual validation**: Both PolicyEngine and TAXSIM implement all state systems
5. **Incremental learning**: Natural ordering allows testing transfer learning hypotheses

### 2.3 Current Status

As of preregistration, federal development shows:

| Component | Match Rate | Test Cases |
|-----------|------------|------------|
| EITC | 85.2% | 30,182 |
| Income Tax (before credits) | 78.8% | 30,182 |
| **Overall** | **82.0%** | 30,182 |

These results on CPS tax units establish the baseline from which we will complete federal and then begin state experiments.

---

## 3. Hypotheses

### H1: Federal Convergence Hypothesis
**Statement:** The federal individual income tax system will achieve ≥95% accuracy against PolicyEngine before state experiments begin.

**Operationalization:**
- Accuracy measured as weighted match rate across all CPS tax units
- Components include: AGI, taxable income, all credits, all deductions
- Match tolerance: $1 per provision

**Success criterion:** 95% overall match rate on CPS before starting state phase.

### H2: Transfer Learning Hypothesis
**Statement:** Encoding performance improves over the course of state implementation—states encoded later require fewer iterations than earlier states of similar complexity.

**Operationalization:**
- Group states into complexity tiers (based on number of brackets, credits, special provisions)
- Compare mean iterations for first 10 states vs. last 10 states within each tier
- Expect ≥20% reduction in iterations for later states

**Mechanism:** Patterns learned from federal rules and early state implementations transfer to later states—common structures like bracket lookups, phase-outs, and filing status adjustments become easier to encode.

### H3: Complexity Scaling Hypothesis
**Statement:** The number of iterations required scales with state tax system complexity.

**Operationalization:**
- Simple states (e.g., flat tax states like IL, IN): ≤3 iterations to 95%
- Medium states (e.g., standard progressive systems): 4-7 iterations
- Complex states (e.g., CA, NY with multiple credits): 8+ iterations

**Complexity scoring:**
- +1 per tax bracket
- +1 per credit/deduction type
- +2 per income-based phase-out
- +3 for alternative minimum tax provisions

### H4: Cross-Validator Agreement Hypothesis
**Statement:** When Cosilico disagrees with one validator, manual review will reveal:
- 40%: Cosilico error (our encoding is wrong)
- 30%: Validator bug (existing implementation is wrong)
- 30%: Specification ambiguity (statute is unclear)

**Operationalization:**
- Examine cases where Cosilico matches one validator but not the other
- Categorize root cause through statute analysis
- Track bug reports filed and accepted upstream

### H5: Cost Efficiency Hypothesis
**Statement:** The cost per state (API tokens × rate) decreases over time and averages <$50 per state.

**Operationalization:**
- Track total tokens (input + output) per state
- Estimate manual cost at $5,000-$20,000 per state (based on PolicyEngine historical effort)
- Expect >99% cost reduction vs. manual implementation

### H6: Oracle Bug Discovery Hypothesis
**Statement:** The encoding process will discover genuine bugs in PolicyEngine or TAXSIM.

**Operationalization:**
- Track all discrepancies where Cosilico encoding appears correct after statute review
- File issues with validators; track acceptance rate
- Expect ≥5 confirmed bugs across all 51 jurisdictions

---

## 4. Methods

### 4.1 Federal Tax Provisions (Development Phase)

We will complete the following federal components before beginning state experiments:

**Income Components:**
- Wages, salaries, tips (W-2)
- Interest and dividends
- Capital gains (short and long term)
- Business income (Schedule C)
- Rental income (Schedule E)
- Social Security benefits (taxable portion)

**Above-the-Line Deductions:**
- IRA/401k contributions
- Student loan interest
- Self-employment tax deduction
- Health savings account contributions

**Adjusted Gross Income (26 USC § 62)**

**Itemized vs. Standard Deduction:**
- Standard deduction (26 USC § 63)
- SALT deduction with cap (26 USC § 164)
- Mortgage interest (26 USC § 163)
- Charitable contributions (26 USC § 170)

**Credits:**
- Earned Income Tax Credit (26 USC § 32)
- Child Tax Credit (26 USC § 24)
- Child and Dependent Care Credit (26 USC § 21)
- Education credits (26 USC § 25A)
- Premium Tax Credit (26 USC § 36B)

**Tax Calculation:**
- Regular tax liability (rate brackets)
- Alternative Minimum Tax (26 USC § 55-59)
- Net Investment Income Tax (26 USC § 1411)

### 4.2 State Tax Systems (Experimental Phase)

After federal completion, we encode state income tax systems in a random order stratified by complexity:

**No Income Tax (8 states):** AK, FL, NV, NH*, SD, TN*, TX, WA, WY
(*NH and TN tax interest/dividends only)

**Flat Tax States (10 states):** CO, IL, IN, KY, MA, MI, NC, NH, PA, UT

**Progressive Tax States (32 states + DC):** Ordered randomly within tier

### 4.3 Validators

**Primary Validators:**

| Validator | Coverage | API Access | Source |
|-----------|----------|------------|--------|
| PolicyEngine-US | Federal + 50 states + DC | Yes | Open source |
| TAXSIM (NBER) | Federal + 50 states + DC | Yes | Academic |

**Validation Protocol:**
1. Generate test cases from CPS microdata (30,000+ tax units)
2. Run identical inputs through Cosilico, PolicyEngine, and TAXSIM
3. Calculate match rates for each provision
4. Investigate discrepancies systematically

**Match Criteria:**
- Dollar amounts: within $1
- Rates/percentages: exact match
- Boolean flags: exact match

### 4.4 Agentic Loop Configuration

**Model:** Claude Sonnet 4 (claude-sonnet-4-20250514)
**Max iterations:** 10 per provision
**Target accuracy:** 95%

**Tools available:**
- `execute_dsl`: Run code against test cases
- `query_oracle`: Get expected values from validators
- `submit_final_code`: Complete encoding

**Reward Function:**
- Oracle alignment (70%): Match rate against validators
- Generalization (20%): Accuracy on holdout test cases
- Efficiency (10%): Token count and code conciseness

### 4.5 Metrics

**Primary Metrics:**
- Match rate: % of test cases matching validators (within tolerance)
- Iterations: Number of generate-test cycles per state
- Cumulative accuracy: Running match rate across all completed states

**Secondary Metrics:**
- Tokens per state
- Cost per state
- Time to convergence
- Bug discovery rate (bugs found / states completed)

---

## 5. Analysis Plan

### H1 Analysis (Federal Convergence)
- Track match rate progression during federal development
- Report final match rate with 95% CI via bootstrap
- Success: point estimate ≥95%

### H2 Analysis (Transfer Learning)
- Regression: iterations ~ state_order + complexity + (1|tier)
- Expect negative coefficient on state_order (p < 0.05)
- Plot learning curve: iterations vs. cumulative states completed

### H3 Analysis (Complexity Scaling)
- ANOVA: iterations by complexity tier
- Post-hoc pairwise comparisons with Bonferroni correction
- Report effect sizes (eta-squared)

### H4 Analysis (Cross-Validator Agreement)
- Categorize all triple-disagreements (Cosilico vs. PE vs. TAXSIM)
- Chi-square test for distribution across error categories
- Report proportions with 95% CI

### H5 Analysis (Cost Efficiency)
- Calculate mean and total cost
- Compare to estimated manual cost
- Plot cost per state over time (test for exponential decay)

### H6 Analysis (Bug Discovery)
- Track all filed issues and outcomes
- Calculate discovery rate per 1000 test cases
- Categorize bug types

---

## 6. Data Collection Protocol

### 6.1 Federal Development Procedure
1. Implement provision in Cosilico DSL
2. Run against CPS microdata
3. Compare to PolicyEngine
4. Iterate until ≥95% match or convergence plateau
5. Log all metrics and conversation traces

### 6.2 State Experiment Procedure
1. Randomize state order within complexity tiers
2. For each state:
   a. Generate test cases from CPS (state-filtered)
   b. Run agentic loop with logging
   c. Record all metrics
   d. Investigate and categorize any discrepancies
3. Update live dashboard after each state

### 6.3 Logging
All runs will log:
- Full conversation history (prompts and responses)
- Token counts per turn
- Test results per iteration
- Final code
- Timestamps
- Discrepancy investigations

Logs stored in: `paper/data/runs/`
Dashboard: https://cosilico.ai/validation

### 6.4 Stopping Rules
- Stop iteration if accuracy ≥95% (success)
- Stop iteration if accuracy unchanged for 3 consecutive iterations (plateau)
- Stop iteration at 10 iterations (max)
- Do not stop study early—complete all 51 jurisdictions

---

## 7. Deviations and Amendments

Any deviations from this preregistration will be documented in:
`paper/amendments.md`

**Types of acceptable deviations:**
- Reordering states within tiers (if randomization reveals issues)
- Adding additional test cases
- Bug fixes in tooling (not affecting results)

**Types requiring justification:**
- Changing target accuracy threshold
- Changing max iterations
- Excluding states post-hoc
- Changing validator weights

---

## 8. Timeline

- **Weeks 1-4:** Complete federal tax system (development phase)
- **Weeks 5-8:** State experiments (flat tax and simple progressive states)
- **Weeks 9-12:** State experiments (complex progressive states)
- **Week 13:** Analysis and writeup

---

## 9. Code and Data Availability

All code, data, and analysis will be available at:
- Repository: https://github.com/CosilicoAI/rac
- Live Dashboard: https://cosilico.ai/validation
- Paper: https://docs.rac.ai/paper/

---

## Appendix A: State Complexity Classification

### No Income Tax (Complexity: 0)
Alaska, Florida, Nevada, South Dakota, Texas, Washington, Wyoming
(New Hampshire and Tennessee tax only interest/dividends)

### Flat Tax States (Complexity: 1-2)
Colorado (4.4%), Illinois (4.95%), Indiana (3.05%), Kentucky (4.0%),
Massachusetts (5.0%), Michigan (4.05%), North Carolina (4.75%),
Pennsylvania (3.07%), Utah (4.65%)

**Scoring:**
- +1 base for any income tax
- +1 if different treatment for certain income types

### Progressive States - Simple (Complexity: 3-5)
States with 2-4 brackets and few credits
Examples: Arizona, New Mexico, North Dakota

**Scoring:**
- +1 per bracket above 1
- +1 per major credit

### Progressive States - Medium (Complexity: 6-8)
States with 5-7 brackets or multiple credits
Examples: Oregon, Minnesota, Wisconsin

### Progressive States - Complex (Complexity: 9+)
States with 8+ brackets, AMT, or extensive credit systems
Examples: California (9 brackets + AMT), New York (8 brackets + multiple credits)

---

## Appendix B: Test Case Generation

For each state, test cases will be stratified across:

**Income levels:** $0, $10K, $25K, $50K, $75K, $100K, $150K, $200K, $500K, $1M
**Filing status:** Single, MFJ, MFS, HoH
**Dependents:** 0, 1, 2, 3, 4+
**Age:** <65, 65+
**Income composition:** Wages only, mixed income, retirement income

**Minimum per state:** 1,000 test cases
**Stratification ensures:** Coverage of all bracket boundaries and credit phase-outs

---

## Appendix C: Validator Comparison Protocol

When Cosilico disagrees with a validator:

1. **Identify scope:** Single test case or systematic pattern?
2. **Cross-reference:** Does the other validator agree with Cosilico or the first validator?
3. **Statute review:** Read original state statute and IRS/state guidance
4. **Root cause:** Classify as Cosilico error, validator bug, or ambiguous specification
5. **Resolution:** Fix Cosilico encoding OR file upstream issue
6. **Documentation:** Log all findings in `paper/data/discrepancies/`

This protocol ensures systematic investigation of all discrepancies and contributes to validator improvement regardless of error source.
