use axiom_rules::compile::{CompileError, CompiledProgramArtifact, compile_program_file_to_json};
use axiom_rules::rulespec::{RuleSpecError, lower_rulespec_str};

fn assert_same_artifact(left: CompiledProgramArtifact, right: CompiledProgramArtifact) {
    let left = serde_json::to_value(left).expect("left artifact serialises");
    let right = serde_json::to_value(right).expect("right artifact serialises");
    assert_eq!(left, right);
}

#[test]
fn rulespec_matches_rac_for_snap_like_formulas() {
    let rulespec = r#"
format: rulespec/v1
module:
  id: us.snap.tx.demo
  title: Texas SNAP demo subset
relations:
  - name: member_of_household
    arity: 2
rules:
  - name: snap_state_sme_flat_amount
    kind: parameter
    dtype: Money
    unit: USD
    source: "TWH / TW Bulletin 25-15 §2"
    versions:
      - effective_from: 2025-10-01
        formula: "170"
  - name: snap_medical_deduction_threshold
    kind: parameter
    dtype: Money
    unit: USD
    versions:
      - effective_from: 2008-10-01
        formula: "35"
  - name: standard_deduction
    kind: derived
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    sources:
      - citation: "7 CFR 273.9(c)(1)(i)"
        url: "https://www.ecfr.gov/current/title-7/section-273.9"
    versions:
      - effective_from: 2025-10-01
        formula: |
          match household_size:
              1 => 209
              2 => 209
              3 => 209
              4 => 223
  - name: household_size
    kind: derived
    entity: Household
    dtype: Integer
    period: Month
    versions:
      - effective_from: 2025-10-01
        formula: len(member_of_household)
  - name: earned_income_total
    kind: derived
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    versions:
      - effective_from: 2025-10-01
        formula: sum(member_of_household.earned_income)
  - name: unearned_income_total
    kind: derived
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    versions:
      - effective_from: 2025-10-01
        formula: sum(member_of_household.unearned_income)
  - name: gross_income
    kind: derived
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    versions:
      - effective_from: 2025-10-01
        formula: earned_income_total + unearned_income_total
  - name: medical_deduction
    kind: derived
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    source: "7 CFR 273.9(d)(3)(x) - Texas SME election"
    versions:
      - effective_from: 2025-10-01
        formula: |
          if has_elderly_or_disabled_member:
              if total_medical_expenses > snap_medical_deduction_threshold:
                  snap_state_sme_flat_amount
              else: 0
          else: 0
  - name: snap_allotment
    kind: derived
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    versions:
      - effective_from: 2025-10-01
        formula: max(0, gross_income - medical_deduction)
"#;

    let rac = r#"
snap_state_sme_flat_amount:
    dtype: Money
    unit: USD
    source: "TWH / TW Bulletin 25-15 §2"
    from 2025-10-01: 170

snap_medical_deduction_threshold:
    dtype: Money
    unit: USD
    from 2008-10-01: 35

standard_deduction:
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    source: "7 CFR 273.9(c)(1)(i)"
    source_url: "https://www.ecfr.gov/current/title-7/section-273.9"
    from 2025-10-01:
        match household_size:
            1 => 209
            2 => 209
            3 => 209
            4 => 223

household_size:
    entity: Household
    dtype: Integer
    period: Month
    from 2025-10-01: len(member_of_household)

earned_income_total:
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    from 2025-10-01: sum(member_of_household.earned_income)

unearned_income_total:
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    from 2025-10-01: sum(member_of_household.unearned_income)

gross_income:
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    from 2025-10-01: earned_income_total + unearned_income_total

medical_deduction:
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    source: "7 CFR 273.9(d)(3)(x) - Texas SME election"
    from 2025-10-01:
        if has_elderly_or_disabled_member:
            if total_medical_expenses > snap_medical_deduction_threshold:
                snap_state_sme_flat_amount
            else: 0
        else: 0

snap_allotment:
    entity: Household
    dtype: Money
    period: Month
    unit: USD
    from 2025-10-01: max(0, gross_income - medical_deduction)
"#;

    assert_same_artifact(
        CompiledProgramArtifact::from_yaml_or_rulespec_str(rulespec).expect("RuleSpec compiles"),
        CompiledProgramArtifact::from_rac_str(rac).expect(".rac compiles"),
    );
}

#[test]
fn rulespec_matches_rac_for_date_and_relation_judgment_formulas() {
    let rulespec = r#"
format: rulespec/v1
module:
  id: uk.housing.section21.demo
rules:
  - name: minimum_notice_days
    kind: parameter
    dtype: Integer
    versions:
      - effective_from: 2015-10-01
        formula: "56"
  - name: notice_days
    kind: derived
    entity: Tenancy
    dtype: Integer
    period: Day
    versions:
      - effective_from: 2015-10-01
        formula: days_between(notice_served_date, possession_date)
  - name: recent_council_notice_count
    kind: derived
    entity: Tenancy
    dtype: Integer
    period: Day
    versions:
      - effective_from: 2015-10-01
        formula: count_where(council_notice_of_tenancy, notice_within_relevant_period)
  - name: retaliatory_eviction_bar_applies
    kind: derived
    entity: Tenancy
    dtype: Judgment
    period: Day
    versions:
      - effective_from: 2015-10-01
        formula: recent_council_notice_count > 0
  - name: section_21_notice_valid
    kind: derived
    entity: Tenancy
    dtype: Judgment
    period: Day
    source: "Housing Act 1988 s.21"
    versions:
      - effective_from: 2015-10-01
        formula: |
          notice_days >= minimum_notice_days
          and not retaliatory_eviction_bar_applies
          and not tenancy_deposit_unprotected
"#;

    let rac = r#"
minimum_notice_days:
    dtype: Integer
    from 2015-10-01: 56

notice_days:
    entity: Tenancy
    dtype: Integer
    period: Day
    from 2015-10-01: days_between(notice_served_date, possession_date)

recent_council_notice_count:
    entity: Tenancy
    dtype: Integer
    period: Day
    from 2015-10-01: count_where(council_notice_of_tenancy, notice_within_relevant_period)

retaliatory_eviction_bar_applies:
    entity: Tenancy
    dtype: Judgment
    period: Day
    from 2015-10-01: recent_council_notice_count > 0

section_21_notice_valid:
    entity: Tenancy
    dtype: Judgment
    period: Day
    source: "Housing Act 1988 s.21"
    from 2015-10-01:
        notice_days >= minimum_notice_days
        and not retaliatory_eviction_bar_applies
        and not tenancy_deposit_unprotected
"#;

    assert_same_artifact(
        CompiledProgramArtifact::from_yaml_or_rulespec_str(rulespec).expect("RuleSpec compiles"),
        CompiledProgramArtifact::from_rac_str(rac).expect(".rac compiles"),
    );
}

#[test]
fn rulespec_rejects_derived_relations_until_relation_outputs_are_modelled() {
    let err = lower_rulespec_str(
        r#"
format: rulespec/v1
rules:
  - name: eligible_member_of_household
    kind: derived_relation
    arity: 2
    versions:
      - effective_from: 2025-01-01
        formula: member_of_household
"#,
    )
    .expect_err("derived_relation is intentionally not supported yet");

    assert!(matches!(err, RuleSpecError::UnsupportedRuleKind { .. }));
}

#[test]
fn compile_rejects_rules_yaml_without_rulespec_discriminator() {
    let err = CompiledProgramArtifact::from_yaml_or_rulespec_str(
        r#"
rules:
  - name: ambiguous
    formula: "1"
"#,
    )
    .expect_err("ambiguous RuleSpec-shaped YAML must be rejected");

    assert!(matches!(err, CompileError::AmbiguousRuleSpecYaml { .. }));
}

#[test]
fn compile_program_file_to_json_accepts_rulespec_yaml() {
    let temp_root = std::env::temp_dir().join(format!(
        "axiom-rules-rulespec-compile-test-{}",
        std::process::id()
    ));
    let program_path = temp_root.join("rules.yaml");
    let artifact_path = temp_root.join("rules.compiled.json");
    std::fs::create_dir_all(&temp_root).expect("temp dir is created");
    std::fs::write(
        &program_path,
        r#"
format: rulespec/v1
rules:
  - name: flat_amount
    kind: parameter
    dtype: Money
    unit: USD
    versions:
      - effective_from: 2025-01-01
        formula: "10"
"#,
    )
    .expect("RuleSpec fixture is written");

    let artifact = compile_program_file_to_json(&program_path, &artifact_path)
        .expect("RuleSpec file compiles");

    assert!(
        artifact_path.exists(),
        "compiled artifact should be written"
    );
    assert_eq!(artifact.program.parameters.len(), 1);
    std::fs::remove_dir_all(temp_root).expect("temp dir is removed");
}
