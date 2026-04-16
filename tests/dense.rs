use std::collections::HashMap;
use std::str::FromStr;

use rac::api::{ExecutionMode, ExecutionQuery, ExecutionRequest, OutputValue, execute_request};
use rac::compile::CompiledProgramArtifact;
use rac::dense::{
    DenseBatchSpec, DenseColumn, DenseCompiledProgram, DenseOutputValue, DenseRelationBatchSpec,
    DenseRelationKey,
};
use rac::spec::{
    DatasetSpec, InputRecordSpec, IntervalSpec, JudgmentOutcomeSpec, PeriodKindSpec, PeriodSpec,
    RelationRecordSpec, ScalarValueSpec,
};
use rust_decimal::Decimal;
use serde::Deserialize;

const FLAT_TAX_PROGRAM_YAML: &str = include_str!("../examples/flat_tax_program.yaml");
const FAMILY_ALLOWANCE_PROGRAM_YAML: &str = include_str!("../examples/family_allowance_program.yaml");
const SNAP_PROGRAM_YAML: &str = include_str!("../examples/snap_program.yaml");
const SNAP_CASES_YAML: &str = include_str!("../examples/snap_cases.yaml");

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
