//! Programme composition via `extends`: an amending YAML file that carries
//! additional parameter versions (or extra derived outputs, relations, units)
//! should merge into its base programme and have the engine pick whichever
//! version is live for the query period. Demonstrated here via the UC
//! programme's 2026-27 parameter amendments. Uses the YAML surface because
//! the `.rac` loader does not yet compose `extends:` amendments.

use std::path::Path;

use rac::api::{
    ExecutionMode, ExecutionQuery, ExecutionRequest, OutputValue, execute_request,
};
use rac::compile::CompiledProgramArtifact;
use rac::spec::{
    DatasetSpec, InputRecordSpec, IntervalSpec, PeriodKindSpec, PeriodSpec, RelationRecordSpec,
    ScalarValueSpec,
};

fn repo_root() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn single_claimant_dataset(benefit_unit_id: &str, adult_id: &str, interval: IntervalSpec) -> DatasetSpec {
    DatasetSpec {
        inputs: vec![
            InputRecordSpec {
                name: "is_couple".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: benefit_unit_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool { value: false },
            },
            InputRecordSpec {
                name: "has_housing_costs".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: benefit_unit_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool { value: false },
            },
            InputRecordSpec {
                name: "eligible_housing_costs".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: benefit_unit_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal { value: "0".to_string() },
            },
            InputRecordSpec {
                name: "non_dep_deductions_total".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: benefit_unit_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal { value: "0".to_string() },
            },
            InputRecordSpec {
                name: "earned_income_monthly".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: benefit_unit_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal { value: "0".to_string() },
            },
            InputRecordSpec {
                name: "unearned_income_monthly".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: benefit_unit_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal { value: "0".to_string() },
            },
            InputRecordSpec {
                name: "capital_total".to_string(),
                entity: "BenefitUnit".to_string(),
                entity_id: benefit_unit_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Decimal { value: "0".to_string() },
            },
            InputRecordSpec {
                name: "age_25_or_over".to_string(),
                entity: "Adult".to_string(),
                entity_id: adult_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool { value: true },
            },
            InputRecordSpec {
                name: "has_lcwra".to_string(),
                entity: "Adult".to_string(),
                entity_id: adult_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool { value: false },
            },
            InputRecordSpec {
                name: "is_carer".to_string(),
                entity: "Adult".to_string(),
                entity_id: adult_id.to_string(),
                interval: interval.clone(),
                value: ScalarValueSpec::Bool { value: false },
            },
        ],
        relations: vec![RelationRecordSpec {
            name: "adult_of_benefit_unit".to_string(),
            tuple: vec![adult_id.to_string(), benefit_unit_id.to_string()],
            interval,
        }],
    }
}

fn uc_month(year: i32, month: u32, end_day: u32) -> PeriodSpec {
    PeriodSpec {
        kind: PeriodKindSpec::Month,
        start: chrono::NaiveDate::from_ymd_opt(year, month, 1).expect("valid date"),
        end: chrono::NaiveDate::from_ymd_opt(year, month, end_day).expect("valid date"),
    }
}

fn run_amended(period: PeriodSpec) -> String {
    // SI 2026/148 — Social Security Benefits Up-rating Order 2026 — amends
    // the base UC Regs 2013 programme via `extends:` and lives at its own
    // legislation.gov.uk-mirrored path, not inside the 2013 folder.
    let amendments_path: &Path = &repo_root()
        .join("programmes")
        .join("uksi")
        .join("2026")
        .join("148")
        .join("rules.yaml");
    let artifact = CompiledProgramArtifact::from_yaml_file(amendments_path)
        .expect("amended programme loads");
    let interval = IntervalSpec {
        start: period.start,
        end: period.end,
    };
    let dataset = single_claimant_dataset("bu-1", "adult-1", interval);
    let response = execute_request(ExecutionRequest {
        mode: ExecutionMode::Explain,
        program: artifact.program.clone(),
        dataset,
        queries: vec![ExecutionQuery {
            entity_id: "bu-1".to_string(),
            period,
            outputs: vec!["standard_allowance".to_string()],
        }],
    })
    .expect("explain execution succeeds");
    match response.results[0]
        .outputs
        .get("standard_allowance")
        .expect("standard_allowance output")
    {
        OutputValue::Scalar { value, .. } => match value {
            ScalarValueSpec::Decimal { value } => value.clone(),
            _ => panic!("standard_allowance should be decimal"),
        },
        _ => panic!("standard_allowance should be a scalar"),
    }
}

fn decimal(value: &str) -> rust_decimal::Decimal {
    use std::str::FromStr;
    rust_decimal::Decimal::from_str(value).expect("valid decimal")
}

#[test]
fn extends_leaves_pre_amendment_period_unchanged() {
    // Query for May 2025 — before the 2026-04-06 amendment takes effect.
    // Expect 2025-26 standard allowance (single 25+): £400.14.
    let period = uc_month(2025, 5, 31);
    let value = run_amended(period);
    assert_eq!(decimal(&value), decimal("400.14"));
}

#[test]
fn extends_kicks_in_after_effective_date() {
    // Query for May 2026 — after the 2026-04-06 amendment takes effect.
    // Expect 2026-27 standard allowance (single 25+): £424.90.
    let period = uc_month(2026, 5, 31);
    let value = run_amended(period);
    assert_eq!(decimal(&value), decimal("424.90"));
}
