use std::io::Write;

use axiom_rules::rac_dsl::{load_rac_file, parse_source};
use axiom_rules::rulespec::load_rulespec_file;

const FLAT_TAX_RAC: &str = r#"
personal_allowance:
    dtype: Money
    unit: USD
    from 2025-01-01: 1000

gross_income:
    entity: Person
    dtype: Money
    period: Year
    unit: USD
    from 2025-01-01: income

income_tax:
    entity: Person
    dtype: Money
    period: Year
    unit: USD
    from 2025-01-01: ceil(gross_income * 0.1)
"#;

#[test]
fn parses_flat_tax_rac() {
    let module = parse_source(FLAT_TAX_RAC).expect("flat_tax.rac parses");
    assert_eq!(module.variables.len(), 3);
    let income_tax = module
        .variables
        .iter()
        .find(|v| v.path == "income_tax")
        .unwrap();
    assert_eq!(income_tax.entity.as_deref(), Some("Person"));
    assert_eq!(income_tax.dtype.as_deref(), Some("Money"));
    assert_eq!(income_tax.unit.as_deref(), Some("USD"));
    assert_eq!(income_tax.period.as_deref(), Some("Year"));
    assert_eq!(income_tax.values.len(), 1);
}

#[test]
fn lowers_rac_file_to_program() {
    let path = std::env::temp_dir().join(format!(
        "axiom-rules-rac-dsl-test-{}.rac",
        std::process::id()
    ));
    let mut file = std::fs::File::create(&path).expect("temp .rac file created");
    file.write_all(FLAT_TAX_RAC.as_bytes())
        .expect("temp .rac written");

    let spec = load_rac_file(&path).expect("loads");
    let _ = std::fs::remove_file(path);

    assert_eq!(spec.parameters.len(), 1);
    let derived_names: Vec<&str> = spec.derived.iter().map(|d| d.name.as_str()).collect();
    assert!(derived_names.contains(&"gross_income"));
    assert!(derived_names.contains(&"income_tax"));
}

#[test]
fn all_rulespec_files_parse_and_lower() {
    fn walk(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
        for entry in std::fs::read_dir(dir).unwrap() {
            let p = entry.unwrap().path();
            if p.is_dir() {
                walk(&p, out);
            } else if p.file_name().and_then(|s| s.to_str()) == Some("rules.yaml") {
                out.push(p);
            }
        }
    }
    let mut rulespec_files = Vec::new();
    walk(std::path::Path::new("programmes"), &mut rulespec_files);
    rulespec_files.sort();
    let mut failures: Vec<String> = Vec::new();
    for p in &rulespec_files {
        match load_rulespec_file(p) {
            Ok(_) => {}
            Err(e) => failures.push(format!("{}: {}", p.display(), e)),
        }
    }
    assert!(
        failures.is_empty(),
        "RuleSpec files failed to load: {}",
        failures.join("\n  ")
    );
    eprintln!("  loaded {} RuleSpec files", rulespec_files.len());
}
