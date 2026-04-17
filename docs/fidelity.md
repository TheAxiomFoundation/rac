# Fidelity audit

What each prototype programme does versus what the cited statute actually says. Written honestly so users can rely on the prototype knowing where it is faithful, where it has pre-computed legal facts into inputs, and where it is silent about statutory content.

Read this alongside [`docs/time-period-semantics.md`](time-period-semantics.md), which covers how the period and interval model handles time-varying facts.

## The format

For each programme we list:
- **Encoded in the DSL** — legal concepts the programme computes itself.
- **Pushed to the caller as inputs** — legal facts the caller must determine outside the DSL (typically the hardest parts: eligibility gates, qualifying-date tests, pre-applied limits).
- **Omitted** — statutory content the programme does not represent at all.
- **Known deviations** — specific cases where the programme's output can disagree with the legally correct answer.

## universal_credit_program.yaml

Cited: Universal Credit Regulations 2013 (SI 2013/376) regs 18, 22, 24, 24(2), 24B, 25, 27, 28, 29, 36, 72, plus Schedule 4.

**Encoded in the DSL.** Standard allowance by single/couple × under-25/25+ (reg 36 table). Child element with the two-rate split in reg 24(2): higher rate for a qualifying first child born before 6 April 2017, standard rate for every other qualifying child. Disabled-child addition at both lower and higher rates (reg 24(2)) aggregated by count over flagged children. LCWRA and carer elements each paid once per benefit unit (regs 27, 29). Max UC as the sum of elements (reg 22(1)). Housing element as eligible rent minus non-dep deductions, floored at zero. Work-allowance eligibility from reg 22(2) (has qualifying child or has LCWRA). Work-allowance amount chosen by the with/without-housing rule (Sch 4). Earned-income taper at 55%. Capital tariff income at £4.35 per complete £250 above £6,000 (reg 72, using `floor`). Capital disentitlement above £16,000 (reg 18).

**Pushed to the caller as inputs.** Whether each adult is 25 or over (the *at-some-point-in-the-AP* detail). Whether each adult has LCWRA (the Work Capability Assessment outcome, which is its own regulated determination — Parts 5 and 6 of the UC Regs). Whether each adult is a carer under reg 29 (the 35-hour substantial-care test and carer's-allowance alignment). For each child: whether they qualify for the child element after applying the two-child limit and its exceptions (reg 24B plus SI 2017/376 Sch — adoption, kinship care, multiple births, non-consensual conception); whether they are the higher-rate first child (meaning: born before 6 April 2017 *and* the eldest qualifying child *and* the family qualified for transitional protection); disability level ("lower" / "higher" / "none") computed against the DLA / PIP / ADP tests. Eligible housing costs (LHA / local reference rent caps, service-charge eligibility, bedroom entitlement — Sch 1–5). Non-dep deduction total (the band table in reg 28 applied per non-dep). Net earned income (reg 54 deductions — tax, NIC, 100% of allowed pension contributions). Unearned income calculation (regs 66–80).

**Omitted.** The childcare costs element (reg 31 — 85% of eligible costs up to a cap, with eligibility tests against work conditions). The benefit cap (Welfare Reform Act 2012 Part 4, applied as a reduction to housing element under reg 82 UCR). Transitional protection and managed-migration run-on (SI 2022/752). Sanctions and hardship payments (regs 99–110). The alternative max UC for mixed-age couples becoming entitled to Pension Credit. The SDP transitional element for legacy-benefit movers (SI 2019/1152). Deductions from the award (third-party, tax-credit recovery, advance repayment — Sch 6). Surplus earnings carry-forward (reg 54A). Recovery of overpayments.

**Known deviations.** The April uprating AP: UC rates change on the first Monday of April each year. A claimant whose AP starts before that date and ends after it will, under reg 38, have the new rates apply from the effective date. This programme uses the rate effective at the AP's start date for the whole AP, so one AP per year per claim will understate the award by a few pounds. The first and last AP of any claim can legally be shorter than a whole month; the programme treats every AP as a one-month abstraction. Any rule that operates on the end-of-AP rather than the AP as a whole (e.g. capital figure, change-of-circumstance crossing a boundary) relies on the caller supplying the right figure — the programme has no "as of" vs "across the period" distinction.

## child_benefit_responsibility_program.yaml

Cited: Income Support (General) Regulations 1987 (SI 1987/1967) reg 15.

**Encoded in the DSL.** The positive test at reg 15(1) via `count_related(cb_receipt) > 0`. The anti-join fallback at reg 15(2) via `count_related(cb_receipt) == 0`. The sole-claim fallback within reg 15(2) (claimant wins when exactly one CB claim has been made). The usual-residence fallback otherwise. The final responsible-person id as an if-cascade over those three cases.

**Pushed to the caller as inputs.** The count of historical CB claims (`cb_claim_count`). The id of the sole claimant when there has been exactly one CB claim (`sole_claimant_id`). The id of the person the child usually lives with (`usual_resident_id`). The id of the person currently receiving CB (`cb_recipient_id`), where applicable.

**Omitted.** Reg 15(1A) transitive rule: if child A is themselves receiving CB for child B, whoever is responsible for A is responsible for B. Reg 15(3) partial-week override via reg 16(6) (child in local-authority care or custody — responsibility attaches only for the part of the benefit week when the child lives with the claimant). The reg 14(3) family-extension sweep for s.145A CBA periods. Reg 15(4) uniqueness enforcement at the benefit-unit level (the programme picks a responsible person but does not reject datasets where multiple persons would claim responsibility — the caller is trusted to have resolved ambiguity).

**Known deviations.** In scenarios where more than one person receives CB for the same child in the same week (rare but legally possible before a Commissioners' decision), the programme reports the first such person as responsible; the regulation actually requires tribunal resolution. Where reg 16(6) carves out a partial week, the programme attributes responsibility for the whole week.

## notional_capital_program.yaml

Cited: Council Tax Reduction (Scotland) Regulations 2021 (SSI 2021/249) reg 71.

**Encoded in the DSL.** The deprivation-rule sum of disposed amounts filtered by purpose (`secure_ctr`) and reason (neither `debt` nor `reasonable_purchase`), via `sum_related` with a `where` predicate. Count of disposals whose purpose is to secure CTR. The capital-for-CTR total as actual capital + notional.

**Pushed to the caller as inputs.** The `disposal_purpose` text per disposal (whether, in the authority's opinion, the disposal was made to secure or increase CTR — reg 71(1)). The `disposal_reason` text per disposal ("debt" / "reasonable_purchase" / other — reg 71(3)). Actual capital (requires its own reg 62 valuation).

**Omitted.** Reg 71(2) carry-over of notional capital already deemed under reg 50 of the UC Regs 2013. Reg 71(4) deeming of *unclaimed* capital that the applicant could have acquired had they applied for it — this is counterfactual and the DSL does not support it. The diminishing-capital rule in reg 72 (notional capital reduces over time as it would have been spent on CTR).

**Known deviations.** An applicant whose notional capital should diminish over successive weeks will, in this programme, be treated as holding the full notional amount indefinitely. An applicant who failed to claim available capital is treated as not holding it, contrary to reg 71(4).

## uk_income_tax_program.yaml

Cited: rUK income tax rules as at 2025-26 — covers ITA 2007 s.35 (personal allowance and taper) and the basic/higher/additional rate structure. Source attribution on the YAML derived outputs is less granular here than in the UC programme — this predates the citation rollout and is worth revisiting.

**Encoded in the DSL.** Gross income as the sum of five components. Personal allowance with the £100,000 taper to zero at £125,140 (s.35(1)–(2)), rounded up to a multiple of £1 (s.35(3)). Taxable income. Basic-rate band (first £37,700 of taxable income). Higher-rate band up to £125,140 taxable. Additional-rate above. Income tax as the sum of band amounts times their rates.

**Pushed to the caller as inputs.** Each of the five income components pre-aggregated: employment income, self-employment income, pension income, property income, savings income. Residence (implicitly true — residence gate of s.56 is not checked).

**Omitted.** s.35(4) adjusted-net-income definition: the prototype treats gross income *as* adjusted net income, which is only correct when there are no gift-aid contributions, no relief-at-source pension contributions, and no s.457/458 trade-union deductions. Savings income is treated as ordinary income: the starting-rate-for-savings band (s.12) and personal savings allowance (s.12A) are not modelled. Dividend income is treated as ordinary income: the dividend allowance (s.13A) and dividend rates (s.8(2)) are not modelled. Marriage allowance transfer (s.55A–E) is not modelled. Blind person's allowance (s.38) is not modelled. Scottish rates and bands are not modelled: this programme is rUK only. Capital gains are separate (TCGA) and not covered. Overlap profit / basis-period rules for self-employment. PAYE credit and foreign-tax credit.

**Known deviations.** For taxpayers with non-trivial dividend or savings income the programme will overstate tax (because it rates such income at ordinary bands rather than the more generous dividend/savings bands). For Scottish taxpayers the programme produces the rUK figure, which is wrong for Scotland. For taxpayers with gift-aid or RAS pension contributions the personal allowance taper starts at the wrong threshold (it should start at the true adjusted-net-income threshold, not gross).

## state_pension_transitional_program.yaml

Cited: Pensions Act 2014 s.4.

**Encoded in the DSL.** Pre-commencement qualifying year count (s.4(4)) via `count_related` with a where-clause on the year-start date and the reckonable-1979 flag. Post-commencement qualifying year count. Total qualifying years. Pensionable-age gate (s.4(1)(a)). Minimum-qualifying-years gate (s.4(1)(b), parameterised at 10 per regulations). Has-at-least-one-pre-commencement-year gate (s.4(1)(c)). Combined entitlement as the AND of the three.

**Pushed to the caller as inputs.** For each candidate year of service: whether it is a qualifying year under SSCBA 1992 ss.22-23 (`is_qualifying`), whether it is a reckonable year under reg 13(1) of SI 1979/643 (`is_reckonable_1979`), and the year's start date. The person's pensionable age (PA 1995 Sch 4 lookup — not modelled). The person's current age in years.

**Omitted.** s.4(3) does not model the bar on claiming a s.2 full-rate pension when s.4 entitlement exists (we compute s.4 entitlement only). Class 3 NIC voluntary contributions are not represented — the caller must have already determined whether each year qualifies. Home Responsibilities Protection credits, credits for ill-health, and credits for caring responsibilities are all baked into the `is_qualifying` input. s.3 full-rate computation (for post-commencement-only claimants) and s.4 transitional-rate amount computation (using the pre/post-commencement weighting of ss.5–8) are both out of scope — this programme determines *entitlement*, not amount.

**Known deviations.** None at the entitlement level within the encoded conditions: if the caller supplies correct `is_qualifying` and `is_reckonable_1979` flags, and the correct pensionable age, the programme produces the legally correct entitlement judgment.

## ct_marginal_relief_program.yaml

Cited: Corporation Tax Act 2010 s.18B (marginal relief) and s.18E (associated-company count); s.3 main rate.

**Encoded in the DSL.** Days-in-AP via `days_between(period_start, period_end) + 1`. Associated-company count via `count_related` over the `associate_of` relation. Effective lower and upper limits pro-rated by days-in-AP / 365 and divided by (1 + number of associates). Within-marginal-band judgment. Eligibility AND of UK residence, not close-investment-holding, within-band, and no ring-fence profits. Marginal-relief formula `F × (U_eff − A) × (N / A)`. Gross CT at 25% of taxable total profits. CT after relief as `max(0, gross − relief)`.

**Pushed to the caller as inputs.** UK residence (reg implicitly assumes UK corporation-tax residence rules are already applied — CTA 2009 ss.14-16). Close-investment-holding status (s.18N definition). Augmented profits (s.18L — the sum of taxable total profits and exempt ABGH distributions, pre-computed). Taxable total profits (per Part 5 CTA 2009). Ring-fence profits (s.275 — oil and gas receipts).

**Omitted.** The small-profits-rate path (s.18A): when augmented profits are at or below the lower limit, CT is charged at 19% under s.18A. This programme applies the 25% main rate to all profits and deducts marginal relief, which is wrong for small-profits companies. The FY-straddle rule (s.8-9): an AP that spans two financial years with different rates, limits, or F must be apportioned between the two FYs and computed separately. This programme uses whichever parameter version is effective at the AP start. The associate-count-changing-during-AP rule (s.18E(3)) — the number of associates is taken at a point in time without the prorating the statute allows. No adjustment for SEIS/EIS or other reliefs that change taxable profits.

**Known deviations.** A company with augmented profits below £50,000 (lower limit) will be charged at 25% in this programme instead of the small-profits-rate 19%. The computed CT will therefore be too high by 6 percentage points on every pound of taxable profit for such companies. Any company whose AP straddles 1 April with changed rates/limits/F will be computed against the AP-start values rather than the proper two-FY apportionment; for FY-straddling APs between 2022 and 2023 this matters materially because the main rate went from 19% to 25%.

## snap_program.yaml

Cited: US federal SNAP rules for the 48 contiguous states and DC for FY 2026. This is an intentionally simplified prototype — the exact regulations (7 CFR 273) are cited only loosely via the standard deduction, income limit, and max allotment tables.

**Encoded in the DSL.** Household size from `count_related`. Earned and unearned income aggregated via `sum_related`. Gross income as earned plus unearned. Earned-income deduction at 20%. Standard deduction looked up by household size. Adjusted income before shelter. Half adjusted income. Elderly/disabled household flag as a judgment. Excess-shelter unclamped and clamped (capped at $744 for non-elderly, uncapped for elderly per the prototype). Net income. Gross and net income limit tests. Maximum allotment lookup by household size. Monthly allotment as `max(0, max_allotment − 0.3 × net_income)` rounded up.

**Pushed to the caller as inputs.** Household-member relation (who belongs to this SNAP household). Each member's earned and unearned income. Dependent care, child support, and medical deductions — all already computed per 7 CFR 273.9 and 273.10. Shelter costs. Has-elderly-or-disabled-member flag.

**Omitted.** Categorical eligibility (broad-based vs narrow categorical eligibility rules). Asset tests. Work requirements and ABAWD time limits. Expedited service. Vehicle exemptions. State options and waivers. The homeless shelter deduction (separate from the regular shelter deduction). Utility allowances (SUA/LUA). The dependent-care deduction cap (which technically has a per-dependent limit). Quality control and claims-overpayment recovery. Any state-specific variations (only the 48 contiguous states baseline is used). The actual USDA thresholds may vary from what the prototype encodes.

**Known deviations.** Because homeless and utility allowances are not modelled, households who would receive a SUA in reality will receive a lower allotment here. Because the excess shelter cap for non-elderly households is hardcoded at $744 (the FY26 figure), callers using this programme across fiscal years must update the literal.

## ated_program.yaml

Cited: Finance Act 2013 s.99.

**Encoded in the DSL.** Days in chargeable period (`days_between(period_start, period_end) + 1`) and days from entry day to end of period (`days_between(entry_day, period_end) + 1`). Band lookup via a six-level nested `if` on the taxable value, producing an integer band number used as the index into `ated_band_annual_amount`. Full annual amount when the chargeable person is in charge on day 1 of the period; otherwise N/Y pro-rated amount per s.99(6).

**Pushed to the caller as inputs.** Taxable value on the relevant day (the five-yearly revaluation is out of scope — s.99(4) and Sch 35 supply the revaluation timing). Whether the chargeable person was in charge on the first day of the chargeable period. The entry day where not.

**Omitted.** s.100 interim reliefs (charities, property rental businesses, dwellings opened to the public, etc.). s.106 mid-period disposal adjustments. Chargeable-person groups and co-ownership apportionment (s.96). The 2027 revaluation (bands above are 2024-25 figures; a future version with an additional parameter version per FY would be straightforward).

**Known deviations.** None at the single-dwelling-interest level within the encoded conditions, provided the caller supplies the correct taxable value and first-day-of-period flag. A dwelling that qualifies for an interim relief under s.100 will nonetheless attract the full band charge in this programme — the relief needs to be subtracted outside.

## auto_enrolment_program.yaml

Cited: Pensions Act 2008 s.3.

**Encoded in the DSL.** Age gate at 22 (s.3(1)(a)) via integer comparison. Pensionable-age upper gate (s.3(1)(b)) via integer comparison. Earnings trigger pro-rated by pay reference period length (s.3(6B)) as `trigger × prp_months / 12`. Earnings test (s.3(1)(c)). Not-already-an-active-member gate (s.3(3)). Not-recently-opted-out gate (s.3(4)). Final duty as an `and` of all five gates.

**Pushed to the caller as inputs.** Current age in years (no date-of-birth math in the DSL). Pensionable age in years (the PA 1995 Sch 4 lookup is not modelled). Earnings in the pay reference period (a reg 54 UCR-style calculation is not needed here because s.3 uses gross earnings payable). Pay reference period length in months (the PRP determination under s.15 is the caller's). Active-member status and recently-opted-out status.

**Omitted.** Re-enrolment cycle (ss.5-6). Multi-employer concurrent jobs (the section applies per employer). The definition of "qualifying scheme" (Part 1 of PA 2008). Opt-in rights for non-jobholders (s.7-8). Postponement provisions (ss.11-13). Cross-border workers.

**Known deviations.** A jobholder entering the 22–SPA age band during the PRP (or crossing it) gets a point-in-time classification; the programme uses whichever age the caller supplies. Same for any other status that changes within the PRP — the caller must resolve the point-in-time question before supplying the data.

## child_benefit_rates_program.yaml

Cited: Child Benefit (Rates) Regulations 2006 (SI 2006/965) reg 2.

**Encoded in the DSL.** Split of children into enhanced-rate-eligible and standard-rate via a filtered `count_related` on `is_eldest_in_household AND NOT resides_with_parent`. Voluntary-org disqualification (reg 2(4)(a)) via an `if` that zeroes out `num_enhanced_rate` when `is_voluntary_org` is true. Standard rate count as total minus enhanced. Total weekly rate as sum of (count × rate) for each band.

**Pushed to the caller as inputs.** Per-child `is_eldest_in_household` (this is the reg 2(2) tie-break across cohabiting partners and polygamous marriages — genuinely hard, involves comparing DOBs across households). Per-child `resides_with_parent` (this is per (claimant, child) pair, not per claimant, per reg 2(4)(b)). Per-claimant `is_voluntary_org`.

**Omitted.** Reg 2(5) cross-references to other benefit interactions. The tie-break *mechanism* itself (we take the outcome as an input). The guardian's allowance interaction.

**Known deviations.** In a mixed-household scenario where the eldest-in-household determination is disputed, the programme silently follows whichever value the caller supplied. This is the same pattern as UC's first-child-premium and every other "pre-applied tie-break" elsewhere.

## scottish_ctr_max_program.yaml

Cited: Scottish Council Tax Reduction Regulations 2021 (SSI 2021/249) reg 79.

**Encoded in the DSL.** Days in the financial year via `days_between(period_start, period_end) + 1` (statute explicitly denominates B in days). Count of non-student liable persons via `count_related` with a `where NOT is_student` predicate. Net annual amount A as `ct_annual − discounts − other_reductions`. Joint-and-several divisor with the partner-only carve-out (reg 79(4)) via an `if` on a partner-only-joint flag. Band E–H taper via `if band_number > 4 then A − A/C else A` where C is looked up by band number. Daily maximum as `A_after_taper / days_in_fy − non_dep_deductions_daily`, floored at zero.

**Pushed to the caller as inputs.** `ct_annual`, `ct_discounts`, and `ct_other_reductions` per reg 79(1)(a) (the authority-set charge and the discount/reduction determinations are external). `band_number` 1–8 for A–H. `non_dep_deductions_daily` (the reg 90 banded table is not modelled). `partner_only_joint` flag for the reg 79(4) carve-out. Per-liable-person `is_student` flag (the reg 20(2) student-status test is external).

**Omitted.** Mid-year band change (the programme assumes band is constant for the period). Mid-year joint-liability change. Reg 80 (entitlement to reduction in relation to a dwelling), reg 90 (non-dep deduction bands), reg 91 (polygamous marriages).

**Known deviations.** A dwelling whose band changes mid-FY will compute against whichever band the caller supplies. Similarly for liable-persons composition. A case where non-dep deductions exceed the daily A/B is correctly floored at zero.

## flat_tax_program.yaml and family_allowance_program.yaml

Both are fictional — not modelled on any real statute. They exist to exercise the DSL on simple scalar and relational patterns and are not claimed to be correct encodings of anything.

## What this audit says

Three categories of fidelity risk, in order of concern:

1. **Pushed-to-input fidelity.** The prototype takes shortcuts by making the caller pre-compute hard legal facts. These are explicit in the "Pushed to the caller as inputs" lists above. A caller who supplies the wrong input — e.g. treats a child as qualifying under reg 24B when they actually fall outside an exception, or declares augmented profits as taxable total profits — will get a wrong answer and the DSL will not catch it. The defence is that the input names are semantically precise and the source citations tell callers exactly which regulation supplies the input.

2. **Omitted paths.** The most serious omission is the SNAP homeless/utility allowances and the CT small-profits-rate path. Both produce wrong numbers for affected populations. UK income tax omits dividend, savings, marriage-allowance, and Scottish rules. UC omits childcare, benefit cap, transitional protection. In every case the omission is documented above and the programme's output is only claimed correct for the subset of the population the programme covers.

3. **Statutory edges.** A handful of rules are correctly stated but operate at period edges the prototype flattens — the April uprating AP, FY-straddling APs, diminishing notional capital, part-week child-benefit responsibility. These are deviations of legally small magnitudes (a few pounds per claim), but they are real. They reflect the time-period model as documented in `docs/time-period-semantics.md`, not a bug in the encodings.

The working rule going forward: every new programme ships with a fidelity entry in this document that lists the above four categories explicitly. A programme that does not do this should be treated as unverified.
