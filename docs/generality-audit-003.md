# Generality audit 003 — ten more random UK sections

## Method

Same method as [audit 001](generality-audit-001.md) and [audit 002](generality-audit-002.md): sample ten UK legislation sections at random via Lex, excluding anything already covered, and attempt to round-trip each against the current DSL. Sample is in [`diverse-uk-legislation-sample-003.md`](../diverse-uk-legislation-sample-003.md). Between audit 002 and this one, the DSL gained `period_start`, `period_end`, `days_between`, and `date_add_years`. UC got its reg 24(2) first-child-premium fix, and every programme is now covered by a fidelity entry in [`docs/fidelity.md`](fidelity.md).

## Per-section verdicts

**7 fit cleanly** — big jump from 3/10 in both previous audits.

**SSCBA 1992 s.9** (secondary Class 1 NIC) fits. The charge is `percentage × max(0, earnings − secondary_threshold)`, with the percentage chosen by an if-chain over apprentice status and age-related-rate eligibility, and an optional piecewise split at the upper secondary threshold. Every branch expressible with scalar arithmetic, comparisons, effective-dated parameters, and a bool/text input for age group. No new primitives needed.

**Child Support Act 1991 Sch 1** (maintenance formula) fits for the nil/flat/basic tiers. Priority cascade (`if nil else if flat else basic`) works as nested `if`. The basic-rate percentage lookups by number of qualifying children are integer-indexed parameter lookups. The relevant-other-children discount is a pre-`if`-chain scalar adjustment. The reduced-rate band between £100 and £200 is set by separate regulations not in Sch 1 itself — legitimately out of scope of the schedule, so excluded.

**SSI 2021/249 reg 79** (Scottish CTR daily maximum) fits. Uses `period_start` and `period_end` with `days_between` to compute days in the financial year. Band E–H taper via effective-dated parameter lookup. Student exclusion via `count_related` with a `where` predicate. This is the cleanest test yet of the new period primitives against a daily-apportionment rule.

**UKSI 2006/965 reg 2** (child benefit enhanced rate) fits *if* the `is_eldest_in_household` flag is pre-computed per child and supplied as input. The pattern of count_related with filters for enhanced-rate and standard-rate groups, then multiplying by the respective rate, mirrors the UC first-child-premium fix. The per-child voluntary-org and residing-with-parent exclusions also go in the where clause. Pre-computing "eldest" is reasonable because the caller's data model will naturally order children by DOB — the same argument that made UC's `is_higher_rate_first_child` acceptable. The DSL would need argmin-over-relation to do it without pre-computation.

**CTA 2010 s.18A** (small profits rate) fits — it's the sibling of s.18B already encoded. Same pattern: eligibility as an `and` of inputs, rate as a parameter, tax as `profits × rate`. The small-profits-rate path is the part missing from the existing CT marginal relief programme (a fidelity gap noted in [`docs/fidelity.md`](fidelity.md)); adding it would give full-width CT coverage.

**FA 2013 s.99** (ATED annual chargeable amount) fits cleanly and is an excellent test of the new period primitives. The band table is expressible as a nested `if` over taxable value, selecting the annual amount. The N/Y part-year apportionment (reg 99(6)) is `days_between(entry_day, period_end) + 1` divided by `days_between(period_start, period_end) + 1`. Encoded below as a proof.

**Pensions Act 2008 s.3** (auto-enrolment duty) fits. Age gate (22–SPA), earnings trigger pro-rated by pay-reference-period length (straightforward scalar math using `prp_months / 12` as input), and three anti-joins (not active member, not recently opted out, not already enrolled) — all expressible. Age-at-date would need `date_add_years` on DOB plus comparison if done in the DSL; easier to supply current age as an input per convention.

**ERA 1996 s.108** (unfair-dismissal qualifying period) fits for the single-span case. The two-year test is `date_add_years(span_start, 2) <= effective_date_of_termination`. The one-month carve-out for s.64(2) dismissals is a parameter swap driven by an input bool. The twenty-odd exception sections (s.99 to s.105, reg 28 TICE, reg 7 PTW, reg 6 FTE, reg 42 ECR, etc.) all disapply the qualifying period — encodable as a long `or` of bool inputs, one per exception. Multi-span continuous-employment rules (ss.210–219 covering strike breaks, TUPE transfers, reinstatement) are the genuine partial — we'd need interval arithmetic to aggregate continuous stretches across gaps, which is out of scope.

**2 partial fits.**

**UKSI 2015/173 reg 10** (state pension deferral increment) fits in arithmetic — `base_rate × (1 + deferral_weeks × (1/9)/100)` — but the deferral-weeks count is itself a sum over a set of deferral intervals (the gap between SPA and first claim, plus every suspend/resume cycle). Summing per-interval lengths requires either `sum_related` over an expression derived per related record (the "weeks in this interval" computation) — which we don't support — or pre-computing total_deferral_weeks outside the DSL. The latter is a hollow fit: the whole rule is the summation.

**ITEPA 2003 s.180** (beneficial-loan £10,000 threshold) is partial heading towards fail. "At all times in the year the amount outstanding does not exceed £10,000" is a max-over-days test against an aggregate that itself sums across two or more loans. That's two levels of aggregation where one is max-over-time — beyond what the DSL expresses today. Supplying `max_yearly_balance` as an input would reduce the rule to `input <= 10000`, which is not really the rule. Counted as fail.

**1 fail outright.**

**ITEPA 2003 s.180** as above.

## Score across all three audits

| | Audit 001 | Audit 002 | Audit 003 |
| --- | --- | --- | --- |
| Fit cleanly | 3 | 3 | 7 |
| Partial | 4 | 5 | 2 |
| Fail | 3 | 2 | 1 |

Across 30 sampled sections: 13 fit cleanly, 11 partial, 6 fail. Before the period primitives and Date dtype landed, audit 003 would have scored roughly 4/10 fit (SSI reg 79, ATED, unfair dismissal, and auto-enrolment all need date or period arithmetic). So the recent additions moved the rolling clean-fit ratio up meaningfully.

## Ranked operator gaps after audit 003

Still in play, in rough order of recurrence and leverage:

**Cumulative / rolling aggregation over time**. Audit 001 theatre tax relief, audit 002 VAT threshold, audit 003 beneficial-loan threshold, deferral increment. Four sections across thirty. "Maximum over days in the year of the sum of loan balances" and "sum weeks across a set of intervals" are both instances of the same underlying need. This is now the single most-recurrent unaddressed gap.

**Argmin/argmax over a relation**. Audit 003 child benefit reg 2 needs the eldest child in the household. Workable today by pre-computing an `is_eldest` flag, but it's a structurally-addressable primitive: pick the record with the extreme value on some input, surface a bool on each record.

**`sum_related` over a derived-per-record value**. Already flagged as a limitation; bites in audit 003's deferral increment (weeks per interval is a derived value, not an input). Relaxing this would unlock the deferral rule and several others.

**Per-related-record parameter lookup**. Audit 002 IHT NRB transfer. Not in audit 003. Low recurrence but likely widespread across historical rules.

**FY-straddle apportionment**. Audit 002 CT marginal relief, audit 003 CT small profits rate. Same gap, same two sections.

**Multi-span continuous-employment**. Audit 003 unfair dismissal. Needs interval aggregation with gaps.

**Counterfactual**. Still the biggest and hardest. Lower recurrence than I initially thought — fewer than 5/30 sections truly need parameter/input overlays. Subjective "reasonable grounds" and "most beneficial" are qualitative judgments that belong outside the DSL.

**Cross-entity pair-keyed derivation**. Relatively few audit-003 sections hit this — the child benefit tie-break across cohabiting-partner households is the one that approaches it, but even that can be done by pre-computing household membership.

## What this says

We are closing on saturation for sections that are arithmetic over a period with a well-defined entity. The remaining gaps cluster heavily on time-aggregation (rolling sums, max-over-days, count-weeks-across-intervals) and on derived-value aggregation. A `max_over_days` or `sum_intervals` primitive that sweeps a relation with per-record day ranges and returns either a max of per-day aggregates or a summed interval length would address four of the six remaining sections across all three audits.

Also still outstanding: counterfactual (honestly now 3–4/30), cross-entity pair-keyed (3–4/30). Both remain worth doing but audit evidence suggests they unlock less than the time-aggregation primitive would.

## Proof

Encoded alongside this audit: FA 2013 s.99 ATED ([`examples/ated_program.yaml`](../examples/ated_program.yaml), [`examples/ated_cases.yaml`](../examples/ated_cases.yaml), [`python/examples/run_ated_cases.py`](../python/examples/run_ated_cases.py), and a matching dense test). This is the cleanest end-to-end test of `period_start`, `period_end`, `days_between`, and the band-table pattern. Cases cover the six band amounts and the part-year apportionment.

## Suggested next round

Implement `max_over_days` or a period-sweep primitive. Re-sample ten more sections. Target 8–9/10 clean fits in audit 004.
