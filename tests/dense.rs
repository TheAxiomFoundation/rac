use std::collections::HashMap;
use std::str::FromStr;

use rac::api::{ExecutionMode, ExecutionQuery, ExecutionRequest, OutputValue, execute_request};
use rac::compile::CompiledProgramArtifact;
use rac::dense::{
    DenseBatchSpec, DenseColumn, DenseCompiledProgram, DenseOutputValue, DenseRelationBatchSpec,
    DenseRelationKey,
};
use rac::spec::{
    DTypeSpec, DatasetSpec, InputRecordSpec, IntervalSpec, JudgmentOutcomeSpec, PeriodKindSpec,
    PeriodSpec, RelationRecordSpec, ScalarValueSpec,
};
use rust_decimal::Decimal;
use serde::Deserialize;

const FLAT_TAX_PROGRAM_YAML: &str = include_str!("../examples/flat_tax_program.yaml");
const FAMILY_ALLOWANCE_PROGRAM_YAML: &str = include_str!("../examples/family_allowance_program.yaml");
const SNAP_PROGRAM_YAML: &str = include_str!("../examples/snap_program.yaml");
const SNAP_CASES_YAML: &str = include_str!("../examples/snap_cases.yaml");
const CHILD_BENEFIT_PROGRAM_YAML: &str =
    include_str!("../examples/child_benefit_responsibility_program.yaml");
const CHILD_BENEFIT_CASES_YAML: &str =
    include_str!("../examples/child_benefit_responsibility_cases.yaml");
const NOTIONAL_CAPITAL_PROGRAM_YAML: &str =
    include_str!("../examples/notional_capital_program.yaml");
const UK_INCOME_TAX_PROGRAM_YAML: &str =
    include_str!("../examples/uk_income_tax_program.yaml");
const UK_INCOME_TAX_CASES_YAML: &str =
    include_str!("../examples/uk_income_tax_cases.yaml");
const UC_PROGRAM_YAML: &str = include_str!("../examples/universal_credit_program.yaml");
const UC_CASES_YAML: &str = include_str!("../examples/universal_credit_cases.yaml");
const STATE_PENSION_PROGRAM_YAML: &str =
    include_str!("../examples/state_pension_transitional_program.yaml");
const STATE_PENSION_CASES_YAML: &str =
    include_str!("../examples/state_pension_transitional_cases.yaml");
const CT_MARGINAL_RELIEF_PROGRAM_YAML: &str =
    include_str!("../examples/ct_marginal_relief_program.yaml");
const CT_MARGINAL_RELIEF_CASES_YAML: &str =
    include_str!("../examples/ct_marginal_relief_cases.yaml");

#[test]
fn dense_flat_tax_matches_explain_mode() {
    let period = month_period();
    let artifact =
        CompiledProgramArtifact::from_yaml_str(FLAT_TAX_PROGRAM_YAML).expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("Person"))
        .expect("dense compilation succeeds");

    let people = [
        ("person-1", decimal("800")),
        ("person-2", decimal("1500")),
        ("person-3", decimal("4000")),
    ];

    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset: DatasetSpec {
            inputs: people
                .iter()
                .map(|(person_id, income)| InputRecordSpec {
                    name: "income".to_string(),
                    entity: "Person".to_string(),
                    entity_id: (*person_id).to_string(),
                    interval: period_interval(&period),
                    value: ScalarValueSpec::Decimal {
                        value: income.normalize().to_string(),
                    },
                })
                .collect(),
            relations: Vec::new(),
        },
        queries: people
            .iter()
            .map(|(person_id, _)| ExecutionQuery {
                entity_id: (*person_id).to_string(),
                period: period.clone(),
                outputs: vec![
                    "gross_income".to_string(),
                    "taxable_income".to_string(),
                    "high_income".to_string(),
                    "income_tax".to_string(),
                    "net_income".to_string(),
                ],
            })
            .collect(),
    })
    .expect("explain execution succeeds");

    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            DenseBatchSpec {
                row_count: people.len(),
                inputs: HashMap::from([(
                    "income".to_string(),
                    DenseColumn::Decimal(people.iter().map(|(_, income)| *income).collect()),
                )]),
                relations: HashMap::new(),
            },
            &[
                "gross_income".to_string(),
                "taxable_income".to_string(),
                "high_income".to_string(),
                "income_tax".to_string(),
                "net_income".to_string(),
            ],
        )
        .expect("dense execution succeeds");

    for row in 0..people.len() {
        compare_scalar(
            explain.results[row]
                .outputs
                .get("gross_income")
                .expect("gross income output"),
            dense_result.outputs.get("gross_income").expect("dense gross income"),
            row,
        );
        compare_scalar(
            explain.results[row]
                .outputs
                .get("taxable_income")
                .expect("taxable income output"),
            dense_result
                .outputs
                .get("taxable_income")
                .expect("dense taxable income"),
            row,
        );
        compare_judgment(
            explain.results[row]
                .outputs
                .get("high_income")
                .expect("high income output"),
            dense_result
                .outputs
                .get("high_income")
                .expect("dense high income"),
            row,
        );
        compare_scalar(
            explain.results[row]
                .outputs
                .get("income_tax")
                .expect("income tax output"),
            dense_result.outputs.get("income_tax").expect("dense income tax"),
            row,
        );
        compare_scalar(
            explain.results[row]
                .outputs
                .get("net_income")
                .expect("net income output"),
            dense_result.outputs.get("net_income").expect("dense net income"),
            row,
        );
    }
}

#[test]
fn dense_family_allowance_matches_explain_mode() {
    let period = month_period();
    let artifact = CompiledProgramArtifact::from_yaml_str(FAMILY_ALLOWANCE_PROGRAM_YAML)
        .expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("Household"))
        .expect("dense compilation succeeds");

    let households = [
        ("household-1", vec![("person-1", decimal("1200"))]),
        (
            "household-2",
            vec![("person-2", decimal("900")), ("person-3", decimal("700"))],
        ),
        (
            "household-3",
            vec![
                ("person-4", decimal("1800")),
                ("person-5", decimal("1600")),
                ("person-6", decimal("1500")),
            ],
        ),
    ];

    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset: family_allowance_dataset(&period, &households),
        queries: households
            .iter()
            .map(|(household_id, _)| ExecutionQuery {
                entity_id: (*household_id).to_string(),
                period: period.clone(),
                outputs: vec![
                    "household_size".to_string(),
                    "earned_income_total".to_string(),
                    "qualifies".to_string(),
                    "monthly_allowance".to_string(),
                ],
            })
            .collect(),
    })
    .expect("explain execution succeeds");

    let mut offsets = vec![0_usize];
    let mut earned_income = Vec::new();
    for (_, members) in &households {
        for (_, income) in members {
            earned_income.push(*income);
        }
        offsets.push(earned_income.len());
    }

    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            DenseBatchSpec {
                row_count: households.len(),
                inputs: HashMap::new(),
                relations: HashMap::from([(
                    DenseRelationKey {
                        name: "member_of_household".to_string(),
                        current_slot: 1,
                        related_slot: 0,
                    },
                    DenseRelationBatchSpec {
                        offsets,
                        inputs: HashMap::from([(
                            "earned_income".to_string(),
                            DenseColumn::Decimal(earned_income),
                        )]),
                    },
                )]),
            },
            &[
                "household_size".to_string(),
                "earned_income_total".to_string(),
                "qualifies".to_string(),
                "monthly_allowance".to_string(),
            ],
        )
        .expect("dense execution succeeds");

    for row in 0..households.len() {
        compare_scalar(
            explain.results[row]
                .outputs
                .get("household_size")
                .expect("household size output"),
            dense_result
                .outputs
                .get("household_size")
                .expect("dense household size"),
            row,
        );
        compare_scalar(
            explain.results[row]
                .outputs
                .get("earned_income_total")
                .expect("earned income total output"),
            dense_result
                .outputs
                .get("earned_income_total")
                .expect("dense earned income total"),
            row,
        );
        compare_judgment(
            explain.results[row]
                .outputs
                .get("qualifies")
                .expect("qualifies output"),
            dense_result.outputs.get("qualifies").expect("dense qualifies"),
            row,
        );
        compare_scalar(
            explain.results[row]
                .outputs
                .get("monthly_allowance")
                .expect("monthly allowance output"),
            dense_result
                .outputs
                .get("monthly_allowance")
                .expect("dense monthly allowance"),
            row,
        );
    }
}

#[test]
fn dense_snap_matches_explain_mode() {
    let artifact =
        CompiledProgramArtifact::from_yaml_str(SNAP_PROGRAM_YAML).expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("Household"))
        .expect("dense compilation succeeds");
    let case_file: SnapCaseFile = serde_yaml::from_str(SNAP_CASES_YAML).expect("fixture parses");
    let period = case_file.cases[0].period.clone();
    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset: snap_dataset_for_cases(&case_file.cases),
        queries: case_file.cases.iter().map(snap_query).collect(),
    })
    .expect("explain execution succeeds");

    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            snap_dense_batch(&case_file.cases),
            &[
                "household_size".to_string(),
                "gross_income".to_string(),
                "net_income".to_string(),
                "passes_gross_income_test".to_string(),
                "passes_net_income_test".to_string(),
                "snap_eligible".to_string(),
                "snap_allotment".to_string(),
            ],
        )
        .expect("dense execution succeeds");

    for row in 0..case_file.cases.len() {
        compare_scalar(
            explain.results[row]
                .outputs
                .get("household_size")
                .expect("household size output"),
            dense_result
                .outputs
                .get("household_size")
                .expect("dense household size"),
            row,
        );
        compare_scalar(
            explain.results[row]
                .outputs
                .get("gross_income")
                .expect("gross income output"),
            dense_result.outputs.get("gross_income").expect("dense gross income"),
            row,
        );
        compare_scalar(
            explain.results[row]
                .outputs
                .get("net_income")
                .expect("net income output"),
            dense_result.outputs.get("net_income").expect("dense net income"),
            row,
        );
        compare_judgment(
            explain.results[row]
                .outputs
                .get("passes_gross_income_test")
                .expect("gross test output"),
            dense_result
                .outputs
                .get("passes_gross_income_test")
                .expect("dense gross test"),
            row,
        );
        compare_judgment(
            explain.results[row]
                .outputs
                .get("passes_net_income_test")
                .expect("net test output"),
            dense_result
                .outputs
                .get("passes_net_income_test")
                .expect("dense net test"),
            row,
        );
        compare_judgment(
            explain.results[row]
                .outputs
                .get("snap_eligible")
                .expect("eligibility output"),
            dense_result
                .outputs
                .get("snap_eligible")
                .expect("dense eligibility"),
            row,
        );
        compare_scalar(
            explain.results[row]
                .outputs
                .get("snap_allotment")
                .expect("snap allotment output"),
            dense_result
                .outputs
                .get("snap_allotment")
                .expect("dense allotment"),
            row,
        );
    }
}

#[test]
fn dense_child_benefit_responsibility_matches_explain_mode() {
    let artifact = CompiledProgramArtifact::from_yaml_str(CHILD_BENEFIT_PROGRAM_YAML)
        .expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("Child"))
        .expect("dense compilation succeeds");
    let case_file: ChildBenefitCaseFile =
        serde_yaml::from_str(CHILD_BENEFIT_CASES_YAML).expect("fixture parses");
    let period = case_file.cases[0].period.clone();

    let outputs = [
        "cb_recipient_count".to_string(),
        "has_cb_recipient".to_string(),
        "needs_fallback".to_string(),
        "sole_claim_fallback".to_string(),
        "usual_residence_fallback".to_string(),
        "responsible_person".to_string(),
    ];

    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset: child_benefit_dataset(&case_file.cases),
        queries: case_file
            .cases
            .iter()
            .map(|case| ExecutionQuery {
                entity_id: case.child_id.clone(),
                period: case.period.clone(),
                outputs: outputs.to_vec(),
            })
            .collect(),
    })
    .expect("explain execution succeeds");

    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            child_benefit_dense_batch(&case_file.cases),
            &outputs,
        )
        .expect("dense execution succeeds");

    for (row, case) in case_file.cases.iter().enumerate() {
        compare_scalar(
            explain.results[row]
                .outputs
                .get("cb_recipient_count")
                .expect("cb recipient count output"),
            dense_result
                .outputs
                .get("cb_recipient_count")
                .expect("dense cb recipient count"),
            row,
        );
        for judgment in [
            "has_cb_recipient",
            "needs_fallback",
            "sole_claim_fallback",
            "usual_residence_fallback",
        ] {
            compare_judgment(
                explain.results[row]
                    .outputs
                    .get(judgment)
                    .unwrap_or_else(|| panic!("{judgment} output")),
                dense_result
                    .outputs
                    .get(judgment)
                    .unwrap_or_else(|| panic!("dense {judgment}")),
                row,
            );
        }
        compare_scalar(
            explain.results[row]
                .outputs
                .get("responsible_person")
                .expect("responsible person output"),
            dense_result
                .outputs
                .get("responsible_person")
                .expect("dense responsible person"),
            row,
        );
        let _ = case; // silence unused binding when asserts match
    }
}

#[test]
fn dense_uk_income_tax_matches_explain_mode() {
    let artifact = CompiledProgramArtifact::from_yaml_str(UK_INCOME_TAX_PROGRAM_YAML)
        .expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("Taxpayer"))
        .expect("dense compilation succeeds");
    let case_file: UkIncomeTaxCaseFile =
        serde_yaml::from_str(UK_INCOME_TAX_CASES_YAML).expect("fixture parses");
    let period = case_file.cases[0].period.clone();
    let outputs = [
        "gross_income".to_string(),
        "personal_allowance".to_string(),
        "taxable_income".to_string(),
        "income_tax".to_string(),
        "net_income".to_string(),
    ];

    let mut dataset = DatasetSpec::default();
    for case in &case_file.cases {
        let interval = period_interval(&case.period);
        for (name, value) in [
            ("employment_income", &case.employment_income),
            ("self_employment_income", &case.self_employment_income),
            ("pension_income", &case.pension_income),
            ("property_income", &case.property_income),
            ("savings_income", &case.savings_income),
        ] {
            dataset.inputs.push(InputRecordSpec {
                name: name.to_string(),
                entity: "Taxpayer".to_string(),
                entity_id: case.taxpayer_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: value.clone(),
                },
            });
        }
    }

    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset,
        queries: case_file
            .cases
            .iter()
            .map(|case| ExecutionQuery {
                entity_id: case.taxpayer_id.clone(),
                period: case.period.clone(),
                outputs: outputs.to_vec(),
            })
            .collect(),
    })
    .expect("explain execution succeeds");

    let mut employment = Vec::with_capacity(case_file.cases.len());
    let mut self_employment = Vec::with_capacity(case_file.cases.len());
    let mut pension = Vec::with_capacity(case_file.cases.len());
    let mut property = Vec::with_capacity(case_file.cases.len());
    let mut savings = Vec::with_capacity(case_file.cases.len());
    for case in &case_file.cases {
        employment.push(decimal(&case.employment_income));
        self_employment.push(decimal(&case.self_employment_income));
        pension.push(decimal(&case.pension_income));
        property.push(decimal(&case.property_income));
        savings.push(decimal(&case.savings_income));
    }
    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            DenseBatchSpec {
                row_count: case_file.cases.len(),
                inputs: HashMap::from([
                    ("employment_income".to_string(), DenseColumn::Decimal(employment)),
                    (
                        "self_employment_income".to_string(),
                        DenseColumn::Decimal(self_employment),
                    ),
                    ("pension_income".to_string(), DenseColumn::Decimal(pension)),
                    ("property_income".to_string(), DenseColumn::Decimal(property)),
                    ("savings_income".to_string(), DenseColumn::Decimal(savings)),
                ]),
                relations: HashMap::new(),
            },
            &outputs,
        )
        .expect("dense execution succeeds");

    for row in 0..case_file.cases.len() {
        for output in &outputs {
            compare_scalar(
                explain.results[row]
                    .outputs
                    .get(output)
                    .unwrap_or_else(|| panic!("{output} output for row {row}")),
                dense_result
                    .outputs
                    .get(output)
                    .unwrap_or_else(|| panic!("dense {output}")),
                row,
            );
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
struct UkIncomeTaxCaseFile {
    cases: Vec<UkIncomeTaxCase>,
}

#[derive(Clone, Debug, Deserialize)]
struct UkIncomeTaxCase {
    taxpayer_id: String,
    period: PeriodSpec,
    employment_income: String,
    self_employment_income: String,
    pension_income: String,
    property_income: String,
    savings_income: String,
}

#[test]
fn dense_ct_marginal_relief_matches_explain_mode() {
    let artifact = CompiledProgramArtifact::from_yaml_str(CT_MARGINAL_RELIEF_PROGRAM_YAML)
        .expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("Company"))
        .expect("dense compilation succeeds");
    let case_file: CtMarginalReliefCaseFile =
        serde_yaml::from_str(CT_MARGINAL_RELIEF_CASES_YAML).expect("fixture parses");
    let period = case_file.cases[0].period.clone();

    let outputs = [
        "ap_days".to_string(),
        "num_associates".to_string(),
        "associates_divisor".to_string(),
        "lower_limit_effective".to_string(),
        "upper_limit_effective".to_string(),
        "within_marginal_band".to_string(),
        "eligible_for_marginal_relief".to_string(),
        "marginal_relief".to_string(),
        "gross_corporation_tax".to_string(),
        "corporation_tax_after_relief".to_string(),
    ];

    let mut dataset = DatasetSpec::default();
    for case in &case_file.cases {
        let interval = period_interval(&case.period);
        dataset.inputs.extend([
            InputRecordSpec {
                name: "uk_resident".to_string(),
                entity: "Company".to_string(),
                entity_id: case.company_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool {
                    value: case.uk_resident,
                },
            },
            InputRecordSpec {
                name: "close_investment_holding".to_string(),
                entity: "Company".to_string(),
                entity_id: case.company_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool {
                    value: case.close_investment_holding,
                },
            },
            InputRecordSpec {
                name: "augmented_profits".to_string(),
                entity: "Company".to_string(),
                entity_id: case.company_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.augmented_profits.clone(),
                },
            },
            InputRecordSpec {
                name: "taxable_total_profits".to_string(),
                entity: "Company".to_string(),
                entity_id: case.company_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.taxable_total_profits.clone(),
                },
            },
            InputRecordSpec {
                name: "ring_fence_profits".to_string(),
                entity: "Company".to_string(),
                entity_id: case.company_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.ring_fence_profits.clone(),
                },
            },
        ]);
        for associate in &case.associates {
            dataset.relations.push(RelationRecordSpec {
                name: "associate_of".to_string(),
                tuple: vec![associate.clone(), case.company_id.clone()],
                interval: interval.clone(),
            });
        }
    }

    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset,
        queries: case_file
            .cases
            .iter()
            .map(|case| ExecutionQuery {
                entity_id: case.company_id.clone(),
                period: case.period.clone(),
                outputs: outputs.to_vec(),
            })
            .collect(),
    })
    .expect("explain execution succeeds");

    let mut uk_resident = Vec::with_capacity(case_file.cases.len());
    let mut close_investment_holding = Vec::with_capacity(case_file.cases.len());
    let mut augmented_profits = Vec::with_capacity(case_file.cases.len());
    let mut taxable_total_profits = Vec::with_capacity(case_file.cases.len());
    let mut ring_fence_profits = Vec::with_capacity(case_file.cases.len());
    let mut offsets = Vec::with_capacity(case_file.cases.len() + 1);
    offsets.push(0_usize);
    let mut cursor = 0_usize;
    for case in &case_file.cases {
        uk_resident.push(case.uk_resident);
        close_investment_holding.push(case.close_investment_holding);
        augmented_profits.push(decimal(&case.augmented_profits));
        taxable_total_profits.push(decimal(&case.taxable_total_profits));
        ring_fence_profits.push(decimal(&case.ring_fence_profits));
        cursor += case.associates.len();
        offsets.push(cursor);
    }

    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            DenseBatchSpec {
                row_count: case_file.cases.len(),
                inputs: HashMap::from([
                    ("uk_resident".to_string(), DenseColumn::Bool(uk_resident)),
                    (
                        "close_investment_holding".to_string(),
                        DenseColumn::Bool(close_investment_holding),
                    ),
                    (
                        "augmented_profits".to_string(),
                        DenseColumn::Decimal(augmented_profits),
                    ),
                    (
                        "taxable_total_profits".to_string(),
                        DenseColumn::Decimal(taxable_total_profits),
                    ),
                    (
                        "ring_fence_profits".to_string(),
                        DenseColumn::Decimal(ring_fence_profits),
                    ),
                ]),
                relations: HashMap::from([(
                    DenseRelationKey {
                        name: "associate_of".to_string(),
                        current_slot: 1,
                        related_slot: 0,
                    },
                    DenseRelationBatchSpec {
                        offsets,
                        inputs: HashMap::new(),
                    },
                )]),
            },
            &outputs,
        )
        .expect("dense execution succeeds");

    for row in 0..case_file.cases.len() {
        for output in &outputs {
            let explain_value = explain.results[row]
                .outputs
                .get(output)
                .unwrap_or_else(|| panic!("{output} output for row {row}"));
            let dense_value = dense_result
                .outputs
                .get(output)
                .unwrap_or_else(|| panic!("dense {output}"));
            match explain_value {
                OutputValue::Scalar { .. } => compare_scalar(explain_value, dense_value, row),
                OutputValue::Judgment { .. } => {
                    compare_judgment(explain_value, dense_value, row)
                }
            }
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
struct CtMarginalReliefCaseFile {
    cases: Vec<CtMarginalReliefCase>,
}

#[derive(Clone, Debug, Deserialize)]
struct CtMarginalReliefCase {
    company_id: String,
    period: PeriodSpec,
    uk_resident: bool,
    close_investment_holding: bool,
    augmented_profits: String,
    taxable_total_profits: String,
    ring_fence_profits: String,
    associates: Vec<String>,
}

#[test]
fn dense_state_pension_transitional_matches_explain_mode() {
    let artifact = CompiledProgramArtifact::from_yaml_str(STATE_PENSION_PROGRAM_YAML)
        .expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("Person"))
        .expect("dense compilation succeeds");
    let case_file: StatePensionCaseFile =
        serde_yaml::from_str(STATE_PENSION_CASES_YAML).expect("fixture parses");
    let period = case_file.cases[0].period.clone();

    let outputs = [
        "pre_commencement_qy_count".to_string(),
        "post_commencement_qy_count".to_string(),
        "total_qy_count".to_string(),
        "reached_pensionable_age".to_string(),
        "meets_minimum_qy".to_string(),
        "has_any_pre_commencement_year".to_string(),
        "entitled_to_transitional_rate".to_string(),
    ];

    let mut dataset = DatasetSpec::default();
    for case in &case_file.cases {
        let interval = period_interval(&case.period);
        dataset.inputs.extend([
            InputRecordSpec {
                name: "current_age_years".to_string(),
                entity: "Person".to_string(),
                entity_id: case.person_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Integer {
                    value: case.current_age_years,
                },
            },
            InputRecordSpec {
                name: "pensionable_age_years".to_string(),
                entity: "Person".to_string(),
                entity_id: case.person_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Integer {
                    value: case.pensionable_age_years,
                },
            },
        ]);
        for qy in &case.qualifying_years {
            dataset.inputs.extend([
                InputRecordSpec {
                    name: "year_start".to_string(),
                    entity: "QualifyingYear".to_string(),
                    entity_id: qy.id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Date {
                        value: chrono::NaiveDate::parse_from_str(&qy.year_start, "%Y-%m-%d")
                            .expect("valid date"),
                    },
                },
                InputRecordSpec {
                    name: "is_qualifying".to_string(),
                    entity: "QualifyingYear".to_string(),
                    entity_id: qy.id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Bool {
                        value: qy.is_qualifying,
                    },
                },
                InputRecordSpec {
                    name: "is_reckonable_1979".to_string(),
                    entity: "QualifyingYear".to_string(),
                    entity_id: qy.id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Bool {
                        value: qy.is_reckonable_1979,
                    },
                },
            ]);
            dataset.relations.push(RelationRecordSpec {
                name: "qualifying_year_of".to_string(),
                tuple: vec![qy.id.clone(), case.person_id.clone()],
                interval: interval.clone(),
            });
        }
    }

    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset,
        queries: case_file
            .cases
            .iter()
            .map(|case| ExecutionQuery {
                entity_id: case.person_id.clone(),
                period: case.period.clone(),
                outputs: outputs.to_vec(),
            })
            .collect(),
    })
    .expect("explain execution succeeds");

    // Build dense batch.
    let mut current_age = Vec::with_capacity(case_file.cases.len());
    let mut pensionable_age = Vec::with_capacity(case_file.cases.len());
    let mut qy_offsets = Vec::with_capacity(case_file.cases.len() + 1);
    qy_offsets.push(0_usize);
    let mut cursor = 0_usize;
    let mut year_start: Vec<chrono::NaiveDate> = Vec::new();
    let mut is_qualifying: Vec<bool> = Vec::new();
    let mut is_reckonable_1979: Vec<bool> = Vec::new();
    for case in &case_file.cases {
        current_age.push(case.current_age_years);
        pensionable_age.push(case.pensionable_age_years);
        for qy in &case.qualifying_years {
            year_start.push(
                chrono::NaiveDate::parse_from_str(&qy.year_start, "%Y-%m-%d")
                    .expect("valid date"),
            );
            is_qualifying.push(qy.is_qualifying);
            is_reckonable_1979.push(qy.is_reckonable_1979);
            cursor += 1;
        }
        qy_offsets.push(cursor);
    }

    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            DenseBatchSpec {
                row_count: case_file.cases.len(),
                inputs: HashMap::from([
                    (
                        "current_age_years".to_string(),
                        DenseColumn::Integer(current_age),
                    ),
                    (
                        "pensionable_age_years".to_string(),
                        DenseColumn::Integer(pensionable_age),
                    ),
                ]),
                relations: HashMap::from([(
                    DenseRelationKey {
                        name: "qualifying_year_of".to_string(),
                        current_slot: 1,
                        related_slot: 0,
                    },
                    DenseRelationBatchSpec {
                        offsets: qy_offsets,
                        inputs: HashMap::from([
                            (
                                "year_start".to_string(),
                                DenseColumn::Date(year_start),
                            ),
                            (
                                "is_qualifying".to_string(),
                                DenseColumn::Bool(is_qualifying),
                            ),
                            (
                                "is_reckonable_1979".to_string(),
                                DenseColumn::Bool(is_reckonable_1979),
                            ),
                        ]),
                    },
                )]),
            },
            &outputs,
        )
        .expect("dense execution succeeds");

    for row in 0..case_file.cases.len() {
        for output in &outputs {
            let explain_value = explain.results[row]
                .outputs
                .get(output)
                .unwrap_or_else(|| panic!("{output} output for row {row}"));
            let dense_value = dense_result
                .outputs
                .get(output)
                .unwrap_or_else(|| panic!("dense {output}"));
            match explain_value {
                OutputValue::Scalar { .. } => compare_scalar(explain_value, dense_value, row),
                OutputValue::Judgment { .. } => {
                    compare_judgment(explain_value, dense_value, row)
                }
            }
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
struct StatePensionCaseFile {
    cases: Vec<StatePensionCase>,
}

#[derive(Clone, Debug, Deserialize)]
struct StatePensionCase {
    person_id: String,
    period: PeriodSpec,
    current_age_years: i64,
    pensionable_age_years: i64,
    qualifying_years: Vec<StatePensionYear>,
}

#[derive(Clone, Debug, Deserialize)]
struct StatePensionYear {
    id: String,
    year_start: String,
    is_qualifying: bool,
    is_reckonable_1979: bool,
}

#[test]
fn dense_universal_credit_matches_explain_mode() {
    let artifact = CompiledProgramArtifact::from_yaml_str(UC_PROGRAM_YAML)
        .expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("BenefitUnit"))
        .expect("dense compilation succeeds");
    let case_file: UcCaseFile =
        serde_yaml::from_str(UC_CASES_YAML).expect("fixture parses");
    let period = case_file.cases[0].period.clone();

    let outputs = [
        "standard_allowance".to_string(),
        "child_element_total".to_string(),
        "disabled_child_element_total".to_string(),
        "lcwra_element".to_string(),
        "carer_element".to_string(),
        "housing_element".to_string(),
        "max_uc".to_string(),
        "work_allowance_amount".to_string(),
        "earnings_deduction".to_string(),
        "tariff_income".to_string(),
        "over_capital_limit".to_string(),
        "uc_award".to_string(),
    ];

    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset: uc_dataset(&case_file.cases),
        queries: case_file
            .cases
            .iter()
            .map(|case| ExecutionQuery {
                entity_id: case.benefit_unit_id.clone(),
                period: case.period.clone(),
                outputs: outputs.to_vec(),
            })
            .collect(),
    })
    .expect("explain execution succeeds");

    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            uc_dense_batch(&case_file.cases),
            &outputs,
        )
        .expect("dense execution succeeds");

    for row in 0..case_file.cases.len() {
        for output in &outputs {
            let explain_value = explain.results[row]
                .outputs
                .get(output)
                .unwrap_or_else(|| panic!("{output} output for row {row}"));
            let dense_value = dense_result
                .outputs
                .get(output)
                .unwrap_or_else(|| panic!("dense {output}"));
            match explain_value {
                OutputValue::Scalar { .. } => compare_scalar(explain_value, dense_value, row),
                OutputValue::Judgment { .. } => {
                    compare_judgment(explain_value, dense_value, row)
                }
            }
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
struct UcCaseFile {
    cases: Vec<UcCase>,
}

#[derive(Clone, Debug, Deserialize)]
struct UcCase {
    benefit_unit_id: String,
    period: PeriodSpec,
    is_couple: bool,
    has_housing_costs: bool,
    eligible_housing_costs: String,
    non_dep_deductions_total: String,
    earned_income_monthly: String,
    unearned_income_monthly: String,
    capital_total: String,
    adults: Vec<UcAdult>,
    children: Vec<UcChild>,
}

#[derive(Clone, Debug, Deserialize)]
struct UcAdult {
    id: String,
    age_25_or_over: bool,
    has_lcwra: bool,
    is_carer: bool,
}

#[derive(Clone, Debug, Deserialize)]
struct UcChild {
    id: String,
    qualifies_for_child_element: bool,
    disability_level: String,
}

fn uc_dataset(cases: &[UcCase]) -> DatasetSpec {
    let mut dataset = DatasetSpec::default();
    for case in cases {
        let interval = period_interval(&case.period);
        dataset.inputs.extend([
            InputRecordSpec {
                name: "is_couple".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: case.benefit_unit_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool {
                    value: case.is_couple,
                },
            },
            InputRecordSpec {
                name: "has_housing_costs".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: case.benefit_unit_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool {
                    value: case.has_housing_costs,
                },
            },
            InputRecordSpec {
                name: "eligible_housing_costs".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: case.benefit_unit_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.eligible_housing_costs.clone(),
                },
            },
            InputRecordSpec {
                name: "non_dep_deductions_total".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: case.benefit_unit_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.non_dep_deductions_total.clone(),
                },
            },
            InputRecordSpec {
                name: "earned_income_monthly".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: case.benefit_unit_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.earned_income_monthly.clone(),
                },
            },
            InputRecordSpec {
                name: "unearned_income_monthly".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: case.benefit_unit_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.unearned_income_monthly.clone(),
                },
            },
            InputRecordSpec {
                name: "capital_total".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: case.benefit_unit_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.capital_total.clone(),
                },
            },
        ]);
        for adult in &case.adults {
            dataset.inputs.extend([
                InputRecordSpec {
                    name: "age_25_or_over".to_string(),
                    entity: "Adult".to_string(),
                    entity_id: adult.id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Bool {
                        value: adult.age_25_or_over,
                    },
                },
                InputRecordSpec {
                    name: "has_lcwra".to_string(),
                    entity: "Adult".to_string(),
                    entity_id: adult.id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Bool {
                        value: adult.has_lcwra,
                    },
                },
                InputRecordSpec {
                    name: "is_carer".to_string(),
                    entity: "Adult".to_string(),
                    entity_id: adult.id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Bool {
                        value: adult.is_carer,
                    },
                },
            ]);
            dataset.relations.push(RelationRecordSpec {
                name: "adult_of_benefit_unit".to_string(),
                tuple: vec![adult.id.clone(), case.benefit_unit_id.clone()],
                interval: interval.clone(),
            });
        }
        for child in &case.children {
            dataset.inputs.extend([
                InputRecordSpec {
                    name: "qualifies_for_child_element".to_string(),
                    entity: "Child".to_string(),
                    entity_id: child.id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Bool {
                        value: child.qualifies_for_child_element,
                    },
                },
                InputRecordSpec {
                    name: "disability_level".to_string(),
                    entity: "Child".to_string(),
                    entity_id: child.id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Text {
                        value: child.disability_level.clone(),
                    },
                },
            ]);
            dataset.relations.push(RelationRecordSpec {
                name: "child_of_benefit_unit".to_string(),
                tuple: vec![child.id.clone(), case.benefit_unit_id.clone()],
                interval: interval.clone(),
            });
        }
    }
    dataset
}

fn uc_dense_batch(cases: &[UcCase]) -> DenseBatchSpec {
    let mut is_couple = Vec::with_capacity(cases.len());
    let mut has_housing_costs = Vec::with_capacity(cases.len());
    let mut eligible_housing_costs = Vec::with_capacity(cases.len());
    let mut non_dep_deductions_total = Vec::with_capacity(cases.len());
    let mut earned_income_monthly = Vec::with_capacity(cases.len());
    let mut unearned_income_monthly = Vec::with_capacity(cases.len());
    let mut capital_total = Vec::with_capacity(cases.len());

    let mut adult_offsets = Vec::with_capacity(cases.len() + 1);
    adult_offsets.push(0_usize);
    let mut adult_cursor = 0_usize;
    let mut adult_age_25_or_over: Vec<bool> = Vec::new();
    let mut adult_has_lcwra: Vec<bool> = Vec::new();
    let mut adult_is_carer: Vec<bool> = Vec::new();

    let mut child_offsets = Vec::with_capacity(cases.len() + 1);
    child_offsets.push(0_usize);
    let mut child_cursor = 0_usize;
    let mut child_qualifies: Vec<bool> = Vec::new();
    let mut child_disability: Vec<String> = Vec::new();

    for case in cases {
        is_couple.push(case.is_couple);
        has_housing_costs.push(case.has_housing_costs);
        eligible_housing_costs.push(decimal(&case.eligible_housing_costs));
        non_dep_deductions_total.push(decimal(&case.non_dep_deductions_total));
        earned_income_monthly.push(decimal(&case.earned_income_monthly));
        unearned_income_monthly.push(decimal(&case.unearned_income_monthly));
        capital_total.push(decimal(&case.capital_total));

        for adult in &case.adults {
            adult_age_25_or_over.push(adult.age_25_or_over);
            adult_has_lcwra.push(adult.has_lcwra);
            adult_is_carer.push(adult.is_carer);
            adult_cursor += 1;
        }
        adult_offsets.push(adult_cursor);

        for child in &case.children {
            child_qualifies.push(child.qualifies_for_child_element);
            child_disability.push(child.disability_level.clone());
            child_cursor += 1;
        }
        child_offsets.push(child_cursor);
    }

    DenseBatchSpec {
        row_count: cases.len(),
        inputs: HashMap::from([
            ("is_couple".to_string(), DenseColumn::Bool(is_couple)),
            (
                "has_housing_costs".to_string(),
                DenseColumn::Bool(has_housing_costs),
            ),
            (
                "eligible_housing_costs".to_string(),
                DenseColumn::Decimal(eligible_housing_costs),
            ),
            (
                "non_dep_deductions_total".to_string(),
                DenseColumn::Decimal(non_dep_deductions_total),
            ),
            (
                "earned_income_monthly".to_string(),
                DenseColumn::Decimal(earned_income_monthly),
            ),
            (
                "unearned_income_monthly".to_string(),
                DenseColumn::Decimal(unearned_income_monthly),
            ),
            (
                "capital_total".to_string(),
                DenseColumn::Decimal(capital_total),
            ),
        ]),
        relations: HashMap::from([
            (
                DenseRelationKey {
                    name: "adult_of_benefit_unit".to_string(),
                    current_slot: 1,
                    related_slot: 0,
                },
                DenseRelationBatchSpec {
                    offsets: adult_offsets,
                    inputs: HashMap::from([
                        (
                            "age_25_or_over".to_string(),
                            DenseColumn::Bool(adult_age_25_or_over),
                        ),
                        (
                            "has_lcwra".to_string(),
                            DenseColumn::Bool(adult_has_lcwra),
                        ),
                        (
                            "is_carer".to_string(),
                            DenseColumn::Bool(adult_is_carer),
                        ),
                    ]),
                },
            ),
            (
                DenseRelationKey {
                    name: "child_of_benefit_unit".to_string(),
                    current_slot: 1,
                    related_slot: 0,
                },
                DenseRelationBatchSpec {
                    offsets: child_offsets,
                    inputs: HashMap::from([
                        (
                            "qualifies_for_child_element".to_string(),
                            DenseColumn::Bool(child_qualifies),
                        ),
                        (
                            "disability_level".to_string(),
                            DenseColumn::Text(child_disability),
                        ),
                    ]),
                },
            ),
        ]),
    }
}

#[test]
fn dense_date_add_days_matches_explain_mode() {
    use rac::spec::{
        DerivedSemanticsSpec, DerivedSpec, JudgmentExprSpec, ProgramSpec,
        ScalarExprSpec,
    };

    let mut program = ProgramSpec::default();
    program.derived.push(DerivedSpec {
        name: "relevant_week_start".to_string(),
        entity: "PartWeek".to_string(),
        dtype: DTypeSpec::Date,
        unit: None,
        source: None,
        source_url: None,
        semantics: DerivedSemanticsSpec::Scalar {
            expr: ScalarExprSpec::DateAddDays {
                date: Box::new(ScalarExprSpec::Input {
                    name: "part_week_end".to_string(),
                }),
                days: Box::new(ScalarExprSpec::Literal {
                    value: ScalarValueSpec::Integer { value: -6 },
                }),
            },
        },
    });
    program.derived.push(DerivedSpec {
        name: "relevant_week_ends_on_end".to_string(),
        entity: "PartWeek".to_string(),
        dtype: DTypeSpec::Judgment,
        unit: None,
        source: None,
        source_url: None,
        semantics: DerivedSemanticsSpec::Judgment {
            expr: JudgmentExprSpec::Comparison {
                left: Box::new(ScalarExprSpec::Derived {
                    name: "relevant_week_start".to_string(),
                }),
                op: rac::spec::ComparisonOpSpec::Lt,
                right: Box::new(ScalarExprSpec::Input {
                    name: "part_week_end".to_string(),
                }),
            },
        },
    });

    let artifact = CompiledProgramArtifact::compile(program).expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("PartWeek"))
        .expect("dense compilation succeeds");

    let period = PeriodSpec {
        kind: PeriodKindSpec::BenefitWeek,
        start: chrono::NaiveDate::from_ymd_opt(2026, 1, 5).expect("date"),
        end: chrono::NaiveDate::from_ymd_opt(2026, 1, 11).expect("date"),
    };
    let interval = period_interval(&period);
    let part_weeks = [
        ("pw-1", chrono::NaiveDate::from_ymd_opt(2026, 1, 8).expect("date")),
        ("pw-2", chrono::NaiveDate::from_ymd_opt(2026, 1, 11).expect("date")),
        ("pw-3", chrono::NaiveDate::from_ymd_opt(2026, 2, 1).expect("date")),
    ];

    let mut dataset = DatasetSpec::default();
    for (id, end_date) in &part_weeks {
        dataset.inputs.push(InputRecordSpec {
            name: "part_week_end".to_string(),
            entity: "PartWeek".to_string(),
            entity_id: id.to_string(),
            interval: interval.clone(),
            value: ScalarValueSpec::Date { value: *end_date },
        });
    }

    let outputs = [
        "relevant_week_start".to_string(),
        "relevant_week_ends_on_end".to_string(),
    ];
    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset,
        queries: part_weeks
            .iter()
            .map(|(id, _)| ExecutionQuery {
                entity_id: id.to_string(),
                period: period.clone(),
                outputs: outputs.to_vec(),
            })
            .collect(),
    })
    .expect("explain execution succeeds");

    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            DenseBatchSpec {
                row_count: part_weeks.len(),
                inputs: HashMap::from([(
                    "part_week_end".to_string(),
                    DenseColumn::Date(part_weeks.iter().map(|(_, date)| *date).collect()),
                )]),
                relations: HashMap::new(),
            },
            &outputs,
        )
        .expect("dense execution succeeds");

    for row in 0..part_weeks.len() {
        compare_scalar(
            explain.results[row]
                .outputs
                .get("relevant_week_start")
                .expect("relevant_week_start output"),
            dense_result
                .outputs
                .get("relevant_week_start")
                .expect("dense relevant_week_start"),
            row,
        );
        compare_judgment(
            explain.results[row]
                .outputs
                .get("relevant_week_ends_on_end")
                .expect("judgment output"),
            dense_result
                .outputs
                .get("relevant_week_ends_on_end")
                .expect("dense judgment"),
            row,
        );
    }
}

#[test]
fn dense_notional_capital_matches_explain_mode() {
    let artifact = CompiledProgramArtifact::from_yaml_str(NOTIONAL_CAPITAL_PROGRAM_YAML)
        .expect("programme compiles");
    let dense = DenseCompiledProgram::from_artifact(&artifact, Some("Applicant"))
        .expect("dense compilation succeeds");

    let period = PeriodSpec {
        kind: PeriodKindSpec::Custom {
            name: "ctr_week".to_string(),
        },
        start: chrono::NaiveDate::from_ymd_opt(2026, 2, 2).expect("date"),
        end: chrono::NaiveDate::from_ymd_opt(2026, 2, 8).expect("date"),
    };
    let interval = period_interval(&period);

    // Four applicants exercising every branch of the filter.
    struct Disposal {
        amount: &'static str,
        purpose: &'static str,
        reason: &'static str,
    }
    struct Applicant {
        id: &'static str,
        actual_capital: &'static str,
        disposals: Vec<Disposal>,
    }
    let applicants = vec![
        Applicant {
            id: "applicant-a",
            actual_capital: "4000",
            disposals: vec![],
        },
        Applicant {
            id: "applicant-b",
            actual_capital: "3500",
            disposals: vec![
                Disposal {
                    amount: "2500",
                    purpose: "secure_ctr",
                    reason: "none",
                },
                Disposal {
                    amount: "900",
                    purpose: "secure_ctr",
                    reason: "debt",
                },
                Disposal {
                    amount: "700",
                    purpose: "secure_ctr",
                    reason: "reasonable_purchase",
                },
                Disposal {
                    amount: "1100",
                    purpose: "other",
                    reason: "none",
                },
            ],
        },
        Applicant {
            id: "applicant-c",
            actual_capital: "500",
            disposals: vec![Disposal {
                amount: "10000",
                purpose: "secure_ctr",
                reason: "none",
            }],
        },
        Applicant {
            id: "applicant-d",
            actual_capital: "6500",
            disposals: vec![
                Disposal {
                    amount: "4000",
                    purpose: "other",
                    reason: "none",
                },
                Disposal {
                    amount: "3200",
                    purpose: "secure_ctr",
                    reason: "reasonable_purchase",
                },
            ],
        },
    ];

    let mut dataset = DatasetSpec::default();
    for applicant in &applicants {
        dataset.inputs.push(InputRecordSpec {
            name: "actual_capital".to_string(),
            entity: "Applicant".to_string(),
            entity_id: applicant.id.to_string(),
            interval: interval.clone(),
            value: ScalarValueSpec::Decimal {
                value: applicant.actual_capital.to_string(),
            },
        });
        for (disposal_index, disposal) in applicant.disposals.iter().enumerate() {
            let disposal_id = format!("{}-disposal-{}", applicant.id, disposal_index);
            dataset.relations.push(RelationRecordSpec {
                name: "applicant_disposal".to_string(),
                tuple: vec![applicant.id.to_string(), disposal_id.clone()],
                interval: interval.clone(),
            });
            dataset.inputs.extend([
                InputRecordSpec {
                    name: "disposal_amount".to_string(),
                    entity: "Disposal".to_string(),
                    entity_id: disposal_id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Decimal {
                        value: disposal.amount.to_string(),
                    },
                },
                InputRecordSpec {
                    name: "disposal_purpose".to_string(),
                    entity: "Disposal".to_string(),
                    entity_id: disposal_id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Text {
                        value: disposal.purpose.to_string(),
                    },
                },
                InputRecordSpec {
                    name: "disposal_reason".to_string(),
                    entity: "Disposal".to_string(),
                    entity_id: disposal_id,
                    interval: interval.clone(),
                    value: ScalarValueSpec::Text {
                        value: disposal.reason.to_string(),
                    },
                },
            ]);
        }
    }

    let outputs = [
        "counted_disposals".to_string(),
        "notional_capital".to_string(),
        "capital_for_ctr".to_string(),
    ];
    let explain = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset,
        queries: applicants
            .iter()
            .map(|applicant| ExecutionQuery {
                entity_id: applicant.id.to_string(),
                period: period.clone(),
                outputs: outputs.to_vec(),
            })
            .collect(),
    })
    .expect("explain execution succeeds");

    // Build the dense batch with offsets over the flat disposal list.
    let mut offsets = Vec::with_capacity(applicants.len() + 1);
    offsets.push(0_usize);
    let mut disposal_amount = Vec::new();
    let mut disposal_purpose = Vec::new();
    let mut disposal_reason = Vec::new();
    let mut actual_capital = Vec::with_capacity(applicants.len());
    for applicant in &applicants {
        actual_capital.push(decimal(applicant.actual_capital));
        for disposal in &applicant.disposals {
            disposal_amount.push(decimal(disposal.amount));
            disposal_purpose.push(disposal.purpose.to_string());
            disposal_reason.push(disposal.reason.to_string());
        }
        offsets.push(disposal_amount.len());
    }

    let dense_result = dense
        .execute(
            &period.to_model().expect("period converts"),
            DenseBatchSpec {
                row_count: applicants.len(),
                inputs: HashMap::from([(
                    "actual_capital".to_string(),
                    DenseColumn::Decimal(actual_capital),
                )]),
                relations: HashMap::from([(
                    DenseRelationKey {
                        name: "applicant_disposal".to_string(),
                        current_slot: 0,
                        related_slot: 1,
                    },
                    DenseRelationBatchSpec {
                        offsets,
                        inputs: HashMap::from([
                            (
                                "disposal_amount".to_string(),
                                DenseColumn::Decimal(disposal_amount),
                            ),
                            (
                                "disposal_purpose".to_string(),
                                DenseColumn::Text(disposal_purpose),
                            ),
                            (
                                "disposal_reason".to_string(),
                                DenseColumn::Text(disposal_reason),
                            ),
                        ]),
                    },
                )]),
            },
            &outputs,
        )
        .expect("dense execution succeeds");

    for row in 0..applicants.len() {
        for output in &outputs {
            compare_scalar(
                explain.results[row]
                    .outputs
                    .get(output)
                    .unwrap_or_else(|| panic!("{output} output for row {row}")),
                dense_result
                    .outputs
                    .get(output)
                    .unwrap_or_else(|| panic!("dense {output}")),
                row,
            );
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
struct ChildBenefitCaseFile {
    cases: Vec<ChildBenefitCase>,
}

#[derive(Clone, Debug, Deserialize)]
struct ChildBenefitCase {
    child_id: String,
    period: PeriodSpec,
    cb_recipients: Vec<String>,
    cb_claim_count: i64,
    cb_recipient_id: String,
    sole_claimant_id: String,
    usual_resident_id: String,
}

fn child_benefit_dataset(cases: &[ChildBenefitCase]) -> DatasetSpec {
    let mut dataset = DatasetSpec::default();
    for case in cases {
        let interval = period_interval(&case.period);
        dataset.inputs.extend([
            InputRecordSpec {
                name: "cb_claim_count".to_string(),
                entity: "Child".to_string(),
                entity_id: case.child_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Integer {
                    value: case.cb_claim_count,
                },
            },
            InputRecordSpec {
                name: "cb_recipient_id".to_string(),
                entity: "Child".to_string(),
                entity_id: case.child_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Text {
                    value: case.cb_recipient_id.clone(),
                },
            },
            InputRecordSpec {
                name: "sole_claimant_id".to_string(),
                entity: "Child".to_string(),
                entity_id: case.child_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Text {
                    value: case.sole_claimant_id.clone(),
                },
            },
            InputRecordSpec {
                name: "usual_resident_id".to_string(),
                entity: "Child".to_string(),
                entity_id: case.child_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Text {
                    value: case.usual_resident_id.clone(),
                },
            },
        ]);
        for recipient in &case.cb_recipients {
            dataset.relations.push(RelationRecordSpec {
                name: "cb_receipt".to_string(),
                tuple: vec![recipient.clone(), case.child_id.clone()],
                interval: interval.clone(),
            });
        }
    }
    dataset
}

fn child_benefit_dense_batch(cases: &[ChildBenefitCase]) -> DenseBatchSpec {
    let mut offsets = Vec::with_capacity(cases.len() + 1);
    let mut cb_claim_count = Vec::with_capacity(cases.len());
    let mut cb_recipient_id = Vec::with_capacity(cases.len());
    let mut sole_claimant_id = Vec::with_capacity(cases.len());
    let mut usual_resident_id = Vec::with_capacity(cases.len());
    offsets.push(0_usize);
    let mut cursor = 0_usize;
    for case in cases {
        cursor += case.cb_recipients.len();
        offsets.push(cursor);
        cb_claim_count.push(case.cb_claim_count);
        cb_recipient_id.push(case.cb_recipient_id.clone());
        sole_claimant_id.push(case.sole_claimant_id.clone());
        usual_resident_id.push(case.usual_resident_id.clone());
    }

    DenseBatchSpec {
        row_count: cases.len(),
        inputs: HashMap::from([
            (
                "cb_claim_count".to_string(),
                DenseColumn::Integer(cb_claim_count),
            ),
            (
                "cb_recipient_id".to_string(),
                DenseColumn::Text(cb_recipient_id),
            ),
            (
                "sole_claimant_id".to_string(),
                DenseColumn::Text(sole_claimant_id),
            ),
            (
                "usual_resident_id".to_string(),
                DenseColumn::Text(usual_resident_id),
            ),
        ]),
        relations: HashMap::from([(
            DenseRelationKey {
                name: "cb_receipt".to_string(),
                current_slot: 1,
                related_slot: 0,
            },
            DenseRelationBatchSpec {
                offsets,
                inputs: HashMap::new(),
            },
        )]),
    }
}

fn compare_scalar(explain: &OutputValue, dense: &DenseOutputValue, row: usize) {
    let OutputValue::Scalar { value, .. } = explain else {
        panic!("expected scalar output");
    };
    let DenseOutputValue::Scalar(dense_column) = dense else {
        panic!("expected dense scalar output");
    };
    let dense_value = dense_column.scalar_value_at(
        row,
        &match value {
            ScalarValueSpec::Bool { .. } => rac::model::DType::Bool,
            ScalarValueSpec::Integer { .. } => rac::model::DType::Integer,
            ScalarValueSpec::Decimal { .. } => rac::model::DType::Decimal,
            ScalarValueSpec::Text { .. } => rac::model::DType::Text,
            ScalarValueSpec::Date { .. } => rac::model::DType::Date,
        },
    );
    match (value, dense_value) {
        (ScalarValueSpec::Bool { value }, rac::model::ScalarValue::Bool(dense)) => {
            assert_eq!(*value, dense)
        }
        (ScalarValueSpec::Integer { value }, rac::model::ScalarValue::Integer(dense)) => {
            assert_eq!(*value, dense)
        }
        (ScalarValueSpec::Decimal { value }, rac::model::ScalarValue::Decimal(dense)) => {
            assert_eq!(decimal(value), dense)
        }
        (ScalarValueSpec::Text { value }, rac::model::ScalarValue::Text(dense)) => {
            assert_eq!(value, &dense)
        }
        (ScalarValueSpec::Date { value }, rac::model::ScalarValue::Date(dense)) => {
            assert_eq!(*value, dense)
        }
        other => panic!("mismatched scalar values: {other:?}"),
    }
}

fn compare_judgment(explain: &OutputValue, dense: &DenseOutputValue, row: usize) {
    let OutputValue::Judgment { outcome, .. } = explain else {
        panic!("expected judgment output");
    };
    let DenseOutputValue::Judgment(values) = dense else {
        panic!("expected dense judgment output");
    };
    let dense = match values[row] {
        rac::model::JudgmentOutcome::Holds => JudgmentOutcomeSpec::Holds,
        rac::model::JudgmentOutcome::NotHolds => JudgmentOutcomeSpec::NotHolds,
        rac::model::JudgmentOutcome::Undetermined => JudgmentOutcomeSpec::Undetermined,
    };
    assert_eq!(*outcome, dense);
}

fn month_period() -> PeriodSpec {
    PeriodSpec {
        kind: PeriodKindSpec::Month,
        start: chrono::NaiveDate::from_ymd_opt(2026, 1, 1).expect("date"),
        end: chrono::NaiveDate::from_ymd_opt(2026, 1, 31).expect("date"),
    }
}

fn period_interval(period: &PeriodSpec) -> IntervalSpec {
    IntervalSpec {
        start: period.start,
        end: period.end,
    }
}

fn family_allowance_dataset(
    period: &PeriodSpec,
    households: &[(&str, Vec<(&str, Decimal)>)],
) -> DatasetSpec {
    let interval = period_interval(period);
    let mut dataset = DatasetSpec::default();
    for (household_id, members) in households {
        for (person_id, income) in members {
            dataset.inputs.push(InputRecordSpec {
                name: "earned_income".to_string(),
                entity: "Person".to_string(),
                entity_id: (*person_id).to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: income.normalize().to_string(),
                },
            });
            dataset.relations.push(RelationRecordSpec {
                name: "member_of_household".to_string(),
                tuple: vec![(*person_id).to_string(), (*household_id).to_string()],
                interval: interval.clone(),
            });
        }
    }
    dataset
}

#[derive(Clone, Debug, Deserialize)]
struct SnapCaseFile {
    cases: Vec<SnapCase>,
}

#[derive(Clone, Debug, Deserialize)]
struct SnapCase {
    household_id: String,
    period: PeriodSpec,
    members: Vec<SnapMember>,
    dependent_care_deduction: String,
    child_support_deduction: String,
    medical_deduction: String,
    shelter_costs: String,
    has_elderly_or_disabled_member: bool,
}

#[derive(Clone, Debug, Deserialize)]
struct SnapMember {
    person_id: String,
    earned_income: String,
    unearned_income: String,
}

fn snap_query(case: &SnapCase) -> ExecutionQuery {
    ExecutionQuery {
        entity_id: case.household_id.clone(),
        period: case.period.clone(),
        outputs: vec![
            "household_size".to_string(),
            "gross_income".to_string(),
            "net_income".to_string(),
            "passes_gross_income_test".to_string(),
            "passes_net_income_test".to_string(),
            "snap_eligible".to_string(),
            "snap_allotment".to_string(),
        ],
    }
}

fn snap_dataset_for_cases(cases: &[SnapCase]) -> DatasetSpec {
    let mut dataset = DatasetSpec::default();
    for case in cases {
        let interval = period_interval(&case.period);
        dataset.inputs.extend([
            InputRecordSpec {
                name: "dependent_care_deduction".to_string(),
                entity: "Household".to_string(),
                entity_id: case.household_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.dependent_care_deduction.clone(),
                },
            },
            InputRecordSpec {
                name: "child_support_deduction".to_string(),
                entity: "Household".to_string(),
                entity_id: case.household_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.child_support_deduction.clone(),
                },
            },
            InputRecordSpec {
                name: "medical_deduction".to_string(),
                entity: "Household".to_string(),
                entity_id: case.household_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.medical_deduction.clone(),
                },
            },
            InputRecordSpec {
                name: "shelter_costs".to_string(),
                entity: "Household".to_string(),
                entity_id: case.household_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal {
                    value: case.shelter_costs.clone(),
                },
            },
            InputRecordSpec {
                name: "has_elderly_or_disabled_member".to_string(),
                entity: "Household".to_string(),
                entity_id: case.household_id.clone(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool {
                    value: case.has_elderly_or_disabled_member,
                },
            },
        ]);

        for member in &case.members {
            dataset.inputs.extend([
                InputRecordSpec {
                    name: "earned_income".to_string(),
                    entity: "Person".to_string(),
                    entity_id: member.person_id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Decimal {
                        value: member.earned_income.clone(),
                    },
                },
                InputRecordSpec {
                    name: "unearned_income".to_string(),
                    entity: "Person".to_string(),
                    entity_id: member.person_id.clone(),
                    interval: interval.clone(),
                    value: ScalarValueSpec::Decimal {
                        value: member.unearned_income.clone(),
                    },
                },
            ]);
            dataset.relations.push(RelationRecordSpec {
                name: "member_of_household".to_string(),
                tuple: vec![member.person_id.clone(), case.household_id.clone()],
                interval: interval.clone(),
            });
        }
    }
    dataset
}

fn snap_dense_batch(cases: &[SnapCase]) -> DenseBatchSpec {
    let mut member_offsets = Vec::with_capacity(cases.len() + 1);
    let mut earned_income = Vec::new();
    let mut unearned_income = Vec::new();
    let mut dependent_care = Vec::with_capacity(cases.len());
    let mut child_support = Vec::with_capacity(cases.len());
    let mut medical = Vec::with_capacity(cases.len());
    let mut shelter = Vec::with_capacity(cases.len());
    let mut elderly_or_disabled = Vec::with_capacity(cases.len());

    member_offsets.push(0);
    for case in cases {
        dependent_care.push(decimal(&case.dependent_care_deduction));
        child_support.push(decimal(&case.child_support_deduction));
        medical.push(decimal(&case.medical_deduction));
        shelter.push(decimal(&case.shelter_costs));
        elderly_or_disabled.push(case.has_elderly_or_disabled_member);
        for member in &case.members {
            earned_income.push(decimal(&member.earned_income));
            unearned_income.push(decimal(&member.unearned_income));
        }
        member_offsets.push(earned_income.len());
    }

    DenseBatchSpec {
        row_count: cases.len(),
        inputs: HashMap::from([
            (
                "dependent_care_deduction".to_string(),
                DenseColumn::Decimal(dependent_care),
            ),
            (
                "child_support_deduction".to_string(),
                DenseColumn::Decimal(child_support),
            ),
            ("medical_deduction".to_string(), DenseColumn::Decimal(medical)),
            ("shelter_costs".to_string(), DenseColumn::Decimal(shelter)),
            (
                "has_elderly_or_disabled_member".to_string(),
                DenseColumn::Bool(elderly_or_disabled),
            ),
        ]),
        relations: HashMap::from([(
            DenseRelationKey {
                name: "member_of_household".to_string(),
                current_slot: 1,
                related_slot: 0,
            },
            DenseRelationBatchSpec {
                offsets: member_offsets,
                inputs: HashMap::from([
                    ("earned_income".to_string(), DenseColumn::Decimal(earned_income)),
                    (
                        "unearned_income".to_string(),
                        DenseColumn::Decimal(unearned_income),
                    ),
                ]),
            },
        )]),
    }
}

fn decimal(value: &str) -> Decimal {
    Decimal::from_str(value).expect("valid decimal")
}
