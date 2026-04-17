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
