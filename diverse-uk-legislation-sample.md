# Ten diverse UK legislation sections for DSL stress test

Sampled via the Lex API (`https://lex.lab.i.ai.gov.uk`), cross-checked against legislation.gov.uk. Spread across tax, benefits, pensions, family, corporate, devolved, and employment law. None overlap with the sections listed as already covered.

---

## 1. Income Tax Act 2007 s.55B — Marriage allowance: tax reduction entitlement

URL: https://www.legislation.gov.uk/ukpga/2007/3/section/55B

Summary: Transferable married-couple tax reduction — the recipient spouse gets a tax reduction equal to the basic rate applied to a transferable amount, provided the other spouse has made an election and the recipient is a basic-rate taxpayer.

Operative text (quoted, abbreviated):

> (1) An individual is entitled to a tax reduction for a tax year of the appropriate percentage of the transferable amount if the conditions in subsection (2) are met.
> (2) The conditions are that— (a) the individual is the gaining party ... in the case of an election under section 55C which is in force for the tax year, (b) the individual is not, for the tax year, liable to tax at a rate other than the basic rate, the default basic rate, the savings basic rate, the dividend nil rate, the Scottish basic rate ... (c) the individual meets the requirements of section 56 (residence) for the tax year, and (d) neither the individual nor the relinquishing spouse or civil partner makes a claim ... under section 45 (married couple's allowance ...) or section 46 ...
> (3) "The appropriate percentage" is the basic rate or default basic rate or, in the case of a Scottish taxpayer or Welsh taxpayer, the Scottish basic rate or Welsh basic rate ...
> (4) "The transferable amount"— (a) for the tax year 2015-16, is £1,060, and (b) for the tax year 2016-17 and subsequent tax years, is 10% of the amount of personal allowance specified in section 35(1) for the tax year ...
> (5) If the transferable amount calculated in accordance with subsection (4)(b) would otherwise not be a multiple of £10, it is to be rounded up to the nearest amount which is a multiple of £10.
> (6) If an individual is entitled to a tax reduction under subsection (1) by reference to an election under section 55C, the personal allowance to which the relinquishing spouse or civil partner is entitled under section 35 ... is reduced for the tax year by the transferable amount.

Structured computation:

```
inputs:
  individual (Person), tax_year (Year),
  election(relinquishing, gaining, tax_year)  # relation from s.55C
  rate_liability(individual, tax_year)        # set of tax rates
  residence_ok(individual, tax_year)          # s.56
  married_couple_claim(individual | spouse, tax_year)
  personal_allowance(tax_year), basic_rate(jurisdiction, tax_year)
  transferable_amount = 1060 if tax_year == 2015-16
                       else round_up_to_10(personal_allowance(tax_year) * 0.10)

output:
  tax_reduction(individual, tax_year) : Money
  personal_allowance_adjustment(relinquishing, tax_year) : Money

rule:
  if election(R, individual, tax_year) and
     rate_liability(individual, tax_year) subset of {basic, default_basic, savings_basic, ...} and
     residence_ok(individual, tax_year) and
     not married_couple_claim(individual | R, tax_year):
       tax_reduction := basic_rate(juris(individual), tax_year) * transferable_amount
       personal_allowance(R, tax_year) -= transferable_amount
       # but if individual dies during tax_year, the -= is ignored
time granularity: tax year
edge cases: death mid-year disables reduction on the relinquisher; dividend nil rate taxpayers allowed only if they would not have been upper/additional dividend liable.
```

Structures used: scalar arithmetic; conditional branching; positive relational membership (election); anti-join (no s.45/46 claim); parameter lookup with effective-dated versioning (transferable amount rule splits at 2015-16 vs 2016-17+; personal allowance is effective-dated); multi-entity crossing (individual and relinquishing spouse); counterfactual (dividend nil rate: "would for that year neither be liable to ... if section 13A were omitted"); defeater (s.55B ignored if remittance basis claim under s.809G/845E).

---

## 2. Corporation Tax Act 2009 s.1169 — Artificially inflated claims for relief or tax credit

URL: https://www.legislation.gov.uk/ukpga/2009/4/section/1169

Summary: Anti-avoidance: transactions attributable to arrangements whose main object is to obtain or increase land-remediation or BLAGAB relief or tax credit are disregarded for computing that relief.

Operative text:

> (1) To the extent that a transaction is attributable to arrangements entered into wholly or mainly for a disqualifying purpose, it is to be disregarded for the purposes mentioned in subsection (2).
> (2) Those purposes are determining for an accounting period the amount of— (a) any relief to which a company is entitled under Chapter 2, (b) any land remediation tax credits to which a company is entitled under section 1151, (c) any relief ... under section 1161 or 1162, and (d) any BLAGAB tax credits ... under section 1164.
> (3) Arrangements are entered into wholly or mainly for a "disqualifying purpose" if their main object, or one of their main objects, is to enable a company to obtain— (a) relief under Chapter 2 to which the company would not otherwise be entitled or of a greater amount than that to which it would otherwise be entitled, (b) a land remediation tax credit ... (c) relief under section 1161 or 1162 ... or (d) a life assurance company tax credit ...
> (4) In this section "arrangements" includes any scheme, agreement or understanding, whether or not legally enforceable.

Structured computation:

```
inputs:
  transaction T, arrangements A, company C, accounting_period AP
  attributable(T, A), purpose(A, disqualifying) : Bool
  baseline_relief(C, AP)    # relief in counterfactual world where A absent
  actual_relief(C, AP)      # relief including T
output:
  relief_allowed(C, AP) : Money
rule:
  disqualifying(A) iff
     main_object(A) ∈ {obtain relief C would not otherwise be entitled to,
                       obtain a greater amount than otherwise}
  disregarded_transactions := {T | ∃A: attributable(T,A) ∧ disqualifying(A)}
  relief_allowed := recompute Chapter 2 / s.1151 / s.1161-2 / s.1164 excluding disregarded_transactions
time granularity: accounting period
edge cases: partial attribution ("to the extent that"), so T may be disregarded proportionally.
```

Structures used: conditional branching; anti-join / exclusion of transactions; counterfactual ("would not otherwise be entitled", "greater amount than ... otherwise"); scoped status ("for the purposes of determining ... relief"); legal fiction ("disregarded"); defeater / exception precedence (overrides Chapter 2 entitlement); aggregation (relief amounts summed over transactions, minus disregarded ones).

---

## 3. Children Act 1989 s.2 — Parental responsibility for children

URL: https://www.legislation.gov.uk/ukpga/1989/41/section/2

Summary: Allocates parental responsibility (PR) between parents depending on marital/civil-partnership status at birth and HFEA parenthood; multiple people may hold PR concurrently.

Operative text:

> (1) Where a child's father and mother were married to, or civil partners of, each other at the time of his birth, they shall each have parental responsibility for the child.
> (1A) Where a child— (a) has a parent by virtue of section 42 of the Human Fertilisation and Embryology Act 2008; or (b) has a parent by virtue of section 43 of that Act and is a person to whom section 1(3) of the Family Law Reform Act 1987 applies, the child's mother and the other parent shall each have parental responsibility for the child.
> (2) Where a child's father and mother were not married to, or civil partners of, each other at the time of his birth— (a) the mother shall have parental responsibility for the child; (b) the father shall have parental responsibility for the child if he has acquired it (and has not ceased to have it) in accordance with the provisions of this Act.
> (2A) Where a child has a parent by virtue of section 43 of the 2008 Act and is not a person to whom section 1(3) of the 1987 Act applies— (a) the mother shall have parental responsibility ...; (b) the other parent shall have parental responsibility ... if she has acquired it (and has not ceased to have it) ...
> (5) More than one person may have parental responsibility for the same child at the same time.
> (6) A person who has parental responsibility for a child at any time shall not cease to have that responsibility solely because some other person subsequently acquires parental responsibility for the child.
> (7) Where more than one person has parental responsibility for a child, each of them may act alone and without the other (or others) ...
> (9) A person who has parental responsibility for a child may not surrender or transfer any part of that responsibility to another but may arrange for some or all of it to be met by one or more persons acting on his behalf.

Structured computation:

```
inputs:
  child C, parents (mother M, father F or other_parent OP)
  marital_status(M, F, at = birth(C)) ∈ {married, civil_partners, none}
  hfea_parent_s42(X, C), hfea_parent_s43(X, C)
  flra_1_3_applies(C)
  acquired_PR(X, C, t), ceased_PR(X, C, t)
output:
  has_PR(Person, Child, t) : Bool   -- a many-to-one relation evolving over time
rule:
  if married_or_CP_at_birth(M, F, C):  has_PR(M,C,*) ∧ has_PR(F,C,*)
  else:                                 has_PR(M,C,*) and (has_PR(F,C,t) iff acquired_PR(F,C,t) ∧ ¬ceased_PR(F,C,t))
  if hfea_parent_s42(OP,C) or (hfea_parent_s43(OP,C) ∧ flra_1_3(C)):
      has_PR(M,C,*) ∧ has_PR(OP,C,*)
  monotone: once true, stays true unless explicitly ceased (s.2(6))
  multiplicity: |{x : has_PR(x, C, t)}| ≥ 0, unbounded
time granularity: continuous, with event-based updates (acquisition/cessation)
edge cases: s.2(9) — cannot transfer PR but can delegate; acting alone permitted under s.2(7) subject to enactments requiring joint consent.
```

Structures used: positive relational membership; multi-entity crossing (pair/tuple of parent × child); conditional branching; fixed-point / monotone derivation (PR is persistent once acquired); partial-period / interval (PR evaluated at time t); anti-join (father has PR only if not ceased); legal fiction / recharacterisation (abolition of "natural guardian" rule in s.2(4)); scoped status ("for the purposes of this Act").

---

## 4. Corporation Tax Act 2009 s.1217J — Theatre tax relief: amount of additional deduction

URL: https://www.legislation.gov.uk/ukpga/2009/4/section/1217J

Summary: Computes the additional CT deduction for a separate theatrical trade in a given period of account: the deduction is the lower of UK core expenditure or 80% of total qualifying expenditure, netted against deductions already taken in prior periods.

Operative text:

> (1) The amount of an additional deduction to which a company is entitled as a result of a claim under section 1217H is calculated as follows.
> (2) For the first period of account during which the separate theatrical trade is carried on, the amount of the additional deduction is E, where— E is— so much of the qualifying expenditure incurred to date as is UK expenditure, or if less, 80% of the total amount of qualifying expenditure incurred to date.
> (3) For any period of account after the first, the amount of the additional deduction is — E − P where — E is— so much of the qualifying expenditure incurred to date as is UK expenditure, or if less, 80% of the total amount of qualifying expenditure incurred to date, and P is the total amount of the additional deductions given for previous periods.
> (4) The Treasury may by regulations amend the percentage specified in subsection (2) or (3).

Structured computation:

```
inputs:
  company C, separate_theatrical_trade T, period_of_account P_i (i = 1,2,...)
  uk_qualifying_expenditure_to_date(T, end(P_i))  : Money
  total_qualifying_expenditure_to_date(T, end(P_i))  : Money
  prior_additional_deductions(T, P_1..P_{i-1})  : Money
  percentage = 80% (modifiable by regulation)
output:
  additional_deduction(C, T, P_i) : Money
rule:
  E(i) = min(uk_qualifying_expenditure_to_date(i),
             percentage * total_qualifying_expenditure_to_date(i))
  if i == 1:  additional_deduction = E(1)
  else:       additional_deduction = E(i) − sum_{k<i} additional_deduction(k)
time granularity: period of account (variable-length, per company)
edge cases: claim must exist under s.1217H; percentage parameter may change between periods.
```

Structures used: scalar arithmetic; aggregation over a relation (sum of past deductions; sum of qualifying expenditure to date); conditional branching (first vs later period); parameter lookup with effective-dated versioning (percentage alterable by Treasury regulations); fixed-point / recursive derivation (each period depends on cumulative prior periods — tail recursion over period sequence); partial-period / interval intersection ("incurred to date" — cumulative over overlapping periods).

---

## 5. Employment and Support Allowance Regulations 2008 (SI 2008/794) reg 166 — Relevant week

URL: https://www.legislation.gov.uk/uksi/2008/794/regulation/166

Summary: Defines the seven-day "relevant week" window used to pro-rate ESA across part-weeks at the start, end, or benefit-week boundary of an award.

Operative text:

> (1) Where a part-week— (a) is the whole period for which an employment and support allowance is payable, or occurs at the beginning of an award, the relevant week is the period of 7 days ending on the last day of that part-week; or (b) occurs at the end of an award, the relevant week is the period of 7 days beginning on the first day of the part-week.
> (2) Where a claimant has an award of an employment and support allowance and that claimant's benefit week changes, for the purpose of calculating the amounts of an employment and support allowance payable for the part-week beginning on the day after the last complete benefit week before the change and ending immediately before the change, the relevant week is the period of 7 days beginning on the day after the last complete benefit week.

Structured computation:

```
inputs:
  award A of claimant K
  part_week PW ⊂ [start(A), end(A)]   # a subinterval shorter than 7 days
  benefit_week_change_event(K, t)
output:
  relevant_week(A, PW) : Interval(7 days)
rule:
  let L = last day of PW, F = first day of PW
  if PW is the whole payable period OR PW at start of A:
      relevant_week = [L - 6 days, L]
  else if PW at end of A:
      relevant_week = [F, F + 6 days]
  else if benefit_week_change during A:
      let LCBW = last complete benefit week before change
      relevant_week = [end(LCBW) + 1 day, end(LCBW) + 7 days]
time granularity: day; output is a 7-day interval
edge cases: multiple part-weeks in same award (start + end + change); need to distinguish which case applies.
```

Structures used: conditional branching; partial-period / interval intersection (part-week is a subinterval; relevant week is a 7-day window anchored to its endpoints); scoped status ("for the purpose of calculating"); legal fiction / recharacterisation (the part-week is treated as carrying a deemed "week" for averaging).

---

## 6. Statutory Paternity Pay and Statutory Adoption Pay (General) Regulations 2002 (SI 2002/2822) reg 35A — Meaning of "week"

URL: https://www.legislation.gov.uk/uksi/2002/2822/regulation/35A

Summary: Fixes the start and end dates of the first of the 26 qualifying continuous-employment weeks for SPP/SAP entitlement: the first week runs from the first day of employment to midnight the following Saturday.

Operative text:

> (1) This regulation applies where a person ("P") has been in employed earner's employment with the same employer in each of 26 consecutive weeks (but no more than 26 weeks), ending with— (a) in relation to P's entitlement to statutory paternity pay (birth), the week immediately preceding the 14th week before the expected week of the child's birth, or (b) in relation to P's entitlement to statutory paternity pay (adoption), the week in which P is notified that P has been matched with the child for the purposes of adoption.
> (2) For the purpose of determining whether P's employment amounts to a continuous period of at least 26 weeks (see sections 171ZA(2)(b) and 171ZL(2)(b) of the Act), the first of those 26 weeks is a period commencing on the first day of P's employment with the employer ("the start date") and ending at midnight on— (a) the first Saturday after the start date, or (b) where the start date is a Saturday, that day.

Structured computation:

```
inputs:
  person P, employer E
  start_date = first day of P's employment with E
  reference_week:                                          # context-dependent
     birth case: week immediately before 14th week before expected_week_of_birth(child)
     adoption case: week P is notified of match
output:
  continuity_satisfied(P, E, reference_week) : Bool
  week_1_interval(P, E) : Interval
rule:
  week_1 = [start_date, next_Saturday_midnight(start_date)]
           # if start_date is Saturday, end is Saturday midnight same day
  weeks_2..26 = 26 consecutive calendar weeks following week_1
  continuity_satisfied iff employed(P, E, each day) for all those weeks
                          and weeks end with reference_week
time granularity: day (Saturday-to-Saturday weeks); anchored to birth/adoption context
edge cases: start date is a Saturday (week 1 is a single day); exactly 26 weeks — "no more than 26 weeks" caveat.
```

Structures used: scalar arithmetic (day counts); conditional branching (start-on-Saturday edge case); partial-period / interval intersection (first week is a variable-length sub-week anchored on Saturday); multi-entity crossing (person × employer across a period); scoped status ("for the purpose of determining").

---

## 7. Housing Benefit Regulations 2006 (SI 2006/213) reg 70 — Maximum housing benefit

URL: https://www.legislation.gov.uk/uksi/2006/213/regulation/70

Summary: Maximum HB is 100% of the claimant's weekly eligible rent minus any non-dependant deductions.

Operative text:

> The amount of a person's appropriate maximum housing benefit in any week shall be 100 per cent. of his eligible rent calculated on a weekly basis in accordance with regulations 80 and 81 (calculation of weekly amounts and rent free periods) less any deductions in respect of non-dependants which fall to be made under regulation 74 (non-dependant deductions).

Structured computation:

```
inputs:
  claimant K, week w
  eligible_rent_weekly(K, w)    : Money          # per reg 80, 81
  non_dependants(K, w)          : Set[Person]    # household membership
  non_dep_deduction(nd, w)      : Money          # per reg 74 (banded table)
output:
  max_HB(K, w) : Money
rule:
  max_HB(K, w) = eligible_rent_weekly(K, w)
                 − Σ_{nd ∈ non_dependants(K, w)} non_dep_deduction(nd, w)
  max_HB >= 0  (floor implicit)
time granularity: week
edge cases: rent-free periods (reg 81 adjusts weekly figure to zero in some weeks).
```

Structures used: scalar arithmetic; aggregation over a relation (sum of deductions per non-dependant); positive relational membership (non-dependant ∈ household of claimant); parameter lookup with effective-dated versioning (non-dep deduction band amounts); partial-period / interval intersection (rent-free weeks zero out the eligible rent).

---

## 8. Pensions Act 2008 s.13 — Qualifying earnings

URL: https://www.legislation.gov.uk/ukpga/2008/30/section/13

Summary: Qualifying earnings for auto-enrolment contributions are gross earnings between two thresholds (currently £6,240 and £50,270 for a 12-month pay reference period), with linear pro-rating for shorter/longer pay reference periods.

Operative text:

> (1) A person's qualifying earnings in a pay reference period of 12 months are the part (if any) of the gross earnings payable to that person in that period that is— (a) more than £6,240, and (b) not more than £50,270.
> (2) In the case of a pay reference period of less or more than 12 months, subsection (1) applies as if the amounts in paragraphs (a) and (b) were proportionately less or more.
> (3) In this section, "earnings", in relation to a person, means sums of any of the following descriptions that are payable to the person in connection with the person's employment— (a) salary, wages, commission, bonuses and overtime; (b) statutory sick pay ...; (c) statutory maternity pay ...; (d) statutory paternity pay ...; (e) statutory adoption pay ...; (ea) statutory shared parental pay ...; (eb) statutory parental bereavement pay ...; (ec) statutory neonatal care pay ...; (f) sums prescribed for the purposes of this section.

Structured computation:

```
inputs:
  person P, pay_reference_period PRP of length months(PRP)
  earnings_components(P, PRP): { salary, wages, commission, bonuses, overtime,
                                 SSP, SMP, SPP, SAP, ShPP, SPBP, SNCP, prescribed }
output:
  qualifying_earnings(P, PRP) : Money
rule:
  lower  = 6240  * months(PRP) / 12
  upper  = 50270 * months(PRP) / 12
  gross  = Σ over earnings_components
  qualifying_earnings = clamp(gross, lower, upper) − lower
                      = max(0, min(gross, upper) − lower)
time granularity: pay reference period (variable months)
edge cases: PRP ≠ 12 months — thresholds proportionate; "prescribed" sums pull in extra components via regulation.
```

Structures used: scalar arithmetic; aggregation over a relation (sum of earnings components); conditional branching (below lower / between bounds / above upper); partial-period / interval intersection (pro-rata by PRP length); parameter lookup with effective-dated versioning (thresholds £6,240 / £50,270 updated by annual Order); scoped status ("for the purposes of this section" — prescribed sums).

---

## 9. Public Service Pensions Act 2013 s.10 — Pension age

URL: https://www.legislation.gov.uk/ukpga/2013/25/section/10

Summary: Couples normal/deferred pension age of public-service scheme members to their state pension age (floor of 65), except for uniformed services (firefighters, police, armed forces) whose normal pension age is fixed at 60; changes in SPA automatically flow through to all accrued benefits.

Operative text:

> (1) The normal pension age of a person under a scheme under section 1 must be— (a) the same as the person's state pension age, or (b) 65, if that is higher.
> (2) Subsection (1) does not apply in relation to— (a) fire and rescue workers who are firefighters, (b) members of a police force, and (c) members of the armed forces. The normal pension age of such persons under a scheme under section 1 must be 60.
> (3) The deferred pension age of a person under a scheme under section 1 must be— (a) the same as the person's state pension age, or (b) 65, if that is higher.
> (4) Where— (a) a person's state pension age changes, and (b) the person's normal or deferred pension age under a scheme under section 1 changes as a result of subsection (1) or (3), the change to the person's normal or deferred pension age must under the scheme apply in relation to all the benefits (including benefits already accrued under the scheme) which may be paid to or in respect of the person under the scheme and to which the normal or deferred pension age is relevant.
> (5) In this Act— (a) "normal pension age" ... means the earliest age at which the person is entitled to receive benefits under the scheme (without actuarial adjustment) on leaving the service ...; (b) "deferred pension age" ... means the earliest age at which the person is entitled to receive benefits under the scheme (without actuarial adjustment) after leaving the service ... at a time before normal pension age ...; (c) "state pension age", in relation to a person, means the pensionable age of the person as specified from time to time in Part 1 of Schedule 4 to the Pensions Act 1995.

Structured computation:

```
inputs:
  member M, scheme S (a scheme made under s.1)
  category(M) ∈ {firefighter, police, armed_forces, other}
  state_pension_age(M)  : Integer (from PA 1995 Sch 4, time-varying)
output:
  normal_pension_age(M, S)    : Integer
  deferred_pension_age(M, S)  : Integer
rule:
  if category(M) ∈ {firefighter, police, armed_forces}:
      normal_pension_age := 60
  else:
      normal_pension_age := max(state_pension_age(M), 65)
  deferred_pension_age := max(state_pension_age(M), 65)
  when state_pension_age(M) changes:
      normal_pension_age and deferred_pension_age recompute;
      the change applies retroactively to ALL benefits already accrued
time granularity: member × scheme, with monotone recomputation on SPA change
edge cases: category change mid-career; SPA schedule amendments; "without actuarial adjustment" caveat in the definition.
```

Structures used: scalar arithmetic (max); conditional branching (category split); positive relational membership (category(M)); parameter lookup with effective-dated versioning (PA 1995 Sch 4 changes over time); fixed-point / recursive derivation (SPA change propagates to accrued benefits); counterfactual / scoped status ("without actuarial adjustment" — the benefit is measured against a hypothetical actuarial baseline); multi-entity crossing (member × scheme).

---

## 10. Council Tax Reduction (Scotland) Regulations 2021 (SSI 2021/249) reg 71 — Notional capital

URL: https://www.legislation.gov.uk/ssi/2021/249/regulation/71

Summary: Deprivation rule: if a CTR applicant has given away capital to secure or increase their award, the authority treats them as still owning it, except where disposed of to pay debts or make reasonable purchases; failing to claim capital that could have been acquired also counts as deprivation.

Operative text:

> (1) An applicant is to be treated as possessing capital (and is assumed to have a yield from that capital as described in regulation 63) where the applicant has, in the opinion of a relevant authority, deprived themselves of that capital for the purpose of securing entitlement to council tax reduction or an increased amount of council tax reduction.
> (2) Where an applicant— (a) deprived themselves of capital for the purpose of securing entitlement to universal credit or to an increased amount of universal credit, and (b) was treated as possessing that capital under regulation 50 of the 2013 Regulations for the purposes of calculating the applicant's award of universal credit, the applicant is to be treated as possessing that capital under paragraph (1) for the purposes of calculating an applicant's capital under these Regulations.
> (3) An applicant is not to be treated as depriving themselves of capital under paragraph (1) if the applicant disposes of it for the purposes of— (a) reducing or paying a debt owed by the applicant, or (b) purchasing goods or services if the expenditure was reasonable in the circumstances of the applicant's case.
> (4) For the purposes of this regulation, "deprived" includes a failure to make an application for capital that would have been acquired by the applicant had it been sought.

Structured computation:

```
inputs:
  applicant A, relevant authority RA, date d
  actual_capital(A, d)        : Money
  disposed_capital(A, d)      : Set[(asset, amount, reason)]
  unclaimed_capital(A, d)     : Money     # would have been acquired if sought
  purpose(reason)  ∈ {secure_CTR, increase_CTR, pay_debt, reasonable_purchase, other, secure_UC, increase_UC}
  prior_UC_notional_capital(A, d) : Money  # per UC Regs 2013 reg 50
output:
  capital_for_CTR(A, d) : Money
rule:
  base = actual_capital(A, d)
  notional = Σ amount over disposed assets where
              RA_opinion(purpose ∈ {secure_CTR, increase_CTR})
              AND NOT (reason ∈ {pay_debt, reasonable_purchase})
  notional += unclaimed_capital(A, d)  -- deeming under (4)
  notional += prior_UC_notional_capital(A, d) if purpose ∈ {secure_UC, increase_UC}
  capital_for_CTR = base + notional
  yield: derive assumed income under reg 63
time granularity: weekly assessment
edge cases: RA's opinion is itself a discretionary input; "reasonable in the circumstances" is a standard test; double-counting avoided where UC already deemed capital.
```

Structures used: scalar arithmetic; conditional branching; anti-join / absence ("not to be treated ... if ... debt or reasonable purchase"); counterfactual ("would have been acquired ... had it been sought" and UC "would have obtained greater award"); legal fiction / recharacterisation ("treated as possessing capital"); scoped status ("for the purposes of calculating ... capital under these Regulations"); parameter lookup (link to yield rule in reg 63); multi-entity crossing (applicant × authority × capital asset); defeater / exception precedence ((3) defeats (1)).

---

## Notes on fidelity and sourcing

All operative text above is quoted from Lex API responses cross-referenced against `legislation.gov.uk`. Section 1 (ITA 2007 s.55B) is the as-in-force version including devolved-rate amendments; a handful of cross-references (e.g. to s.55C, s.56, s.35) are referenced rather than quoted to keep each entry self-contained. Section 2 (CTA 2009 s.1169) is the live version; subsection numbering follows the 2025-04-01 consolidation. Section 3 (Children Act s.2) is the post-2008 HFEA-amended version. Section 4 (CTA 2009 s.1217J) is quoted as it stands — note the percentage is currently 80% but Treasury may vary it. Section 9 (PSPA 2013 s.10) is as enacted; "Part 1 of Schedule 4 to the Pensions Act 1995" is the parameter table being referenced. Section 10 (SSI 2021/249 reg 71) is the Scottish council-tax reduction rule; no English equivalent was selected (HB Regs 2006 reg 70 is English instead).
