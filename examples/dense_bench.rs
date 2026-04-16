use std::collections::HashMap;
use std::time::Instant;

use chrono::NaiveDate;
use rac::compile::CompiledProgramArtifact;
use rac::dense::{
    DenseBatchSpec, DenseColumn, DenseCompiledProgram, DenseRelationBatchSpec, DenseRelationKey,
};
use rac::model::{Period, PeriodKind};
use rust_decimal::Decimal;

const FLAT_TAX_PROGRAM_YAML: &str = include_str!("flat_tax_program.yaml");
const FAMILY_ALLOWANCE_PROGRAM_YAML: &str = include_str!("family_allowance_program.yaml");
const SNAP_PROGRAM_YAML: &str = include_str!("snap_program.yaml");

fn main() {
    let households = std::env::args()
        .nth(1)
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(100_000);
    let period = Period {
        kind: PeriodKind::Month,
        start: NaiveDate::from_ymd_opt(2026, 1, 1).expect("date"),
        end: NaiveDate::from_ymd_opt(2026, 1, 31).expect("date"),
    };

    println!("dense benchmark rows: {households}");

    benchmark_flat_tax(households, &period);
    benchmark_family_allowance(households, &period);
    benchmark_snap_generic(households, &period);
}

fn benchmark_flat_tax(rows: usize, period: &Period) {
    let compile_started = Instant::now();
    let artifact =
        CompiledProgramArtifact::from_yaml_str(FLAT_TAX_PROGRAM_YAML).expect("programme compiles");
    let compiled = DenseCompiledProgram::from_artifact(&artifact, Some("Person"))
        .expect("dense compilation succeeds");
    let compile_elapsed = compile_started.elapsed();

    let batch_started = Instant::now();
    let incomes = (0..rows)
        .map(|index| Decimal::from(800 + ((index * 37) % 4_500) as i64))
        .collect::<Vec<Decimal>>();
    let batch = DenseBatchSpec {
        row_count: rows,
        inputs: HashMap::from([("income".to_string(), DenseColumn::Decimal(incomes))]),
        relations: HashMap::new(),
    };
    let batch_elapsed = batch_started.elapsed();

    let execute_started = Instant::now();
    let results = compiled
        .execute(
            period,
            batch,
            &[
                "gross_income".to_string(),
                "taxable_income".to_string(),
                "income_tax".to_string(),
                "net_income".to_string(),
            ],
        )
        .expect("dense execution succeeds");
    let execute_elapsed = execute_started.elapsed();

    print_summary(
        "flat_tax_generic_dense",
        rows,
        compile_elapsed,
        batch_elapsed,
        execute_elapsed,
    );
    if let Some(rac::dense::DenseOutputValue::Scalar(DenseColumn::Decimal(net_income))) =
        results.outputs.get("net_income")
    {
        println!("  sample_net_income: {}", net_income[0].normalize());
    }
}

fn benchmark_family_allowance(rows: usize, period: &Period) {
    let compile_started = Instant::now();
    let artifact = CompiledProgramArtifact::from_yaml_str(FAMILY_ALLOWANCE_PROGRAM_YAML)
        .expect("programme compiles");
    let compiled = DenseCompiledProgram::from_artifact(&artifact, Some("Household"))
        .expect("dense compilation succeeds");
    let compile_elapsed = compile_started.elapsed();

    let batch_started = Instant::now();
    let mut offsets = Vec::with_capacity(rows + 1);
    let mut earned_income = Vec::new();
    offsets.push(0);
    for row in 0..rows {
        let size = 1 + (row % 4);
        for member in 0..size {
            earned_income.push(Decimal::from(600 + (((row + member) * 43) % 1_200) as i64));
        }
        offsets.push(earned_income.len());
    }
    let batch = DenseBatchSpec {
        row_count: rows,
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
    };
    let batch_elapsed = batch_started.elapsed();

    let execute_started = Instant::now();
    let results = compiled
        .execute(
            period,
            batch,
            &[
                "household_size".to_string(),
                "earned_income_total".to_string(),
                "monthly_allowance".to_string(),
            ],
        )
        .expect("dense execution succeeds");
    let execute_elapsed = execute_started.elapsed();

    print_summary(
        "family_allowance_generic_dense",
        rows,
        compile_elapsed,
        batch_elapsed,
        execute_elapsed,
    );
    if let Some(rac::dense::DenseOutputValue::Scalar(DenseColumn::Decimal(allowance))) =
        results.outputs.get("monthly_allowance")
    {
        println!("  sample_monthly_allowance: {}", allowance[0].normalize());
    }
}

fn benchmark_snap_generic(rows: usize, period: &Period) {
    let compile_started = Instant::now();
    let artifact =
        CompiledProgramArtifact::from_yaml_str(SNAP_PROGRAM_YAML).expect("programme compiles");
    let compiled = DenseCompiledProgram::from_artifact(&artifact, Some("Household"))
        .expect("dense compilation succeeds");
    let compile_elapsed = compile_started.elapsed();

    let batch_started = Instant::now();
    let batch = build_snap_dense_batch(rows);
    let batch_elapsed = batch_started.elapsed();

    let execute_started = Instant::now();
    let results = compiled
        .execute(
            period,
            batch,
            &[
                "gross_income".to_string(),
                "net_income".to_string(),
                "snap_allotment".to_string(),
            ],
        )
        .expect("dense execution succeeds");
    let execute_elapsed = execute_started.elapsed();

    print_summary(
        "snap_generic_dense",
        rows,
        compile_elapsed,
        batch_elapsed,
        execute_elapsed,
    );
    if let Some(rac::dense::DenseOutputValue::Scalar(DenseColumn::Decimal(allotment))) =
        results.outputs.get("snap_allotment")
    {
        println!("  sample_snap_allotment: {}", allotment[0].normalize());
    }
}

fn build_snap_dense_batch(rows: usize) -> DenseBatchSpec {
    let mut offsets = Vec::with_capacity(rows + 1);
    let mut earned_income = Vec::new();
    let mut unearned_income = Vec::new();
    let mut dependent_care = Vec::with_capacity(rows);
    let mut child_support = Vec::with_capacity(rows);
    let mut medical = Vec::with_capacity(rows);
    let mut shelter = Vec::with_capacity(rows);
    let mut elderly_or_disabled = Vec::with_capacity(rows);

    offsets.push(0);
    for row in 0..rows {
        let members = 1 + (row % 4);
        dependent_care.push(Decimal::from(((row * 17) % 250) as i64));
        child_support.push(Decimal::from(((row * 11) % 120) as i64));
        medical.push(Decimal::from(((row * 7) % 180) as i64));
        shelter.push(Decimal::from(750 + ((row * 29) % 900) as i64));
        elderly_or_disabled.push(row % 5 == 0);
        for member in 0..members {
            earned_income.push(Decimal::from(250 + (((row + member) * 31) % 900) as i64));
            unearned_income.push(Decimal::from((((row + member) * 13) % 220) as i64));
        }
        offsets.push(earned_income.len());
    }

    DenseBatchSpec {
        row_count: rows,
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
                offsets,
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

fn print_summary(
    label: &str,
    rows: usize,
    compile_elapsed: std::time::Duration,
    batch_elapsed: std::time::Duration,
    execute_elapsed: std::time::Duration,
) {
    let households_per_second = rows as f64 / execute_elapsed.as_secs_f64();
    println!("{label}:");
    println!("  compile: {:.4} ms", compile_elapsed.as_secs_f64() * 1_000.0);
    println!("  batch_build: {:.4} ms", batch_elapsed.as_secs_f64() * 1_000.0);
    println!("  execute: {:.4} ms", execute_elapsed.as_secs_f64() * 1_000.0);
    println!("  throughput: {:.2} rows/s", households_per_second);
}
