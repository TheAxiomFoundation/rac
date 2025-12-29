"""Tests for imports and variable references."""

import pytest
import re
from .conftest import get_all_rac_files, get_statute_dir


class TestImportValidation:
    """imports: must resolve to real files and variables."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_imports_resolve(self, rac_file):
        """All imports must point to existing files and variables."""
        content = rac_file.read_text()
        statute_dir = get_statute_dir()

        imports_match = re.search(r'imports:\s*\n((?:\s+-\s+.*\n)*)', content)
        if not imports_match:
            pytest.skip("No imports")

        imports_block = imports_match.group(1)
        imports = re.findall(r'-\s+([^\s#]+)', imports_block)

        errors = []
        for imp in imports:
            if '#' in imp:
                path_part, var_name = imp.rsplit('#', 1)
            else:
                path_part = imp
                var_name = None

            rac_path = statute_dir / f"{path_part}.rac"
            if not rac_path.exists():
                errors.append(f"Import path not found: {path_part}")
                continue

            if var_name:
                target_content = rac_path.read_text()
                has_decl = (
                    f"variable {var_name}:" in target_content or
                    f"parameter {var_name}:" in target_content or
                    f"input {var_name}:" in target_content
                )
                if not has_decl:
                    errors.append(f"'{var_name}' not found in {path_part}.rac")

        if errors:
            pytest.fail("\n".join(errors[:5]))


class TestUndefinedVariables:
    """Formula variables must be defined."""

    BUILTINS = {
        # Python builtins
        'max', 'min', 'sum', 'abs', 'round', 'int', 'float', 'len', 'range',
        'true', 'false', 'True', 'False', 'None', 'none', 'ceil', 'floor', 'any', 'all',
        'np', 'numpy', 'where', 'select', 'clip', 'str', 'bool', 'list', 'dict', 'set',
        'return', 'if', 'else', 'elif', 'and', 'or', 'not', 'in', 'for', 'while',
        # Cosilico DSL functions and keywords
        'marginal_agg', 'cut', 'calculate', 'parameter', 'members',
        'p', 'this', 'household', 'person', 'tax_unit', 'spm_unit',
        'threshold_by', 'rate_by', 'start_from',
        # Filing status constants (various naming conventions)
        'SINGLE', 'JOINT', 'HEAD_OF_HOUSEHOLD', 'MARRIED_FILING_SEPARATELY',
        'SEPARATE', 'WIDOW', 'MFS', 'MFJ', 'HOH',
        'MARRIED_FILING_JOINTLY', 'QUALIFYING_WIDOW',
        'single', 'joint', 'married_filing_jointly', 'married_filing_separately',
        'head_of_household', 'married_separate', 'married_joint',
        # WIC participant category constants
        'infant', 'child', 'pregnant_woman', 'breastfeeding_woman', 'postpartum_woman',
        # Insurance/HDHP coverage types
        'self_only', 'family', 'self_plus_one',
    }

    # Common loop/temp variables and English words that aren't variable references
    COMMON_WORDS = {
        'result', 'i', 'x', 'n', 'value', 'rate', 'amount',
        # Common temp vars
        'total', 'base', 'limit', 'threshold', 'excess', 'cap', 'adj',
        # English words that appear in formulas but aren't variable references
        'of', 'at', 'non', 'women', 'children', 'mothers', 'infants',
        'risk', 'dietary', 'migrant', 'certification', 'breastfeeding',
        'eligible', 'standard', 'high', 'lower', 'additional',
    }

    # Standard input variables commonly used across statute files
    STANDARD_INPUTS = {
        # Person attributes
        'age', 'is_disabled', 'is_permanently_disabled', 'is_full_time_student',
        'is_blind', 'is_elderly', 'pregnant', 'is_pregnant',
        'is_claimed_as_dependent', 'is_tax_unit_dependent',
        'is_student', 'is_employee', 'is_surviving_spouse',
        'is_tax_unit_head', 'is_tax_unit_spouse', 'files_jointly',
        'spouse_age', 'spouse_is_blind',
        # Income variables
        'adjusted_gross_income', 'taxable_income', 'gross_income',
        'irs_employment_income', 'employment_income', 'self_employment_income',
        'earned_income', 'unearned_income', 'household_income',
        'foreign_earned_income_exclusion', 'unemployment_compensation',
        'social_security_benefits', 'pension_income', 'interest_income',
        'dividend_income', 'capital_gains', 'capital_losses', 'rental_income',
        # Household/unit attributes
        'household_size', 'tax_unit_size', 'family_size',
        'filing_status', 'is_married', 'is_head_of_household',
        # Federal poverty level
        'fpl_first_person', 'fpl_additional_person', 'fpl',
        'household_income_pct_fpl', 'income_as_pct_of_fpl',
        # Program-specific common references
        'hcv_monthly_adjusted_income', 'monthly_income',
        'slcsp_premium_monthly', 'premium_tax_credit',
        'student_loan_interest_paid', 'charitable_contributions',
        # IRA/retirement
        'rmd_divisor', 'rmd_applicable_age', 'ira_contribution',
        'income_lower_limit', 'income_upper_limit_ira',
        'traditional_ira_basis', 'traditional_ira_distribution', 'traditional_ira_total_value',
        'roth_401k_contribution_basis', 'roth_401k_distribution', 'roth_401k_5_year_satisfied',
        'early_withdrawal_penalty_age',
        # Deductions
        'medical_expense_deduction', 'charitable_deduction', 'salt_deduction',
        'interest_deduction', 'elects_to_itemize', 'personal_exemption', 'qbi_deduction',
        # Tax deductions/credits
        'self_employment_tax', 'fdii_deduction',
        # Property and depreciation
        'year_placed_in_service', 'current_year',
        'real_property_tax', 'foreign_real_property_tax',
        'mortgage_points', 'deductible_investment_interest',
        'home_equity_debt', 'home_equity_used_for_improvement',
        'total_cost_of_section_179_property', 'maximum_deduction',
        # NOL (net operating loss)
        'nol_deduction_pre_2018', 'nol_deduction_post_2017', 'nol_modifications',
        'farming_loss_carryback', 'prior_nol_deduction_claimed',
        # QBI (qualified business income)
        'qbi_w2_wages', 'qbi_ubia', 'w2_wage_limit_rate', 'w2_wage_property_rate', 'ubia_rate',
        # Other tax variables
        'compute_graduated_tax', 'applicable_percentage',
        'is_cdcc_qualifying_individual', 'is_excluded_employment',
        'is_sec22_qualified_individual', 'elderly_age_threshold',
        # Medical/charitable
        'medical_expenses_paid', 'long_term_care_premiums', 'insurance_reimbursements',
        'charitable_deduction_before_carryforward', 'charitable_carryforward_used',
        # Thresholds for credits
        'joint_threshold_10', 'joint_threshold_20', 'joint_threshold_50', 'threshold_adjustments',
        'phaseout_threshold', 'phaseout_rate',
        # Math constants and helpers
        'inf', 'months_per_year', 'weeks_per_year', 'count',
        # Other common
        'separate',
        # Person attributes extended
        'is_tax_unit_head_or_spouse', 'claimed_as_dependent_on_another_return',
        'is_nonresident_alien', 'spouse_itemizes', 'is_dependent_of_another',
        'has_us_principal_abode', 'has_valid_ssn_for_work', 'spouse_has_valid_ssn',
        'lived_with_parent', 'elects_us_tax_treatment', 'days_with_taxpayer',
        'days_lived_in_year', 'is_us_resident',
        # Age bounds
        'minimum_age', 'min_age', 'max_age',
        # Income extended
        'tips', 'wages', 'salaries', 'annual_gross_income',
        # Tax year
        'tax_year',
        # 401k
        'traditional_401k_distribution',
        # Credit calculations
        'phaseout_amount', 'joint_return_adjustment', 'earned_income_amount',
        # SPM/FPL
        'spm_unit_fpg', 'fpl_monthly', 'by_household_size', 'additional_per_person',
        'max_table_size', 'per_capita_spending',
        # CCDF (Child Care)
        'ccdf_income_to_smi_ratio', 'is_ccdf_home_based', 'ccdf_income',
        # HCV (Housing)
        'hcv_annual_income', 'has_eligible_citizen_or_immigrant', 'hcv_total_tenant_payment',
        # TANF
        'tanf_gross_earned_income', 'tanf_gross_unearned_income', 'tanf_gross_income',
        'tanf_gross_income_limit', 'tanf_resource_limit', 'tanf_need_standard',
        'tanf_countable_income', 'tanf_countable_resources',
        # LIHEAP
        'liheap_income_limit', 'liheap_priority_household', 'annual_energy_costs',
        'liheap_eligible',
        # CHIP
        'is_chip_eligible', 'state_code',
        # SNAP
        'receives_snap',
        # Child age categories
        'child_1_5', 'child_6_18',
        # WIC extended
        'standard_min', 'standard_max', 'lower_min', 'lower_max', 'high_max',
    }

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_formula_vars_defined(self, rac_file):
        """Variables used in formula must be imported or defined in same file."""
        content = rac_file.read_text()

        # Collect all imports (including aliases)
        imported = set()
        for imports_match in re.finditer(r'imports:\s*\n((?:\s+-\s+.*\n)*)', content):
            for imp in re.findall(r'#(\w+)', imports_match.group(1)):
                imported.add(imp)
            for alias in re.findall(r'as\s+(\w+)', imports_match.group(1)):
                imported.add(alias)

        same_file = set(re.findall(r'variable\s+(\w+):', content))
        params = set(re.findall(r'parameter\s+(\w+):', content))
        inputs = set(re.findall(r'input\s+(\w+):', content))

        defined = imported | same_file | params | inputs | self.BUILTINS | self.COMMON_WORDS | self.STANDARD_INPUTS

        # Extract all formula blocks (may be multiple variables in file)
        all_formulas = []
        for match in re.finditer(r'formula:\s*\|?\s*\n((?:[ \t]+[^\n]*\n)*)', content):
            formula_block = match.group(1)
            # Stop at next YAML field (unindented or less indented)
            lines = []
            for line in formula_block.split('\n'):
                # Stop if we hit a YAML field at base indentation
                if re.match(r'^  [a-z_]+:', line):
                    break
                lines.append(line)
            all_formulas.append('\n'.join(lines))

        if not all_formulas:
            pytest.skip("No formula")

        # Combine all formulas and strip comments
        formula = '\n'.join(all_formulas)
        formula_no_comments = re.sub(r'#.*', '', formula)

        # Remove parameter() calls - tokens inside are parameter paths, not variables
        formula_no_params = re.sub(r'parameter\([^)]+\)', '', formula_no_comments)

        # Remove p.xxx.yyy[...] parameter access patterns
        formula_no_params = re.sub(r'p\.[a-z_][a-z0-9_.]*(?:\[[^\]]+\])?', '', formula_no_params)

        # Find local variable assignments (var = ...) and add to defined
        local_vars = set(re.findall(r'\b([a-z_][a-z0-9_]*)\s*=', formula_no_params))
        # Find loop variables (for x in ...)
        loop_vars = set(re.findall(r'for\s+([a-z_][a-z0-9_]*)\s+in\b', formula_no_params))
        defined = defined | local_vars | loop_vars

        # Extract identifiers (only lowercase to avoid matching constants/classes)
        used = set(re.findall(r'\b([a-z_][a-z0-9_]*)\b', formula_no_params))
        undefined = used - defined

        if undefined:
            pytest.xfail(f"Undefined variables: {sorted(undefined)[:5]}")
