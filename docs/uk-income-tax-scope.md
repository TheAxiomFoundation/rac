# UK income tax — full modelling scope

## What's already in

[`programmes/ukpga/2007/3/program.yaml`](../programmes/ukpga/2007/3/program.yaml) is the rUK 2025-26 headline: five gross-income inputs, personal allowance with the £100,000 taper, basic/higher/additional rate bands, total tax, net income. One taxpayer, one tax year. Eight HMRC-validated cases pass in explain mode and the fast path benchmarks at 2–3m taxpayers/second.

This doc is the punch list for turning that into something you could hand a real UK taxpayer and expect the right answer.

## The ITA 2007 s.23 skeleton

Every item below sits inside one of the seven steps from [s.23](https://www.legislation.gov.uk/ukpga/2007/3/section/23) — the statutory calculation skeleton. The current programme compresses steps 1–5 and skips 6 and 7. Re-drawing it as explicit steps is the first refactor.

| Step | Content | Currently |
|------|---------|-----------|
| 1 | Total income (sum of components) | `gross_income` |
| 2 | Reliefs deducted → net income | missing |
| 3 | Allowances deducted → taxable income | personal allowance only |
| 4 | Tax at each applicable rate on each slice | NSND-only, rUK-only |
| 5 | Sum of Step 4 amounts | `income_tax` |
| 6 | Tax reducers subtracted | missing |
| 7 | Add HICBC, pension charges, Gift Aid recovery, other Part-15A-ish charges | missing |

Naming the derived outputs after the steps (`step_1_total_income`, `step_2_net_income`, …) keeps the trace readable as a statutory proof.

## Step 1 — income classification

The headline omission is that "income" is three tax-distinct things with three rate tables. All three need their own input channels and carry through to Step 4 separately.

**Non-savings non-dividend (NSND):** employment, self-employment, pension, property, trading, miscellaneous. Already lumped in `gross_income`; needs splitting.

**Savings:** bank/BS interest, gilt interest, certain bond coupons, purchased life-annuity interest. New inputs. ISA interest is statutorily excluded — either an `isa_flag` gate or simply never passed in.

**Dividends:** UK dividends, foreign dividends (with double-taxation-relief complications), OEIC equalisation. New inputs.

All three expressible as further `add` derived outputs over input components. No DSL gaps.

## Step 2 — reliefs (net income)

The ones that matter at scale:

- trading losses carry-forward / carry-back ([ITA s.83, s.89](https://www.legislation.gov.uk/ukpga/2007/3/section/83))
- property losses ([ITA s.117](https://www.legislation.gov.uk/ukpga/2007/3/section/117))
- qualifying loan interest ([ITA s.383](https://www.legislation.gov.uk/ukpga/2007/3/section/383))
- gross pension contributions under net-pay (reduces employment income before it reaches Step 1 — handled at source)
- gift of shares/land to charity ([ITA s.431](https://www.legislation.gov.uk/ukpga/2007/3/section/431))
- share-loss relief ([ITA s.131](https://www.legislation.gov.uk/ukpga/2007/3/section/131))
- EIS loss relief on negligible-value claims

All are scalar subtractions with floors at zero once passed in as per-taxpayer inputs. The structural issue is cross-period state for carry-forward and carry-back — the prototype has no temporal linkage across tax years, so these start as inputs computed by the caller. This is the same gap that came up in [generality audit 005](generality-audit-005.md) for CTA 2010 s.37.

## Step 3 — allowances

| Allowance | 2025-26 | Section | DSL shape |
|-----------|---------|---------|-----------|
| Personal allowance + £100k taper | £12,570 | [ITA s.35, s.55B](https://www.legislation.gov.uk/ukpga/2007/3/section/35) | done |
| Blind person's allowance | £3,130 | [ITA s.38](https://www.legislation.gov.uk/ukpga/2007/3/section/38) | bool input + add |
| Married couple's allowance (pre-1935) | £11,270 × 10% reducer | [ITA s.45](https://www.legislation.gov.uk/ukpga/2007/3/section/45) | Step 6 reducer, income taper |
| Marriage allowance — outbound | PA − £1,260 | [ITA s.55B](https://www.legislation.gov.uk/ukpga/2007/3/section/55B) | subtract from PA, input flag |
| Marriage allowance — inbound | £252 reducer | [ITA s.55C](https://www.legislation.gov.uk/ukpga/2007/3/section/55C) | Step 6 reducer |
| Personal savings allowance | £1,000 / £500 / £0 | [ITA s.12B](https://www.legislation.gov.uk/ukpga/2007/3/section/12B) | band-conditional lookup |
| Starting rate for savings | £5,000 @ 0% | [ITA s.12](https://www.legislation.gov.uk/ukpga/2007/3/section/12) | NSND-above-PA taper |
| Dividend allowance | £500 | [ITA s.13A](https://www.legislation.gov.uk/ukpga/2007/3/section/13A) | 0% slice at foot of dividend band |
| Trading allowance | £1,000 | [ITTOIA s.783A](https://www.legislation.gov.uk/ukpga/2005/5/section/783A) | subtract from trading income |
| Property allowance | £1,000 | [ITTOIA s.783B](https://www.legislation.gov.uk/ukpga/2005/5/section/783B) | subtract from property income |
| Rent-a-room relief | £7,500 | [ITTOIA s.784](https://www.legislation.gov.uk/ukpga/2005/5/section/784) | subtract from property income, election |

Personal savings allowance and starting rate for savings are the fiddly ones. PSA depends on your marginal band, which you don't know until you've walked the NSND through Step 4 first. Starting rate tapers by `max(0, nsnd_taxable − 0)` — it's only available if NSND doesn't use up the first £5,000 of taxable territory above the PA. Expressible today, just with the right ordering of derived outputs.

The marriage allowance transfer is a cross-entity fact — A transfers £1,260 of their PA to B, raising B's reducer — which currently has to be modelled as paired inputs rather than a single relation. Same gap as HICBC below.

## Step 4 — rates

Three tax tables, three countries, three income types. At the extreme (a Scottish-resident with NSND + savings + dividends) you need to allocate slices across three rate ladders.

**rUK bands (2025-26):** 20 / 40 / 45 at thresholds 37,700 / 125,140. Already in programme.

**Welsh rates** ([ITA s.6B](https://www.legislation.gov.uk/ukpga/2007/3/section/6B)): NSND only, set by Senedd. Currently match rUK but structurally a separate parameter set keyed by `welsh_resident`. Cheap to model as a second parameter series.

**Scottish rates** ([ITA s.6A](https://www.legislation.gov.uk/ukpga/2007/3/section/6A) + annual Scottish Rate Resolution): NSND only. Six bands at 2025-26 — starter 19%, basic 20%, intermediate 21%, higher 42%, advanced 45%, top 48%. Adds two more `*_band_amount` derived outputs and a country-conditional rate ladder. Savings and dividends still follow rUK rates even for Scottish residents.

**Savings rates:** 20 / 40 / 45 stacked on top of NSND within the same band thresholds — i.e. savings income fills the band ladder from whatever point NSND left off.

**Dividend rates** ([ITTOIA s.13](https://www.legislation.gov.uk/ukpga/2005/5/section/13)): 8.75 / 33.75 / 39.35, stacked on top of NSND + savings.

The ordering is statute: NSND first, then savings, then dividends fill the bands. Expressible as a chain of derived `*_remaining_basic_band`, `*_remaining_higher_band` outputs that thread the residual through each income type. Verbose but cleanly representable.

**Band-extending items:** Gift Aid and relief-at-source pension contributions gross up (÷ 0.8) and widen both basic and higher thresholds by the grossed amount ([ITA s.192](https://www.legislation.gov.uk/ukpga/2007/3/section/192), [FA 2004 s.192](https://www.legislation.gov.uk/ukpga/2004/12/section/192)). Plain arithmetic on the band parameters at the point they're consumed.

## Step 6 — tax reducers

[ITA s.26](https://www.legislation.gov.uk/ukpga/2007/3/section/26) names the ordering. In practice:

- married couple's allowance (s.45)
- marriage allowance inbound (s.55C) — capped at £252
- EIS subscription relief at 30% ([ITA s.158](https://www.legislation.gov.uk/ukpga/2007/3/section/158))
- SEIS subscription relief at 50% ([ITA s.257AB](https://www.legislation.gov.uk/ukpga/2007/3/section/257AB))
- VCT relief at 30% ([ITA s.263](https://www.legislation.gov.uk/ukpga/2007/3/section/263))
- social investment tax relief (closed to new investment from April 2023; still in the statute)
- community investment tax relief ([ITA s.333](https://www.legislation.gov.uk/ukpga/2007/3/section/333))
- maintenance payments relief (pre-1935, tiny)
- notional tax on life insurance chargeable events

Each applies in order, each capped at the tax liability remaining. Modelled as a chain of derived outputs, each `tax_after_X = max(0, tax_before_X − min(reducer, tax_before_X))`. The DSL handles this today — it's just long.

## Step 7 — add-ons

**High Income Child Benefit Charge** ([ITEPA s.681B](https://www.legislation.gov.uk/ukpga/2003/1/section/681B)): claws back child benefit from the higher-income partner in a couple, 1% per £200 of adjusted net income over £60,000, full at £80,000 (from 2024-25). Needs: adjusted net income derivation, cross-partner comparison, pointer to the CB programme's output. Cross-entity again.

**Pension annual allowance charge** ([FA 2004 s.227](https://www.legislation.gov.uk/ukpga/2004/12/section/227)): excess above £60,000 annual allowance (with tapering from £260k adjusted income), taxed at the member's marginal rate. Marginal-rate bit needs the same band allocation as Step 4.

**Pension scheme sanction charges and unauthorised payment charges** — fixed-rate charges, straightforward.

**Gift Aid recovery** ([ITA s.424](https://www.legislation.gov.uk/ukpga/2007/3/section/424)): if tax paid < Gift Aid relief claimed, taxpayer owes the shortfall. One `max(0, relief − tax_paid)`.

**Life insurance chargeable event gains with top slicing relief** ([ITTOIA s.535](https://www.legislation.gov.uk/ukpga/2005/5/section/535)): this is the only item on the list that needs something the DSL currently can't express cleanly — the calculation is iterative over policy years and requires a "relieved liability − unrelieved liability" comparison. Expressible if N years is bounded, but the generic version wants a small-scale loop operator. Live with as an input for now.

## Beyond the Act

**Student loans** (plans 1, 2, 4, 5, postgraduate): 9% (6% for PG) over plan-specific thresholds, collected with tax but legally separate. Own programme under [ukpga/1998/14](https://www.legislation.gov.uk/ukpga/1998/14).

**Class 2 and Class 4 NICs:** cover in [SSCBA 1992](https://www.legislation.gov.uk/ukpga/1992/4). Class 4 already shown to fit cleanly in [audit 005](generality-audit-005.md).

**Scottish income tax residency test:** the 183-day rule and close-connection tests are temporal-relational and need a year of daily location data. Ideally a separate programme; realistically a `scottish_resident` input for now.

**Non-residence, remittance basis, split-year:** reform in force from April 2025 replaces the remittance basis with a four-year FIG regime. Framework-heavy; likely caller-supplied adjusted totals.

## DSL gaps this exposes

In priority order by how often the gap shows up in this punch list:

1. **Cross-entity / pair-keyed derivation.** Marriage allowance, HICBC partner selection, couples' joint-notional-income tests all want "for this taxpayer, also look at their partner". Flagged in the [README](../README.md) generality-audit summary as a headline gap. Until then, paired inputs — which works but sacrifices the "relational" side of the pitch for the one part of the tax code that's most obviously relational.

2. **Ordered state threading.** Tax reducers (Step 6) and band allocation across NSND → savings → dividends (Step 4) both need a running residual. Works today as a chain of derived outputs, but the programme YAML gets long and the trace is noisy. A tiny `let`/`scan` sugar would compress it.

3. **Cross-period state.** Loss carry-forward and carry-back want this year's Step 2 deduction to depend on prior years' unused losses. Same gap raised by CTA 2009 s.1217J (audit 001), VAT rolling 12-month turnover (audit 002), and CTA 2010 s.37 (audit 005). This is the one recurring structural gap across audits.

4. **Bounded-loop / fixed-point operator for top slicing relief.** One-item blocker that isn't urgent.

Nothing here changes the pitch — the seven-step skeleton, classifications, allowances, bands, reducers, and add-ons are all expressible with the existing operators. The cross-entity gap is the one that hurts narratively, because a real UK couple interacts with the tax system jointly even though the tax itself is individual.

## Suggested programme layout

One programme per legislated unit. Sharing via `extends` to avoid duplicating the rate and allowance parameters.

```
programmes/
  ukpga/2007/3/                       -- ITA 2007 rates, bands, allowances, s.23 skeleton
    section/23/program.yaml
    section/35/program.yaml           -- PA and £100k taper
    section/38/program.yaml           -- blind person's allowance
    section/55B/program.yaml          -- marriage allowance outbound
    section/55C/program.yaml          -- marriage allowance inbound
    section/12/program.yaml           -- starting rate for savings
    section/12B/program.yaml          -- personal savings allowance
    section/13A/program.yaml          -- dividend allowance
    section/26/program.yaml           -- tax reducer ordering
    section/6A/program.yaml           -- Scottish rates
    section/6B/program.yaml           -- Welsh rates
  ukpga/2003/1/section/681B/          -- HICBC
  ukpga/2005/5/
    section/13/program.yaml           -- dividend tax rates
    section/783A/program.yaml         -- trading allowance
    section/783B/program.yaml         -- property allowance
    section/784/program.yaml          -- rent-a-room
  ukpga/2004/12/
    section/192/program.yaml          -- pension tax relief at source
    section/227/program.yaml          -- annual allowance charge
```

A `programmes/ukpga/2007/3/section/23/program.yaml` at the top composes everything with `extends` and resolves the step 1–7 chain. The existing monolithic programme then becomes a thin wrapper for the rUK-headline demo.
