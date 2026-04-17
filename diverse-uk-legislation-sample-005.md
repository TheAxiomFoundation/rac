# Diverse UK legislation sample — round 005

Method: random picks from the Lex API (`lex.lab.i.ai.gov.uk`), sampled across 20 topic queries. Ten sections picked for diversity, excluding anything already covered in audits 001–004, the prototype, or the pitch deck. No definition-only or pure enabling-power sections.

Topic spread (10 distinct domains): income tax; corporation tax; VAT; CGT; IHT; NIC; Pension Credit; state pension; council tax reduction; immigration.

---

## 1. ITEPA 2003 s.323A — Trivial benefits provided by employers

https://www.legislation.gov.uk/ukpga/2003/1/section/323A

Summary: exempts small benefits-in-kind (≤£50) from income tax provided they are not cash, not contractual, and not rewards for services; close-company directors are subject to an additional £300 annual cap.

Operative text:
"(1) No liability to income tax arises in respect of a benefit … if— (a) conditions A to D are met, or (b) in a case where subsection (2) applies, conditions A to E are met. (2) This subsection applies where— (a) the employer is a close company, and (b) the employee is— (i) a director or other office-holder …, or (ii) a member of the family or household of such a person. (3) Condition A is that the benefit is not cash or a cash voucher. (4) Condition B is that the benefit cost … does not exceed £50. (5) 'benefit cost' means— (a) the cost of providing the benefit, or (b) … the average cost per person. (7) Condition C is that the benefit is not provided pursuant to relevant salary sacrifice arrangements or any other contractual obligation. (9) Condition D is that the benefit is not provided in recognition of particular services …" [Condition E: close-co annual aggregate per director ≤ £300.]

Pseudocode: inputs per benefit — `benefit_cost`, `is_cash`, `is_contractual`, `is_for_services`, `employer_is_close_co`, `recipient_is_director_household`, `tax_year`. Compute `cost_per_person` (average if group benefit); require `not is_cash AND cost_per_person ≤ 50 AND not is_contractual AND not is_for_services`; if close-co director route, additionally require `sum_over_tax_year(cost_per_person filter:close_co, director_family) ≤ 300`. Output: boolean exemption, defaulting taxable amount to 0 or to `cost_per_person`. Time granularity: per benefit occurrence with annual aggregation for E. Edge cases: group-benefit averaging; benefit that tips the £300 cap mid-year.

Legal structures: scalar arithmetic; conditional branching; positive relational membership (director/household); anti-join (not contractual, not cash); aggregation with filter (£300 annual cap); scoped status (close-co director); parameter lookup with versioning (£50, £300); point-in-time vs over-period facts.

---

## 2. CTA 2010 s.37 — Relief for trade losses against total profits

https://www.legislation.gov.uk/ukpga/2010/4/section/37

Summary: lets a company deduct a trading loss from its total profits of the loss-making period and carry it back against the previous 12 months, subject to a UK-trade requirement, a 2-year claim window and FIFO ordering across losses.

Operative text:
"(1) This section applies if, in an accounting period, a company … makes a loss in the trade. (3) If the company makes a claim, the relief is given by deducting the loss from the company's total profits of— (a) the accounting period in which the loss is made … and (b) if the claim so requires, previous accounting periods so far as they fall (wholly or partly) within the period of 12 months ending immediately before the loss-making period begins. (4) The amount of a deduction … for any accounting period is the amount of the loss so far as it cannot be deducted … for a subsequent accounting period. (5) The company may not make a claim if … the company carries on the trade wholly outside the United Kingdom. (6) A deduction under subsection (3)(b) may be made … only if the company— (a) carried on the trade in the period, and (b) did not do so wholly outside the United Kingdom. (7) The claim must be made within two years after the end of the loss-making period. (8) If, for an accounting period, deductions … are to be made for losses of different accounting periods, the deductions are to be made in the order in which the losses were made (starting with the earliest loss)."

Pseudocode: inputs per company × AP — `trading_profit_or_loss`, `total_profits`, `trade_wholly_outside_uk`, `claim_made`. For each loss-making AP L: if outside-UK trade or claim window expired, skip; deduct from own-period total profits first; for residual, walk APs overlapping the 12 months ending at start of L (skip outside-UK or no-trade APs); apportion profits by days for partial overlap; when multiple losses compete for one AP, apply earliest loss first (s.(8)). Output: per-AP reduction in `chargeable_total_profits`. Time granularity: AP-level, day-level for the 12-month window. Edge cases: short APs, overlapping claims, group-relief interaction.

Legal structures: scalar arithmetic; conditional branching; anti-join (not wholly-outside-UK); partial-period / interval intersection; fixed-point / recursive derivation across competing losses; defeater / exception precedence (outside-UK defeats); aggregation with filter; date arithmetic (2y/12m windows); point-in-time vs over-period.

---

## 3. VATA 1994 s.7A — Place of supply of services

https://www.legislation.gov.uk/ukpga/1994/23/section/7A

Summary: sets the default B2B/B2C place-of-supply rule — for business recipients, where the recipient belongs; otherwise where the supplier belongs — subject to the Schedule 4A special rules.

Operative text:
"(1) This section applies, subject to section 57A, for determining … the country in which services are supplied. (2) A supply of services is to be treated as made— (a) where the person to whom the services are supplied is a relevant business person, in the country in which the recipient belongs, and (b) otherwise, in the country in which the supplier belongs. (3) The place of supply of a right to services is the same as that in which the supply of the services would be treated as made if made by the supplier of the right to the recipient of the right. (4) A person is a relevant business person if— (a) the person carries on a business, and (b) the services are not received wholly for private purposes. (5) Subsection (2) has effect subject to Schedule 4A."

Pseudocode: inputs per supply — `supplier.country`, `recipient.country`, `recipient.carries_on_business`, `recipient.wholly_private`, `service_kind`. `relevant_business_person = carries_on_business AND NOT wholly_private`. Default: `recipient.country` if business else `supplier.country`. Then apply Sch 4A overrides in priority (land-related, events, electronically supplied B2C, use-and-enjoyment, etc.), each producing a different country. Output: `place_of_supply: Country` (text). Time granularity: point-in-time per supply. Edge cases: mixed-use recipient still counts as business; multi-establishment supplier.

Legal structures: conditional branching; scoped status ("relevant business person"); legal fiction (right-to-services treated as services); defeater precedence (Sch 4A overrides default); text / identity output; parameter lookup (Sch 4A rule table); multi-entity crossing; point-in-time facts.

---

## 4. TCGA 1992 s.223 — Amount of relief (principal private residence)

https://www.legislation.gov.uk/ukpga/1992/12/section/223

Summary: exempts gain on disposal of an only/main residence — fully if occupied throughout ownership (last 9 months always deemed occupied), or time-apportioned otherwise; specific absence categories count as deemed occupation if bookended by actual residence.

Operative text:
"(1) No part of a gain … shall be a chargeable gain if the dwelling-house … has been the individual's only or main residence throughout the period of ownership, or throughout the period of ownership except for all or any part of the last 9 months. (2) Where subsection (1) does not apply, a fraction of the gain shall not be a chargeable gain, that fraction being— (a) the length of the part or parts of the period of ownership during which the dwelling-house … was the only or main residence, inclusive of the last 9 months in any event, divided by (b) the length of the period of ownership. (3) (a) a period of absence not exceeding 3 years, (b) any period of absence throughout which the individual worked in an employment … all duties performed outside the UK, (c) any period of absence not exceeding 4 years … in consequence of the situation of his place of work, shall be treated as if the dwelling-house were occupied by the individual as a residence, if conditions A and B are met."

Pseudocode: inputs — `gain`, `ownership_interval`, per-day `status`. Apply deemed-occupation: for each absence segment of kind k, if there was prior occupation AND resumed occupation (or "prevented by work"), flip status to occupied within per-kind cap (3y for (a); unlimited for (b); 4y for (c) and (d)). Also deem occupied for the last 9 months. `occupied_days = sum(status == main_residence)`; if equal to ownership days, exempt full gain; else `exempt = gain × occupied_days / ownership_days`. Time granularity: day-level. Edge cases: overlapping absence kinds; spouse-linked (d); never-had-another-residence traps.

Legal structures: scalar arithmetic; partial-period / interval intersection; conditional branching; aggregation with filter; defeater precedence (deeming overrides absence); legal fiction (treated as occupied when away); scoped status (main-residence election); multi-entity crossing (spouse's work); date arithmetic (9m tail, 3y/4y caps); counterfactual ("prevented from resuming residence").

---

## 5. FA 1986 s.102 — Gifts with reservation (IHT anti-avoidance)

https://www.legislation.gov.uk/ukpga/1986/41/section/102

Summary: where a donor gives property but fails to cede possession or keeps benefiting, the property is treated as part of their death estate (or as a fresh PET when the reservation ends) — overriding the ordinary 7-year PET regime.

Operative text:
"(1) … this section applies where … an individual disposes of any property by way of gift and either— (a) possession and enjoyment … is not bona fide assumed by the donee at or before the beginning of the relevant period; or (b) at any time in the relevant period the property is not enjoyed to the entire exclusion, or virtually to the entire exclusion, of the donor …. 'The relevant period' means a period ending on the date of the donor's death and beginning seven years before that date or, if it is later, on the date of the gift. (3) If, immediately before the death of the donor, there is any property which … is property subject to a reservation then, to the extent that the property would not, apart from this section, form part of the donor's estate …, that property shall be treated … as property to which he was beneficially entitled immediately before his death. (4) If, at a time before the end of the relevant period, any property ceases to be property subject to a reservation, the donor shall be treated … as having at that time made a disposition of the property by a disposition which is a potentially exempt transfer."

Pseudocode: inputs — `gift_date`, `death_date`, `value_at_gift`, per-day `donor_excluded`, `donor_benefited`. `relevant_period = [max(gift_date, death_date − 7y), death_date]`. `has_reservation(d) = donor_benefited(d) OR NOT donor_excluded(d)` (with "virtually entire exclusion" de-minimis). If reservation persists at death: add `value_at_death(property)` to death estate. If reservation ends at day `d` < death: emit a deemed PET on `d` valued at `d`, which re-enters the 7y PET regime. Output: addition to estate plus deemed-PET events. Time granularity: daily status; lifetime interval. Edge cases: property substitutions; partial reservations; carve-outs in s.(5).

Legal structures: scalar arithmetic; conditional branching; anti-join ("entire exclusion of the donor"); partial-period intersection; fixed-point / recursive derivation (deemed PET re-enters PET regime); defeater precedence (overrides ordinary gift rules); legal fiction (property notionally in estate); counterfactual ("would not, apart from this section, form part of the donor's estate"); date arithmetic (7y relevant period); point-in-time vs over-period facts (reservation evaluated daily).

---

## 6. SSCBA 1992 s.15 — Class 4 NIC

https://www.legislation.gov.uk/ukpga/1992/7/section/15

Summary: charges self-employed people Class 4 NIC on profits between a lower (£12,570) and upper (£50,270) limit at a main rate (6%), and at an additional rate (2%) above the upper limit.

Operative text:
"(1) Class 4 contributions shall be payable for any tax year in respect of all profits which— (a) are immediately derived from one or more trades, professions or vocations, (b) are profits chargeable to income tax under Chapter 2 of Part 2 of ITTOIA 2005 for the corresponding year of assessment, and (c) are not profits of a trade, profession or vocation carried on wholly outside the United Kingdom. (3) The amount of a Class 4 contribution … is equal to the aggregate of— (a) the main Class 4 percentage of so much of the profits as exceeds £12,570 but does not exceed £50,270; and (b) the additional Class 4 percentage of so much as exceeds £50,270. (3ZA) The main Class 4 percentage is 6% and the additional Class 4 percentage is 2%."

Pseudocode: inputs per person × tax year — `trading_profit`, `trade_wholly_outside_uk`. If outside-UK, contribution = 0. Else `band1 = max(0, min(profit, 50270) − 12570)`, `band2 = max(0, profit − 50270)`, `class4 = 0.06 × band1 + 0.02 × band2`. Time granularity: tax year. Edge cases: LLP partner attribution (s.(3A)); multiple trades aggregated; losses offsetting profits across trades.

Legal structures: scalar arithmetic (band thresholds); conditional branching; parameter lookup with effective-dated versioning (thresholds and rates are Finance-Act-amendable); anti-join (not wholly outside UK); aggregation with filter (sum across trades); point-in-time vs over-period facts.

---

## 7. State Pension Credit Act 2002 s.3 — Savings credit

https://www.legislation.gov.uk/ukpga/2002/16/section/3

Summary: tops up pensioners whose qualifying income exceeds the "savings credit threshold" to reward modest saving, but tapers the top-up above the standard minimum guarantee; eligibility restricted to those at pensionable age before 6 April 2016.

Operative text:
"(1) The first of the conditions … is that the claimant— (a) has attained pensionable age before 6 April 2016 and has attained the age of 65, or (b) is a member of a couple, the other member of which falls within paragraph (a). (2) The second … is that— (a) the claimant's qualifying income exceeds the savings credit threshold; and (b) the claimant's income is such that … amount A exceeds amount B. (3) Where the claimant is entitled to a savings credit, the amount … shall be the amount by which amount A exceeds amount B. (4) 'amount A' is the smaller of— the maximum savings credit; and a prescribed percentage of the amount by which qualifying income exceeds the savings credit threshold. 'Amount B' is a prescribed percentage of the amount (if any) by which the claimant's income exceeds the appropriate minimum guarantee; or if there is no such excess, nil. (7) 'the maximum savings credit' is a prescribed percentage of the difference between the standard minimum guarantee and the savings credit threshold."

Pseudocode: inputs — `date_reached_pensionable_age`, `age`, `couple_partner_qualifies`, weekly `qualifying_income`, weekly `total_income`. Parameters (annually uprated): `SCT` (threshold), `SMG` (standard min guarantee), `AMG` (appropriate min guarantee), `reward_pct` (60%), `taper_pct` (40%). Eligible iff reached pensionable age before 2016-04-06 and aged ≥ 65, or partner does. `max_sc = reward_pct × (SMG − SCT)`. `A = min(max_sc, reward_pct × max(0, qualifying_income − SCT))`. `B = taper_pct × max(0, total_income − AMG)`. `savings_credit = max(0, A − B)`. Time granularity: weekly benefit, annual uprating. Edge cases: couple where only one partner qualifies; s.(5) substitution when AMG ≠ SMG.

Legal structures: scalar arithmetic with min/max; parameter lookup with versioning (SCT, SMG, AMG, percentages uprated each April); conditional branching; scoped status (pre-2016 pensionable age); multi-entity crossing (couple inheritance); positive relational membership (couple); aggregation (couple income pooling); point-in-time vs over-period facts; counterfactual ("if there is no such excess, nil").

---

## 8. Pensions Act 2014 s.17 — Effect of postponing or suspending new state pension

https://www.legislation.gov.uk/ukpga/2014/19/section/17

Summary: lifts a new-state-pension claimant's weekly rate by an increment for each whole week of deferral at a specified percentage, with a 1% minimum threshold and ongoing annual uprating.

Operative text:
"(1) If a person's entitlement to a state pension under this Part has been deferred for a period, the weekly rate … is increased by an amount equal to the sum of the increments to which the person is entitled. (2) But the weekly rate is not to be increased … if the increase would be less than 1% of the person's weekly rate ignoring that subsection. (3) A person is entitled to one increment for each whole week in the period during which the person's entitlement … was deferred. (4) The amount of an increment is equal to a specified percentage of the weekly rate … to which the person would have been entitled immediately before the end of that period if the person's entitlement had not been deferred. (6) The amount of an increase under this section is itself to be increased from time to time in accordance with any order made under section 150 of the Administration Act. (7) … deferred … if the person has opted under section 16 to suspend … (8) … also deferred … if the person is not entitled by reason only of— (a) not satisfying the conditions in section 1 of the Administration Act …"

Pseudocode: inputs — deferral intervals `[d_start, d_end]`, counterfactual `weekly_rate_at_end_if_not_deferred`, `increment_pct` (≈1% per 9 weeks). For each interval: `weeks = floor((d_end − d_start) / 7)`; `increment = weeks × increment_pct × counterfactual_rate`. Sum increments; apply s.150 annual uprating to the already-awarded increment total; if total_increase < 1% of base weekly rate, zero it. New weekly rate = base + uprated increment. Time granularity: weekly, with annual uprating events. Edge cases: partial trailing weeks dropped; multiple deferrals; deferral-by-non-claim under s.(8)(a) vs active opt-out under s.(7); death during deferral crystallises to lump sum under s.8.

Legal structures: scalar arithmetic; parameter lookup with versioning (specified %, s.150 uprating order); conditional branching (1% gate); date arithmetic (whole weeks); counterfactual ("rate to which the person would have been entitled … if … not deferred"); scoped status (deferred); partial-period intersection; aggregation across intervals.

---

## 9. LGFA 1992 s.13A — Reductions by billing authority (council tax)

https://www.legislation.gov.uk/ukpga/1992/14/section/13A

Summary: requires each English billing authority to operate a council tax reduction scheme for the financially needy; Welsh schemes are set centrally by regulations; any authority retains a discretionary top-up.

Operative text:
"(1) The amount of council tax which a person is liable to pay in respect of any chargeable dwelling and any day (as determined in accordance with sections 10 to 13)— (a) in the case of a dwelling … in England, is to be reduced to the extent, if any, required by the authority's council tax reduction scheme; (b) in the case of a dwelling … in Wales, is to be reduced to the extent, if any, required by any council tax reduction scheme made under regulations under subsection (4); (c) in any case, may be reduced to such extent (or, if already reduced under (a) or (b), such further extent) as the billing authority thinks fit. (2) Each billing authority in England must make a scheme specifying the reductions which are to apply … by— (a) persons whom the authority considers to be in financial need, or (b) persons in classes consisting of persons whom the authority considers to be, in general, in financial need."

Pseudocode: inputs per dwelling × day — `gross_ct` (from ss.10–13), `billing_authority`, `country`, claimant attributes. Step 1 (mandatory): look up scheme by (authority, date, country) — England: authority-specific; Wales: central reg. Apply to get `mandatory_reduction`. Step 2 (discretionary): authority may layer a further `discretionary_reduction` under s.(1)(c). `final_ct = max(0, gross_ct − mandatory − discretionary)`. Time granularity: per day. Edge cases: boundary dwellings (Sch 1A); mid-year scheme amendments; claimant moves authority mid-year.

Legal structures: parameter lookup with versioning (scheme per authority per financial year); multi-entity crossing (dwelling × authority × claimant × day); conditional branching (country-dependent rule source); scoped status ("in financial need"); scalar arithmetic; legal fiction (authority-defined need classes); defeater precedence (discretionary on top of mandatory); partial-period intersection (day-apportionment across scheme versions).

---

## 10. NIAA 2002 s.79 — Deportation order: appeal

https://www.legislation.gov.uk/ukpga/2002/41/section/79

Summary: bars the Home Secretary from making a deportation order while an in-country appeal could still be brought or is pending, except where the order is an automatic-deportation order under s.32(5) UK Borders Act 2007.

Operative text:
"(1) A deportation order may not be made in respect of a person while an appeal under section 82(1) that may be brought or continued from within the United Kingdom relating to the decision to make the order— (a) could be brought (ignoring any possibility of an appeal out of time with permission), or (b) is pending. (2) In this section 'pending' has the meaning given by section 104. (3) This section does not apply to a deportation order which states that it is made in accordance with section 32(5) of the UK Borders Act 2007. (4) But a deportation order made in reliance on subsection (3) does not invalidate leave to enter or remain, in accordance with section 5(1) of the Immigration Act 1971, if and for so long as section 78 above applies."

Pseudocode: inputs per person × date — `decision_date`, `appeal_rights`, `appeal_status ∈ {could_still_bring, pending, determined, withdrawn}`, `appeal_window_days`, `auto_deport_under_uka2007_s32_5`, `section_78_applies`. `bar = (appeal_rights == in_country AND status == could_still_bring AND within_window) OR (in_country appeal pending)`. If `auto_deport_under_uka2007_s32_5`: `bar = False`, but while `section_78_applies` the order does not invalidate existing leave. `may_make_order = NOT bar`. Output: permission boolean plus scoped leave-preservation exception. Time granularity: point-in-time gate. Edge cases: late appeals with permission (ignored); abandoned appeals; multi-track appeal rights (HR vs protection).

Legal structures: conditional branching; scoped status (appeal pending; leave preserved); defeater precedence (UKBA override, then s.78 re-asserts sub-rule); anti-join (no in-country appeal rights open); counterfactual ("ignoring any possibility of an appeal out of time with permission"); multi-entity crossing; text / identity output (boolean decision); date arithmetic (appeal window).

---

## Coverage across the ten sections

| Structure | Sections |
|---|---|
| Scalar arithmetic | 1, 2, 4, 5, 6, 7, 8, 9 |
| Conditional branching | all ten |
| Positive relational membership | 1, 3, 7 |
| Anti-join | 1, 2, 5, 6, 10 |
| Partial-period / interval intersection | 2, 4, 5, 8, 9 |
| Fixed-point / recursive derivation | 2, 5 |
| Defeater / exception precedence | 2, 3, 5, 9, 10 |
| Legal fiction / recharacterisation | 3, 4, 5, 9 |
| Scoped status | 1, 3, 4, 7, 8, 10 |
| Counterfactual | 4, 5, 7, 8, 10 |
| Aggregation over a relation (with filter) | 1, 2, 4, 6, 7, 8 |
| Parameter lookup with effective-dated versioning | 1, 3, 6, 7, 8, 9 |
| Multi-entity crossing | 3, 4, 7, 9, 10 |
| Text / identity output | 3, 10 |
| Date arithmetic | 2, 4, 5, 8, 10 |
| Point-in-time vs over-period facts | 1, 2, 3, 5, 6, 7, 8, 10 |

Every structure on the target list is exercised by at least two of the ten sections.
