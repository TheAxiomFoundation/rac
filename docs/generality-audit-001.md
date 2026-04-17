# Generality audit 001 — ten random UK sections

## Method

Ten UK legislation sections were sampled via the Lex API with broad queries (not curated), spanning tax, benefits, pensions, family, corporate, property, devolved, and employment law. The full sample and operative text is in `diverse-uk-legislation-sample.md`. Each section was assessed against the current RAC DSL on the question: can we write this section in the DSL by hand, run it in explain mode against realistic cases, compile it into the dense path, and benchmark it at millions of rows per second? Anything short of all three is a gap. The goal is not to patch individual sections but to identify patterns that recur and would generalise.

Current DSL capabilities, for reference: scalar types (bool, integer, decimal, text, judgment); effective-dated integer-keyed parameters; arithmetic (add/sub/mul/div/max/min/ceil); conditional `if`; three-valued judgments with and/or/not; single-entity evaluation; `count_related` and `sum_related(input)` aggregations. No interval output, no date arithmetic, no cross-entity derivation, no counterfactual, no per-tuple evaluation, no filtered aggregation.

## Per-section verdicts

Three sections round-trip cleanly today.

**Housing Benefit Regulations 2006 reg 70** (max HB = weekly eligible rent minus non-dependant deductions) fits natively: `sum_related` over non-dependants, scalar subtraction, floor at zero. The banded non-dep deduction table has to be fed as a per-non-dependant input rather than looked up inside the aggregation; in practice that is what callers will do anyway, but it is technically a simplification.

**Pensions Act 2008 s.13** (qualifying earnings = clamp(gross, lower, upper) − lower, pro-rated by pay reference period length) fits cleanly. The pay reference period length comes in as an input on the custom period, the lower and upper thresholds are effective-dated parameters, and the arithmetic is max/min/sub.

**Public Service Pensions Act 2013 s.10** (normal pension age = 60 for uniformed services, else max(state pension age, 65)) fits. Category membership would be ergonomic as a set-membership operator rather than an OR-of-equalities, but this is cosmetic.

Four sections round-trip partially — the core computation fits if we pre-compute away the hard part, but the hard part is exactly what the legislation is about.

**Income Tax Act 2007 s.55B** (marriage allowance transfer): the entitlement half fits — basic-rate check, residence check, anti-join on the s.45/46 claim, effective-dated transferable amount. The corresponding reduction of the relinquishing spouse's personal allowance is a second output on a different entity (the relinquisher). The DSL has no way to express that both people receive derived outputs from the same rule. A separate programme keyed on the relinquisher would duplicate the election check. The dividend-nil-rate caveat ("would for that year not be liable at upper rate if s.13A were omitted") is a counterfactual we cannot express.

**Corporation Tax Act 2009 s.1217J** (theatre tax relief additional deduction): the per-period formula `min(UK, 80% × total) − prior_deductions` fits if we supply cumulative UK expenditure, cumulative total expenditure, and cumulative prior deductions as inputs per period. The fact that `prior_deductions(i)` is itself the sum of `additional_deduction(1..i-1)` is a cross-period recursion the dense path refuses (`cyclic dense compilation dependency`). A real implementation would need cross-period fixed-point evaluation.

**Housing Benefit reg 70** as noted above — partial only under a strict reading. Counted as fits above.

**Scottish CTR reg 71** (notional capital): the notional capital figure is a filtered sum — `Σ amount over disposed assets WHERE purpose = secure_CTR AND reason ∉ {debt, reasonable_purchase}`. `sum_related` has no predicate today. The counterfactual unclaimed-capital clause ("would have been acquired had it been sought") and the UC cross-reference add further counterfactual dependencies. Opinion-of-authority features three times in subtle ways: the authority's opinion that the purpose was to secure CTR is itself a legal fact the DSL would need to consume as a first-class qualitative judgment input.

Three sections fail outright.

**Children Act 1989 s.2** (parental responsibility) cannot be encoded at all. The output is itself a relation — `has_PR(person, child, t)` — not a scalar per entity. It evolves monotonically over events (acquisition/cessation). The DSL derives only scalars and judgments under a single entity; it has no concept of derived relations, no event-accumulation over time, and no pair-keyed evaluation.

**ESA Regs 2008 reg 166** (relevant week for part-weeks) and **SPP/SAP reg 35A** (meaning of "week"): both compute an interval as output. The DSL has no interval-valued output type and no interval arithmetic (shift by N days, intersect, anchor to next weekday). Neither can be encoded at all.

**CTA 2009 s.1169** (anti-avoidance: disregard transactions whose arrangements have a disqualifying main purpose): the rule is inherently counterfactual — the disqualifying test compares "relief obtained" against "relief the company would otherwise be entitled to". Without a counterfactual evaluator, the section reduces to "trust an opinion input".

Summary: 3 fit, 4 partial, 3 fail outright. 7 of 10 sections expose at least one gap that cannot be papered over.

## Ranked operator and type gaps

Ordered by recurrence across the ten sections, not by implementation difficulty.

**Counterfactual evaluation** (sections 1, 2, 9 marginally, 10) — 3–4/10. The ability to ask "what would X be if Y were different?" — different parameters, different facts, different statutory text. This is the single most recurrent gap across law generally and features prominently in the Axiom pitch deck for exactly this reason. Minimum design: a `counterfactual` expression that runs a sub-evaluation against an overlay dataset or overlay parameter set, returning the counterfactual scalar. Overlay model rather than rerunning the whole programme. Would need a clear answer on which evaluations are allowed to be counterfactual (parameters-only, or facts too) and on caching.

**Cross-entity / multi-entity evaluation** (sections 1, 3, 6, and arguably 10) — 3–4/10. The ability for a rule about person A to also emit outputs on person B (marriage allowance reducing the relinquisher's PA), or to be keyed on a pair (parental responsibility of person × child, employment continuity of person × employer). Current evaluator runs per (entity_id, period). Minimum design: allow derived outputs to declare their entity dynamically (e.g. `entity_expr: related_entity_id`), or support pair-keyed entities where the entity type is itself a tuple. Pair-keyed is simpler and covers most cases; it requires indexing relations by both slots and carrying a pair-id through the evaluator. The dense path would need a second level of offsets to handle pair-keyed aggregation.

**Interval output and interval arithmetic** (sections 5, 6) — 2/10 explicit, but it underpins every mention of "part-week", "tax year", "accounting period" in law. Minimum design: add an `Interval` dtype, plus operators `interval.shift(days)`, `interval.intersect(other)`, `interval.anchor_next_weekday(dow)`. At the engine level, Interval becomes a fourth scalar alongside bool/integer/decimal/text; at the dense level it's two date columns. Date arithmetic (`next_saturday`, `day_count`) falls out of this.

**Filtered aggregation** (sections 7, 10) — 2/10. `sum_related(R, value) WHERE predicate` and `count_related(R) WHERE predicate`. The predicate is evaluated per-related-record against inputs on that related record. Current DSL has `sum_related(input)` only, with no per-record predicate. Minimum design: extend `SumRelated` and `CountRelated` variants with an optional `where: JudgmentExpr` that evaluates on the related record's inputs. The dense path already materialises related-record columns, so filtering is cheap. This also subsumes the "SumRelated over derived values per related entity" gap if we allow the predicate to reference cross-related-derivations.

**Cross-period accumulation / fixed-point** (sections 4, 9's accrued-benefits recomputation) — 1–2/10. A derived output whose value in period P depends on its own value in prior periods. Minimum design: `prior(derived_name, offset: periods)` as an expression, with an explicit base-case and a declared iteration direction. Engine evaluates periods in order; dense path lifts iteration to a cumulative scan over a period dimension added alongside the row dimension.

**Derived relations as outputs** (section 3) — 1/10, but the only way to encode entire areas of family and attribution law. Minimum design: add `RelationDerived` alongside scalar `Derived`, producing tuple sets whose schema is declared. Consumers use the derived relation in the same slots as input relations. In the dense path, derived relations are produced as offsets + tuple columns. This is the biggest structural change on the list — but without it, entire statutes in family and attribution law are off-limits.

**Qualitative/opinion input as first-class** (sections 2, 10) — 2/10. Law often turns on the opinion of a person or authority. Today this has to be modelled as a bool or judgment input, which works for single-entity evaluation but loses the crucial distinction between "no opinion has been formed" and "the opinion was negative". Minimum design: a `ThreeValuedInput` dtype that produces a judgment (holds/not_holds/undetermined) directly from the dataset, rather than a bool that compares as holds/not_holds. Small, cheap, subsumes the under-determined case the Axiom deck flags as the difference between `not_holds` and `not_established`.

**Set-membership operator** (section 9 ergonomic, sections 3 and 10 marginally) — 1–3/10. `x in (a, b, c)` as a judgment expression, compiling to an OR of equalities. Pure ergonomics — expressible today but noisy.

**Day-level / variable-period granularity** (section 6 explicit, section 3 continuous) — 1/10 as the primary gap but implicit in any law that talks about day counts. Probably falls out of interval arithmetic.

## What this says about current generality

Three sections out of ten round-trip cleanly today. That is a reasonable starting point given the DSL has seven expression kinds and two aggregation primitives, but seven of ten is a lot of law still out of reach. The gaps cluster: counterfactual, cross-entity, intervals, filtered aggregation. Of those four, filtered aggregation is the cheapest to add and unlocks two sections immediately. Interval arithmetic is a medium lift (new dtype, new operators, dense representation) and unlocks a family of time-based rules. Cross-entity evaluation is a structural change to the engine but addresses the widest range of remaining law. Counterfactual is the hardest and most conceptually distinct — it asks the engine to run sub-evaluations, which touches caching and explain-mode behaviour — but it is also the single most-cited pattern in the deck and in the sample.

One cheap win per operator added would not be the right metric; the right metric is how much additional law each addition brings inside the DSL's boundary. Filtered aggregation is small work and brings in 2/10. Cross-entity pair evaluation is moderate work and brings in roughly 3/10 plus whole areas of family and employment law. Counterfactual is large work but brings in a pattern that recurs in nearly every anti-avoidance provision, many tax benefits, and most pension rules — likely 4/10 on this sample but far more across the corpus.

Nothing in the sample justifies a bespoke operator for a single legal pattern. Every proposed addition above covers at least two sections and should cover many more outside the sample. The DSL today is narrower than it looks — the count_related anti-join generalised well (free within the existing design), but each of the four big gaps above would mean meaningful engine work, and the case for doing each of them comes from legislation itself, not from patching individual sections.

## Suggested next round

If the question is what to build next, filtered aggregation is the obvious smallest step — it is additive to the existing `SumRelated`/`CountRelated` variants, it compiles straightforwardly in the dense path, and it brings in a concrete section (HB reg 70 without the simplification, CTR reg 71's notional capital) on an operator we already nominally have. After that, either interval arithmetic (medium lift, unlocks time-based rules) or cross-entity pair evaluation (larger lift, unlocks family and attribution law). Counterfactual after those, because it depends on the engine being settled enough to host sub-evaluations cleanly.

None of this should be done without a fresh generality audit of another ten random sections once each addition lands.
