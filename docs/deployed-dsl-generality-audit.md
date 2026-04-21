# Deployed `.rac` DSL — non-tax-benefit generality audit

## Question

Can the deployed `.rac` DSL (main of `github.com/TheAxiomFoundation/rac`) encode
arbitrary legislation, or does its fit drop off sharply outside the
tax-benefit domain where it was designed? Pairs with Max's PR #23 comment
asking for honest evidence about what a rewrite would or wouldn't unlock.

## Method

**Target grammar.** The deployed parser at `src/rac/parser.py` accepts
`entity`, `amend`, `from`, `to`, `match`, `if`/`elif`/`else`, `and`/`or`/
`not`. Built-in functions are `min`, `max`, `abs`, `round`, `sum`, `len`,
`clip`, `any`, `all`. Metadata fields are `source`, `label`, `description`,
`unit`, `dtype`, `period`, `default`, `indexed_by`, `status`. Entities
carry typed fields, foreign keys (`-> Entity`), and reverse relations
(`[Entity]`). Not our Rust-loader extensions — this is the surface a
rac-uk or rac-us programme runs against today.

**Sample.** Ten sections, one per non-tax-benefit domain, committed before
reading the operative text to rule out cherry-picking for fit. No tax,
benefits, pensions, NMW, SNAP, or anything PolicyEngine already covers.
Every section is cited to legislation.gov.uk so the choice is reviewable.

**Verdict scheme.**

| Verdict | Meaning |
|---|---|
| Clean fit | The operative rule is expressible directly in the deployed `.rac` grammar. Inputs are the kinds of facts a caller would reasonably supply (ages, amounts, booleans that don't themselves require legal judgment). |
| Partial | Expressible only if the caller pre-applies one or more judgments that the statute itself puts at the centre of the rule (e.g. "dishonesty", "significant harm"). The DSL reduces to `and`/`or` of supplied booleans — structurally fine but the DSL is doing none of the interesting work. |
| Fail | The rule is a duty, an entitlement, a procedural discretion, or a validity test, not a function from facts to outputs. No expression in any deterministic DSL captures what the provision says. |

## Sample and verdicts

### 1. Children Act 1989 s.31 — threshold for care orders (family)

> (2) A court may only make a care order or supervision order if it is
> satisfied — (a) that the child concerned is suffering, or is likely to
> suffer, significant harm; and (b) that the harm, or likelihood of harm,
> is attributable to — (i) the care given to the child … not being what
> it would be reasonable to expect a parent to give to him; or (ii) the
> child's being beyond parental control.
> (3) No care order … may be made with respect to a child who has reached
> the age of seventeen (or sixteen, in the case of a child who is married).

Age test fits trivially (`age < 17 or (age < 16 and is_married)`).
"Significant harm", attribution, and "reasonable to expect a parent"
are the substantive content, and all three are pure judgments with
their own case-law bodies. The DSL can express `age_gate and
significant_harm_finding and attribution_finding` only if a human (or
the court) pre-determines the last two.

**Verdict: partial** — the DSL does nothing the caller couldn't do with
`and`.

### 2. Theft Act 1968 s.1 — basic definition of theft (criminal)

> (1) A person is guilty of theft if he dishonestly appropriates property
> belonging to another with the intention of permanently depriving the
> other of it.

Five elements (dishonesty, appropriation, property, belonging to another,
intent to permanently deprive) each carry their own case-law definition.
The statutory rule is "AND of the five". Expressible in deployed `.rac`
as `dishonesty and appropriation and property_of_another and intent`
if the caller pre-applies each.

**Verdict: partial** — pure conjunction of caller-determined legal
conclusions.

### 3. Landlord and Tenant Act 1985 s.11 — repairing obligations (property)

> (1) In a lease to which this section applies … there is implied a
> covenant by the lessor — (a) to keep in repair the structure and
> exterior of the dwelling-house …; (b) to keep in repair and proper
> working order the installations in the dwelling-house for the supply of
> water, gas and electricity and for sanitation …; and (c) to keep in
> repair and proper working order the installations in the dwelling-house
> for space heating and heating water.

Not a rule that produces an output from inputs. It imposes an ongoing
duty on a landlord and attaches judgment-based carve-outs ("age,
character and prospective life of the dwelling-house and the locality").
Nothing to compute.

**Verdict: fail** — duty-as-output, not a function.

### 4. Employment Rights Act 1996 s.98 — fairness of dismissal (employment)

> (1) In determining … whether the dismissal of an employee is fair or
> unfair, it is for the employer to show — (a) the reason … for the
> dismissal, and (b) that it is … a reason falling within subsection (2)
> or some other substantial reason of a kind such as to justify the
> dismissal …
> (4) … the determination of the question whether the dismissal is fair
> or unfair … depends on whether in the circumstances … the employer
> acted reasonably or unreasonably in treating it as a sufficient reason
> for dismissing the employee; and (b) shall be determined in accordance
> with equity and the substantial merits of the case.

The taxonomy in s.98(2) (capability, conduct, redundancy, legal
incompatibility) could be represented as an enum. The core test at
s.98(4) — reasonableness, "equity and the substantial merits" — is the
archetypal judgment. Reasonableness is not a computable function.

**Verdict: fail** — the reasonableness test at the heart of the
provision isn't encodable in any DSL.

### 5. Immigration Act 1971 s.3 — leave to enter (immigration)

> (1) Except as otherwise provided by or under this Act, where a person
> is not a British citizen — (a) he shall not enter the United Kingdom
> unless given leave to do so …; (b) he may be given leave to enter …
> either for a limited or for an indefinite period; (c) if he is given
> limited leave …, it may be given subject to … conditions …

Basic rule fits: `is_british or has_valid_leave`. Conditions (work
restrictions, reporting, curfew, electronic monitoring) are an open
list — expressible as boolean flags if enumerated, but the list itself
grows by amendment and by Secretary of State discretion.

**Verdict: partial** — the primary boolean holds; everything conditional
on Secretary of State discretion (subsection 1A) doesn't.

### 6. Companies Act 2006 s.172 — duty to promote the success of the company (corporate)

> (1) A director of a company must act in the way he considers, in good
> faith, would be most likely to promote the success of the company for
> the benefit of its members as a whole, and in doing so have regard
> (amongst other matters) to — (a) the likely consequences of any
> decision in the long term, (b) the interests of the company's
> employees, (c) the need to foster the company's business relationships
> with suppliers, customers and others, (d) the impact of the company's
> operations on the community and the environment, (e) the desirability
> of the company maintaining a reputation for high standards of business
> conduct, and (f) the need to act fairly as between members of the
> company.

"Acts … in good faith", "most likely to promote the success", "have
regard (amongst other matters) to" — pure judgment, open-ended factor
list, no determinable output.

**Verdict: fail** — the entire substantive content is judgment.

### 7. Licensing Act 2003 s.141 — sale of alcohol to a person who is drunk (regulatory / criminal)

> (1) A person to whom subsection (2) applies commits an offence if, on
> relevant premises, he knowingly — (a) sells or attempts to sell alcohol
> to a person who is drunk, or (b) allows alcohol to be sold to such a
> person.

Offence = AND of elements (knowingly, sells, to drunk person). Each is
a judgment. Structurally encodable, substantively not — the interesting
content is in the judgments.

**Verdict: partial** — conjunction of caller-supplied judgments.

### 8. Senior Courts Act 1981 s.31 — application for judicial review (procedural / public law)

> (3) No application for judicial review shall be made unless the leave of
> the High Court has been obtained in accordance with rules of court; and
> the court shall not grant leave to make such an application unless it
> considers that the applicant has a sufficient interest in the matter
> to which the application relates.
> (6) Where the High Court considers that there has been undue delay in
> making an application for judicial review, the court may refuse to
> grant — (a) leave for the making of the application; or (b) any relief
> sought … if it considers that the granting of the relief sought would
> be likely to cause substantial hardship to, or substantially prejudice
> the rights of, any person or would be detrimental to good
> administration.

"Sufficient interest", "undue delay", "substantial hardship",
"detrimental to good administration" — four judgments. The section's
substance is judicial discretion.

**Verdict: fail** — procedural discretion, not a function.

### 9. Scotland Act 1998 s.29 — legislative competence of the Scottish Parliament (devolution / constitutional)

> (1) An Act of the Scottish Parliament is not law so far as any
> provision of the Act is outside the legislative competence of the
> Parliament.
> (2) A provision is outside that competence so far as any of the
> following paragraphs apply — (a) it would form part of the law of a
> country or territory other than Scotland …; (b) it relates to reserved
> matters; (c) it is in breach of the restrictions in Schedule 4; (d) it
> is incompatible with any of the Convention rights …; (e) it would
> remove the Lord Advocate from his position as head of the systems of
> criminal prosecution and investigation of deaths in Scotland.
> (3) … the question whether a provision of an Act of the Scottish
> Parliament relates to a reserved matter is to be determined … by
> reference to the purpose of the provision, having regard (among other
> things) to its effect in all the circumstances.

Conjunction of five legal tests each of which is itself a substantive
question of law ("relates to reserved matters" is the entire subject of
Imperial Tobacco v Lord Advocate 2012 UKSC 61 and its progeny). The
purpose test at (3) — "having regard (among other things) to its effect
in all the circumstances" — is open-ended by design.

**Verdict: fail** — constitutional validity, pure legal judgment.

### 10. Data Protection Act 2018 s.45 — right of access, law enforcement processing (data protection)

> (1) A data subject is entitled to obtain from the controller — (a)
> confirmation as to whether or not personal data concerning him or her
> is being processed, and (b) where that is the case, access to the
> personal data and the information set out in subsection (2).
> (4) The rights conferred by subsection (1) may be restricted, wholly
> or partly, to the extent that and for so long as the restriction is, …
> a necessary and proportionate measure to — (a) avoid obstructing an
> official or legal inquiry …; (b) avoid prejudicing the prevention,
> detection, investigation or prosecution of criminal offences …;
> (c) protect public security …; (d) protect national security; (e)
> protect the rights and freedoms of others.

Entitlement + duty in subsection (1). Restrictions in (4) gated by
"necessary and proportionate" — the central proportionality test of
modern administrative law.

**Verdict: fail** — duty-as-output plus proportionality judgment.

## Tally

| Section | Domain | Verdict | What the DSL does / doesn't express |
|---|---|---|---|
| Children Act 1989 s.31 | family | partial | age gate fits; "significant harm" and attribution are judgments |
| Theft Act 1968 s.1 | criminal | partial | AND of five judgments; DSL adds nothing over `and` |
| L&T Act 1985 s.11 | housing | fail | duty on landlord, not a function |
| ERA 1996 s.98 | employment | fail | reasonableness / "equity and substantial merits" is judgment |
| Immigration Act 1971 s.3 | immigration | partial | basic boolean rule fits; discretion doesn't |
| Companies Act 2006 s.172 | corporate | fail | "good faith" + open-ended factors |
| Licensing Act 2003 s.141 | regulatory | partial | offence = AND of judgment elements |
| Senior Courts Act 1981 s.31 | procedural / JR | fail | judicial discretion, no function |
| Scotland Act 1998 s.29 | constitutional | fail | validity test, pure legal judgment |
| DPA 2018 s.45 | data protection | fail | duty + "necessary and proportionate" |

Clean fit: **0/10**. Partial: **4/10**. Fail: **6/10**.

## What the audit actually shows

The deployed `.rac` grammar encodes **zero of ten** non-tax-benefit
sections cleanly. Four are expressible as `and`/`or` of caller-supplied
booleans — a pattern the DSL technically supports but where every
substantive legal judgment has been pre-applied by the caller, so the
encoding is trivial. Six aren't functions at all — they're duties,
entitlements, procedural discretions, or validity tests.

The failure mode is not the DSL's operator set. Adding `ceil`,
`days_between`, filtered aggregation, three-valued judgments, and
counterfactuals to the grammar would not shift any of these verdicts,
because the missing structure is not a missing operator. The missing
structure is the recognition that much of law is:

1. **Judgment-shaped** — legal conclusions that a human must decide
   ("significant harm", "good faith", "reasonableness", "sufficient
   interest", "necessary and proportionate"), not computed.
2. **Duty-shaped** — an obligation attaching to a party, with no
   computed output at all (repairing covenants, directors' duties, data
   subject rights).
3. **Procedurally discretionary** — the court / Secretary of State / a
   regulator decides in the circumstances; no deterministic input-to-
   output function exists.

A DSL that limits itself to "inputs → outputs via arithmetic and
booleans" will always produce the 6/10 fail rate outside tax-benefit,
because tax-benefit is unusual for being almost entirely computation.
That's the honest ceiling. It is not a defect that further engine work
on the rewrite branch will fix.

## Implication for PR #23

Max's framing is right. The rewrite doesn't change the fit rate on
non-tax-benefit law, because the fit rate outside tax-benefit is
constrained by the shape of law itself, not by the operator set on
either side of the port. The work the rewrite actually delivers —
filtered aggregation, date arithmetic, three-valued judgments, Rust
substrate, typed AST-as-YAML for AutoRAC — is real and defensible on
its own terms. It is not a generality story.

The PR description should therefore be reframed as: *ships operators
that the tax-benefit audits surfaced (filtered aggregation, date
arithmetic, judgments with undetermined, citations); ships a typed
substrate; none of it moves the long tail*. Merge on those terms, not
on "computable law".

## Reproducibility

Sampling pre-registered 2026-04-21: one section per non-tax-benefit
domain from the list above, URL committed before reading operative text.
All operative text fetched from legislation.gov.uk. The `.rac` grammar
reference is the deployed parser at `github.com/TheAxiomFoundation/rac`
on main at commit 58f3122 (or whatever current HEAD is).

Anyone disputing a verdict should be able to flip it with a specific
encoding in the deployed grammar — those are the terms of the argument.
