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
    let program = load_rac_file("programmes/other/flat_tax/rules.rac").expect("loads");
    // Four parameters (personal_allowance, high_income_threshold, basic_rate, high_rate).
    assert_eq!(program.parameters.len(), 4);
    // Six entity-scoped derived outputs.
    let derived_names: Vec<&str> = program.derived.values().map(|d| d.name.as_str()).collect();
    for name in ["gross_income", "taxable_income", "high_income", "tax_rate", "income_tax", "net_income"] {
        assert!(derived_names.contains(&name), "missing derived {}", name);
    }
}
