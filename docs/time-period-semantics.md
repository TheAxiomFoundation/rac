# Time-period semantics

An honest audit of how the prototype handles time today, where that works, and where it bends.

## The model

There are three kinds of temporal binding in the prototype.

**Query period.** Every request executes a bundle of derived outputs *for a given period*. A period has a `kind` (`month`, `benefit_week`, `tax_year`, `custom("...")`), a `start` date, and an `end` date. The engine never invents periods — the caller supplies them. A batch of queries in fast mode currently requires one period shared across the batch, because the dense executor is compiled against a single period at a time.

**Input interval.** Every input record carries an `interval: {start, end}` during which that input is taken to hold. Lookup is set-containment: a record is valid for the query iff `record.interval.start <= period.start AND record.interval.end >= period.end`. The engine picks the first matching record by `record.interval.start` descending (so the most recent enclosing record wins). Partial overlap is ignored — a record whose interval crosses the period boundary without fully enclosing it is not matched. There is no apportionment, no summing across overlapping records, and no "value at the start of the period" semantics distinct from "value across the period".

**Effective-dated parameters.** Parameters have versions each tagged with an `effective_from` date. Lookup picks the most recent version with `effective_from <= period.start`. If the query period straddles a version change, the version active at the start of the period is used for the whole computation — the prototype does not apportion across a mid-period rate change.

Relations carry an interval too. A tuple is present in the relation for queries whose period is contained by the relation's interval, using the same set-containment rule as inputs.

## What this means per worked programme

**SNAP (monthly).** SNAP benefits are calculated monthly. Period kind = `month`, interval per input = that month. Household membership is supplied as a `member_of_household` relation with a monthly interval. This is a clean fit — callers provide month-at-a-time snapshots and the engine does no temporal reasoning beyond set-containment.

**Child benefit responsibility (reg 15, weekly).** Period kind = `benefit_week` (7 days starting on a claimant-specific day). Inputs and relations carry matching weekly intervals. Again a clean fit; the anti-join logic operates within a single week with no cross-week reasoning.

**rUK income tax (annual).** Period kind = `tax_year`. Each of the five gross income components is supplied as a single record with interval spanning the tax year. Thresholds are effective-dated to 6 April of each year. Straightforward.

**Pensions Act s.13 qualifying earnings (variable pay reference period).** The pay reference period length in months is supplied as an input (`prp_months`) and used to pro-rate thresholds. The period itself is a `custom("pay_reference_period")` supplying the dates. Pro-rata is explicit in the arithmetic, not derived from period length — this dodges the "what is one month" question by making it a user-provided fact.

**Universal Credit (monthly assessment period).** Period kind = `month`, though legally a UC assessment period (AP) is a calendar-month-equivalent anchored to the claimant's first claim date — so APs can straddle calendar months. The prototype treats every AP as a `month` period; the caller is responsible for supplying inputs whose interval matches the AP. Earned income, capital, housing costs, and non-dependant deductions are all supplied as monthly interval records.

**Scottish CTR notional capital (weekly).** Period kind = `benefit_week`. Disposals are supplied as per-disposal records with the same weekly interval (even though disposals are historical events; they are treated as "relevant in week X" by the caller).

## Where the model bends

**Periods that don't decompose cleanly.** UC's assessment period is legally a "period of one month" (reg 21 UCR 2013). When an AP doesn't map to a calendar month — e.g. a first AP that starts mid-month — the regs tell you to treat the AP as a conceptual month anyway, with specific edge-case adjustments (reg 26(3), the starting-month calculation). The prototype ignores this edge and assumes 30-day-equivalent APs. For 99% of APs on a given claim this is right; the first and last APs of each claim are approximate.

**Partial-overlap inputs are silently dropped.** If a caller supplies an earnings record with interval `[1 May, 14 May]` and the query period is `[1 May, 31 May]`, the record does not match (interval doesn't contain the period) and lookup returns `MissingInput`. There is no "take the overlapping portion" mode. Callers must pre-split or aggregate inputs to match the query period exactly. This is a sharp edge: programmes that assume annual data will silently break on monthly queries and vice versa.

**Point-in-time inputs have no first-class encoding.** UC capital is legally "capital at any point during the AP that triggers tariff income" (more or less). Child benefit responsibility depends on who is currently *receiving* child benefit — a point-in-time fact, not an averaged-over-the-week fact. The prototype represents these as inputs with an interval matching the query period, relying on the caller to have asked the right point-in-time question before supplying the data. This works but buries a real distinction.

**Parameter apportionment across mid-period rate changes.** If UC rates changed on 7 April and someone's AP spans 25 March – 24 April, UC regs actually apply the new rate from the effective date (reg 38). The prototype uses the rate effective at period start — so this specific edge case (the April uprating AP) is computed with the prior year's rates. This is wrong for that one AP per claim per year.

**Multi-period sums / running totals.** Tax calculations often sum monthly PAYE figures across a year. The prototype has no built-in mechanism for this — the user must either supply the annual total as an input (what our income tax programme does) or run twelve monthly queries and add them outside the DSL.

**Cumulative period-over-period state.** CTA 2009 s.1217J theatre tax relief is a recursive cumulative calculation: the deduction in period *i* depends on the sum of deductions in all prior periods. The prototype has no way to express this — it compiles acyclically per period. This showed up in the generality audit.

**Derived periods.** Some rules define the period itself (e.g., NISR 1996/198 reg 152 defines the "relevant week" by reference to award boundaries). The prototype cannot produce a period as an output; periods are only query inputs.

## What legislation would force us to add next

Looking at the existing worked programmes and the generality audit sample together, the highest-leverage additions for time handling, ordered by how many existing or sampled sections each would unlock:

1. **Period-level operators**: `period.start`, `period.end` exposed as `Date` expressions; period-contains-date, period-overlap-with-interval, period-overlap-fraction. These let programmes reason about the query period explicitly without dropping to day counts. Minimal implementation; unblocks partial-period rules and the UC first/last-AP edge.

2. **Apportioned input lookup**: an input semantic that says "this record covers the overlap between its interval and the query period, pro-rated". Required for monthly queries against annually-supplied data, and for the parameter apportionment problem above. Non-trivial — needs a clear rule for what "pro-rated" means (flat day-weighted, calendar-month-weighted, etc.).

3. **Point-in-time inputs**: a separate kind of input that resolves by matching a specific date (not an enclosing interval). Useful for "capital on the day the claim was made" and similar. Small change.

4. **Cross-period recursion / cumulative fold**: evaluate a derived as a fold over a sequence of periods. Needed for theatre tax relief and any cumulative allowance. The dense path becomes a cumulative scan on an extra period axis. Medium change; intersects with cross-entity work.

5. **Derived relations whose interval is derived**: the outputs of some rules include a period (the "relevant week" cases). Big change; needs derived periods to be first-class and parameterised over the evaluation context.

## Honest assessment

The current model is clean and works for any rule that is (a) evaluated per whole query period, (b) consumes inputs that exactly cover that period, and (c) does not need to reason about sub-period events or cross-period flows. Every worked programme today fits this model — including Universal Credit, as long as callers feed one record per AP and the first/last AP edge is accepted as approximate.

When a rule steps outside that — part-week carve-outs, mid-period rate changes, cumulative reliefs, period-defining rules — the prototype currently asks the caller to pre-compute the answer and supply it as an input. This is honest for the prototype stage. Each specific operator above would pull a chunk of that pre-computation back into the DSL, and the generality-audit cycle will say which chunk is most worth pulling in next.

## On `days_between` and day-level arithmetic

`days_between(from_date, to_date) -> Integer` exists as a primitive. It is deliberately narrow. It is intended for rules whose statutory text is itself expressed in days — FA 2013 s.99 ATED ("the number of days from (and including) the relevant day to the end of the chargeable period"), ESA Regs 2008 reg 166 (7-day relevant-week windows anchored to specific part-week dates), and similar.

It is **not** intended as the default way to reason about the length or fraction of a period. Most statutes that pro-rate across a period do so at period level: CTA 2010 s.18B says limits "shall be reduced proportionately" when an AP is less than 12 months; SNAP works monthly; UC works monthly; tax thresholds apply annually. Reaching for `days_between / 365` in every such case would bake a particular day-centric convention (and specifically a 365-day year that ignores leap years) into the DSL as a default.

The CT marginal relief programme demonstrates the preferred alternative: it takes an `ap_year_fraction` as a caller input rather than computing `days(AP) / 365`. This keeps the DSL agnostic about how "proportionately" is operationalised — HMRC's 365-day convention, a calendar-month form, a 360-day convention, or something else — and pushes the choice to the caller, where it belongs.

A future period-level operator (e.g. `period_fraction_of_year` that takes the query period and returns a `Decimal`, implementing some specific convention) could replace the input-pushed `ap_year_fraction` pattern once a convention is settled. Until then, explicit callers are the honest design. `days_between` stays in the DSL for the rules that genuinely need it — and a programme reaching for it should explain why in its source citation.
