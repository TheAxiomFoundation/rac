# Deployed `.rac` DSL — non-tax-benefit generality audit

## Question

Can the deployed `.rac` DSL (main of `github.com/TheAxiomFoundation/rac`)
encode arbitrary legislation? Pairs with Max's PR #23 comment asking for
honest evidence about what a rewrite would or wouldn't unlock.

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

**Verdict scheme — revised.** The first draft of this audit used a
"fail" bucket for rules whose substantive content sits in legal
judgments ("reasonable", "good faith", "significant harm",
"proportionate"). That framing was circular — I was defining the
interesting rules out of scope by ruling. Rewritten honestly: every
section's rule is attempted in the deployed `.rac`, with legal
judgments pre-applied as boolean inputs (same pattern tax-benefit
encodings use — `has_lcwra` is a pre-applied WCA determination,
`qualifies_for_child_element` is a pre-applied two-child-limit
exception test). The verdict records what the DSL contributes:

| Verdict | Meaning |
|---|---|
| Rich | The DSL does substantive arithmetic / aggregation. Tax-benefit programmes typically fall here — the encoding is not replicable in a few lines of `and`/`or`. |
| Thin | Structurally encodable, but the DSL is doing boolean composition (`and`/`or`/`not`/`match`) over pre-applied inputs. A JSON blob, a spreadsheet, or Prolog would give you the same leverage. |
| Blocked | Structurally encodable except for a specific operator or shape the deployed grammar lacks. Names the missing shape. |

## Sample and verdicts

### 1. Children Act 1989 s.31 — threshold for care orders (family)

> (2) A court may only make a care order or supervision order if it is
> satisfied — (a) that the child concerned is suffering, or is likely
> to suffer, significant harm; and (b) that the harm, or likelihood of
> harm, is attributable to — (i) the care given to the child … not
> being what it would be reasonable to expect a parent to give to him;
> or (ii) the child's being beyond parental control.
> (3) No care order … may be made with respect to a child who has
> reached the age of seventeen (or sixteen, in the case of a child who
> is married).

```rac
age_gate: entity: Child dtype: Boolean from 1989-11-16:
    age < 17 or (age < 16 and is_married)
care_order_may_be_made: entity: Child dtype: Boolean from 1989-11-16:
    age_gate and significant_harm_finding and attribution_finding
```

`significant_harm_finding` and `attribution_finding` are booleans the
caller supplies (in practice, determined by the court). **Verdict:
thin** — the DSL adds an age gate.

### 2. Theft Act 1968 s.1 — basic definition of theft (criminal)

> (1) A person is guilty of theft if he dishonestly appropriates
> property belonging to another with the intention of permanently
> depriving the other of it.

```rac
guilty_of_theft: entity: Person dtype: Boolean from 1968-07-26:
    dishonesty and appropriation and property and belonging_to_another
    and intent_to_permanently_deprive
```

**Verdict: thin** — AND of five caller-supplied legal conclusions; the
DSL's contribution is the conjunction itself.

### 3. Landlord and Tenant Act 1985 s.11 — repairing obligations (property)

> (1) … there is implied a covenant by the lessor — (a) to keep in
> repair the structure and exterior …; (b) to keep in repair and
> proper working order the installations … for the supply of water,
> gas and electricity and for sanitation …; and (c) to keep in repair
> and proper working order the installations … for space heating and
> heating water.

```rac
duty_fulfilled: entity: Dwelling dtype: Boolean from 1985-10-30:
    structure_in_repair and water_gas_electricity_working
    and sanitation_working and heating_and_hot_water_working
```

A compliance-at-time-T output. Caller supplies the per-system booleans
(typically from a surveyor's assessment). **Verdict: thin** — AND of
four booleans; no arithmetic.

### 4. Employment Rights Act 1996 s.98 — fairness of dismissal (employment)

> (1) … it is for the employer to show — (a) the reason …, and (b)
> that it is … a reason falling within subsection (2) or some other
> substantial reason …
> (2) A reason falls within this subsection if it — (a) relates to
> the capability or qualifications …, (b) relates to the conduct …,
> (c) is that the employee was redundant, or (d) is that the employee
> could not continue to work … without contravention … of a duty or
> restriction imposed by or under an enactment.
> (4) … the determination of the question whether the dismissal is
> fair or unfair … depends on whether in the circumstances … the
> employer acted reasonably …

```rac
reason_is_admissible: entity: Dismissal dtype: Boolean from 1996-08-22:
    match reason_code:
        "capability" => true
        "conduct" => true
        "redundancy" => true
        "statutory_bar" => true
        "other_substantial" => some_other_substantial_reason_established
        _ => false
fair_dismissal: entity: Dismissal dtype: Boolean from 1996-08-22:
    reason_is_admissible and employer_acted_reasonably
```

**Verdict: thin** — `match` over a reason enum, then AND with the
caller's reasonableness determination.

### 5. Immigration Act 1971 s.3 — leave to enter (immigration)

> (1) Except as otherwise provided …, where a person is not a British
> citizen — (a) he shall not enter the United Kingdom unless given
> leave to do so …; (b) he may be given leave … either for a limited
> or for an indefinite period; (c) if he is given limited leave …, it
> may be given subject to … conditions …

```rac
entitled_to_enter: entity: Person dtype: Boolean from 1971-10-28:
    is_british_citizen or has_valid_leave
```

Open-ended condition list (work, study, residence, reporting,
electronic monitoring) is metadata, not computation. **Verdict: thin**
— one OR.

### 6. Companies Act 2006 s.172 — directors' duty to promote the success of the company (corporate)

> (1) A director of a company must act in the way he considers, in
> good faith, would be most likely to promote the success of the
> company for the benefit of its members as a whole, and in doing so
> have regard (amongst other matters) to — (a) the likely consequences
> … in the long term, (b) the interests of the company's employees,
> (c) the need to foster … business relationships …, (d) the impact
> … on the community and the environment, (e) the desirability …
> maintaining a reputation for high standards …, and (f) the need to
> act fairly as between members …

```rac
fulfilled_s172: entity: Director dtype: Boolean from 2008-10-01:
    acted_in_good_faith and most_likely_to_promote_success
    and had_regard_to_long_term and had_regard_to_employees
    and had_regard_to_business_relationships
    and had_regard_to_community_and_environment
    and had_regard_to_reputation and had_regard_to_fair_treatment
```

**Verdict: thin** — AND of eight caller-supplied judgments.

### 7. Licensing Act 2003 s.141 — sale of alcohol to a person who is drunk (regulatory / criminal)

> (1) A person to whom subsection (2) applies commits an offence if,
> on relevant premises, he knowingly — (a) sells or attempts to sell
> alcohol to a person who is drunk, or (b) allows alcohol to be sold
> to such a person.

```rac
offence_committed: entity: Sale dtype: Boolean from 2003-11-24:
    subsection_2_applies and on_relevant_premises and knowingly
    and (sold_or_attempted_sale or allowed_sale) and buyer_was_drunk
```

**Verdict: thin** — AND/OR of offence elements.

### 8. Senior Courts Act 1981 s.31 — application for judicial review (procedural / public law)

> (3) … the court shall not grant leave … unless it considers that the
> applicant has a sufficient interest in the matter …
> (6) Where the High Court considers that there has been undue delay
> … the court may refuse to grant — (a) leave …; or (b) any relief …
> if it considers that the granting of the relief sought would be
> likely to cause substantial hardship to, or substantially prejudice
> the rights of, any person or would be detrimental to good
> administration.

```rac
leave_may_be_granted: entity: Application dtype: Boolean from 1981-07-28:
    has_sufficient_interest and (
        not undue_delay
        or not (would_cause_substantial_hardship
                or would_prejudice_rights
                or would_harm_good_administration)
    )
```

**Verdict: thin** — boolean composition over judicial-discretion
inputs.

### 9. Scotland Act 1998 s.29 — legislative competence (devolution / constitutional)

> (1) An Act of the Scottish Parliament is not law so far as any
> provision of the Act is outside the legislative competence of the
> Parliament.
> (2) A provision is outside that competence so far as any of the
> following paragraphs apply — (a) it would form part of the law of a
> country or territory other than Scotland …; (b) it relates to
> reserved matters; (c) it is in breach of the restrictions in
> Schedule 4; (d) it is incompatible with any of the Convention rights
> …; (e) it would remove the Lord Advocate from his position as head
> of the systems of criminal prosecution …

```rac
within_competence: entity: Provision dtype: Boolean from 1999-07-01:
    not affects_territory_outside_scotland
    and not relates_to_reserved_matter
    and not breaches_schedule_4
    and not incompatible_with_convention_rights
    and not removes_lord_advocate
```

**Verdict: thin** — AND of five NOTs.

### 10. Data Protection Act 2018 s.45 — right of access, law enforcement (data protection)

> (1) A data subject is entitled to obtain from the controller — (a)
> confirmation as to whether or not personal data concerning him or
> her is being processed, and (b) where that is the case, access to
> the personal data and the information set out in subsection (2).
> (4) The rights conferred by subsection (1) may be restricted … to
> the extent that … the restriction is … a necessary and proportionate
> measure to — (a) avoid obstructing an official or legal inquiry …;
> (b) avoid prejudicing the prevention, detection, investigation or
> prosecution of criminal offences; (c) protect public security; (d)
> protect national security; (e) protect the rights and freedoms of
> others.

```rac
entitled_to_access: entity: DataSubject dtype: Boolean from 2018-05-25:
    is_data_subject and not restriction_applies
restriction_applies: entity: DataSubject dtype: Boolean from 2018-05-25:
    (obstructs_inquiry or prejudices_prosecution or protects_security
     or protects_national_security or protects_others_rights)
    and is_necessary_and_proportionate
```

**Verdict: thin** — boolean composition with proportionality as a
pre-applied input.

## Tally

| Section | Domain | Verdict |
|---|---|---|
| Children Act 1989 s.31 | family | thin |
| Theft Act 1968 s.1 | criminal | thin |
| L&T Act 1985 s.11 | housing | thin |
| ERA 1996 s.98 | employment | thin |
| Immigration Act 1971 s.3 | immigration | thin |
| Companies Act 2006 s.172 | corporate | thin |
| Licensing Act 2003 s.141 | regulatory | thin |
| Senior Courts Act 1981 s.31 | procedural / JR | thin |
| Scotland Act 1998 s.29 | constitutional | thin |
| DPA 2018 s.45 | data protection | thin |

Rich: **0/10**. Thin: **10/10**. Blocked: **0/10**.

## What the audit actually shows

The deployed `.rac` grammar structurally encodes all ten non-tax-benefit
sections. The encoding is valid in the same sense tax-benefit encodings
are valid: legal judgments are pre-applied as boolean inputs, and the
DSL composes them with `and`, `or`, `not`, and `match`. "Failing to
encode judgment-heavy law" was the wrong framing — law-as-code has
always meant pre-applying legal conclusions and letting the DSL handle
structure.

What the audit *does* show is that the DSL's **contribution** varies
dramatically by domain. Ten of ten non-tax-benefit encodings are
**thin** — boolean composition that a JSON blob, a spreadsheet, or a
rules engine with `and`/`or` would match. None are **rich** in the
sense UC Regs 2013 is rich: UC's encoding does real arithmetic
(standard allowance selection by age/couple, child elements by count
and rate tier, earnings taper, capital tariff, housing net of non-dep
deductions), and the DSL earns its keep by replacing hundreds of lines
of bespoke calculator code with a small grammar of operators.

For these ten sections, the DSL earns less. Boolean composition is not
zero — it still gives you provenance, temporal versioning of the rules,
composition across files, and citation metadata. But it is not the
"compile law to a calculator" story the rewrite was implicitly
pitched on.

## What this means for operator additions

**Zero of ten sections are "blocked" on a missing operator.** Not
filtered aggregation, not date arithmetic, not three-valued judgments,
not counterfactuals, not cross-entity lookup. Every one of the ten
reduces to boolean composition over caller-supplied inputs. So the
claim "the rewrite adds operators the audits showed were missing" is
true — the tax-benefit audits 001–005 did identify real operator gaps
that moved fit rate from 3/10 clean to 8/10 clean in the
arithmetic-shaped tail. But those gaps bind tax-benefit-adjacent law,
not the long tail sampled here. The long tail is bounded below by how
much of the rule is judgment.

## Implication for PR #23

Max's framing holds. The rewrite ships real operators for the
tax-benefit-adjacent audit findings. It does not unlock new territory
in the long tail, because the long tail is bounded by pre-applied
judgments, not by missing operators. A PR description that claims
generality is overclaiming; one that claims "operators the audits
found were missing + a cleaner substrate for AutoRAC" is defensible.

The more interesting question this audit surfaces — and the one the
rewrite doesn't answer — is whether a DSL whose contribution is "thin
boolean composition" on 80% of the legal corpus is differentiated
enough to justify a dedicated engine versus, say, a library of typed
predicates in Python with citation metadata and temporal versioning.
That's a product question, not an engineering one.

## Reproducibility

Sampling pre-registered 2026-04-21: one section per non-tax-benefit
domain from the list above, URL committed before reading operative text.
All operative text fetched from legislation.gov.uk. The `.rac` grammar
reference is the deployed parser at `github.com/TheAxiomFoundation/rac`
on main.

Anyone disputing a verdict should be able to flip it with a specific
encoding in the deployed grammar — those are the terms of the argument.
