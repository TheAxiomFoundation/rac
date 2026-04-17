# Diverse UK legislation sample 004

Fourth-round generality audit. Ten sections sampled via the Lex API across IHT, VAT, SSP, company law, council tax, automatic enrolment, DWP benefits, SDLT, minimum wage, and corporation-tax R&D relief. No overlap with audits 001-003, the prototype, or the pitch deck.

---

## 1. Inheritance Tax Act 1984, s.18 — transfers between spouses or civil partners

URL: https://www.legislation.gov.uk/ukpga/1984/51/section/18

**Summary.** Removes a lifetime or death-time transfer from IHT to the extent it enriches the transferor's spouse or civil partner, capped where the transferor is a long-term UK resident but the recipient is not.

**Operative text.**
> (1) A transfer of value is an exempt transfer to the extent that the value transferred is attributable to property which becomes comprised in the estate of the transferor's spouse or civil partner or, so far as the value transferred is not so attributable, to the extent that that estate is increased.
> (2) If, immediately before the transfer, the transferor but not the transferor's spouse or civil partner is a long-term UK resident, the value in respect of which the transfer is exempt ... shall not exceed the exemption limit ... less any amount previously taken into account for the purposes of the exemption conferred by this section.
> (2A) ... the exemption limit is the amount shown in the second column of the first row of the Table in Schedule 1 ...
> (3) Subsection (1) shall not apply ... if the testamentary or other disposition (a) takes effect on the termination after the transfer of value of any interest or period, or (b) depends on a condition which is not satisfied within twelve months after the transfer; but paragraph (a) shall not have effect by reason only that the property is given to a spouse or civil partner only if he survives the other ... for a specified period.
> (4) ... property is given to a person if it becomes his property or is held on trust for him.

**Pseudocode.**
```
inputs:  transfer{transferor, recipient, value, date, disposition, condition_deadline?};
         spouse_or_cp(a, b, date) -> bool; long_term_uk_resident(p, date) -> bool;
         prior_exempt_uses(transferor, date); schedule_1_nil_rate(date).
output:  exempt_amount (£); dtype scalar; point-in-time; 12-month condition window.
logic:   if not spouse_or_cp: 0.
         if disposition terminates a prior interest (subs 3a, unless only a survivorship proviso): 0.
         cap = inf if both long-term UK resident, else schedule_1_nil_rate(date) - prior_exempt_uses.
         if condition not met within 12 months: retroactive clawback to 0.
         else: min(value_attributable_to_recipient, cap).
edges:   trust-held property counts as given; survivorship-condition carve-out overrides 3(a).
```

**Structures used.** Scalar arithmetic; conditional branching; positive relational membership (spouse/CP); scoped status (long-term UK residence); parameter lookup with effective-dated versioning (Sch 1); defeater/exception precedence (subs (3) with its proviso); date arithmetic (12-month window); counterfactual (retroactive loss); aggregation over a relation with filter (prior exempt uses).

---

## 2. Value Added Tax Act 1994, s.30 — zero-rating

URL: https://www.legislation.gov.uk/ukpga/1994/23/section/30

**Summary.** Treats a supply as taxable at nil VAT where the goods or services fall within Schedule 8, and provides conditional zero-rating for exports and related export services, with clawback if conditions fail.

**Operative text.**
> (1) Where a taxable person supplies goods or services and the supply is zero-rated ... (a) no VAT shall be charged on the supply; but (b) it shall in all other respects be treated as a taxable supply; and accordingly the rate at which VAT is treated as charged on the supply shall be nil.
> (2) A supply ... is zero-rated ... if the goods or services are of a description for the time being specified in Schedule 8 ...
> (2A) A supply ... which consist of applying a treatment or process to another person's goods is zero-rated ... if by doing so he produces goods, and either (a) those goods are of a description ... specified in Schedule 8; or (b) a supply by him of those goods ... would be of a description so specified.
> (6) A supply of goods is zero-rated ... if the Commissioners are satisfied that the person supplying the goods (a) has exported them; or (b) has shipped them for use as stores on a voyage or flight to an eventual destination outside the United Kingdom ...
> (10) Where the supply of any goods has been zero-rated by virtue of subsection (6) ... and (a) the goods are found in the United Kingdom after the date on which they were alleged to have been ... exported; or (b) any condition ... is not complied with ... the VAT that would have been chargeable on the supply but for the zero-rating shall become payable forthwith ...

**Pseudocode.**
```
inputs:  supply{supplier, goods_or_services, value, date, export_evidence?};
         schedule_8(date) -> set (effective-dated); free_zone_opt_50A(supplier, date) -> bool.
output:  {rate: 0% | standard, vat_due, clawback_flag}; per-supply point-in-time.
logic:   if matches_schedule_8 OR (treatment_produces_item_in_sch8)
            OR (exported_to_eligible_destination AND conditions_met
                AND NOT (GB_export AND free_zone_opt_50A)
                AND NOT (shipped_for_private_voyage)): rate = 0%.
         on discovery of non-export or condition breach:
            reopen period, charge vat_that_would_have_been_chargeable.
edges:   Sch 8 edited by Treasury order (effective-dated parameter).
```

**Structures used.** Scalar arithmetic; conditional branching; positive relational membership (Sch 8); legal fiction/recharacterisation (nil-rate treated as a taxable supply); parameter lookup with effective-dated versioning (Sch 8 edits); defeater/exception precedence (subs (6A), (7)); counterfactual (clawback computes VAT "that would have been chargeable"); multi-entity crossing (supplier, customer, Commissioners).

---

## 3. Social Security Contributions and Benefits Act 1992, s.157 — rates of SSP

URL: https://www.legislation.gov.uk/ukpga/1992/4/section/157

**Summary.** Fixes the weekly SSP rate and gives the daily amount as the weekly rate divided by the number of qualifying days in the Sunday-start week agreed between employer and employee.

**Operative text.**
> (1) Statutory sick pay shall be payable by an employer at the weekly rate of £118.75.
> (2) The Secretary of State may by order (a) amend subsection (1) ... to substitute different provision as to the weekly rate or rates of statutory sick pay; and (b) make such consequential amendments ...
> (3) The amount of statutory sick pay payable by any one employer in respect of any day shall be the weekly rate applicable on that day divided by the number of days which are, in the week (beginning with Sunday) in which that day falls, qualifying days as between that employer and the employee concerned.

**Pseudocode.**
```
inputs:  day; (employer, employee); qualifying_days(employer, employee, week_of(day));
         ssp_weekly_rate(day) (effective-dated; £118.75 from 6 Apr 2025).
output:  scalar £ per day.
logic:   week = Sunday-start week containing day.
         q = |qualifying_days(...)|; if q == 0: undefined.
         daily = ssp_weekly_rate(day) / q.
edges:   rate change mid-week uses the rate on each specific day; qualifying-day set differs
         per employer, so concurrent employments compute independently.
```

**Structures used.** Scalar arithmetic; parameter lookup with effective-dated versioning; date arithmetic (Sunday-anchored week); aggregation over a relation with filter (qualifying-day count per week per employer/employee); multi-entity crossing (employee across employers); point-in-time fact (daily rate) feeding an over-period aggregate (weekly qualifying-day count).

---

## 4. Companies Act 2006, s.477 — small companies: audit exemption

URL: https://www.legislation.gov.uk/ukpga/2006/46/section/477

**Summary.** A company qualifying as small under s.382 is exempt from audit for that year, unless ss.475(2)-(3), 476, 478, or 479 pull it back in.

**Operative text.**
> (1) A company that qualifies as a small company in relation to a financial year is exempt from the requirements of this Act relating to the audit of accounts for that year.
> (4) ... (a) whether a company qualifies as a small company shall be determined in accordance with section 382(1) to (6) ...
> (5) This section has effect subject to section 475(2) and (3) (requirements as to statements to be contained in balance sheet), section 476 (right of members to require audit), section 478 (companies excluded from small companies exemption), and section 479 (availability of small companies exemption in case of group company).

Section 382 supplies the two-year rolling test: small means meeting at least two of three limits (turnover £15m, balance-sheet total £7.5m, average employees 50), with a consecutive-years rule after the first financial year.

**Pseudocode.**
```
inputs:  company, financial_year;
         turnover, bs_total, avg_employees (short-year pro-rated on turnover);
         balance_sheet_statement_present; members_required_audit;
         excluded_s478; group_restriction_s479.
output:  exempt_from_audit (bool).
qualify_small(year):
   m = count(turnover <= 15M, bs_total <= 7.5M, avg_employees <= 50) >= 2.
   first-year: m.  subsequent: m OR (prior_qualified(year-1) AND NOT two_consec_fails).
exempt = qualify_small(year) AND balance_sheet_statement_present
         AND NOT members_required_audit AND NOT excluded_s478
         AND NOT group_restriction_s479.
edges:   short FY pro-rates turnover cap; consecutive-year rule smooths borderline flips;
         s.479 bites even when standalone figures qualify.
```

**Structures used.** Scalar arithmetic; conditional branching; positive relational membership (small-company set); anti-join (ss.476, 478, 479 exclusions); aggregation over a relation with filter (monthly employee headcount -> average); date arithmetic (short-year pro-rata); fixed-point/recursive derivation (two-consecutive-years test recurses on prior-year qualification); defeater/exception precedence.

---

## 5. Local Government Finance Act 1992, s.11 — council tax discounts

URL: https://www.legislation.gov.uk/ukpga/1992/14/section/11

**Summary.** Applies a 25 per cent single-occupier discount or a 50 per cent no-qualifying-occupier discount per chargeable dwelling per day, with Schedule 1 listing disregards.

**Operative text.**
> (1) The amount of council tax payable in respect of any chargeable dwelling and any day shall be subject to a discount equal to the appropriate percentage of that amount if on that day (a) there is only one resident of the dwelling and he does not fall to be disregarded for the purposes of discount; or (b) there are two or more residents of the dwelling and each of them except one falls to be disregarded for those purposes.
> (2) Subject to sections 11A, 11B, 11C, 12, 12A and 12B below, the amount of council tax ... shall be subject to a discount equal to twice the appropriate percentage ... if on that day (a) there is no resident of the dwelling; or (b) there are one or more residents of the dwelling and each of them falls to be disregarded ...
> (3) "the appropriate percentage" means 25 per cent. or, if the Secretary of State by order so provides in relation to the financial year in which the day falls, such other percentage as is specified in the order.
> (5) Schedule 1 to this Act shall have effect for determining who shall be disregarded for the purposes of discount.

**Pseudocode.**
```
inputs:  dwelling, day; residents_on(dwelling, day); disregarded(person, day) (Sch 1);
         appropriate_percentage(fy_of(day)); overrides_ss11A_B_C_12_12A_12B(dwelling, day).
output:  discount_fraction (scalar) applied to daily CT charge.
logic:   non_dis = [r in residents_on(...) if not disregarded(r, day)].
         p = appropriate_percentage(...).
         if |non_dis| == 1: p.
         elif |non_dis| == 0 AND NOT overrides: 2*p.   # subs (2), subject to 11A-C, 12-12B
         else: 0.
edges:   all residents disregarded counts as "no qualifying resident"; overrides flip empty homes
         to a premium; FY boundary can change p on 1 April; per-day attribution for mid-day flips.
```

**Structures used.** Scalar arithmetic; conditional branching; aggregation over a relation with filter (count of non-disregarded residents per dwelling per day); positive relational membership (residence); anti-join (disregards); parameter lookup with effective-dated versioning (appropriate percentage by FY); defeater/exception precedence (ss.11A-11C, 12-12B); point-in-time vs over-period facts (day-level discount, annual liability).

---

## 6. Pensions Act 2011, s.5 — earnings trigger for automatic enrolment and re-enrolment

URL: https://www.legislation.gov.uk/ukpga/2011/19/section/5

**Summary.** Rewrites ss.3(1) and 5(1) of the Pensions Act 2008 so that auto-enrolment / re-enrolment applies to a jobholder aged 22 to SPA earning more than £7,475 in the pay reference period, with proportionate scaling for non-12-month periods.

**Operative text.**
> (1) In section 3 of the 2008 Act (automatic enrolment) for subsection (1) substitute "(1) This section applies to a jobholder (a) who is aged at least 22, (b) who has not reached pensionable age, and (c) to whom earnings of more than £7,475 are payable by the employer in the relevant pay reference period (see section 15)."
> (2) After subsection (6) ... insert "(6A) ... 'earnings' has the meaning given in section 13(3). (6B) In the case of a pay reference period of less or more than 12 months, subsection (1) applies as if the amount in paragraph (c) were proportionately less or more."
> (3) In section 5 of the 2008 Act (automatic re-enrolment) for subsection (1) substitute [identical age, SPA and earnings test].
> (4) After subsection (7) ... insert (7A) [earnings per s.13(3)] and (7B) [proportionate scaling].

**Pseudocode.**
```
inputs:  jobholder, employer, PRP (pay reference period);
         dob, state_pension_age; earnings_in_prp (per s.13(3));
         trigger_amount(day) (reviewed under s.14); rounded_s15A(length, day)?.
output:  applies -> bool (duty to auto-enrol or auto-re-enrol).
logic:   if age_during_prp < 22 OR age_during_prp >= SPA: False.
         L = PRP length in months.
         T = rounded_s15A(L, PRP.end) if set else trigger_amount(PRP.end) * L / 12.
         return earnings_in_prp > T.
edges:   PRP of 1w/2w/1m/other: pro-rata or rounded override; age crosses 22/SPA inside a PRP
         handled PRP-by-PRP; multiple concurrent employments each run the test on their own PRP.
```

**Structures used.** Scalar arithmetic (pro-rata); conditional branching; scoped status (age between 22 and SPA); parameter lookup with effective-dated versioning (annual review under s.14; rounded override under s.15A); date arithmetic (age and PRP length); partial-period/interval intersection (age-band within a PRP); multi-entity crossing (jobholder × employer × PRP).

---

## 7. Social Security Contributions and Benefits Act 1992, s.70 — carer's allowance

URL: https://www.legislation.gov.uk/ukpga/1992/4/section/70

**Summary.** Entitles a carer who is regularly and substantially caring for a qualifyingly disabled person, is not gainfully employed, is 16 or over, is not in full-time education, and satisfies residence conditions, to a weekly allowance; with an 8-week run-on after the disabled person's death and an anti-double-counting rule.

**Operative text.**
> (1) A person shall be entitled to a carer's allowance for any day on which he is engaged in caring for a severely disabled person if (a) he is regularly and substantially engaged in caring for that person; (b) he is not gainfully employed; and (c) the severely disabled person is either such relative of his as may be prescribed or a person of any such other description as may be prescribed.
> (1A) A person who was entitled ... immediately before the death of the severely disabled person ... shall continue to be entitled ... until (a) the end of the week in which he ceases to satisfy any other requirement ...; or (b) the expiry of the period of eight weeks beginning with the Sunday following the death ... whichever occurs first.
> (2) "severely disabled person" means a person in respect of whom there is payable ... attendance allowance or [DLA care at highest/middle], PIP daily living, AFIP, adult/child disability payment, Scottish adult DLA, pension age disability payment ...
> (3) ... under 16 or receiving full-time education [not entitled].
> (4) ... satisfies prescribed conditions as to residence or presence in Great Britain.
> (7) No person shall be entitled for the same day to (a) more than one allowance under this section; or (b) both an allowance under this section and carer support payment.
> (7ZA) Where two or more persons would have a relevant entitlement for the same day in respect of the same severely disabled person, one of them only shall have that entitlement [by joint election or SoS discretion].

**Pseudocode.**
```
inputs:  carer, cared_for, day;
         regularly_substantially_caring, gainfully_employed, cared_for_qualifying_benefit,
         age, full_time_education, present_in_gb, eu_reg_uk_competent;
         concurrent_election(cared_for, day), death_date(cared_for)?, prior_entitlement.
output:  entitled_on(day) bool; weekly £ rate per Sch 4 Pt III para 4.
logic:   if age < 16 or full_time_education: False.
         if cared_for is dead:
            run_on_end = min(end_of_week_failing_other_req, sunday_after_death + 8 weeks).
            return prior_entitlement AND day <= run_on_end.
         ok = regularly_substantially_caring AND NOT gainfully_employed
              AND cared_for_qualifying_benefit
              AND present_in_gb AND (NOT eu_reg_applies OR uk_competent).
         if concurrent_election(cared_for, day) != carer: False.
         return ok.
edges:   two carers tie-break by election or SoS/Scottish Ministers; Scottish CSP blocks CA;
         run-on anchored to Sunday after death (or death itself if a Sunday); gainful-employment
         threshold is effective-dated; disabled person's underlying benefit pause pauses CA.
```

**Structures used.** Scalar arithmetic (earnings threshold); conditional branching; positive relational membership (carer-to-disabled); anti-join (FTE, gainful employment, competing CSP); scoped status; date arithmetic (Sunday anchor, 8-week window); partial-period/interval intersection (run-on); defeater/exception precedence (subs (7), (7ZA)-(7ZC)); multi-entity crossing (carer × disabled × SoS/Scottish Ministers); parameter lookup with effective-dated versioning (Sch 4 rate).

---

## 8. Finance Act 2018, s.41 (inserting Sch 6ZA FA 2003) — SDLT first-time buyer relief

URL: https://www.legislation.gov.uk/ukpga/2018/3/section/41

**Summary.** Inserts Schedule 6ZA FA 2003 to charge a first-time buyer of a single dwelling up to £500,000 at 0 per cent on the first £300,000 and 5 per cent on the remainder, subject to a four-part eligibility test and clawback if a later linked transaction breaks those conditions.

**Operative text.**
> Sch 6ZA para 1: Relief may be claimed for a chargeable transaction if (1) the main subject-matter consists of a major interest in a single dwelling; (2) the relevant consideration ... is not more than £500,000; (3) the purchaser, or (if more than one) each of the purchasers, is a first-time buyer who intends to occupy the purchased dwelling as the purchaser's only or main residence; (4) the transaction is not linked to another land transaction, or is linked only to [garden/grounds or benefit-of-dwelling] land transactions; (7) relief may not be claimed ... if it is a higher rates transaction for the purposes of paragraph 1 of Schedule 4ZA.
> Para 4: ... tax is determined as if Table A were (0% on so much as does not exceed £300,000; 5% on any remainder so far as not exceeding £500,000).
> Para 5: ... if another land transaction linked to the first transaction causes the first to cease to qualify, tax (or additional tax) is chargeable as if the claim had not been made.
> Para 6: "first-time buyer" means an individual who has not previously been a purchaser of a major interest in any dwelling, anywhere in the world (ignoring leases <21 years).

**Pseudocode.**
```
inputs:  transaction{effective_date, purchasers, consideration, rent_element, subject_matter,
         linked_transactions, intention_to_occupy}; schedule_4ZA_higher_rates; prior_worldwide.
output:  SDLT £; effective_date >= 22 Nov 2017.
eligible = subject_matter == major_interest_in_single_dwelling
         AND (consideration - rent_element) <= 500_000
         AND all(first_time_buyer(p) AND intends_main_residence(p) for p in purchasers)
         AND (not linked OR all(l is garden/grounds/benefit for l in linked))
         AND NOT schedule_4ZA_higher_rates.
if eligible:
   cr = max(consideration - rent_element, 0).
   tax = 0 * min(cr, 300_000) + 0.05 * max(min(cr, 500_000) - 300_000, 0).
else: tax = standard Table A.
if later_linked_transaction_breaks_eligibility:
   recompute as if no claim; collect additional tax.
first_time_buyer(person) = NOT prior_worldwide_major_interest_acquisition(person)
   (ignoring leases < 21 years at day after acquisition).
edges:   alternative-finance first transaction: person treated as purchaser;
         shared-ownership/right-to-buy: Sch 9 para 16 excludes relief for certain legs;
         LTT Welsh dwellings now count under the worldwide test.
```

**Structures used.** Scalar arithmetic (two-band piecewise); conditional branching; positive relational membership (linked-transaction graph); anti-join (exclude higher-rates; exclude prior worldwide dwellings); counterfactual (withdrawal: recompute as if no claim); legal fiction/recharacterisation (person-as-purchaser under alternative finance); date arithmetic (effective-date gate; 21-year lease rule); parameter lookup with effective-dated versioning (Table A override); multi-entity crossing (each co-purchaser must be FTB and intend to occupy); fixed-point/recursive derivation (FTB status scans any prior transaction anywhere).

---

## 9. National Minimum Wage Act 1998, s.1 — workers to be paid at least NMW

URL: https://www.legislation.gov.uk/ukpga/1998/39/section/1

**Summary.** Requires an employer to pay any qualifying UK worker at or above compulsory school age at least the prescribed single hourly rate over the pay reference period.

**Operative text.**
> (1) A person who qualifies for the national minimum wage shall be remunerated by his employer in respect of his work in any pay reference period at a rate which is not less than the national minimum wage.
> (2) A person qualifies for the national minimum wage if he is an individual who (a) is a worker; (b) is working, or ordinarily works, in the United Kingdom under his contract; and (c) has ceased to be of compulsory school age.
> (3) The national minimum wage shall be such single hourly rate as the Secretary of State may from time to time prescribe.
> (4) For the purposes of this Act a "pay reference period" is such period as the Secretary of State may prescribe ...
> (5) Subsections (1) to (4) above are subject to the following provisions of this Act.

**Pseudocode.**
```
inputs:  worker, employer, PRP; is_worker, works_in_uk, age, compulsory_school_age_end;
         hours_worked_in_prp, remuneration_in_prp (per reg 2);
         nmw_rate(age_band, day) (effective-dated, age-banded).
output:  compliant (bool); shortfall £.
logic:   qualifies = is_worker AND works_in_uk AND PRP.end > compulsory_school_age_end.
         if not qualifies: N/A.
         rate_owed = nmw_rate(age_band_of(worker, PRP.end), PRP.end).
         effective_hourly = remuneration_in_prp / hours_worked_in_prp.
         compliant = effective_hourly >= rate_owed.
         shortfall = max(0, rate_owed - effective_hourly) * hours_worked_in_prp.
edges:   rate or age-band change inside a PRP; excluded categories via subs (5) referral;
         salary sacrifice and accommodation offset affect the remuneration side.
```

**Structures used.** Scalar arithmetic; conditional branching; scoped status (qualifying worker); parameter lookup with effective-dated versioning (age-banded NMW rates); date arithmetic (school-age end, PRP end); partial-period/interval intersection (age-band change mid-PRP); multi-entity crossing (worker × employer × PRP); counterfactual (rate-that-would-have-been-owed for the shortfall computation).

---

## 10. Corporation Tax Act 2009, s.1044 — R&D additional deduction for SMEs

URL: https://www.legislation.gov.uk/ukpga/2009/4/section/1044

**Summary.** Gives an R&D-intensive SME making a trading loss an additional 86 per cent deduction against trading profits, on top of the normal s.87 deduction, for qualifying Chapter 2 R&D expenditure, provided six cumulative conditions A-F are met.

**Operative text.**
> (1) A company is entitled to corporation tax relief for an accounting period if it meets each of conditions A to F.
> (2) Condition A is that the company is a small or medium-sized enterprise in the period.
> (2A) Condition B is that the company (a) meets the R&D intensity condition in the period, or (b) obtained relief under this Chapter for its most recent prior accounting period of 12 months' duration, having met the R&D intensity condition in that period.
> (4) Condition C is that the company carries on a trade in the period.
> (5) Condition D is that the company has qualifying Chapter 2 expenditure which is allowable as a deduction in calculating for corporation tax purposes the profits of the trade for the period.
> (5A) Condition E is that the company makes a loss in the trade in the period.
> (5B) Condition F is that the company is not an ineligible company (see section 1142).
> (6) For the company to obtain the relief it must make a claim ...
> (7) The relief is an additional deduction in calculating the profits of the trade for the period. The deduction is, in particular, additional to any given under section 87.
> (8) The amount of the additional deduction is 86% of the qualifying Chapter 2 expenditure.

**Pseudocode.**
```
inputs:  company, accounting_period (AP); is_sme, rd_intensive (threshold effective-dated);
         prior_ap.length, relief_claimed_prior; trade_carried_on;
         qualifying_chapter2_expenditure; chapter2_is_trade_deduction;
         trading_loss_before_additional; ineligible_s1142; claim_made.
output:  additional_deduction (£).
conditions: A=is_sme, B=rd_intensive OR (prior_ap.length==12m AND relief_claimed_prior
            AND rd_intensive_in_prior), C=trade_carried_on, D=chapter2_is_trade_deduction,
            E=trading_loss_before_additional, F=NOT ineligible_s1142.
if all(A..F) AND claim_made: 0.86 * qualifying_chapter2_expenditure; else 0.
edges:   short AP breaks B(b)'s 12-month escape hatch; group/connected-enterprise aggregation
         reaches SME status; loss test computed BEFORE the additional deduction to avoid
         self-reference; interaction with s.1045 alternative election and merged-scheme credit.
```

**Structures used.** Scalar arithmetic (86% multiplier); conditional branching (six cumulative conditions); scoped status (SME; R&D-intensive; ineligible); parameter lookup with effective-dated versioning (86%, SME limits, intensity threshold); fixed-point/recursive derivation (Condition B's look-back to a prior AP's own prior-AP-dependent qualification); defeater/exception precedence (ineligibility, no-claim); aggregation over a relation with filter (qualifying Chapter 2 expenditure); date arithmetic (12-month AP length gate); counterfactual (loss computed absent the additional deduction).
