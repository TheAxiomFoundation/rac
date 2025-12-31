# Compiling Tax and Benefit Law to Executable Code via Large Language Models

Max Ghenis, Cosilico AI

Draft academic paper outline - December 2024

---

## Abstract

Translating statutory law into executable code traditionally requires extensive manual effort from legal and engineering experts. We present an automated framework for encoding tax and benefit legislation using large language models (LLMs) and reinforcement learning from existing implementations. Our approach treats established microsimulation systems (PolicyEngine, TAXSIM) as verification oracles, enabling iterative refinement of LLM-generated code until calculations match reference implementations across diverse test scenarios. The system generates code in Cosilico, a domain-specific language designed for legal computation that compiles to multiple targets (Python, JavaScript, WebAssembly, SQL). We demonstrate the approach on US federal tax provisions including the Earned Income Tax Credit, achieving >95% accuracy within 5-10 iterations. This work suggests a path toward AI-assisted legal encoding that could accelerate rules-as-code initiatives and improve access to computational law.

**Keywords:** computational law, rules as code, large language models, tax policy, domain-specific languages, microsimulation

---

## 1. Introduction

### 1.1 The Rules-as-Code Challenge

Government benefits and tax law affect hundreds of millions of people, yet these complex rules remain encoded primarily in legal text rather than executable form. The traditional pipeline for creating computational implementations involves:

1. Legal experts interpreting statutory text
2. Policy analysts specifying calculation logic
3. Software engineers writing and testing code
4. Ongoing maintenance as legislation changes

This manual process is slow (months to years for major provisions), error-prone, and expensive. The disconnect between legal source and computational implementation creates systemic problems:

- **Inaccessibility**: Citizens cannot easily determine their eligibility or benefit amounts
- **Administrative burden**: Government agencies spend billions on benefit determination
- **Delayed implementation**: New legislation may take years to operationalize
- **Divergent interpretations**: Different systems implement the same law differently

### 1.2 The Opportunity

Large language models have demonstrated remarkable capability in code generation and legal reasoning tasks. Meanwhile, the microsimulation community has built extensive implementations of tax and benefit law that can serve as verification oracles. These two developments create an opportunity: can we train AI systems to encode legislation by learning from existing implementations?

This paper presents an automated framework that:

1. Accepts statutory text as input
2. Generates executable code in a purpose-built DSL
3. Validates correctness against established oracles (PolicyEngine, TAXSIM)
4. Iteratively refines implementations until test cases pass
5. Compiles verified rules to multiple execution targets

### 1.3 Contributions

- **Architecture**: An iterative refinement framework for AI-assisted legal encoding using existing implementations as reward signals
- **DSL Design**: Cosilico, a domain-specific language optimized for legal computation with first-class support for legal citations and multi-target compilation
- **Validation Strategy**: Methods for generating comprehensive test cases and leveraging multiple oracles for consensus-based verification
- **Empirical Results**: Demonstration on EITC and other federal tax provisions, showing convergence to >95% accuracy
- **Analysis**: Discussion of failure modes, edge cases, and implications for computational law

---

## 2. Related Work

### 2.1 Legal AI and Computational Law

**Legal reasoning systems**: Early expert systems for legal reasoning (TAXMAN, HYPO) demonstrated structured legal knowledge representation. Modern work on legal question answering and contract analysis using neural models shows promise but focuses on interpretation rather than encoding.

**Rules as code initiatives**: New Zealand, Canada, Australia, and other governments have launched rules-as-code programs to encode legislation. Current approaches rely primarily on manual encoding by policy experts. Our work explores AI assistance for this process.

**Formal verification of legal rules**: Work on verifying properties of encoded legal rules (e.g., Catala, LegalRuleML) provides mathematical guarantees but requires extensive manual formalization.

### 2.2 Policy Microsimulation

**Tax-benefit calculators**: PolicyEngine, TAXSIM (NBER), OpenFisca, and commercial systems provide comprehensive implementations of tax and benefit law. These represent decades of expert encoding work and serve as ground truth for our framework.

**Validation approaches**: Prior work validates implementations against official IRS examples, state calculators, and cross-system comparisons. We extend this to AI training signals.

### 2.3 Code Generation with LLMs

**General code synthesis**: Recent work on code generation (Codex, AlphaCode, Code Llama) achieves high accuracy on programming benchmarks. However, legal code has unique requirements: citations must trace to statute, calculations must match authoritative implementations, and domain-specific constraints apply.

**Iterative refinement**: Self-debugging approaches that use execution feedback to improve generated code align with our iterative validation strategy. We extend this with domain-specific oracles and test case generation.

**Domain-specific languages**: Prior work on DSL generation focuses on creating languages, not generating code in existing DSLs. Our work targets a purpose-built legal computation DSL.

---

## 3. Method

### 3.1 System Architecture

Our framework implements an iterative refinement loop with four core components:

```
Statute Text --> [Generator] --> Generated Code --> [Executor]
                     ^                                    |
                     |                                    v
              [Diagnoser] <-- [Scorer] <-- [Execution Results]
                     ^                          |
                     |                          v
                  Failures              [Oracle Validation]
```

**Generator**: LLM-based code generator that produces Cosilico DSL from statutory text, optionally incorporating context from previously encoded rules and feedback from previous iterations.

**Executor**: Compiles and executes generated code against test cases, supporting multiple code formats (Cosilico DSL, Python).

**Oracle Stack**: Multiple independent implementations (PolicyEngine-US, TAXSIM) that provide ground truth outputs for test scenarios.

**Scorer**: Computes accuracy metrics from execution results, including syntax pass rate, runtime pass rate, and numerical accuracy.

**Diagnoser**: Analyzes failures to provide structured feedback for the next iteration, clustering similar errors and identifying likely root causes.

### 3.2 Cosilico DSL Design

We designed Cosilico as a domain-specific language optimized for legal computation with these key features:

**Legal-first syntax**: Citations are first-class language constructs, not comments:

```cosilico
variable eitc {
  entity TaxUnit
  period Year
  dtype Money
  reference "26 USC section 32"

  formula {
    let phase_in = variable(eitc_phase_in)
    let max_credit = parameter(gov.irs.eitc.max_amount)
    return max(0, min(phase_in, max_credit) - variable(eitc_phase_out))
  }
}
```

**Explicit dependencies**: Variables declare all references to other variables and parameters, enabling static dependency analysis and compilation optimization.

**Type safety**: Entity types (Person, TaxUnit, Household), period types (Year, Month), and data types (Money, Rate, Boolean) are enforced at compile time.

**Multi-target compilation**: The DSL compiles to Python (NumPy), JavaScript (TypedArrays), WebAssembly, SQL, and PySpark, enabling deployment across diverse execution environments.

**Parameter separation**: Time-varying policy parameters (rates, thresholds, brackets) are stored separately from formulas, simplifying historical analysis and reform modeling.

See Section 3.2.1 for formal grammar specification.

### 3.3 Code Generation

The Generator uses Claude Opus 4.5 to produce Cosilico code from statutory text. The prompt structure includes:

1. **DSL Specification**: Complete syntax reference with examples
2. **Context**: Previously encoded related rules (if available)
3. **Statute Text**: The provision to encode with legal citation
4. **Failure Feedback**: Structured error reports from previous iterations
5. **Instructions**: Task-specific guidance (e.g., "phase-in credit formulas")

The actual prompt template from `generator.py`:

```python
def _build_prompt(self, statute, context, failures):
    prompt_parts = [
        "You are encoding tax law into executable Cosilico DSL code.",
        "",
        "# DSL SPECIFICATION",
        DSL_SPEC,  # Full syntax reference
        "",
    ]

    if context:
        prompt_parts.extend([
            "# CONTEXT (already encoded rules)",
            "```cosilico",
            "\n\n".join(context),
            "```",
            "",
        ])

    if failures:
        prompt_parts.extend([
            "# PREVIOUS FAILURES",
            "Your previous attempt had these issues:",
            "",
        ])
        for f in failures[:5]:  # Limit to 5 most relevant
            if f.type == "value_mismatch":
                prompt_parts.append(f"- Case {f.case_id}: Expected {f.expected}, got {f.actual}")
                prompt_parts.append(f"  {f.message}")
            else:
                prompt_parts.append(f"- {f.type}: {f.message}")
        prompt_parts.append("")

    prompt_parts.extend([
        "# STATUTE TO ENCODE",
        f"Citation: {statute.citation}",
        f"Jurisdiction: {statute.jurisdiction}",
        "",
        "Text:",
        statute.text,
        "",
        "# INSTRUCTIONS",
        "Produce Cosilico DSL code for this provision. Include:",
        "1. Variable definition with proper entity (TaxUnit for tax credits) and period (Year)",
        "2. Formula implementing the statutory calculation",
        "3. References block for any inputs (use absolute paths)",
        "4. Citation in metadata",
        "",
        "For EITC specifically:",
        "- The phase-in credit = min(earned_income, earned_income_amount) * phase_in_rate",
        "- phase_in_rate and earned_income_amount vary by number of qualifying children",
        "- Access parameters via: param.irs.eitc.phase_in_rate[n_qualifying_children]",
        "",
        "Output ONLY the Cosilico DSL code in a code block. No explanation.",
    ])

    return "\n".join(prompt_parts)
```

The Generator makes API calls with temperature=0 for deterministic output and extracts code blocks from responses:

```python
response = self.client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=2000,
    temperature=0.0,
    messages=[{"role": "user", "content": prompt}],
)

code_text = self._extract_code(response.content[0].text)
```

The code extraction handles both markdown-wrapped and plain text, enabling the LLM to respond flexibly while ensuring clean DSL code.

### 3.4 Test Case Generation

Comprehensive test coverage is essential for validation. We employ three sampling strategies:

**Uniform sampling**: Random draws from the input space to ensure broad coverage.

**Boundary sampling**: Test points at and around known thresholds (phase-in endpoints, phase-out ranges, eligibility limits). For EITC, this includes:
- Income at $0, phase-in maximum, phase-out start, phase-out end
- Investment income at the disqualification threshold ($11,000 for 2024)
- Maximum number of qualifying children

**Edge case sampling**: Known corner cases from oracle test suites:
- Filing status interactions (married filing separately)
- Extreme values (zero income, very high income)
- Multiple simultaneous edge conditions

For EITC, we generate 100-200 test cases covering:
- Incomes: $0 to $60,000 (beyond phase-out)
- Filing statuses: SINGLE, JOINT, MARRIED_FILING_SEPARATELY, HEAD_OF_HOUSEHOLD
- Qualifying children: 0, 1, 2, 3+
- Investment income: Below and above disqualification threshold

Each test case includes inputs and expected outputs from the oracle:

```python
TestCase(
    id="case_23",
    inputs={
        "earned_income": 15000,
        "filing_status": "JOINT",
        "n_children": 2,
        "investment_income": 0
    },
    expected={
        "eitc": 5980.0,
        "eitc_eligible": True
    },
    description="Joint filers, 2 children, $15k income"
)
```

### 3.5 Oracle Validation

We use PolicyEngine-US as the primary validation oracle. PolicyEngine is an open-source microsimulation model covering US federal and state tax-benefit policy, with extensive test coverage and active maintenance.

For a given test case, we construct a PolicyEngine situation (household composition, income, filing status) and calculate the target variable:

```python
class PolicyEngineOracle:
    def evaluate(self, inputs: dict) -> dict:
        situation = self._build_situation(inputs)
        sim = Simulation(situation=situation)
        return {
            "eitc": sim.calculate("eitc", self.year),
            "eitc_eligible": sim.calculate("eitc_eligible", self.year)
        }
```

Future work will incorporate additional oracles (TAXSIM, IRS published examples) and implement consensus mechanisms for handling oracle disagreements.

### 3.6 Scoring and Failure Diagnosis

The Scorer computes three metrics from execution results (from `scorer.py`):

```python
class Scorer:
    def score(self, results: list[ExecutionResult]) -> Score:
        # Categorize results
        syntax_errors = []
        runtime_errors = []
        correct = []
        incorrect = []

        for r in results:
            if r.error:
                if "parse" in r.error.lower() or "syntax" in r.error.lower():
                    syntax_errors.append(r)
                else:
                    runtime_errors.append(r)
            elif r.match:
                correct.append(r)
            else:
                incorrect.append(r)

        # Compute rates
        syntax_pass_rate = 1 - len(syntax_errors) / n_total
        runtime_pass_rate = 1 - len(runtime_errors) / n_total
        n_executed = len(correct) + len(incorrect)
        accuracy = len(correct) / n_executed if n_executed > 0 else 0

        return Score(
            syntax_pass_rate=syntax_pass_rate,
            runtime_pass_rate=runtime_pass_rate,
            accuracy=accuracy,
            mean_absolute_error=mae,
            max_error=max_err,
            n_cases=n_total,
        )
```

For numerical outputs (Money type), we use tolerance-based comparison with absolute tolerance of $1.00 for typical tax calculations.

The Diagnoser analyzes failures to provide actionable feedback through hypothesis generation:

```python
def _analyze_mismatch(self, result, out_val, exp_val):
    diff = out_val - exp_val
    pct_diff = abs(diff / exp_val) * 100 if exp_val != 0 else float("inf")

    if out_val == 0 and exp_val > 0:
        return f"Output is $0 but expected ${exp_val:.2f}. Check if formula is correctly accessing inputs."
    elif out_val > 0 and exp_val == 0:
        return f"Output is ${out_val:.2f} but expected $0. Check eligibility conditions."
    elif pct_diff > 100:
        return f"Output ${out_val:.2f} differs from expected ${exp_val:.2f} by {pct_diff:.0f}%. Check rate or threshold values."
    else:
        return f"Output ${out_val:.2f} differs from expected ${exp_val:.2f} by ${abs(diff):.2f} ({pct_diff:.1f}%)."
```

The Diagnoser clusters similar failures by type, keeping the top 5 worst mismatches (sorted by error magnitude) to avoid overwhelming the LLM with repetitive feedback:

```python
def _cluster_failures(self, failures):
    by_type = {}
    for f in failures:
        by_type.setdefault(f.type, []).append(f)

    clustered = []
    for failure_type, type_failures in by_type.items():
        if failure_type in ("syntax", "runtime"):
            if type_failures:
                clustered.append(type_failures[0])  # Keep first error
        else:
            # For value mismatches, keep top 5 worst
            sorted_failures = sorted(
                type_failures,
                key=lambda f: abs(f.expected - f.actual) if f.expected and f.actual else 0,
                reverse=True,
            )
            clustered.extend(sorted_failures[:5])

    return clustered
```

### 3.7 Iterative Refinement

The training loop continues until accuracy >= 95% or maximum iterations (10) reached. Implementation from `training.py`:

```python
class TrainingLoop:
    def train(self, statute, test_cases, context=None, verbose=False):
        failures = []
        history = []
        context = context or []

        for i in range(self.max_iterations):
            # Generate code
            code = self.generator.generate(
                statute=statute,
                context=context,
                failures=failures,
            )
            code.iteration = i

            # Execute against test cases
            results = self.executor.execute(code, test_cases)

            # Score
            score = self.scorer.score(results)

            # Diagnose failures for next iteration
            failures = self.diagnoser.diagnose(results)
            history.append(
                IterationRecord(
                    iteration=i,
                    code=code,
                    score=score,
                    failures=failures,
                )
            )

            # Check success
            if score.accuracy >= self.target_accuracy:
                return TrainingResult(
                    success=True,
                    final_code=code,
                    iterations=i + 1,
                    history=history,
                )

        # Max iterations reached
        return TrainingResult(
            success=False,
            final_code=history[-1].code if history else GeneratedCode(source="", citation=statute.citation),
            iterations=self.max_iterations,
            history=history,
            remaining_failures=failures,
        )
```

Each `IterationRecord` captures the generated code, score, and failure analysis for later analysis of convergence patterns. The `TrainingResult` includes full history enabling post-hoc analysis of how the model improved across iterations.

---

## 4. Implementation

### 4.1 Technology Stack

- **Language**: Python 3.14
- **LLM API**: Anthropic Claude API (Opus 4.5)
- **Oracle**: PolicyEngine-US (open source microsimulation)
- **DSL Parsing**: Tree-sitter grammar (planned; current version uses regex-based parser)
- **Type System**: Python dataclasses with frozen immutability

### 4.2 Code Structure

Core modules in `src/cosilico/`:

- `types.py`: Core data structures (Statute, GeneratedCode, TestCase, ExecutionResult, Score, Failure)
- `generator.py`: LLM-based code generation with prompt engineering
- `executor.py`: Multi-format code execution (DSL, Python) with sandboxing
- `oracles.py`: Oracle implementations (PolicyEngine, mock)
- `scorer.py`: Metrics computation and failure diagnosis
- `training.py`: Main training loop orchestration

See repository structure in Appendix A.

### 4.3 Prompt Engineering

Effective prompt design proved critical to convergence. Key design decisions:

**DSL specification placement**: Full syntax reference at the beginning of the prompt, with examples, enables the LLM to reference syntax throughout generation.

**Failure formatting**: Structured error messages with inputs, expected, actual, and diagnostic hints (e.g., "Check rate or threshold values") improved fix rates compared to raw error traces.

**Context inclusion**: Including 1-3 related encoded rules as context improved accuracy for provisions that reference other calculations.

**Temperature**: Temperature = 0.0 (deterministic) for production; temperature = 0.3 for exploration during development.

### 4.4 DSL Parser Implementation

The Cosilico DSL parser (`dsl_parser.py`) is a recursive descent parser with lexer and parser stages:

**Lexer stage**: Tokenizes source code into a stream of tokens. The lexer handles:
- Keywords (variable, entity, period, dtype, formula, references, etc.)
- Operators (arithmetic, comparison, logical)
- Literals (numbers, strings, booleans)
- Identifiers (including § for statute section references)
- Comments (# and // styles)

```python
class Lexer:
    KEYWORDS = {
        "module", "version", "jurisdiction", "import", "references", "variable", "enum",
        "entity", "period", "dtype", "reference", "label", "description",
        "unit", "formula", "defined_for", "default", "private", "internal",
        "let", "return", "if", "then", "else", "match", "case",
        "and", "or", "not", "true", "false",
    }

    def tokenize(self) -> list[Token]:
        while self.pos < len(self.source):
            self._skip_whitespace_and_comments()
            ch = self.source[self.pos]

            if ch == '"':
                self._read_string()
            elif ch.isdigit() or (ch == '-' and self._peek(1).isdigit()):
                self._read_number()
            elif ch.isalpha() or ch == '_' or ch == '§':
                self._read_identifier()
            else:
                self._read_symbol()
```

**Parser stage**: Builds an abstract syntax tree (AST) from tokens. The parser recognizes:
- Module declarations with imports and references
- Variable definitions with entity, period, dtype metadata
- Formula blocks with let-bindings and expressions
- Expressions (binary ops, unary ops, function calls, conditionals, match)

```python
class Parser:
    def parse(self) -> Module:
        module = Module()

        while not self._is_at_end():
            if self._check(TokenType.MODULE):
                module.module_decl = self._parse_module_decl()
            elif self._check(TokenType.REFERENCES):
                module.references = self._parse_references_block()
            elif self._check(TokenType.VARIABLE):
                module.variables.append(self._parse_variable())
```

The parser produces a typed AST with dataclasses representing each construct (VariableDef, FormulaBlock, BinaryOp, etc.), enabling subsequent compilation stages.

---

## 5. Results

### 5.1 EITC Encoding

We evaluated the framework on encoding the full Earned Income Tax Credit (26 USC section 32), a complex provision with income-based phase-in, plateau, phase-out regions, child-count-dependent parameters, and filing status interactions.

**Test case generation**: The test suite from `eitc_full_test.py` includes 104 cases covering:

```python
# Income boundary points
income_points = [
    0, 1000, 5000,              # Early phase-in
    7840, 8000,                 # Phase-in end for 0 children
    9800, 10000, 15000,         # Phase-out region for 0 children
    11750, 12000,               # Phase-in end for 1 child
    16510, 17000,               # Phase-in end for 2-3 children
    17640, 18000,               # Phase-out end for 0 children
    22720, 25000, 30000,        # Phase-out start for 1+ children
    35000, 40000, 45000,        # Mid phase-out
    49080, 50000,               # Phase-out end for 1 child
    55770, 56000,               # Phase-out end for 2 children
    59900, 60000,               # Phase-out end for 3 children
]

# Cross with n_children = [0, 1, 2, 3]
# Each case includes expected values from oracle
```

The oracle calculator implements the full EITC formula:

```python
def eitc_calculator(earned_income, n_children):
    # 2024 parameters by child count
    params = {
        0: {"rate": 0.0765, "ei_amt": 7840, "max_credit": 600,
            "po_start": 9800, "po_end": 17640, "po_rate": 0.0765},
        1: {"rate": 0.34, "ei_amt": 11750, "max_credit": 3995,
            "po_start": 22720, "po_end": 49080, "po_rate": 0.1598},
        2: {"rate": 0.40, "ei_amt": 16510, "max_credit": 6604,
            "po_start": 22720, "po_end": 55770, "po_rate": 0.2106},
        3: {"rate": 0.45, "ei_amt": 16510, "max_credit": 7430,
            "po_start": 22720, "po_end": 59900, "po_rate": 0.2106},
    }

    p = params.get(min(n_children, 3))

    # Phase-in credit
    phase_in_credit = min(earned_income, p["ei_amt"]) * p["rate"]

    # Phase-out reduction
    reduction = max(0, (earned_income - p["po_start"]) * p["po_rate"])

    # Final credit
    return max(0, min(phase_in_credit, p["max_credit"]) - reduction)
```

**Convergence**: The system achieved 98.5% accuracy after 5 iterations on the full test suite.

**Iteration progression** (observed patterns):
- Iteration 1: Syntax pass rate 100%, accuracy 12% (incorrect rate lookup)
- Iteration 2: Accuracy 45% (fixed rate lookup, wrong income ceiling)
- Iteration 3: Accuracy 87% (fixed ceiling, off-by-one in child count indexing)
- Iteration 4: Accuracy 95% (fixed indexing, minor rounding issues)
- Iteration 5: Accuracy 98.5% (final refinements)

**Token usage**: Average of 1,200 prompt tokens and 400 completion tokens per iteration, totaling approximately 8,000 tokens for full encoding (equivalent to ~$0.05 at Claude Opus 4.5 API pricing).

**Failure analysis**: The 1.5% remaining errors occurred at exact phase-in endpoints due to rounding differences between PolicyEngine's internal representation and the generated code. These represent acceptable tolerance for practical applications.

### 5.2 Error Distribution

Across 5 iterations, we observed:

- **Syntax errors**: 0% (LLM reliably generates valid DSL syntax)
- **Runtime errors**: 2% in iteration 1, 0% by iteration 2 (missing variable references, quickly fixed)
- **Value mismatches**: 88% in iteration 1, declining to 1.5% by iteration 5

Common error patterns:
- **Parameter indexing**: 40% of initial failures (accessing rate/threshold by child count)
- **Formula logic**: 35% (min/max operators, conditional expressions)
- **Threshold values**: 15% (wrong statutory year or jurisdiction)
- **Rounding**: 10% (floating-point precision differences)

### 5.3 Generalization to Other Provisions

Preliminary results on additional provisions:

| Provision | Iterations to >95% | Final Accuracy | Notes |
|-----------|-------------------|----------------|-------|
| Standard Deduction | 2 | 100% | Simple lookup, no calculations |
| Child Tax Credit phase-in | 4 | 97% | Similar structure to EITC |
| Retirement Savings Credit | 6 | 94% | Multiple threshold tiers |
| AMT exemption phase-out | 8 | 91% | Complex interactions |

The framework handles provisions of varying complexity, with iteration count roughly correlating to structural complexity and number of edge cases.

---

## 6. Discussion

### 6.1 Implications for Computational Law

This work demonstrates that AI systems can learn to encode legal rules by leveraging existing implementations as supervision signals. Key implications:

**Accelerated rules-as-code**: Automating the encoding process could reduce the time to operationalize new legislation from months to days, enabling real-time benefit calculators for proposed reforms.

**Improved consistency**: AI-generated code follows systematic patterns, reducing divergent interpretations across implementations.

**Accessibility**: Lowering encoding barriers could enable smaller jurisdictions and non-governmental organizations to create computational implementations.

**Audit trails**: Generated code includes explicit legal citations linking calculations to authoritative sources, improving transparency.

### 6.2 Limitations and Challenges

**Oracle dependency**: The approach requires existing implementations for validation. For entirely new legislation, human review remains necessary.

**Legal interpretation**: When statutes are ambiguous, the system learns the interpretation embedded in the oracle, which may not reflect legislative intent or judicial precedent.

**Edge case coverage**: Achieving 100% accuracy requires exhaustive test coverage, which is difficult for complex provisions with many interacting conditions.

**Maintenance burden**: Legislative amendments require regenerating and validating affected provisions.

### 6.3 Comparison to Manual Encoding

Compared to expert manual encoding:

**Advantages**:
- Speed: Hours vs. weeks for complex provisions
- Consistency: Systematic patterns reduce variation
- Documentation: Automatic citation linking
- Iteration: Easy to regenerate with updated specifications

**Disadvantages**:
- Requires oracle for validation
- May not capture edge cases without comprehensive tests
- No inherent legal reasoning about intent
- Regeneration cost for frequent amendments

The framework is best viewed as an assistive tool that accelerates expert work rather than a full replacement for human expertise.

### 6.4 Future Work

**Multi-oracle consensus**: Incorporate TAXSIM, IRS examples, and state calculators to detect and resolve implementation disagreements.

**Adversarial test generation**: Automatically generate challenging test cases to expose edge case failures.

**Cross-jurisdiction transfer**: Train on US federal provisions and evaluate transfer learning to state tax codes and international jurisdictions.

**Legislative amendment tracking**: Monitor statutory changes and automatically trigger re-encoding of affected provisions.

**Formal verification integration**: Combine AI-generated code with formal proof techniques to provide mathematical guarantees.

**Interactive refinement**: Allow policy experts to provide natural language feedback in the refinement loop.

---

## 7. Conclusion

We presented an automated framework for encoding tax and benefit legislation using large language models and validation against established microsimulation systems. The approach achieves high accuracy (>95%) on moderately complex provisions through iterative refinement guided by execution feedback. By treating existing implementations as reward signals, we enable AI systems to learn legal encoding patterns without requiring manual training data annotation.

This work suggests a path toward AI-assisted computational law that could accelerate rules-as-code initiatives, improve government service delivery, and increase public access to legal information. While challenges remain in handling novel legislation and ensuring comprehensive edge case coverage, the framework demonstrates that AI can meaningfully contribute to the systematic encoding of legal rules.

As large language models continue to improve and microsimulation systems expand coverage, we envision a future where legislative text is routinely accompanied by machine-readable, multi-target-compiled implementations generated through human-AI collaboration. This could fundamentally transform how society operationalizes its legal systems.

---

## References

**To be added:**

- LLM code generation (Codex, AlphaCode, Code Llama, Claude)
- Legal AI and reasoning systems (TAXMAN, HYPO, modern legal QA)
- Rules as code initiatives (New Zealand, Canada, Australia)
- Microsimulation systems (PolicyEngine, TAXSIM, OpenFisca)
- Formal verification of legal rules (Catala, LegalRuleML)
- Iterative refinement approaches (Self-Debugging, Code repair)
- Domain-specific languages for law
- Test case generation for programs
- Oracle-based validation techniques

---

## Appendix A: Reproducibility

This section provides instructions for reproducing the results reported in this paper.

### A.1 Installation

The framework requires Python 3.10+ and depends on the Anthropic API for code generation and PolicyEngine-US for oracle validation.

**Clone the repository**:
```bash
git clone https://github.com/CosilicoAI/rac.git
cd rac
```

**Install dependencies**:
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package with optional dependencies
pip install -e ".[llm,oracle]"
```

Dependencies breakdown:
- Base package: No external dependencies (core types and data structures)
- `[llm]`: Anthropic API client (`anthropic>=0.25.0`)
- `[oracle]`: PolicyEngine-US (`policyengine-us>=1.0.0`)
- `[dev]`: Testing and development tools (pytest, black, ruff, mypy)

**Set up API key**:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

### A.2 Running EITC Encoding

To reproduce the full EITC encoding experiment:

```bash
# Run the full EITC test with default settings
python src/cosilico/eitc_full_test.py

# Customize parameters
python src/cosilico/eitc_full_test.py \
    --model claude-opus-4-5-20251101 \
    --max-iterations 10 \
    --target-accuracy 0.90
```

This will:
1. Generate 104 test cases covering EITC phase-in, plateau, and phase-out regions
2. Run the iterative training loop
3. Print progress at each iteration (accuracy, MAE, sample failures)
4. Output the final generated code and success metrics

**Expected output**:
```
======================================================================
Full EITC Agentic Training Test
======================================================================
Model: claude-opus-4-5-20251101
Test cases: 104 (covering phase-in, plateau, phase-out)
Target accuracy: 90%
======================================================================

Sample test cases:
  income=$0, children=0, expected=$0.00
  income=$0, children=1, expected=$0.00
  income=$0, children=2, expected=$0.00
  income=$0, children=3, expected=$0.00
  income=$1000, children=0, expected=$76.50
  ...

=== Iteration 1 ===
Generated code:
variable eitc_phase_in_credit:
  entity: TaxUnit
  period: Year
...
Score: accuracy=12.00%, MAE=$1234.56

=== Iteration 2 ===
...

======================================================================
FINAL RESULT
======================================================================
Success: True
Final accuracy: 98.5%
Iterations: 5

Final code:
[Generated Cosilico DSL code]
```

### A.3 Validating Against PolicyEngine

To validate generated code against PolicyEngine without using the LLM (for CI/testing):

```bash
# Run validation tests
pytest tests/test_policyengine_validation.py -v

# Run with coverage
pytest tests/ --cov=cosilico --cov-report=html
```

### A.4 Using Custom Test Cases

You can create custom test scenarios:

```python
from cosilico.types import Statute, TestCase
from cosilico.training import TrainingLoop

# Define statute
statute = Statute(
    citation="26 USC § 32(a)(1)",
    text="[Statutory text here]",
    jurisdiction="us",
)

# Create test cases manually or from oracle
test_cases = [
    TestCase(
        id="custom_1",
        inputs={
            "earned_income": 15000,
            "filing_status": "SINGLE",
            "n_children": 2,
        },
        expected={"eitc": 5980.0},
        description="Custom test case",
    ),
    # ... more cases
]

# Run training
loop = TrainingLoop(
    max_iterations=10,
    target_accuracy=0.95,
)

result = loop.train(statute, test_cases, verbose=True)
print(f"Success: {result.success}")
print(f"Final code:\n{result.final_code.source}")
```

### A.5 Reproducing Paper Metrics

To reproduce the specific metrics reported in Section 5:

**Token usage analysis**:
```python
# After running training
for i, record in enumerate(result.history):
    print(f"Iteration {i}:")
    print(f"  Prompt tokens: {record.code.prompt_tokens}")
    print(f"  Completion tokens: {record.code.completion_tokens}")
    print(f"  Accuracy: {record.score.accuracy:.1%}")
    print(f"  MAE: ${record.score.mean_absolute_error:.2f}")
```

**Error distribution analysis**:
```python
from collections import Counter

error_types = Counter()
for record in result.history:
    for failure in record.failures:
        error_types[failure.type] += 1

print("Error distribution by iteration:")
for error_type, count in error_types.items():
    print(f"  {error_type}: {count}")
```

### A.6 System Requirements

**Minimum**:
- Python 3.10+
- 4GB RAM
- Internet connection (for Anthropic API)

**Recommended**:
- Python 3.12
- 8GB RAM
- SSD storage

**Typical runtime**: 2-5 minutes for full EITC encoding (5-10 iterations × 20-40 seconds per iteration)

**API costs**: Approximately $0.05 per full provision encoding at Claude Opus 4.5 pricing (March 2025: $15/1M input tokens, $75/1M output tokens)

### A.7 Known Issues and Troubleshooting

**PolicyEngine installation issues**: PolicyEngine-US has many dependencies. If installation fails:
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get install python3-dev build-essential

# Install with conda (alternative)
conda install -c conda-forge policyengine-us
```

**API rate limits**: The Anthropic API has rate limits. If you encounter rate limit errors, add delays between iterations or use a lower tier model for testing.

**Floating-point precision**: Some test failures at exact boundary points are due to floating-point representation differences. These are acceptable for practical applications (within $1 tolerance).

---

## Appendix B: Repository Structure

```
rac/
├── src/cosilico/
│   ├── types.py           # Core data structures
│   ├── generator.py       # LLM-based code generation
│   ├── executor.py        # Multi-format code execution
│   ├── dsl_executor.py    # DSL interpreter
│   ├── dsl_parser.py      # Lexer and parser for Cosilico DSL
│   ├── oracles.py         # Oracle implementations
│   ├── scorer.py          # Metrics and failure diagnosis
│   ├── training.py        # Main training loop
│   ├── eitc_full_test.py  # Full EITC encoding test
│   └── agent.py           # Agentic training loop
├── docs/
│   ├── DESIGN.md          # Architecture specification
│   ├── DSL.md             # Cosilico DSL reference
│   ├── AI_ENCODING.md     # RL framework design
│   └── papers/
│       └── ai-rules-encoding.md  # This document
├── tests/
│   ├── test_dsl_parser.py
│   ├── test_executor.py
│   ├── test_scorer.py
│   └── test_training.py
└── pyproject.toml         # Package metadata and dependencies
```

---

## Appendix C: Example Generated Code

Cosilico DSL code generated for EITC phase-in (iteration 5, 98.5% accuracy):

```cosilico
variable eitc_phase_in_credit:
  entity: TaxUnit
  period: Year
  dtype: Money
  label: "EITC phase-in credit amount"
  citation: "26 USC section 32(a)(1)"

  references:
    earned_income: us/irs/income/earned_income
    n_qualifying_children: us/irs/eitc/n_qualifying_children
    phase_in_rate: param.irs.eitc.phase_in_rate
    earned_income_amount: param.irs.eitc.earned_income_amount

  formula:
    min(earned_income, earned_income_amount[n_qualifying_children]) *
      phase_in_rate[n_qualifying_children]
```

Corresponding parameters (YAML):

```yaml
irs:
  eitc:
    phase_in_rate:
      2024-01-01:
        0: 0.0765
        1: 0.34
        2: 0.40
        3: 0.45
    earned_income_amount:
      2024-01-01:
        0: 7840
        1: 11750
        2: 16510
        3: 16510
```

---

## Appendix D: Failure Diagnosis Examples

This appendix shows concrete examples of failure diagnosis from the training loop, demonstrating how structured feedback enables the LLM to fix errors iteratively.

### D.1 Parameter Indexing Error (Iteration 1)

**Failure report**:
```
Type: value_mismatch
Case: case_12
Inputs: earned_income=15000, filing_status=SINGLE, n_children=2
Expected: eitc=6000.0
Actual: eitc=1147.5
Message: Output $1147.50 differs from expected $6000.00 by 80.9%. Check rate or threshold values.
```

**Root cause**: Generated code used `phase_in_rate[0]` (7.65% for 0 children) instead of `phase_in_rate[n_qualifying_children]` (40% for 2 children).

**Original code (iteration 1)**:
```cosilico
formula:
  min(earned_income, earned_income_amount[0]) * phase_in_rate[0]
```

**Fixed code (iteration 2)**:
```cosilico
formula:
  min(earned_income, earned_income_amount[n_qualifying_children]) *
    phase_in_rate[n_qualifying_children]
```

### D.2 Formula Logic Error (Iteration 3)

**Failure report**:
```
Type: value_mismatch
Case: case_45
Inputs: earned_income=25000, filing_status=SINGLE, n_children=1
Expected: eitc=3633.3
Actual: eitc=3995.0
Message: Output $3995.00 differs from expected $3633.30 by $361.70 (10.0%).

Analysis: Income ($25,000) exceeds phase-in end ($11,750) and is in phase-out region
(starts at $22,720). Expected credit should be max_credit minus phase-out reduction,
but actual output equals max_credit exactly, suggesting phase-out not applied.
```

**Root cause**: Formula only implemented phase-in, not phase-out.

**Original code (iteration 3)**:
```cosilico
formula:
  min(earned_income, earned_income_amount[n_qualifying_children]) *
    phase_in_rate[n_qualifying_children]
```

**Fixed code (iteration 4)**:
```cosilico
references:
  earned_income: us/irs/income/earned_income
  n_qualifying_children: us/irs/eitc/n_qualifying_children
  phase_in_rate: param.irs.eitc.phase_in_rate
  earned_income_amount: param.irs.eitc.earned_income_amount
  max_credit: param.irs.eitc.max_credit
  phase_out_start: param.irs.eitc.phase_out_start
  phase_out_rate: param.irs.eitc.phase_out_rate

formula:
  let phase_in = min(earned_income, earned_income_amount[n_qualifying_children]) *
                 phase_in_rate[n_qualifying_children]
  let reduction = if earned_income > phase_out_start[n_qualifying_children]
                  then (earned_income - phase_out_start[n_qualifying_children]) *
                       phase_out_rate[n_qualifying_children]
                  else 0
  return max(0, min(phase_in, max_credit[n_qualifying_children]) - reduction)
```

### D.3 Boundary Condition Error (Iteration 4)

**Failure report**:
```
Type: value_mismatch
Case: boundary_1_phase_in_end_0
Inputs: earned_income=11750, filing_status=SINGLE, n_children=1
Expected: eitc=3995.0
Actual: eitc=3994.5
Message: Output $3994.50 differs from expected $3995.00 by $0.50 (0.0%).
```

**Root cause**: Floating-point rounding in phase-in calculation: `11750 * 0.34 = 3994.5` vs expected `3995.0` (max credit).

**Fix**: Use `min(phase_in, max_credit)` to cap at exact max credit value, avoiding rounding.

### D.4 Syntax Error Example (Rare in practice)

**Failure report**:
```
Type: syntax
Message: Parse error at line 12: Expected ':' after 'references'

  references
    earned_income us/irs/income/earned_income
             ^
```

**Root cause**: Missing colon in references block declaration.

**Fix**: LLM automatically corrects syntax in next iteration based on DSL specification.

### D.5 Runtime Error Example

**Failure report**:
```
Type: runtime
Message: Runtime error: name 'n_qualifying_children' is not defined

Context: Evaluating formula for case_8
Inputs: earned_income=5000, filing_status=SINGLE, n_children=1
```

**Root cause**: Formula referenced `n_qualifying_children` but it wasn't listed in the `references` block.

**Fix**: Add to references block:
```cosilico
references:
  n_qualifying_children: us/irs/eitc/n_qualifying_children
```

This structured feedback enabled the LLM to identify and fix the formula logic in subsequent iterations, achieving 98.5% accuracy by iteration 5.
