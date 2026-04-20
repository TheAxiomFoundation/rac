use rac::rac::{load_rac_file, parse_source};

const FLAT_TAX_RAC: &str = include_str!("../programmes/other/flat_tax/rules.rac");

#[test]
fn parses_flat_tax_rac() {
    let module = parse_source(FLAT_TAX_RAC).expect("flat_tax.rac parses");
    assert_eq!(module.variables.len(), 10);
    let income_tax = module.variables.iter().find(|v| v.path == "income_tax").unwrap();
    assert_eq!(income_tax.entity.as_deref(), Some("Person"));
    assert_eq!(income_tax.dtype.as_deref(), Some("Money"));
    assert_eq!(income_tax.unit.as_deref(), Some("USD"));
    assert_eq!(income_tax.period.as_deref(), Some("Year"));
    assert_eq!(income_tax.values.len(), 1);
}

#[test]
fn lowers_flat_tax_rac_to_program() {
    let spec = load_rac_file("programmes/other/flat_tax/rules.rac").expect("loads");
    // Four parameters (personal_allowance, high_income_threshold, basic_rate, high_rate).
    assert_eq!(spec.parameters.len(), 4);
    // Six entity-scoped derived outputs.
    let derived_names: Vec<&str> = spec.derived.iter().map(|d| d.name.as_str()).collect();
    for name in ["gross_income", "taxable_income", "high_income", "tax_rate", "income_tax", "net_income"] {
        assert!(derived_names.contains(&name), "missing derived {}", name);
    }
}

#[test]
fn parses_medicare_additional_rac() {
    let spec = load_rac_file("programmes/usc/26/3101/b/2/rules.rac").expect("loads");
    let derived_names: Vec<&str> = spec.derived.iter().map(|d| d.name.as_str()).collect();
    assert!(derived_names.contains(&"additional_medicare_tax"));
    assert!(derived_names.contains(&"threshold"));
}

#[test]
fn all_rac_files_parse_and_lower() {
    // Walk programmes/ for every rules.rac and assert it loads cleanly.
    // Keeps us honest as programmes migrate from YAML → rac.
    fn walk(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
        for entry in std::fs::read_dir(dir).unwrap() {
            let p = entry.unwrap().path();
            if p.is_dir() {
                walk(&p, out);
            } else if p.file_name().and_then(|s| s.to_str()) == Some("rules.rac") {
                out.push(p);
            }
        }
    }
    let mut rac_files = Vec::new();
    walk(std::path::Path::new("programmes"), &mut rac_files);
    rac_files.sort();
    let mut failures: Vec<String> = Vec::new();
    for p in &rac_files {
        match load_rac_file(p) {
            Ok(_) => {}
            Err(e) => failures.push(format!("{}: {}", p.display(), e)),
        }
    }
    assert!(
        failures.is_empty(),
        "rac files failed to load: {}",
        failures.join("\n  ")
    );
    eprintln!("  loaded {} .rac files", rac_files.len());
}
