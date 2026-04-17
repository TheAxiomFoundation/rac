# Generality audit 002 — ten more random UK sections

## Method

The same method as [audit 001](generality-audit-001.md): sample ten sections at random from UK primary and secondary legislation via Lex, excluding anything already covered, and attempt to round-trip each through the current DSL. A section "fits" only if it can be written by hand, run against cases, compiled to dense, and benchmarked at millions per second — anything less counts as partial or fail. The ten sections used here are in [`diverse-uk-legislation-sample-002.md`](../diverse-uk-legislation-sample-002.md). Between audit 001 and this one, the DSL gained filtered aggregation, a `Date` dtype with `date_add_days`, `floor`, source citations, and explain-mode traces.

## Per-section verdicts

**3 fit cleanly.**

**Pensions Act 2014 s.4** (transitional state pension entitlement) fits cleanly and has been encoded end-to-end in [`examples/state_pension_transitional_program.yaml`](../examples/state_pension_transitional_program.yaml). The rule asks whether someone has reached pensionable age, whether their qualifying-year count meets a regulator-set minimum, and whether at least one of those years falls before the 2016 commencement (or is deemed via SI 1979/643 reg 13(1)). The encoding uses `count_related` with a `where` predicate filtering qualifying-year records by date range — the exact pattern that only became expressible after the Date dtype and filtered aggregation landed. Six cases cover classic pre-commencement entitlement, the mixed pre/post case, the three ways to fail (age, minimum, pre-commencement), and the reckonable-1979 deeming. All six match expected; dense matches explain byte-for-byte (`dense_state_pension_transitional_matches_explain_mode`). This is the main new demonstration from this audit.

**LBTT (Scotland) 2013 s.25** (Scottish LBTT banding) fits cleanly. The band/slice/rate pattern is the same shape as the rUK income tax band structure, just over transaction consideration rather than annual income, with bands indexed by transaction type. Core computation uses `parameter_lookup` indexed by band number plus `max(0, min(C, u) − l) × rate` summed across bands. Reliefs (first-time buyer, multiple dwellings, additional dwelling supplement) are additive modifiers that can be folded in the same way the UC programme handles its various element types. Schedule 19 (lease rent NPV) is a separate computation over a different base, not a variant of this one. Not yet implemented as a worked example; no new operators would be needed for the core banding.

**ITA 2007 s.35** (personal allowance with £100k taper) fits cleanly and overlaps with what the existing UK income tax programme already does. The four-step adjusted-net-income definition (`net_income − gift_aid − pension_contributions + s.457/458_addback`) is straightforward scalar arithmetic; the taper is an `if` on the threshold; the £1 rounding is `ceil`. Nothing new needed. Would be useful to split out of the income tax programme so other programmes (marriage allowance) can reuse it.

**5 partial fits.**

**IHTA 1984 s.8A** (nil-rate band transfer between spouses) is partial. The percentage-per-deceased-spouse formula can be encoded if each deceased's E, VT, and NRBMD at death are supplied as inputs — `sum_related` over claimed deceased spouses gives the aggregate percentage, and `min(total_pct, 100)` caps at 100%. What does not fit: the parameter lookup for NRBMD at *each deceased spouse's death date*, which is a per-related-entity effective-dated lookup. Our `parameter_lookup` resolves against the query period, not against arbitrary per-record dates. A workaround is to pre-compute NRBMD per deceased spouse as an input on that spouse — which is the same kind of pre-computation that appeared in audit 001. A better answer would be per-related-record parameter lookups.

**TCGA 1992 s.1K** (annual exempt amount for CGT) is partial. The deduction value fits cleanly (`min(AEA, net_gains_after_same_year_losses)`, gated on not claiming remittance basis or foreign election). What does not fit: the allocation of the deduction across gains at different rates, described in subsection (5) as "in whatever way is most beneficial to the person". That is taxpayer optimisation, not a deterministic rule. The PR substitution for the year of death plus two (subsection (7)) also doesn't fit naturally — it is an entity substitution over a temporal window, which would be easiest if derived entities were first-class.

**CTA 2010 s.18B** (corporation tax marginal relief) is partial. The headline formula `F × (U − A) × (N / A)` fits cleanly. The associated-company count fits with `count_related`. What does not fit: the pro-rating of the upper and lower limits by `days(AP) / 365` when the AP is not a whole year, and the apportionment when the AP straddles two financial years with different F, U, L. The first needs a period-length primitive; the second needs either multi-period aggregation or explicit apportionment operators. Both are legally material — most APs in practice do not align with the financial year.

**ERA 1996 s.162** (statutory redundancy pay) is partial. The 20-year look-back, the three age-band weighting (1.5 / 1.0 / 0.5 weeks), and the sum-over-years structure all fit in principle using `sum_related` over a year-of-service relation where each year carries its own weight as a pre-computed input. What does not fit naturally: computing the age-at-each-year-boundary inside the DSL. Our `date_add_days` can approximate year arithmetic via day counts but misses leap-year precision, and legally the weight hinges on the employee's age "in that year of employment" — a year-exact calculation. In practice callers would pre-compute the weight per year-of-service as an input, which pushes the hardest part outside the DSL.

**SI 2009/470 reg 44** (student loan repayments) is partial. The per-plan pro-rated threshold, the 9%/6% rates, the concurrent plan aggregation, the default threshold fallback when the borrower is non-compliant, the floor-to-whole-pounds rounding — all of these fit. The remaining gap is the pro-rating of thresholds by earnings-period length versus tax-year length, which needs a period-length primitive. Close to a clean fit; only one operator away.

**1 fail outright.**

**VATA 1994 Sch 1 para 1** (VAT registration threshold) fails. The historic test is a rolling 12-month taxable-supply sum evaluated at every month-end; the forward test is a 30-day forecast; the release valve at £88,000 is another 12-month forecast. The rule cannot be expressed in the current DSL because it requires aggregation over a window of periods (the last twelve months) and counterfactual forecasts. Callers could pre-compute the rolling sum and supply it as an input, but then the rule reduces to `input > £90,000`, which is not really the rule. This is an honest failure and maps to the "cumulative over a sliding window" gap already flagged in audit 001 via CTA 2009 s.1217J.

**1 legally unusual — fits technically, but the meaningful content is qualitative.**

**CA 2006 s.172** (directors' duty to promote success) is expressible as a Bool check over input flags — good faith, factor-consideration bits, insolvency state, company purpose — but the real content of the duty is the qualitative good-faith assessment courts actually perform. The DSL can model the mechanical breach test, and that is legally meaningful (failing to "have regard to" a listed factor at all is actionable), but it does not capture the hard part. This is honest: legal rules that turn on qualitative judgment are not what the DSL is for, and forcing them through the DSL is over-reach. Counted as a non-fit for the generality score.

## Score versus audit 001

| | Audit 001 | Audit 002 |
| --- | --- | --- |
| Fit cleanly | 3 | 3 |
| Partial | 4 | 5 |
| Fail | 3 | 2 |

The clean-fit count is static at 3/10, which is important to report honestly: the recent operator additions (filtered aggregation, Date, Floor, citations, traces) did not move any audit-001 *section* from partial to fit, but they did make one audit-002 section (Pensions Act s.4) a clean fit that would not have been before. They also converted audit-001's CTR reg 71 from partial to fit (demonstrated in code). So two additional sections (one in each audit) are fully expressible because of the recent additions.

The partial count grew slightly (4 → 5) and the fail count shrank (3 → 2). That reflects the DSL becoming able to express *parts* of more sections, even where it cannot express the whole. That is a real improvement and the right direction, but it also means the DSL's "boundary" is widening faster than the "inside" — most of what remains is close but not quite, and the gaps tend to be the same ones.

## Ranked operator gaps after audit 002

Combining both audits and ordering by recurrence:

**Cumulative / rolling aggregation over a window of periods.** Audit 001's CTA 2009 s.1217J (cumulative prior deductions) and audit 002's VATA Sch 1 para 1 (rolling 12-month turnover) both need this. It is also implicit in TCGA s.1K's brought-forward losses. Effectively three sections across the two audits. A sum-over-past-N-periods operator is the minimum; a more general approach is a periodic recursion that lets a derived reference its own value in the prior period.

**Period-length primitives.** Audit 002's CTA s.18B, ERA s.162, and SI 2009/470 reg 44 all need "how long is this period" or "how does this period relate to a reference period". Three sections out of ten. A `period_start` / `period_end` pair of expressions returning `Date`, plus a way to compute a ratio of two periods' lengths (in whatever unit the legislation demands), would close all three. Keep it period-oriented rather than day-oriented to avoid baking in day-centrism.

**Per-related-record parameter lookup.** Audit 002's IHTA s.8A needs to look up the nil-rate-band maximum at each deceased spouse's death date, not at the query period. Currently parameters resolve against the query period only. A `parameter_lookup` variant that takes a per-related-record date would solve this. One section so far, but likely to recur in anything historical and multi-entity.

**Counterfactual evaluation.** Still the biggest. Audit 001 had CTA 2009 s.1169 anti-avoidance (3-4/10 including marginal cases); audit 002 has TCGA s.1K "most beneficial" allocation, CA 2006 s.172 "would be most likely", VATA Sch 1 "reasonable grounds for believing". Across the twenty sampled sections the counterfactual / subjective-forecast pattern appears 6–7 times. By far the most recurrent unaddressed gap.

**Cross-entity / pair-keyed evaluation.** Audit 001 flagged this at 3-4/10 (marriage allowance cross-entity, Children Act s.2 derived relation, SPP/SAP person×employer×day). Audit 002 adds IHTA s.8A (survivor × each deceased) and TCGA s.1K (individual vs PR substitution). Still 4-5/10 overall. No movement since audit 001 because the underlying structural change hasn't been made.

**Derived periods.** Audit 001's NISR 1996/198 reg 152 defines a period as its output. Audit 002 doesn't add a clear example but TCGA s.1K's "year of death + two" window is adjacent. 1/10 each audit.

**Year-exact date arithmetic.** Audit 002's ERA s.162 redundancy-pay age bands want exact-year reckoning backwards from the relevant date. Our `date_add_days` is approximate for year arithmetic because of leap years. A `date_add_years` operator or a more general calendar-unit arithmetic would fix it. 1/10.

## What this says about next moves

Counterfactual is still ranked first across the twenty sections, but it is also the hardest to design well. Period-length and cumulative/rolling aggregation together touch half of audit 002's partials and are both concrete engineering changes without deep semantic work.

If the aim is "biggest unlock per unit effort", the ordering is: (1) period-length primitives (one week of work, three sections unlocked), (2) per-related-record parameter lookup (smaller, one section unlocked but likely many more across the corpus), (3) cumulative / rolling aggregation (medium effort, two to three sections). Counterfactual and cross-entity pair evaluation remain the big structural moves and should be done next once the smaller additions above have been run through another audit.

Between audits we should also split ITA 2007 s.35 out of the UK income tax programme and into a standalone personal-allowance programme, and build out LBTT s.25 as a worked Scottish tax example. Both are clean fits today.
