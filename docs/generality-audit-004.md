# Generality audit 004 — ten more random UK sections

## Method

Same as audits 001–003: ten fresh sections sampled via Lex across different statute types. The DSL has not changed since audit 003 (notes from that round led to walking back `date_add_years` and reframing `days_between` as a narrow primitive, but neither move alters what can be encoded). Sample in [`diverse-uk-legislation-sample-004.md`](../diverse-uk-legislation-sample-004.md). Three of audit 003's clean-fit verdicts (auto-enrolment, child-benefit rates, Scottish CTR reg 79) were converted from asserted to proven by end-to-end encoding between audits 003 and 004, alongside ATED.

## Per-section verdicts

**8 fit cleanly**, with some honest caveats on caller-supplied facts.

**IHTA 1984 s.18** (IHT spouse/CP exemption) fits. The core rule is `exempt = if both_long_term_uk_resident then value else min(value, schedule_1_nil_rate − prior_exempt_uses)`, gated by `spouse_or_cp` and by a 12-month condition flag. The nil-rate-band maximum is effective-dated. `prior_exempt_uses` is a per-transferor cumulative figure the caller must supply (same pattern as UC's pre-applied two-child limit). The 12-month condition (subs (3)(b)) is the one awkward bit — we take `condition_satisfied_within_12_months` as a bool input, which is effectively asking the caller to resolve a future-looking condition by query time. For point-in-time evaluation after the condition window has closed, that's fine.

**VATA 1994 s.30** (VAT zero-rating) fits at the point-in-time rate-assignment level: `rate = if zero_rated_qualifies then 0 else standard_rate`. The clawback on later breach (subs (10)) is a separate query against a later period, which is the same pattern the prototype already uses for UC assessment-period rate changes. Omits: the Schedule-8 item list (caller supplies `matches_schedule_8` bool).

**SSCBA 1992 s.157** (SSP weekly rate) fits. `daily = weekly_rate / qualifying_days_in_week`, with `qualifies_days_in_week` supplied as an integer input (the Sunday-start week determination and the qualifying-day agreement between employer and employee are external legal facts).

**Companies Act 2006 s.477** (small-companies audit exemption) fits cleanly for each AP: count how many of three size limits the company meets (via an integer sum of `if <limit> then 1 else 0`), and require `count >= 2`. The consecutive-year rolling rule folds into a single input: `qualified_prior_year` (bool). Anti-joins for the s.476/478/479 exclusions are bool inputs.

**Local Government Finance Act 1992 s.11** (council-tax discounts) fits cleanly. Count of non-disregarded residents via filtered `count_related`. Then three-way if: `count == 1` → 25%, `count == 0 AND NOT override` → 50%, else 0. The "appropriate percentage" is an effective-dated parameter per FY.

**Pensions Act 2011 s.5** (auto-enrolment earnings trigger amendment) is a parameter-level amendment to Pensions Act 2008 s.3, which is already encoded as `auto_enrolment_program.yaml`. This audit counts it as a fit because adding the new effective-dated parameter version is a one-line change; nothing in the DSL blocks it.

**National Minimum Wage Act 1998 s.1** (entitlement and shortfall) fits. Age-band determination via nested `if`, parameter lookup by age-band number, `effective_hourly = remuneration / hours`, compliance test against the rate owed, shortfall computation. All expressible in current DSL.

**CTA 2009 s.1044** (R&D SME additional deduction) fits. `deduction = if conditions_A_to_F then 0.86 × qualifying_expenditure else 0`. Conditions A–F are six bool inputs; the 86% and the intensity-threshold are effective-dated parameters. Condition B(b)'s rolling prior-AP qualification is a caller-supplied bool (`prior_ap_qualified_and_intensive_with_12m_length`).

**2 partial fits.**

**SSCBA 1992 s.70** (carer's allowance) is partial. The core entitlement test (regular and substantial caring, not gainfully employed, cared-for on qualifying benefit, age ≥ 16, not in full-time education, present in GB, no competing election) all fits cleanly as an `and` of bool inputs, with age comparison against 16 done in the DSL. The 8-week death run-on (subs (1A)) is the partial: the run-on end is `min(end_of_week_failing_other_req, sunday_after_death + 8 weeks)`. Our DSL can do `date_add_days(sunday_after_death, 56)` but can't compute `sunday_after_death` from `death_date` without day-of-week arithmetic (we don't have `weekday_of` or `next_weekday`). Caller-supplied `sunday_after_death` makes it fit, but that's an extra pre-computation the caller probably doesn't otherwise need.

**FA 2018 Sch 6ZA** (SDLT first-time buyer relief) fits the mechanical parts — two-band piecewise tax, eligibility gate, count of FTB purchasers. The "first-time buyer" test (para 6) is inherently recursive: "has not previously been a purchaser of a major interest in any dwelling, anywhere in the world (ignoring leases < 21 years)". The caller can supply `is_first_time_buyer` as a bool per purchaser, which encodes the final fact but erases most of the legal content. The 21-year lease carve-out is a meaningful piece of law that the caller has to work out separately. Counted partial because the `is_ftb` input is very load-bearing.

**0 fail outright.**

First audit with zero outright failures.

## Running score across all four audits

| | 001 | 002 | 003 | 004 |
| --- | --- | --- | --- | --- |
| Fit cleanly | 3 | 3 | 7 | 8 |
| Partial | 4 | 5 | 2 | 2 |
| Fail | 3 | 2 | 1 | 0 |

**Across 40 sampled sections: 21 fit, 13 partial, 6 fail.** 52% clean fit, 85% at least partial. The cumulative direction is clearly toward saturation — 4/5 rounds would hit better than 5/10 on a random sample, and the recent two rounds are at 70-80% fit.

The ten audit-004 sections together used no new DSL features — the current DSL is handling a random draw of law without needing changes, which is the saturation marker the project has been pushing toward. Audit 004 is the first round where that's true. One audit isn't saturation — need 2-3 consecutive rounds at this level to claim it convincingly.

## Gap patterns after audit 004

The recurring partials and the few edge cases in this round point at:

**Day-of-week arithmetic** (carer's allowance run-on; SSP week anchor). `weekday_of(date)` and `next_weekday(date, dow)` would be the simplest forms. Low recurrence so far (2/40) but appears in any rule anchored to a specific weekday. Note: many of the sections that *conceptually* have a weekly anchor (child benefit, SSP, UC AP) handle it by accepting caller-supplied boundaries, so the actual DSL pressure is less than the statutory reading suggests.

**Cumulative / rolling aggregation over time** remains the top structural gap — it was the one fail in audit 003 (beneficial loan threshold) and the partial in audit 002 (VAT threshold and theatre tax). Audit 004 avoided this pattern. Still worth flagging.

**Worldwide-history recursive tests** (FTB, prior-AP R&D intensive) — sections with lookbacks that would need either a prior-query mechanism or a `this_variable_last_period` primitive. Low recurrence (~2/40 explicit) but fundamental to anti-avoidance and transitional rules generally.

Counterfactual, cross-entity pair-keyed, and per-related-record parameter lookup were all less prominent in audit 004 than I expected.

## Suggested next

Keep running audits rather than adding primitives. If the next audit stays above 7/10 fits, we're at saturation for the "arithmetic-over-period with pre-computed legal facts" shape of law. If it drops, the gap pattern will tell us what to add.

Two programmes from this audit are especially worth encoding as proof: **NMWA s.1** (age-banded NMW) and **LGFA 1992 s.11** (council-tax discounts). Both exercise existing primitives cleanly and fill domain gaps (employment law, council-tax liability).
