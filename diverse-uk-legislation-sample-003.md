# Diverse UK legislation sample 003

Third-round generality audit. Ten sections, ten statutes, ten policy domains.
Source: Lex API (lex.lab.i.ai.gov.uk). None overlap with audits 001/002, the
prototype, or the pitch-deck list.

Spread: NIC, child support, council tax reduction (Scotland), child benefit,
corporation tax, income tax (benefits-in-kind), ATED (property tax on companies),
occupational pensions (auto-enrolment), state pension deferral, employment rights.

---

## 1. SSCBA 1992 s.9 — Calculation of secondary Class 1 NIC

URL: https://www.legislation.gov.uk/ukpga/1992/4/section/9

**Subject.** Sets the employer (secondary) Class 1 NIC charge: percentage of
weekly earnings above the secondary threshold, with an age-related carve-out.

**Text (extract).**
> (1) Where a secondary Class 1 contribution is payable as mentioned in section
> 6(1)(b) above, the amount of that contribution shall be the relevant
> percentage of so much of the earnings paid in the tax week, in respect of the
> employment in question, as exceeds the current secondary threshold (or the
> prescribed equivalent).
>
> (1A) For the purposes of subsection (1) "the relevant percentage" is— (a) if
> section 9A below applies to the earnings, the age-related secondary
> percentage; (aa) if section 9B below (zero-rate secondary Class 1
> contributions for certain apprentices) applies to the earnings, 0%; (b)
> otherwise, the secondary percentage.
>
> (2) For the purposes of this Act the secondary percentage is 15%; but that
> percentage is subject to alteration under sections 143 and 145 of the
> Administration Act.

**Pseudocode.**
```
inputs:
  earnings[employment, tax_week]: money
  secondary_threshold[tax_week]: money   # parameter, re-laid yearly
  secondary_percentage[tax_week]: pct    # parameter
  earner_age_group[employment, tax_week]: enum
  apprentice_status[employment, tax_week]: bool
  upper_secondary_threshold[age_group, tax_week]: money | null

per employment, per tax_week:
  excess = max(0, earnings - secondary_threshold)
  if apprentice_status:
    rate = 0
  elif earner_age_group has age-related rate:
    if upper_secondary_threshold present and earnings > UST:
      rate_below = age_related_pct   # applied to portion up to UST
      rate_above = secondary_pct     # applied to portion above UST
    else:
      rate = age_related_pct
  else:
    rate = secondary_pct
  nic = rate * excess (piecewise if split above)

output: money per employment per tax_week
granularity: weekly facts, summed annually
edges: pay_reference_period != 1 week needs "prescribed equivalent"; earner
  under 16 (no charge); 0% age-related still counts as "liable"
```

**Structures.** scalar arithmetic; conditional branching; piecewise threshold;
parameter lookup with effective-dated versioning; point-in-time age classification;
defeater (apprentice 0% overrides age-related); scoped status (apprentice,
age-group, UST regime).

---

## 2. Child Support Act 1991 Sch 1 paras 1–5 — Maintenance calculations

URL: https://www.legislation.gov.uk/ukpga/1991/48/schedule/1

**Subject.** The tiered child-support formula: basic rate by gross weekly
income and number of qualifying children, reduced by relevant other children,
with reduced/flat/nil bands below £200.

**Text (extract).**
> 2(1) Subject to sub-paragraph (2), the basic rate is the following percentage
> of the non-resident parent's gross weekly income— 12% where the non-resident
> parent has one qualifying child; 16% where the non-resident parent has two
> qualifying children; 19% where the non-resident parent has three or more
> qualifying children.
>
> (2) If the gross weekly income of the non-resident parent exceeds £800, the
> basic rate is the aggregate of the amount found by applying sub-paragraph (1)
> in relation to the first £800 of that income and the following percentage of
> the remainder— 9% / 12% / 15% [by number of qualifying children].
>
> (3) If the non-resident parent also has one or more relevant other children,
> gross weekly income shall be treated for the purposes of sub-paragraphs (1)
> and (2) as reduced by the following percentage— 11% / 14% / 16%.
>
> 4(1) ... a flat rate of £7 is payable if the nil rate does not apply and—
> (a) the non-resident parent's gross weekly income is £100 or less; or (b) he
> receives any benefit, pension or allowance prescribed...
>
> 5. The rate payable is nil if the non-resident parent— (a) is of a prescribed
> description; or (b) has a gross weekly income of below £7.

**Pseudocode.**
```
inputs:
  gross_weekly_income[nrp, week]: money
  qualifying_children[nrp, week]: int        # for whom this calc is
  relevant_other_children[nrp, week]: int    # in NRP's household
  nrp_on_prescribed_benefit[nrp, week]: bool
  partner_on_prescribed_benefit[nrp, week]: bool
  nrp_is_prescribed_description[nrp, week]: bool

per nrp, per week:
  if nil_rate_applies (desc or gwi < 7): rate = 0
  elif flat_rate_applies (gwi <= 100 or on benefit): rate = 7
  elif reduced_rate (100 < gwi < 200): rate = regulations
  else: # basic
    roc_pct = {0:0, 1:11, 2:14, 3+:16}[min(relevant_other_children,3)]
    adj_gwi = gwi * (1 - roc_pct/100)
    tier1 = min(adj_gwi, 800)
    tier2 = max(0, adj_gwi - 800)
    qc = min(qualifying_children, 3)  # capped at 3+
    pct1 = {1:12, 2:16, 3:19}[qc]
    pct2 = {1:9,  2:12, 3:15}[qc]
    rate = tier1 * pct1/100 + tier2 * pct2/100

output: money per week per nrp; apportion across persons-with-care
granularity: weekly fact
edges: shared care adjustments (Sch 1 paras 7–8); multiple PWC apportionment;
  para 5A when NRP has a qualifying maintenance arrangement re non-qualifying
  child — floor at £7; tie-breaker rules for exactly £100 vs £200 boundary.
```

**Structures.** scalar arithmetic; piecewise with overlapping tiers; conditional
branching with priority order (nil > flat > reduced > basic); parameter lookup;
positive relational membership (qualifying children, relevant other children);
aggregation over a relation (count); defeater / exception precedence (para 5A
minimum-floor override); multi-entity crossing (NRP, PWC, child, partner).

---

## 3. SSI 2021/249 reg 79 — Maximum council tax reduction (Scotland)

URL: https://www.legislation.gov.uk/ssi/2021/249/regulation/79

**Subject.** Formula for the daily maximum Scottish council tax reduction,
with a band E–H taper and joint-and-several apportionment.

**Text (extract).**
> (1) ... the amount of a person's maximum council tax reduction in respect of
> a day for which the person is liable to pay council tax is amount A divided
> by the amount B where— (a) A is the amount set by the relevant authority as
> the council tax for the relevant financial year ... subject to— (i) any
> discount which may be appropriate to that dwelling, and (ii) any reduction in
> liability for council tax under Regulations made under section 80 of the
> Act ... other than a reduction under these Regulations, and (b) B is the
> number of days in that financial year, less any deductions in respect of
> non-dependants which fall to be made under regulation 90.
>
> (2) ... for dwellings in bands E to H the amount is (A − A/C) / B less any
> non-dependant deductions ... where C is 1.075 (E), 1.125 (F), 1.175 (G),
> 1.225 (H).
>
> (4) Where an applicant is jointly and severally liable for council tax ...
> amount A is to be divided by the number of persons who are jointly and
> severally liable for that tax.

**Pseudocode.**
```
inputs:
  ct_annual[dwelling, fy]: money            # authority-set
  ct_discounts[dwelling, fy]: money
  ct_other_reductions[dwelling, fy]: money
  band[dwelling]: enum {A..H}
  days_in_fy[fy]: int
  non_dep_deductions[person, day]: money    # reg 90
  jointly_liable_persons[dwelling, day]: set
  is_student_excluded[person, day]: bool    # reg 20(2)

per person, per day:
  A_raw = ct_annual - ct_discounts - ct_other_reductions
  liable_count = |{p in jointly_liable_persons : not is_student_excluded(p)}|
  if liable_count > 1 and partner-only-case is false:
    A = A_raw / liable_count
  else:
    A = A_raw
  B = days_in_fy
  if band in {E,F,G,H}:
    C = {E:1.075, F:1.125, G:1.175, H:1.225}[band]
    max_reduction = (A - A/C) / B - non_dep_deductions
  else:
    max_reduction = A / B - non_dep_deductions

output: money per person per day
granularity: daily fact; annual params
edges: partner-only joint liability disables (4); mid-year band change;
  negative result (if non-dep deductions exceed A/B) — floored at 0 implicit.
```

**Structures.** scalar arithmetic; conditional branching on band enum; parameter
lookup with effective-dated versioning; partial-period / per-day apportionment
from annual total; aggregation over a relation (count of joint-liable persons);
anti-join (exclude students); multi-entity crossing (person, dwelling, partner).

---

## 4. UKSI 2006/965 reg 2 — Rate of child benefit

URL: https://www.legislation.gov.uk/uksi/2006/965/regulation/2

**Subject.** Weekly child benefit rate, with enhanced rate only for the eldest
child in a household and tie-break across partners/polygamous marriages.

**Text (extract).**
> (1) The weekly rate of child benefit payable in respect of a child or
> qualifying young person shall be— (a) subject to paragraphs (2) to (5), in a
> case where in any week a child or qualifying young person is the only person
> or, if not the only person, the elder or eldest person in respect of whom
> child benefit is payable to a person, £26.05 ("the enhanced rate"); (b) in
> any other case, £17.25.
>
> (2) If, in any week— (a) a person is— (i) living with his spouse or civil
> partner, (ii) living with another person as his spouse or civil partner, or
> (iii) a member of a polygamous marriage ... ; (b) child benefit would, but
> for this paragraph, be payable to that person ... at the enhanced rate; and
> (c) child benefit would, but for this paragraph, be payable at that rate to
> one of the other [cohabiting] persons ... in respect of another child ... ,
> the enhanced rate shall be payable in that week in respect of only the elder
> or eldest of the children.
>
> (4) Child benefit shall not be payable at the enhanced rate if the person to
> whom child benefit is payable is— (a) a voluntary organisation; or (b) a
> person residing (otherwise than as mentioned in paragraph (2)(a)) with a
> parent of the child or qualifying young person in respect of whom it is
> payable.

**Pseudocode.**
```
inputs:
  child_benefit_receivable[claimant, child, week]: bool
  child_dob[child]: date
  claimant_household[claimant, week]: household_id   # cohab / polygamous
  claimant_is_voluntary_org[claimant]: bool
  claimant_resides_with_parent[claimant, child, week]: bool

per household, per week:
  candidates = {(claimant, child) : child_benefit_receivable}
  eldest = argmax over candidates by child_dob (earliest DOB)
  for (claimant, child) in candidates:
    base = 17.25
    if (claimant, child) == eldest
       and not claimant_is_voluntary_org(claimant)
       and not claimant_resides_with_parent(claimant, child, week):
       rate = 26.05
    else:
       rate = 17.25

output: money per claimant per child per week
granularity: weekly fact
edges: tied DOBs (statute silent — in practice first-registered); cross-household
  tie-break via para (2) (aggregates across cohabiting partners, not just one
  claimant); para (5) interactions with other benefits (elided here).
```

**Structures.** scalar lookup; conditional branching; aggregation over a relation
with filter (argmin of DOB across household); multi-entity crossing (claimant,
child, partner, household); defeater / exception (voluntary org, residing-with-parent);
anti-join across households; parameter lookup with effective-dated versioning
(£26.05 / £17.25 uprated annually).

---

## 5. CTA 2010 s.18A — Profits charged at the standard small profits rate

URL: https://www.legislation.gov.uk/ukpga/2010/4/section/18A

**Subject.** Qualifying test for the corporation tax small profits rate:
UK-resident, not a close investment-holding company, augmented profits within
the lower limit, no ring fence profits.

**Text (full).**
> (1) Corporation tax is charged at the standard small profits rate on a
> company's taxable total profits of an accounting period which are not ring
> fence profits if— (a) the company is UK resident in the accounting period,
> (b) it is not a close investment-holding company in the period, and (c) its
> augmented profits of the accounting period do not exceed the lower limit.
>
> (2) In this Act "the standard small profits rate" means a rate that— (a) is
> lower than the main rate, and (b) is set by Parliament for the financial year
> as the standard small profits rate.
>
> (3) In this Part "ring fence profits" has the same meaning as in Part 8 (see
> section 276).
>
> (4) In the case of a company with ring fence profits, see section 279A(3)
> (small ring fence profits rate chargeable on ring fence profits).

**Pseudocode.**
```
inputs:
  taxable_total_profits[co, ap]: money
  ring_fence_profits[co, ap]: money
  augmented_profits[co, ap]: money     # defined in s.18L
  uk_resident[co, ap]: bool
  is_close_investment_holding[co, ap]: bool
  lower_limit[ap]: money               # parameter, scaled for associated cos
  small_profits_rate[fy]: pct          # parameter
  main_rate[fy]: pct

per co, per ap:
  non_rfp = taxable_total_profits - ring_fence_profits
  qualifies = uk_resident
              and not is_close_investment_holding
              and augmented_profits <= lower_limit
  if qualifies:
    tax_on_non_rfp = non_rfp * small_profits_rate
  else:
    # main rate or marginal relief (s.18B) applies
    ...

output: money per company per accounting period
granularity: accounting-period fact, with financial-year-apportionment when AP
  straddles 1 April
edges: AP straddling 1 April splits between FYs with different rates;
  associated-companies reduction of lower_limit (s.18D); short AP scales limit.
```

**Structures.** scalar arithmetic; conditional branching; positive relational
membership (UK-resident set); anti-join (exclude close investment-holding);
threshold test; parameter lookup with effective-dated versioning; partial-period
apportionment across financial-year boundary; scoped status.

---

## 6. ITEPA 2003 s.180 — Threshold for beneficial loan charge

URL: https://www.legislation.gov.uk/ukpga/2003/1/section/180

**Subject.** De minimis: the taxable-cheap-loan benefit-in-kind charge is
disapplied if the aggregate outstanding balance stays at or below £10,000 for
the whole year, with a separate threshold for non-qualifying loans.

**Text (extract).**
> (1) Section 175 does not have effect in relation to an employee and a tax
> year— (a) if the normal £10,000 threshold is not exceeded, or (b) where the
> loan is a non-qualifying loan and that threshold is exceeded, if the £10,000
> threshold for non-qualifying loans is not exceeded.
>
> (2) The normal £10,000 threshold is not exceeded if at all times in the year
> the amount outstanding on the loan (or, if two or more employment-related
> loans which are taxable cheap loans are outstanding in the year, the
> aggregate of the amount outstanding on them) does not exceed £10,000.
>
> (3) The £10,000 threshold for non-qualifying loans is not exceeded if at all
> times in the year the amount outstanding on the loan (or if two or more
> employment-related loans which are non-qualifying loans are outstanding in
> the year, the aggregate of the amounts outstanding on them) does not exceed
> £10,000.
>
> (5) [a loan is "qualifying" in a year if interest on it is eligible for
> relief under s.383 ITA 2007, ... , is deductible against trade profits, or
> against UK property business profits].

**Pseudocode.**
```
inputs:
  loan_balance[loan, day]: money
  loan_is_taxable_cheap[loan, year]: bool
  loan_is_qualifying[loan, year]: bool    # by reference to interest relief rules
  employee_of[loan, year]: employee

per employee, per year:
  cheap_loans = {l : employee_of(l,year)=employee and loan_is_taxable_cheap}
  max_total = max over days in year of sum_{l in cheap_loans} loan_balance[l,day]
  if max_total <= 10_000: disapply = true
  else:
    non_qual = {l in cheap_loans : not loan_is_qualifying[l,year]}
    max_non_qual = max over days of sum_{l in non_qual} loan_balance[l,day]
    disapply = (max_non_qual <= 10_000)
  # if disapply, s.175 charge does not apply for the year

output: bool (threshold test) per employee per year
granularity: daily balances aggregated to a year-level max-over-time
edges: loans opened/closed mid-year; joint employments; year is tax year not AP.
```

**Structures.** scalar arithmetic; aggregation over a relation with filter
(sum of balances; then max-over-days); threshold test; anti-join
(non-qualifying subset); cross-reference to parameterised test for "qualifying"
via another statute; point-in-time vs over-period facts (daily balance vs
yearly "at all times" predicate); defeater (non-qualifying threshold relieves
when main threshold exceeded).

---

## 7. FA 2013 s.99 — ATED amount of tax chargeable

URL: https://www.legislation.gov.uk/ukpga/2013/29/section/99

**Subject.** Sets the annual chargeable amount for the annual tax on enveloped
dwellings by a step table on taxable value, with part-year apportionment for
mid-period entry.

**Text (extract).**
> (1) The amount of tax charged for a chargeable period with respect to a
> single-dwelling interest is stated in subsection (2) or (3).
>
> (2) If the chargeable person is within the charge with respect to the
> single-dwelling interest on the first day of the chargeable period, the
> amount of tax charged is equal to the annual chargeable amount.
>
> (3) Otherwise, the amount of tax charged is equal to the relevant fraction of
> the annual chargeable amount.
>
> (4) The annual chargeable amount for a single-dwelling interest and a
> chargeable period is determined in accordance with the following table, by
> reference to the taxable value of the interest on the relevant day:
> £3,500 (£500k–£1m); £7,000 (£1m–£2m); £23,350 (£2m–£5m); £54,450 (£5m–£10m);
> £109,050 (£10m–£20m); £218,200 (over £20m).
>
> (6) The relevant fraction is N/Y where N is the number of days from (and
> including) the relevant day to the end of the chargeable period; Y is the
> number of days in the chargeable period.

**Pseudocode.**
```
inputs:
  taxable_value[interest, relevant_day]: money     # revalued every 5 yrs
  chargeable_period[year]: (start, end)            # 1 Apr – 31 Mar
  chargeable_person_entry_day[person, interest, cp]: date | null
  in_charge_on_first_day[person, interest, cp]: bool
  ATED_bands[cp]: list of (lower, upper, annual_amount)  # parameter

per (person, interest, cp):
  tv = taxable_value[interest, relevant_day(cp)]
  annual_amount = lookup_band(ATED_bands[cp], tv)
  if in_charge_on_first_day:
    tax = annual_amount
  else:
    N = days_from(entry_day, end_of_cp) + 1
    Y = days_in(cp)
    tax = annual_amount * N / Y

output: money per person per interest per chargeable period
granularity: chargeable period (12 months from 1 April); daily cut-ins for
  part-period; 5-yearly revaluation dates for tv
edges: mid-period disposal (s.106 adjustment); interim relief (s.100); band
  boundaries — table uses "more than X, not more than Y" (left-open, right-closed).
```

**Structures.** scalar arithmetic; step-function lookup (band table);
partial-period / interval intersection (N/Y apportionment); parameter lookup
with effective-dated versioning (bands, revaluation); point-in-time fact
(taxable value on the "relevant day"); date arithmetic (days-in, days-from);
multi-entity crossing (person, single-dwelling interest, chargeable period).

---

## 8. Pensions Act 2008 s.3 — Automatic enrolment

URL: https://www.legislation.gov.uk/ukpga/2008/30/section/3

**Subject.** Defines the automatic-enrolment duty on employers: jobholder
aged 22 to SPA, earnings above the £10,000 trigger in the pay reference
period, not already an active member of a qualifying scheme.

**Text (extract).**
> (1) This section applies to a jobholder— (a) who is aged at least 22, (b)
> who has not reached pensionable age, and (c) to whom earnings of more than
> £10,000 are payable by the employer in the relevant pay reference period
> (see section 15).
>
> (2) The employer must make prescribed arrangements by which the jobholder
> becomes an active member of an automatic enrolment scheme with effect from
> the automatic enrolment date.
>
> (3) Subsection (2) does not apply if the jobholder was an active member of a
> qualifying scheme on the automatic enrolment date.
>
> (4) Subsection (2) does not apply if, within the prescribed period before the
> automatic enrolment date, the jobholder ceased to be an active member of a
> qualifying scheme because of any action or omission by the jobholder.
>
> (6B) In the case of a pay reference period of less or more than 12 months,
> subsection (1) applies as if the amount in paragraph (c) were proportionately
> less or more.

**Pseudocode.**
```
inputs:
  jobholder_dob[person]: date
  state_pension_age[person, date]: date
  earnings[person, employer, pay_ref_period]: money
  pay_ref_period_length_months[pay_ref_period]: number
  active_member_of_qualifying_scheme[person, date]: bool
  ceased_active_member_due_to_own_action[person, [date_from, date_to]]: bool
  auto_enrolment_trigger[year]: money     # £10,000 parameter
  opt_out_lookback[year]: days            # "prescribed period" parameter

per (person, employer, pay_ref_period):
  d = auto_enrolment_date(person, employer)   # first day s.3 applies (s.4 subject)
  age_ok   = age_at(d) >= 22 and d < state_pension_age(person)
  trigger  = auto_enrolment_trigger * (pay_ref_period_length_months / 12)
  earn_ok  = earnings > trigger
  duty     = age_ok and earn_ok
          and not active_member_of_qualifying_scheme[person, d]
          and not ceased_active_member_due_to_own_action[person, [d - opt_out_lookback, d]]

output: bool (employer duty) per (person, employer, pay-ref-period)
granularity: pay-reference-period fact, indexed to an automatic-enrolment date
edges: SPA equalisation; multiple concurrent employers; variable PRP length;
  re-enrolment cycle (s.5 / s.6); leavers and returners; cross-border workers.
```

**Structures.** conditional branching; threshold test with pro-rata scaling;
date arithmetic (age, SPA); parameter lookup with effective-dated versioning;
scoped status (active member, pensionable age); anti-join (not-already-enrolled,
not-recently-opted-out); multi-entity crossing (jobholder × employer × pay
reference period × scheme); point-in-time status at automatic enrolment date.

---

## 9. UKSI 2015/173 reg 10 — Weekly deferral increment percentage

URL: https://www.legislation.gov.uk/uksi/2015/173/regulation/10

**Subject.** The statutory percentage that governs how much state pension goes
up per week of deferral: one-ninth of one per cent (so a full year of deferral
uplifts pension by roughly 5.8%).

**Text (full).**
> For the purposes of section 17(4) of the 2014 Act (effect of pensioner
> postponing or suspending state pension), the specified percentage is
> one-ninth of 1%.

**Pseudocode.**
```
inputs:
  spa_reached[pensioner]: date
  claim_commencement[pensioner]: date
  pension_suspensions[pensioner]: list of (from, to)     # deferral intervals
  base_weekly_rate[pensioner, date]: money               # new state pension
  deferral_pct_per_week[date]: pct   # 1/9 % = 0.11111...

per pensioner, per week on which pension is in payment:
  deferral_weeks = count_weeks_in( [spa_reached, first_claim_or_resumption) )
                 + sum over (from,to) in pension_suspensions of weeks_in(from,to)
  increment_pct = deferral_weeks * deferral_pct_per_week
  pension = base_weekly_rate * (1 + increment_pct / 100)

output: money per pensioner per week
granularity: weekly; underlying "deferral count" is an over-period aggregate
edges: partial weeks (statute uses whole weeks only); multiple suspend/resume
  cycles; overlap with inherited entitlements; limit on how early deferral
  counts (post-SPA only).
```

**Structures.** scalar arithmetic; parameter lookup (uprated via amending SIs);
aggregation over a relation (count of deferral weeks across intervals);
partial-period / interval intersection (weeks between SPA and first claim);
date arithmetic; point-in-time vs over-period facts (base rate is point-in-time,
increment is cumulative-over-period).

---

## 10. ERA 1996 s.108 — Qualifying period for unfair-dismissal right

URL: https://www.legislation.gov.uk/ukpga/1996/18/section/108

**Subject.** The two-year continuous-employment gate on the right not to be
unfairly dismissed, plus a long enumerated list of exceptions where no
qualifying period applies (discrimination-like, whistleblowing, health-and-
safety, trade-union, family-leave, etc.).

**Text (extract).**
> (1) Section 94 does not apply to the dismissal of an employee unless he has
> been continuously employed for a period of not less than two years ending
> with the effective date of termination.
>
> (2) If an employee is dismissed by reason of any such requirement or
> recommendation as is referred to in section 64(2), subsection (1) has effect
> in relation to that dismissal as if for the words "two years" there were
> substituted the words "one month".
>
> (3) Subsection (1) does not apply if— ... (b) subsection (1) of section 99
> [family leave] ... applies, (c) subsection (1) of section 100 [health and
> safety] ... applies, (d) section 101 [Sunday working, shop workers] applies,
> ... (f) section 103 [redundancy, employee representatives] applies, (ff)
> section 103A [protected disclosure / whistleblowing] applies, (g) section
> 104 [assertion of a statutory right] ... , (gg) section 104A [national
> minimum wage], (gh) section 104B [tax credits], ... (h) section 105
> [selection for redundancy in a protected reason] applies, ... (i)–(k)
> various TUPE / fixed-term / part-time / European Company regulations.

**Pseudocode.**
```
inputs:
  employment_spans[employee, employer]: list of (start, end)
  effective_date_of_termination[employee, employer]: date
  reason_for_dismissal[employee, employer]: enum    # may match >1 category
  dismissed_for_64_2_requirement: bool

per (employee, employer) on dismissal:
  edt = effective_date_of_termination
  continuous_service = continuous_employment_end_to_end(employment_spans, ending at edt)
  base_qp = 2 years
  if dismissed_for_64_2_requirement: base_qp = 1 month
  has_qp = continuous_service >= base_qp

  exception_list = {ss 98B, 99, 100, 101, 101ZA, 101A, 102, 103, 103A,
                    104, 104A, 104B, 104C, 104D, 104E, 104F, 104G, 105,
                    reg 28 TICE 1999, reg 7 PTW Regs 2000,
                    reg 6 FTE Regs 2002, reg 42 ECR 2004, ...}
  disapply_qp = any(reason_matches(s) for s in exception_list)

  entitled = disapply_qp or has_qp
  # If entitled and unfairly dismissed (s.98), s.94 right applies

output: bool per dismissal (gate for s.94)
granularity: point-in-time test at effective date of termination
edges: continuity rules in ss.210–219 (strike breaks, TUPE transfers, reinstate-
  ment after appeal); multiple reasons for dismissal (Smith v Churchills Stairlifts
  etc.); week-1 rollover (Pacitti Jones v O'Brien); statutory notice extension
  of EDT (s.97(2)) — can push employee over the two-year line.
```

**Structures.** conditional branching; positive relational membership (set of
disapplying sections); defeater / exception precedence (any exception disapplies
the qualifying period); date arithmetic (continuous-employment calculation);
partial-period / interval intersection (gaps between spans, statutory notice
extension); legal fiction (s.97(2) statutory notice deemed EDT); scoped status
(continuity of employment across transfers); parameter lookup (two-year vs
one-month regime depending on reason).

---

## Coverage summary

| # | Citation | Domain | Statute |
|---|----------|--------|---------|
| 1 | SSCBA 1992 s.9 | NIC (employer Class 1) | ukpga/1992/4 |
| 2 | Child Support Act 1991 Sch 1 | Child maintenance | ukpga/1991/48 |
| 3 | SSI 2021/249 reg 79 | Council tax reduction (Scotland) | ssi/2021/249 |
| 4 | UKSI 2006/965 reg 2 | Child benefit rates | uksi/2006/965 |
| 5 | CTA 2010 s.18A | Corporation tax (small profits) | ukpga/2010/4 |
| 6 | ITEPA 2003 s.180 | Income tax (beneficial loans) | ukpga/2003/1 |
| 7 | FA 2013 s.99 | ATED (property tax) | ukpga/2013/29 |
| 8 | Pensions Act 2008 s.3 | Auto-enrolment | ukpga/2008/30 |
| 9 | UKSI 2015/173 reg 10 | State pension deferral | uksi/2015/173 |
| 10 | ERA 1996 s.108 | Employment rights (unfair dismissal) | ukpga/1996/18 |

Ten policy areas, ten distinct statutes, no overlap with audits 001 or 002 or
the earlier exclusion list.
