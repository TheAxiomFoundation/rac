# Ten diverse UK legislation sections for DSL stress test (round 2)

Sampled via the Lex API (`https://lex.lab.i.ai.gov.uk`) and cross-checked against legislation.gov.uk. All are distinct from the round-1 sample, the prototype UC regs, and the pitch-deck conformance list. Spread covers IHT, CGT, corporation tax, VAT, employment rights, company law, state pension, Scottish devolved tax, student finance, and income tax.

---

## 1. Inheritance Tax Act 1984 s.8A — Transfer of unused nil-rate band between spouses and civil partners

URL: https://www.legislation.gov.uk/ukpga/1984/51/section/8A

Summary: On the survivor's death, the nil-rate band is uplifted by the percentage of the deceased spouse's nil-rate band that was unused on their earlier death; the uplift is capped at 100% of the band and must be claimed.

Operative text:

> (1) This section applies where— (a) immediately before the death of a person (a "deceased person"), the deceased person had a spouse or civil partner ("the survivor"), and (b) the deceased person had unused nil-rate band on death.
> (2) A person has unused nil-rate band on death if— M > VT where— M is the maximum amount that could be transferred by a chargeable transfer made (under section 4 above) on the person's death if it were to be wholly chargeable to tax at the rate of nil per cent. ... and VT is the value actually transferred by the chargeable transfer so made (or nil if no chargeable transfer is so made).
> (3) Where a claim is made under this section, the nil-rate band maximum at the time of the survivor's death is to be treated for the purposes of the charge to tax on the death of the survivor as increased by the percentage specified in subsection (4) ...
> (4) That percentage is— E / NRBMD × 100 where— E is the amount by which M is greater than VT in the case of the deceased person; and NRBMD is the nil-rate band maximum at the time of the deceased person's death.
> (5) If (apart from this subsection) the amount of the increase ... would exceed the amount of that nil-rate band maximum, the amount of the increase is limited to the amount of that nil-rate band maximum.
> (6) Subsection (5) above may apply either— (a) because the percentage mentioned in subsection (4) above ... is more than 100 because of the amount by which M is greater than VT in the case of one deceased person, or (b) because this section applies in relation to the survivor by reference to the death of more than one person who had unused nil-rate band on death.

Structured computation:

```
inputs:
  survivor S, deceased spouses D_1..D_k (with death dates d_i)
  M(D_i)        : Money  -- max chargeable at nil% at D_i's death
  VT(D_i)       : Money  -- value actually chargeably transferred
  NRBMD(d_i)    : Money  -- nil-rate band max at D_i's death
  NRB(d_S)      : Money  -- nil-rate band max at survivor's death
  claim(S, D_i) : Bool   -- executor claim under s.8A
output:
  nil_rate_band_at_survivor_death(S) : Money
rule:
  for each claimed D_i where M(D_i) > VT(D_i):
      E_i        = M(D_i) - VT(D_i)
      pct_i      = (E_i / NRBMD(d_i)) * 100
  total_pct     = Σ_i pct_i
  uplift        = min(total_pct, 100) * NRB(d_S) / 100
  nil_rate_band = NRB(d_S) + uplift
time granularity: point-in-time at each death event; NRBMD versioned by death date
edge cases: multiple deceased spouses; percentages summed but capped at 100%;
           residence nil-rate interaction via s.8D(2); reduction under s.8C
           (gifts-with-reservation / charged-at-reduced-rate scenarios).
```

Structures used: scalar arithmetic; conditional branching; aggregation over a relation (percentages across multiple deceased spouses); parameter lookup with effective-dated versioning (nil-rate band maximum per Sch 1); counterfactual ("maximum amount that could be transferred ... if it were to be wholly chargeable to tax at the rate of nil per cent."); legal fiction / recharacterisation ("treated as increased"); multi-entity crossing (survivor × each deceased spouse); defeater / exception precedence (cap at 100%); point-in-time facts (NRB at specific death dates).

---

## 2. Taxation of Chargeable Gains Act 1992 s.1K — Annual exempt amount

URL: https://www.legislation.gov.uk/ukpga/1992/12/section/1K

Summary: Each individual deducts up to £3,000 per tax year from chargeable gains; the deduction sits after same-year losses but before brought-forward losses, is forfeited if the remittance basis is claimed, and passes to personal representatives for the year of death and the two following years.

Operative text:

> (1) If an individual is (or, apart from this section, would be) chargeable to capital gains tax for a tax year on chargeable gains, the annual exempt amount for the year is to be deducted from those gains (but no further than necessary to eliminate them).
> (2) The annual exempt amount for a tax year is £3,000.
> (4) The deduction of the annual exempt amount— (a) is made after the deduction of allowable losses accruing in the tax year, but (b) is made before the deduction of allowable losses accruing in a previous tax year or, if section 62 applies, in a subsequent tax year.
> (5) The annual exempt amount may be deducted from gains in whatever way is most beneficial to a person chargeable to capital gains tax (irrespective of the rate of tax at which the gains would otherwise have been charged).
> (6) An individual is not entitled to an annual exempt amount for a tax year if (a) section 809B of ITA 2007 (claim for remittance basis) applies to the individual for the year, or (b) the individual makes a foreign gain claim, a foreign income claim or a foreign employment election for that tax year.
> (7) For the tax year in which an individual dies and for the next two tax years, this section applies to the individual's personal representatives as if references to the individual were to those personal representatives.

Structured computation:

```
inputs:
  individual I, tax_year Y
  chargeable_gains_gross(I, Y)   : list of (gain, rate) pairs
  losses_same_year(I, Y)         : Money
  losses_brought_forward(I, Y)   : Money
  s62_applies(I, Y)              : Bool   -- death-year loss carry-back
  remittance_basis_claim(I, Y)   : Bool
  foreign_election(I, Y)         : Bool
  death_year(I)                  : Year | None
  AEA(Y)                         : Money  -- £3,000
output:
  annual_exempt_deduction(I, Y) : Money
  allocation(I, Y)              : Map[gain -> amount_deducted]
rule:
  eligible := NOT remittance_basis_claim AND NOT foreign_election
  if alive(I, Y):                        person := I
  elif Y in {death_year..death_year+2}:  person := PR(I)
  else:                                   person := None
  if person and eligible:
      net_gains_after_same_year_losses = max(0, Σ gains - losses_same_year)
      deduction = min(AEA(Y), net_gains_after_same_year_losses)
      # "most beneficial" = taxpayer minimises tax across rate bands
      allocation = argmin over allocations summing to deduction of
                    Σ (gain_r - alloc_r) * rate_r
  else:
      deduction = 0
  taxable_after_AEA = net_gains_after_same_year_losses - deduction
  taxable_after_BF  = max(0, taxable_after_AEA - losses_brought_forward)
time granularity: tax year; entity substitutes at death
edge cases: death year + next two years → PRs substitute for individual;
            s.62 carry-back of losses from later year into year of death;
            "most beneficial" allocation is taxpayer's own optimisation.
```

Structures used: scalar arithmetic; conditional branching; anti-join / absence (not entitled if remittance-basis or foreign-election); parameter lookup with effective-dated versioning (AEA changes annually); legal fiction / recharacterisation (PRs stand in for individual for three tax years); aggregation over a relation (sum of gains, ordered loss application); counterfactual ("gains would otherwise have been charged"); scoped status ("for the tax year in which an individual dies"); multi-entity crossing (individual → PR); date arithmetic (death year + 2).

---

## 3. Corporation Tax Act 2010 s.18B — Marginal relief for companies without ring fence profits

URL: https://www.legislation.gov.uk/ukpga/2010/4/section/18B

Summary: A UK-resident, non-close-investment-holding company with augmented profits between the lower and upper limits receives a corporation-tax reduction equal to the standard marginal relief fraction times (upper limit − augmented profits) times (taxable total profits / augmented profits).

Operative text:

> (1) This section applies if— (a) a company is UK resident in an accounting period, (b) it is not a close investment-holding company in the period, (c) its augmented profits of the accounting period exceed the lower limit but do not exceed the upper limit, and (d) its augmented profits of the accounting period do not include any ring fence profits.
> (2) The corporation tax charged on the company's taxable total profits of the accounting period is reduced by an amount equal to— F × (U − A) × (N / A) where— F is the standard marginal relief fraction, U is the upper limit, A is the amount of the augmented profits, and N is the amount of the taxable total profits.
> (3) In this Act "the standard marginal relief fraction" means the fraction set by Parliament for the financial year as the standard marginal relief fraction for the purposes of this Part.

Structured computation:

```
inputs:
  company C, accounting_period AP
  uk_resident(C, AP)              : Bool
  close_investment_holding(C, AP) : Bool
  augmented_profits(C, AP)        : Money  -- A
  taxable_total_profits(C, AP)    : Money  -- N
  ring_fence_profits(C, AP)       : Money
  associated_companies(C, AP)     : Set[Company]
  U(financial_year)               : Money  -- e.g. £250,000
  L(financial_year)               : Money  -- e.g. £50,000
  F(financial_year)               : Fraction  -- 3/200 since FY2023
output:
  marginal_relief(C, AP) : Money
rule:
  num_associates = |associated_companies(C, AP)|
  U_eff = U(FY) / (1 + num_associates) * (days(AP) / 365)
  L_eff = L(FY) / (1 + num_associates) * (days(AP) / 365)
  eligible = uk_resident AND NOT close_investment_holding
             AND L_eff < A <= U_eff
             AND ring_fence_profits(C, AP) == 0
  if eligible:
      marginal_relief = F(FY) * (U_eff - A) * (N / A)
  else:
      marginal_relief = 0
time granularity: accounting period; may straddle financial years
edge cases: AP straddles two FYs with different F, U, L → apportion;
            associated-company count changes during the AP;
            A = 0 cannot be reached (eligibility requires A > L_eff > 0).
```

Structures used: scalar arithmetic; conditional branching; positive relational membership (associated companies); anti-join / absence (NOT close-investment-holding; NOT ring-fence); aggregation over a relation (count of associates); parameter lookup with effective-dated versioning (F, U, L set per financial year); partial-period / interval intersection (AP × financial-year boundary; limits pro-rated by days); multi-entity crossing (company × each associate).

---

## 4. Value Added Tax Act 1994 Schedule 1 para 1 — Liability to be registered (UK-established)

URL: https://www.legislation.gov.uk/ukpga/1994/23/schedule/1

Summary: A UK-established person becomes liable to VAT registration when rolling-12-month taxable turnover exceeds £90,000, or when imminent 30-day turnover will exceed £90,000; a release valve at £88,000 forward-turnover disapplies the historic-test limb.

Operative text:

> 1(1) Subject to sub-paragraphs (3) to (7) below, a person who makes taxable supplies but is not registered under this Act becomes liable to be registered under this Schedule— (a) at the end of any month, if the person is UK-established and the value of his taxable supplies in the period of one year then ending has exceeded £90,000; or (b) at any time, if the person is UK-established and there are reasonable grounds for believing that the value of his taxable supplies in the period of 30 days then beginning will exceed £90,000.
> 1(2) Where a business, or part of a business, carried on by a taxable person is transferred to another person as a going concern, the transferee is UK-established at the time of the transfer and the transferee is not registered under this Act at that time, then ... the transferee becomes liable to be registered under this Schedule at that time if— (a) the value of his taxable supplies in the period of one year ending at the time of the transfer has exceeded £90,000; or (b) there are reasonable grounds for believing that the value of his taxable supplies in the period of 30 days beginning at the time of the transfer will exceed £90,000.
> 1(3) A person does not become liable to be registered by virtue of sub-paragraph (1)(a) or (2)(a) above if the Commissioners are satisfied that the value of his taxable supplies in the period of one year beginning at the time at which, apart from this sub-paragraph, he would become liable to be registered will not exceed £88,000.
> 1(4) In determining the value of a person's supplies ..., supplies made at a time when he was previously registered under this Act shall be disregarded if— (a) his registration was cancelled otherwise than under paragraph 13(3) ..., and (b) the Commissioners are satisfied that before his registration was cancelled he had given them all the information they needed ...

Structured computation:

```
inputs:
  person P, date d
  uk_established(P, d)             : Bool
  taxable_supplies(P, t)           : stream of (date, value)
  going_concern_transfer(to=P, from=Q, at=t_0)
  prior_registration_history(P)    : list of (period, cancellation_reason)
  threshold(d)                     : Money   -- £90,000
  deregistration_threshold(d)      : Money   -- £88,000
output:
  liable_to_register(P, d)         : Bool
  effective_liability_date         : Date
rule:
  -- historic test
  for each month-end m ≤ d:
      rolling_12m = Σ value of taxable_supplies(P, t) for t ∈ (m-1y, m]
                    EXCLUDING supplies during prior registration periods
                    whose cancellation was non-penal (sub-para 4)
      if uk_established(P, m) AND rolling_12m > threshold(m):
          if Commissioners satisfied that
             Σ supplies in (m, m+1y] ≤ deregistration_threshold(m):
              continue
          else:
              liable := True; effective_date := m; return
  -- forward test
  for any t ≤ d:
      if uk_established(P, t) AND
         forecast(Σ supplies in [t, t+30d]) > threshold(t):
          liable := True; effective_date := t; return
  -- TOGC transfer at t_0 re-runs both tests anchored at t_0
time granularity: continuous; tested at every month-end + real time
edge cases: straddling UK-establishment status change; TOGC transferee
            inherits turnover history; prior-cancellation exclusion
            only applies for benign cancellation reasons.
```

Structures used: scalar arithmetic; conditional branching; aggregation over a relation (rolling-12-month sum; 30-day forward sum); positive relational membership (UK-established status); anti-join / absence (exclude supplies from prior-registration periods; historic test blocked by 1(3)); counterfactual ("reasonable grounds for believing ... will exceed"; "will not exceed £88,000"); parameter lookup with effective-dated versioning (threshold changes over time); partial-period / interval intersection (rolling windows); date arithmetic / interval output (effective liability date); multi-entity crossing (transferor/transferee under TOGC); defeater / exception precedence (1(3) defeats the historic-test trigger).

---

## 5. Employment Rights Act 1996 s.162 — Amount of a redundancy payment

URL: https://www.legislation.gov.uk/ukpga/1996/18/section/162

Summary: Statutory redundancy pay is a weighted sum over the last 20 years of continuous service, with 1.5 / 1.0 / 0.5 weeks' pay per year depending whether the employee was 41+, 22+, or younger in that year of service.

Operative text:

> (1) The amount of a redundancy payment shall be calculated by— (a) determining the period, ending with the relevant date, during which the employee has been continuously employed, (b) reckoning backwards from the end of that period the number of years of employment falling within that period, and (c) allowing the appropriate amount for each of those years of employment.
> (2) In subsection (1)(c) "the appropriate amount" means— (a) one and a half weeks' pay for a year of employment in which the employee was not below the age of forty-one, (b) one week's pay for a year of employment (not within paragraph (a)) in which he was not below the age of twenty-two, and (c) half a week's pay for each year of employment not within paragraph (a) or (b).
> (3) Where twenty years of employment have been reckoned under subsection (1), no account shall be taken under that subsection of any year of employment earlier than those twenty years.
> (6) Subsections (1) to (3) apply for the purposes of any provision of this Part by virtue of which an employment tribunal may determine that an employer is liable to pay to an employee— (a) the whole of the redundancy payment to which the employee would have had a right apart from some other provision, or (b) such part of the redundancy payment to which the employee would have had a right apart from some other provision as the tribunal thinks fit ...

Structured computation:

```
inputs:
  employee E, employer ER, relevant_date R
  date_of_birth(E)                 : Date
  continuous_employment_start(E, ER): Date
  weekly_pay(E, R)                 : Money  -- capped by s.227
output:
  redundancy_payment(E, ER, R) : Money
rule:
  look_back_start = max(continuous_employment_start, R - 20 years)
  payment = 0
  for i = 1..20 reckoned backwards from R:
      year_i = [R - i years, R - (i-1) years]
      if year_i intersects [continuous_employment_start, R]:
          age_at_year_i = age(E, start_of_year_i)
          if   age_at_year_i >= 41: weight = 1.5
          elif age_at_year_i >= 22: weight = 1.0
          else:                      weight = 0.5
          payment += weight * weekly_pay
  return payment
time granularity: years reckoned backwards from relevant date;
                  age evaluated at each year boundary
edge cases: < 2 years continuous service → eligibility gate in s.155 / 108;
            s.227 caps weekly pay; s.162(6) applies when a tribunal has
            reduced/denied payment under another provision of this Part.
```

Structures used: scalar arithmetic; conditional branching (three age bands); aggregation over a relation (sum over years of service); partial-period / interval intersection (20-year look-back intersects actual service); date arithmetic (age at each year boundary reckoned backwards); parameter lookup with effective-dated versioning (s.227 weekly-pay cap, updated annually); counterfactual ("to which the employee would have had a right apart from some other provision"); multi-entity crossing (employee × employer × each year); point-in-time versus over-period facts (age at a year boundary vs employment over the interval).

---

## 6. Companies Act 2006 s.172 — Duty to promote the success of the company

URL: https://www.legislation.gov.uk/ukpga/2006/46/section/172

Summary: A director must act in good faith to promote the company's success for the benefit of members as a whole, having regard to six listed matters; the target of the duty is rewritten where the company's purposes are non-member-benefit, and is displaced by creditor-interest rules on insolvency.

Operative text:

> (1) A director of a company must act in the way he considers, in good faith, would be most likely to promote the success of the company for the benefit of its members as a whole, and in doing so have regard (amongst other matters) to— (a) the likely consequences of any decision in the long term, (b) the interests of the company's employees, (c) the need to foster the company's business relationships with suppliers, customers and others, (d) the impact of the company's operations on the community and the environment, (e) the desirability of the company maintaining a reputation for high standards of business conduct, and (f) the need to act fairly as between members of the company.
> (2) Where or to the extent that the purposes of the company consist of or include purposes other than the benefit of its members, subsection (1) has effect as if the reference to promoting the success of the company for the benefit of its members were to achieving those purposes.
> (3) The duty imposed by this section has effect subject to any enactment or rule of law requiring directors, in certain circumstances, to consider or act in the interests of creditors of the company.

Structured computation:

```
inputs:
  director D, company C, decision K at time t
  subjective_belief(D, K, t)        : 'good_faith' | 'not_good_faith'
  purposes(C, t)                    : Set ⊆ {benefit_of_members, other_purposes}
  considered(D, K, factor)          : Bool for each factor in {a..f}
  insolvency_like_state(C, t)       : Bool
output:
  duty_satisfied(D, C, K, t) : Bool
rule:
  objective_goal := if insolvency_like_state(C, t):
                       protect_creditor_interests(C)
                    elif 'other_purposes' ∈ purposes(C, t):
                       achieve(purposes(C, t))
                    else:
                       promote_success_for_members(C)
  duty_satisfied := subjective_belief(D, K, t) == 'good_faith'
                    AND D considered the action most likely to achieve objective_goal
                    AND D had regard to every factor (a)-(f)
                    -- "have regard to" is weaker than "act in accordance with";
                    --  failing to consider a listed factor at all is a breach
time granularity: point-in-time per decision K
output dtype: Bool (with a non-computational "good faith" / reasonableness
              overlay that courts supply)
edge cases: creditor-priority overrides members-benefit near insolvency;
            mixed-purposes clauses under (2); the factor list is
            non-exhaustive ("amongst other matters").
```

Structures used: conditional branching; positive relational membership (factor consideration; purposes set); anti-join / absence (breach if any factor not considered); scoped status ("for the benefit of its members as a whole"; recharacterised under (2)); defeater / exception precedence ((3) subordinates the duty to creditor-interest rules); legal fiction / recharacterisation ((2) rewrites the target of the duty); counterfactual ("would be most likely to promote"); point-in-time facts (per decision); text / identity output (Bool breach with factor-consideration audit trail).

---

## 7. Pensions Act 2014 s.4 — Entitlement to state pension at transitional rate

URL: https://www.legislation.gov.uk/ukpga/2014/19/section/4

Summary: A person reaching pensionable age on/after 6 April 2016 is entitled to a transitional-rate state pension if they have at least the minimum number of qualifying years (set by regulations, at most 10) and at least one pre-commencement qualifying year; pre-1978 reckonable years count towards the minimum even though they are not themselves qualifying years.

Operative text:

> (1) A person is entitled to a state pension payable at the transitional rate if— (a) the person has reached pensionable age, (b) the person has at least the minimum number of qualifying years, and (c) the person has at least one pre-commencement qualifying year.
> (2) The minimum number of qualifying years for a state pension payable at the transitional rate is to be specified in regulations and may not be more than 10.
> (3) A person entitled to a state pension payable at the transitional rate is not entitled to a state pension under section 2.
> (4) In this Part— "post-commencement qualifying year" means a qualifying year beginning on or after 6 April 2016; "pre-commencement qualifying year" means— a qualifying year beginning on or after 6 April 1978 and ending before 6 April 2016, or a reckonable year that would have been treated under regulation 13(1) of the Social Security (Widow's Benefit, Retirement Pensions and Other Benefits) (Transitional) Regulations 1979 (S.I. 1979/643) as a qualifying year for the purposes of determining the person's entitlement to an old state pension that is a Category A retirement pension.
> (5) A reckonable year mentioned in paragraph (b) of the definition of "pre-commencement qualifying year" counts towards the minimum number of qualifying years required by subsection (1)(b) (even though it does not come within the definition of "qualifying year" for the purposes of this Part).

Structured computation:

```
inputs:
  person P, assessment_date d
  date_of_birth(P)              : Date
  pensionable_age(P, d)         : Int     -- PA 1995 Sch 4
  is_qualifying_year(P, Y)      : Bool    -- ss.22-23 SSCBA 1992
  is_reckonable_1979_reg13(P,Y) : Bool    -- deemed for old CatA purposes
  minimum_qy(d)                 : Int     -- ≤10 per regulation
output:
  entitled_transitional_rate(P, d) : Bool
  entitled_s2_full_rate(P, d)      : Bool  -- defeated if above True
rule:
  pre_comm_qy  = { Y : is_qualifying_year(P,Y)
                       AND 1978-04-06 ≤ start(Y) < 2016-04-06 }
                 ∪ { Y : is_reckonable_1979_reg13(P,Y) }
  post_comm_qy = { Y : is_qualifying_year(P,Y) AND start(Y) ≥ 2016-04-06 }
  threshold_count = |pre_comm_qy| + |post_comm_qy|
  entitled_transitional_rate :=
      age(P, d) ≥ pensionable_age(P, d)
      AND threshold_count ≥ minimum_qy(d)
      AND |pre_comm_qy| ≥ 1
  if entitled_transitional_rate:
      entitled_s2_full_rate := False
time granularity: person × assessment date; qualifying years are discrete
edge cases: reckonable 1979-reg-13 years count towards the minimum even
            though not qualifying years proper (scoped fiction); exactly
            one pre-commencement year suffices; minimum ≤ 10.
```

Structures used: scalar arithmetic; conditional branching; positive relational membership (year ∈ two sets); aggregation over a relation (count of qualifying years); parameter lookup with effective-dated versioning (minimum-QY regulations; pensionable-age schedule); scoped status ("for the purposes of this Part"); legal fiction / recharacterisation (s.5 "counts towards" "even though it does not come within the definition"); anti-join / absence (s.2 barred if s.4 applies); partial-period / interval intersection (years × the 1978/2016 window); date arithmetic (qualifying-year intervals); point-in-time vs over-period (age at d vs years accrued by d).

---

## 8. Land and Buildings Transaction Tax (Scotland) Act 2013 s.25 — Amount of tax chargeable

URL: https://www.legislation.gov.uk/asp/2013/11/section/25

Summary: For a Scottish LBTT chargeable transaction, tax is computed by slicing the chargeable consideration across the rates and bands set under s.24 and summing the per-slice products; the rule is subject to reliefs and additional-dwelling supplements.

Operative text:

> (1) The amount of tax chargeable in respect of a chargeable transaction is to be determined as follows.
>   Step 1: For each tax band applicable to the type of transaction, multiply so much of the chargeable consideration for the transaction as falls within the band by the tax rate for that band.
>   Step 2: Calculate the sum of the amounts reached under Step 1. The result is the amount of tax chargeable.
> (2) In the case of a transaction for which the whole or part of the chargeable consideration is rent this section has effect subject to schedule 19 (leases).
> (3) This section is subject to— (za) schedule 2A (additional amount: transactions relating to second homes etc.), (zb) schedule 4A (first-time buyer relief), (a) schedule 5 (multiple dwellings relief), (b) schedule 9 (crofting community right to buy relief), (ba) schedule 10A (sub-sale development relief), (c) Part 3 of schedule 11 (acquisition relief).

Structured computation:

```
inputs:
  transaction T
  transaction_type(T)           : 'residential' | 'non_residential'
  chargeable_consideration(T)   : Money
  includes_rent(T)              : Bool
  is_additional_dwelling(T)     : Bool
  first_time_buyer(T)           : Bool
  linked_transactions(T)        : Set[Transaction]   -- s.26 applies instead
  bands(type, effective_date(T)): ordered list of (lower, upper, rate)
output:
  tax_chargeable(T) : Money
rule:
  C = chargeable_consideration(T)
  tax = 0
  for (l, u, r) in bands(transaction_type(T), effective_date(T)):
      slice = max(0, min(C, u) - l)
      tax += slice * r
  if is_additional_dwelling(T):   tax += additional_amount(T)    -- Sch 2A
  if first_time_buyer(T):          tax  = apply_FTB_relief(tax, T) -- Sch 4A
  if multiple_dwellings(T):        tax  = apply_MDR(tax, T)        -- Sch 5
  if includes_rent(T):             tax  = apply_schedule_19(tax, T)
  if linked_transactions(T):       divert to s.26 apportionment
time granularity: point-in-time (effective date of transaction)
edge cases: linked-transactions formula (s.26) reapportions tax;
            lease NPV rules (Sch 19) replace banding for rent component;
            additional-dwelling supplement is additive, not band-reshaping.
```

Structures used: scalar arithmetic; conditional branching (residential / non-residential; relief eligibility); aggregation over a relation (sum of per-band slices); parameter lookup with effective-dated versioning (bands set by Scottish Ministers by order under s.24); partial-period / interval intersection (consideration sliced across band intervals); defeater / exception precedence ((3) subjects the section to six schedules); multi-entity crossing (linked transactions — transaction × each linked partner); scoped status ("for the type of transaction").

---

## 9. Education (Student Loans) (Repayment) Regulations 2009 (SI 2009/470) reg 44 — Amount of repayments

URL: https://www.legislation.gov.uk/uksi/2009/470/regulation/44

Summary: Employer PAYE deductions for student loans are 9% (plan 1/2/4/5) or 6% (plan 3 / postgraduate) of earnings above the plan-specific threshold, with thresholds pro-rated to the earnings period and defaulted to the lowest plan threshold when a borrower fails to comply with reg 43.

Operative text:

> (1) The repayment deducted must be— (a) in relation to a plan 1, 2, 4, or 5 loan, 9%, and (b) in relation to a plan 3 loan, 6%, of any earnings paid to, or provided to or for the benefit of, the borrower in respect of the employment, which exceed the threshold specified in paragraph (2).
> (2) The threshold is— (a) the repayment threshold or default threshold, where the earnings period specified in respect of those earnings is a tax year; or (b) in any other case, the amount which bears the same relation to the repayment threshold or default threshold as the number of days, weeks or months of the earnings period specified in respect of those earnings bears to the number of days, weeks or months in the tax year respectively.
> (2A) The repayment calculated under paragraph (1)(b) is additional to, and concurrent with, any repayment under paragraph (1)(a).
> (3) Where a repayment calculated under paragraph (1) includes pence as well as pounds the pence are to be ignored.
> (6) The default threshold applies— (a) if, in relation to a plan 1, 2, 4 or 5 loan, the borrower fails to comply with regulation 43 ..., and (b) until the date specified by HMRC in a notice given to the borrower's employer under regulation 49(1).
> (7) The default threshold is whichever repayment threshold for a plan 1, 2, 4 or 5 loan is the lowest repayment threshold.

Structured computation:

```
inputs:
  borrower B, employer E, earnings_period EP
  earnings(B, E, EP)                 : Money
  plans_active(B, at=start(EP))      : Set ⊆ {1, 2, 3, 4, 5}
  reg43_compliant(B, plan, at=EP)    : Bool
  hmrc_notice_date(B, plan)          : Date | None
  repayment_threshold(plan, tax_year): Money   -- Sch 1A
  earnings_period_type(EP)           : 'year' | 'month' | 'week' | 'day'
  earnings_period_length(EP)         : Int
output:
  repayment_deducted(B, E, EP) : Money   -- whole pounds
rule:
  total = 0
  for P in plans_active(B):
      default_active = P ∈ {1,2,4,5}
                       AND NOT reg43_compliant(B, P, EP)
                       AND (hmrc_notice_date(B, P) is None
                            OR end(EP) < hmrc_notice_date(B, P))
      source = min over p' in {1,2,4,5} of repayment_threshold(p', ty(EP))
               if default_active
               else repayment_threshold(P, ty(EP))
      if earnings_period_type(EP) == 'year':
          T_P = source
      else:
          T_P = source * earnings_period_length(EP)
                       / tax_year_length_of(earnings_period_type(EP))
      rate_P = 0.09 if P ∈ {1,2,4,5} else 0.06
      total += floor_to_pounds(max(0, earnings - T_P) * rate_P)
  return total
time granularity: per earnings period (day / week / month / year)
edge cases: borrower with both plan-1/2/4/5 and plan-3 loans → both rates
            applied concurrently to same earnings with each plan's threshold;
            default flips to the lowest threshold until HMRC notice date;
            pence ignored each period.
```

Structures used: scalar arithmetic; conditional branching (plan type; default vs normal threshold); aggregation over a relation (sum of concurrent plan contributions); parameter lookup with effective-dated versioning (Sch 1A updated annually); anti-join / absence (non-compliance with reg 43 flips the threshold source); partial-period / interval intersection (pro-rating earnings-period length vs tax-year length); date arithmetic (HMRC notice date bounds the default window); defeater / exception precedence (default threshold displaces normal threshold conditionally); multi-entity crossing (borrower × employer × each plan); point-in-time vs over-period (plans active at period start vs earnings accrued over the period).

---

## 10. Income Tax Act 2007 s.35 — Personal allowance

URL: https://www.legislation.gov.uk/ukpga/2007/3/section/35

Summary: An individual meeting the s.56 residence test gets a personal allowance (currently £12,570), tapered by £1 for every £2 of adjusted net income above £100,000, reaching zero at £125,140; adjusted net income is defined by a four-step addback.

Operative text:

> (1) An individual who meets the requirements of section 56 (residence etc) is entitled to a personal allowance of £12,570 for a tax year if the individual's adjusted net income for the year does not exceed £100,000.
> (2) If the individual's adjusted net income for the year exceeds £100,000, the allowance under subsection (1) is reduced by one-half of the excess.
> (3) If the amount of any allowance that remains after the operation of subsection (2) would otherwise not be a multiple of £1, it is to be rounded up to the nearest amount which is a multiple of £1.
> (4) For the purposes of this section, an individual's adjusted net income for a tax year is calculated as follows. Step 1: Take the amount of the individual's net income for the tax year. Step 2: If in that tax year the individual makes, or is treated as making, a gift to charity ... deduct the grossed-up amount of the gift. Step 3: If in that tax year the individual makes a contribution to a pension scheme ..., deduct the gross amount of the contribution. Step 4: Add back any deduction allowed under section 457 or 458 of ITTOIA 2005 (payments to trade unions or police organisations) in calculating the individual's net income. The result is the individual's adjusted net income for the tax year.

Structured computation:

```
inputs:
  individual I, tax_year Y
  residence_ok(I, Y)                          : Bool   -- s.56
  net_income(I, Y)                            : Money
  gift_aid_grossed_up(I, Y)                   : Money
  relief_at_source_pension_contributions(I,Y) : Money
  trade_union_police_deductions(I, Y)         : Money  -- s.457/458 ITTOIA
  base_allowance(Y)                           : Money  -- £12,570
  taper_start(Y)                              : Money  -- £100,000
output:
  personal_allowance(I, Y) : Money
rule:
  if NOT residence_ok(I, Y):
      return 0
  ANI = net_income(I, Y)
        - gift_aid_grossed_up(I, Y)
        - relief_at_source_pension_contributions(I, Y)
        + trade_union_police_deductions(I, Y)
  if ANI <= taper_start(Y):
      PA = base_allowance(Y)
  else:
      PA = max(0, base_allowance(Y) - (ANI - taper_start(Y)) / 2)
  return round_up_to_multiple(PA, 1)
time granularity: tax year
edge cases: ANI between £100,000 and £125,140 → tapered; ANI > £125,140 → 0;
            non-resident → 0; rounding up to whole £1; gift-aid grossing
            depends on basic-rate band in force.
```

Structures used: scalar arithmetic; conditional branching (residence gate; below vs above taper start; zero floor); parameter lookup with effective-dated versioning (allowance and taper threshold set annually); positive relational membership (residence status); aggregation over a relation (sum of pension contributions; gifts; union deductions); defeater / exception precedence (non-residence defeats entitlement; taper reduces it); scoped status ("for the purposes of this section" — ANI); counterfactual (ANI back-adds s.457/458 deductions as though never taken); point-in-time vs over-period (residence determined per year vs income accrued over the year).

---

## Notes on fidelity and sourcing

All operative text is quoted from Lex API responses as at April 2026 and cross-checked against `legislation.gov.uk`. Numerical parameters stated at current-force values: VAT threshold £90,000 (raised April 2024); IHT nil-rate-band maximum £325,000 per Sch 1 IHTA 1984; CGT AEA £3,000 for 2024-25 onwards; CT marginal relief fraction 3/200 from FY2023; LBTT bands set by SSI under s.24 of the 2013 Act; student-loan thresholds for 2024-25 are in Sch 1A SI 2009/470; ITA s.35 personal allowance £12,570 is the current statutory figure. Round-2 deliberately picks ITA s.35 rather than a DWP benefit for its tenth slot because the DSL exclusion list already absorbed most child-benefit, UC, HB, CTR and SPP/SAP hand-holds; s.35 sits upstream of round-1's marriage-allowance rule (s.55B) and supplies the personal-allowance parameter that rule depends on.
