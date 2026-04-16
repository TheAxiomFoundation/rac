use std::collections::BTreeMap;
use std::str::FromStr;

use chrono::NaiveDate;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::model::{
    ComparisonOp, DType, DataSet, Derived, DerivedSemantics, IndexedParameter, InputRecord,
    Interval, JudgmentExpr, JudgmentOutcome, ParameterVersion, Period, PeriodKind, Program,
    RelatedValueRef, RelationRecord, ScalarExpr, ScalarValue, UnitDef, UnitKind,
};

#[derive(Debug, Error)]
pub enum SpecError {
    #[error("invalid decimal literal `{literal}`")]
    InvalidDecimal { literal: String },
    #[error("yaml parse error: {0}")]
    Yaml(#[from] serde_yaml::Error),
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct ProgramSpec {
    #[serde(default)]
    pub units: Vec<UnitSpec>,
    #[serde(default)]
    pub relations: Vec<RelationSpec>,
    #[serde(default)]
    pub parameters: Vec<IndexedParameterSpec>,
    #[serde(default)]
    pub derived: Vec<DerivedSpec>,
}

impl ProgramSpec {
    pub fn from_yaml_str(source: &str) -> Result<Self, SpecError> {
        Ok(serde_yaml::from_str(source)?)
    }

    pub fn to_program(&self) -> Result<Program, SpecError> {
        let mut program = Program::default();

        for unit in &self.units {
            program.add_unit(unit.to_model());
        }

        for relation in &self.relations {
            program.add_relation(&relation.name, relation.arity);
        }

        for parameter in &self.parameters {
            program.add_parameter(parameter.to_model()?);
        }

        for derived in &self.derived {
            program.add_derived(derived.to_model()?);
        }

        Ok(program)
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct DatasetSpec {
    #[serde(default)]
    pub inputs: Vec<InputRecordSpec>,
    #[serde(default)]
    pub relations: Vec<RelationRecordSpec>,
}

impl DatasetSpec {
    pub fn to_dataset(&self) -> Result<DataSet, SpecError> {
        Ok(DataSet {
            inputs: self
                .inputs
                .iter()
                .map(InputRecordSpec::to_model)
                .collect::<Result<Vec<InputRecord>, SpecError>>()?,
            relations: self
                .relations
                .iter()
                .map(RelationRecordSpec::to_model)
                .collect::<Result<Vec<RelationRecord>, SpecError>>()?,
        })
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UnitSpec {
    pub name: String,
    #[serde(flatten)]
    pub kind: UnitKindSpec,
}

impl UnitSpec {
    fn to_model(&self) -> UnitDef {
        UnitDef {
            name: self.name.clone(),
            kind: self.kind.to_model(),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum UnitKindSpec {
    Currency { minor_units: u8 },
    Count,
    Ratio,
    Duration,
    Custom { label: String },
}

impl UnitKindSpec {
    fn to_model(&self) -> UnitKind {
        match self {
            Self::Currency { minor_units } => UnitKind::Currency {
                minor_units: *minor_units,
            },
            Self::Count => UnitKind::Count,
            Self::Ratio => UnitKind::Ratio,
            Self::Duration => UnitKind::Duration,
            Self::Custom { label } => UnitKind::Custom(label.clone()),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RelationSpec {
    pub name: String,
    pub arity: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct IndexedParameterSpec {
    pub name: String,
    pub unit: Option<String>,
    #[serde(default)]
    pub versions: Vec<ParameterVersionSpec>,
}

impl IndexedParameterSpec {
    fn to_model(&self) -> Result<IndexedParameter, SpecError> {
        Ok(IndexedParameter {
            name: self.name.clone(),
            unit: self.unit.clone(),
            versions: self
                .versions
                .iter()
                .map(ParameterVersionSpec::to_model)
                .collect::<Result<Vec<ParameterVersion>, SpecError>>()?,
        })
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ParameterVersionSpec {
    pub effective_from: NaiveDate,
    pub values: BTreeMap<i64, ScalarValueSpec>,
}

impl ParameterVersionSpec {
    fn to_model(&self) -> Result<ParameterVersion, SpecError> {
        let mut values = BTreeMap::new();
        for (key, value) in &self.values {
            values.insert(*key, value.to_model()?);
        }
        Ok(ParameterVersion {
            effective_from: self.effective_from,
            values,
        })
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DerivedSpec {
    pub name: String,
    pub entity: String,
    pub dtype: DTypeSpec,
    pub unit: Option<String>,
    #[serde(flatten)]
    pub semantics: DerivedSemanticsSpec,
}

impl DerivedSpec {
    fn to_model(&self) -> Result<Derived, SpecError> {
        Ok(Derived {
            name: self.name.clone(),
            entity: self.entity.clone(),
            dtype: self.dtype.to_model(),
            unit: self.unit.clone(),
            semantics: self.semantics.to_model()?,
        })
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DTypeSpec {
    Judgment,
    Bool,
    Integer,
    Decimal,
    Text,
}

impl DTypeSpec {
    pub fn from_model(dtype: &DType) -> Self {
        match dtype {
            DType::Judgment => Self::Judgment,
            DType::Bool => Self::Bool,
            DType::Integer => Self::Integer,
            DType::Decimal => Self::Decimal,
            DType::Text => Self::Text,
        }
    }

    fn to_model(&self) -> DType {
        match self {
            Self::Judgment => DType::Judgment,
            Self::Bool => DType::Bool,
            Self::Integer => DType::Integer,
            Self::Decimal => DType::Decimal,
            Self::Text => DType::Text,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "semantics", rename_all = "snake_case")]
pub enum DerivedSemanticsSpec {
    Scalar { expr: ScalarExprSpec },
    Judgment { expr: JudgmentExprSpec },
}

impl DerivedSemanticsSpec {
    fn to_model(&self) -> Result<DerivedSemantics, SpecError> {
        match self {
            Self::Scalar { expr } => Ok(DerivedSemantics::Scalar(expr.to_model()?)),
            Self::Judgment { expr } => Ok(DerivedSemantics::Judgment(expr.to_model()?)),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ScalarValueSpec {
    Bool { value: bool },
    Integer { value: i64 },
    Decimal { value: String },
    Text { value: String },
}

impl ScalarValueSpec {
    pub fn from_model(value: ScalarValue) -> Self {
        match value {
            ScalarValue::Bool(value) => Self::Bool { value },
            ScalarValue::Integer(value) => Self::Integer { value },
            ScalarValue::Decimal(value) => Self::Decimal {
                value: value.normalize().to_string(),
            },
            ScalarValue::Text(value) => Self::Text { value },
        }
    }

    fn to_model(&self) -> Result<ScalarValue, SpecError> {
        match self {
            Self::Bool { value } => Ok(ScalarValue::Bool(*value)),
            Self::Integer { value } => Ok(ScalarValue::Integer(*value)),
            Self::Decimal { value } => Ok(ScalarValue::Decimal(Decimal::from_str(value).map_err(
                |_| SpecError::InvalidDecimal {
                    literal: value.clone(),
                },
            )?)),
            Self::Text { value } => Ok(ScalarValue::Text(value.clone())),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ScalarExprSpec {
    Literal {
        value: ScalarValueSpec,
    },
    Input {
        name: String,
    },
    Derived {
        name: String,
    },
    ParameterLookup {
        parameter: String,
        index: Box<ScalarExprSpec>,
    },
    Add {
        items: Vec<ScalarExprSpec>,
    },
    Sub {
        left: Box<ScalarExprSpec>,
        right: Box<ScalarExprSpec>,
    },
    Mul {
        left: Box<ScalarExprSpec>,
        right: Box<ScalarExprSpec>,
    },
    Div {
        left: Box<ScalarExprSpec>,
        right: Box<ScalarExprSpec>,
    },
    Max {
        items: Vec<ScalarExprSpec>,
    },
    Min {
        items: Vec<ScalarExprSpec>,
    },
    Ceil {
        value: Box<ScalarExprSpec>,
    },
    CountRelated {
        relation: String,
        current_slot: usize,
        related_slot: usize,
    },
    SumRelated {
        relation: String,
        current_slot: usize,
        related_slot: usize,
        value: RelatedValueRefSpec,
    },
    If {
        condition: Box<JudgmentExprSpec>,
        then_expr: Box<ScalarExprSpec>,
        else_expr: Box<ScalarExprSpec>,
    },
}

impl ScalarExprSpec {
    fn to_model(&self) -> Result<ScalarExpr, SpecError> {
        match self {
            Self::Literal { value } => Ok(ScalarExpr::Literal(value.to_model()?)),
            Self::Input { name } => Ok(ScalarExpr::Input(name.clone())),
            Self::Derived { name } => Ok(ScalarExpr::Derived(name.clone())),
            Self::ParameterLookup { parameter, index } => Ok(ScalarExpr::ParameterLookup {
                parameter: parameter.clone(),
                index: Box::new(index.to_model()?),
            }),
            Self::Add { items } => Ok(ScalarExpr::Add(
                items
                    .iter()
                    .map(ScalarExprSpec::to_model)
                    .collect::<Result<Vec<ScalarExpr>, SpecError>>()?,
            )),
            Self::Sub { left, right } => Ok(ScalarExpr::Sub(
                Box::new(left.to_model()?),
                Box::new(right.to_model()?),
            )),
            Self::Mul { left, right } => Ok(ScalarExpr::Mul(
                Box::new(left.to_model()?),
                Box::new(right.to_model()?),
            )),
            Self::Div { left, right } => Ok(ScalarExpr::Div(
                Box::new(left.to_model()?),
                Box::new(right.to_model()?),
            )),
            Self::Max { items } => Ok(ScalarExpr::Max(
                items
                    .iter()
                    .map(ScalarExprSpec::to_model)
                    .collect::<Result<Vec<ScalarExpr>, SpecError>>()?,
            )),
            Self::Min { items } => Ok(ScalarExpr::Min(
                items
                    .iter()
                    .map(ScalarExprSpec::to_model)
                    .collect::<Result<Vec<ScalarExpr>, SpecError>>()?,
            )),
            Self::Ceil { value } => Ok(ScalarExpr::Ceil(Box::new(value.to_model()?))),
            Self::CountRelated {
                relation,
                current_slot,
                related_slot,
            } => Ok(ScalarExpr::CountRelated {
                relation: relation.clone(),
                current_slot: *current_slot,
                related_slot: *related_slot,
            }),
            Self::SumRelated {
                relation,
                current_slot,
                related_slot,
                value,
            } => Ok(ScalarExpr::SumRelated {
                relation: relation.clone(),
                current_slot: *current_slot,
                related_slot: *related_slot,
                value: value.to_model(),
            }),
            Self::If {
                condition,
                then_expr,
                else_expr,
            } => Ok(ScalarExpr::If {
                condition: Box::new(condition.to_model()?),
                then_expr: Box::new(then_expr.to_model()?),
                else_expr: Box::new(else_expr.to_model()?),
            }),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum RelatedValueRefSpec {
    Input { name: String },
    Derived { name: String },
}

impl RelatedValueRefSpec {
    fn to_model(&self) -> RelatedValueRef {
        match self {
            Self::Input { name } => RelatedValueRef::Input(name.clone()),
            Self::Derived { name } => RelatedValueRef::Derived(name.clone()),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum JudgmentExprSpec {
    Comparison {
        left: Box<ScalarExprSpec>,
        op: ComparisonOpSpec,
        right: Box<ScalarExprSpec>,
    },
    Derived {
        name: String,
    },
    And {
        items: Vec<JudgmentExprSpec>,
    },
    Or {
        items: Vec<JudgmentExprSpec>,
    },
    Not {
        item: Box<JudgmentExprSpec>,
    },
}

impl JudgmentExprSpec {
    fn to_model(&self) -> Result<JudgmentExpr, SpecError> {
        match self {
            Self::Comparison { left, op, right } => Ok(JudgmentExpr::Comparison {
                left: left.to_model()?,
                op: op.to_model(),
                right: right.to_model()?,
            }),
            Self::Derived { name } => Ok(JudgmentExpr::Derived(name.clone())),
            Self::And { items } => Ok(JudgmentExpr::And(
                items
                    .iter()
                    .map(JudgmentExprSpec::to_model)
                    .collect::<Result<Vec<JudgmentExpr>, SpecError>>()?,
            )),
            Self::Or { items } => Ok(JudgmentExpr::Or(
                items
                    .iter()
                    .map(JudgmentExprSpec::to_model)
                    .collect::<Result<Vec<JudgmentExpr>, SpecError>>()?,
            )),
            Self::Not { item } => Ok(JudgmentExpr::Not(Box::new(item.to_model()?))),
        }
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ComparisonOpSpec {
    Lt,
    Lte,
    Gt,
    Gte,
    Eq,
    Ne,
}

impl ComparisonOpSpec {
    fn to_model(self) -> ComparisonOp {
        match self {
            Self::Lt => ComparisonOp::Lt,
            Self::Lte => ComparisonOp::Lte,
            Self::Gt => ComparisonOp::Gt,
            Self::Gte => ComparisonOp::Gte,
            Self::Eq => ComparisonOp::Eq,
            Self::Ne => ComparisonOp::Ne,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum JudgmentOutcomeSpec {
    Holds,
    NotHolds,
    Undetermined,
}

impl From<JudgmentOutcome> for JudgmentOutcomeSpec {
    fn from(value: JudgmentOutcome) -> Self {
        match value {
            JudgmentOutcome::Holds => Self::Holds,
            JudgmentOutcome::NotHolds => Self::NotHolds,
            JudgmentOutcome::Undetermined => Self::Undetermined,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct PeriodSpec {
    #[serde(flatten)]
    pub kind: PeriodKindSpec,
    pub start: NaiveDate,
    pub end: NaiveDate,
}

impl PeriodSpec {
    pub fn to_model(&self) -> Result<Period, SpecError> {
        Ok(Period {
            kind: self.kind.to_model(),
            start: self.start,
            end: self.end,
        })
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "period_kind", rename_all = "snake_case")]
pub enum PeriodKindSpec {
    Month,
    BenefitWeek,
    TaxYear,
    Custom { name: String },
}

impl PeriodKindSpec {
    fn to_model(&self) -> PeriodKind {
        match self {
            Self::Month => PeriodKind::Month,
            Self::BenefitWeek => PeriodKind::BenefitWeek,
            Self::TaxYear => PeriodKind::TaxYear,
            Self::Custom { name } => PeriodKind::Custom(name.clone()),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct IntervalSpec {
    pub start: NaiveDate,
    pub end: NaiveDate,
}

impl IntervalSpec {
    fn to_model(&self) -> Interval {
        Interval {
            start: self.start,
            end: self.end,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct InputRecordSpec {
    pub name: String,
    pub entity: String,
    pub entity_id: String,
    pub interval: IntervalSpec,
    pub value: ScalarValueSpec,
}

impl InputRecordSpec {
    fn to_model(&self) -> Result<InputRecord, SpecError> {
        Ok(InputRecord {
            name: self.name.clone(),
            entity: self.entity.clone(),
            entity_id: self.entity_id.clone(),
            interval: self.interval.to_model(),
            value: self.value.to_model()?,
        })
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RelationRecordSpec {
    pub name: String,
    pub tuple: Vec<String>,
    pub interval: IntervalSpec,
}

impl RelationRecordSpec {
    fn to_model(&self) -> Result<RelationRecord, SpecError> {
        Ok(RelationRecord {
            name: self.name.clone(),
            tuple: self.tuple.clone(),
            interval: self.interval.to_model(),
        })
    }
}
