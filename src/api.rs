use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::compile::CompiledProgramArtifact;
use crate::engine::{Engine, EvalError};
use crate::model::{DerivedSemantics, JudgmentOutcome};
use crate::spec::{
    DTypeSpec, DatasetSpec, JudgmentOutcomeSpec, PeriodSpec, ProgramSpec, ScalarValueSpec,
};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExecutionRequest {
    pub mode: ExecutionMode,
    pub program: ProgramSpec,
    pub dataset: DatasetSpec,
    pub queries: Vec<ExecutionQuery>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompiledExecutionRequest {
    pub mode: ExecutionMode,
    pub dataset: DatasetSpec,
    pub queries: Vec<ExecutionQuery>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionMode {
    Explain,
    Fast,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExecutionQuery {
    pub entity_id: String,
    pub period: PeriodSpec,
    pub outputs: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExecutionResponse {
    pub metadata: ExecutionMetadata,
    pub results: Vec<QueryResult>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExecutionMetadata {
    pub requested_mode: ExecutionMode,
    pub actual_mode: ExecutionMode,
    pub fallback_reason: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct QueryResult {
    pub entity_id: String,
    pub period: PeriodSpec,
    pub outputs: BTreeMap<String, OutputValue>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum OutputValue {
    Scalar {
        dtype: DTypeSpec,
        unit: Option<String>,
        value: ScalarValueSpec,
    },
    Judgment {
        unit: Option<String>,
        outcome: JudgmentOutcomeSpec,
    },
}

#[derive(Debug, Error)]
pub enum ApiError {
    #[error(transparent)]
    Eval(#[from] EvalError),
    #[error(transparent)]
    Spec(#[from] crate::spec::SpecError),
}

pub fn execute_request(request: ExecutionRequest) -> Result<ExecutionResponse, ApiError> {
    let requested_mode = request.mode.clone();
    let program = request.program.to_program()?;
    let dataset = request.dataset.to_dataset()?;

    match requested_mode {
        ExecutionMode::Explain => execute_explain(
            &program,
            &dataset,
            request.queries,
            ExecutionMetadata {
                requested_mode: ExecutionMode::Explain,
                actual_mode: ExecutionMode::Explain,
                fallback_reason: None,
            },
        ),
        ExecutionMode::Fast => match crate::bulk::try_execute(&program, &dataset, &request.queries)? {
            crate::bulk::FastPathResult::Executed(response) => Ok(response.with_metadata(
                ExecutionMetadata {
                    requested_mode: ExecutionMode::Fast,
                    actual_mode: ExecutionMode::Fast,
                    fallback_reason: None,
                },
            )),
            crate::bulk::FastPathResult::Unsupported { reason } => execute_explain(
                &program,
                &dataset,
                request.queries,
                ExecutionMetadata {
                    requested_mode: ExecutionMode::Fast,
                    actual_mode: ExecutionMode::Explain,
                    fallback_reason: Some(reason),
                },
            ),
        },
    }
}

pub fn execute_compiled_request(
    artifact: CompiledProgramArtifact,
    request: CompiledExecutionRequest,
) -> Result<ExecutionResponse, ApiError> {
    execute_request(ExecutionRequest {
        mode: request.mode,
        program: artifact.program,
        dataset: request.dataset,
        queries: request.queries,
    })
}

fn execute_explain(
    program: &crate::model::Program,
    dataset: &crate::model::DataSet,
    queries: Vec<ExecutionQuery>,
    metadata: ExecutionMetadata,
) -> Result<ExecutionResponse, ApiError> {
    let mut engine = Engine::new(&program, &dataset);
    let mut results = Vec::with_capacity(queries.len());

    for query in queries {
        let period = query.period.to_model()?;
        let mut outputs = BTreeMap::new();

        for output_name in query.outputs {
            let derived = program
                .derived
                .get(&output_name)
                .ok_or_else(|| EvalError::UnknownDerived(output_name.clone()))?;

            match &derived.semantics {
                DerivedSemantics::Scalar(_) => {
                    let value = engine.evaluate_scalar(&output_name, &query.entity_id, &period)?;
                    outputs.insert(
                        output_name,
                        OutputValue::Scalar {
                            dtype: DTypeSpec::from_model(&derived.dtype),
                            unit: derived.unit.clone(),
                            value: ScalarValueSpec::from_model(value),
                        },
                    );
                }
                DerivedSemantics::Judgment(_) => {
                    let outcome =
                        engine.evaluate_judgment(&output_name, &query.entity_id, &period)?;
                    outputs.insert(
                        output_name,
                        OutputValue::Judgment {
                            unit: derived.unit.clone(),
                            outcome: match outcome {
                                JudgmentOutcome::Holds => JudgmentOutcomeSpec::Holds,
                                JudgmentOutcome::NotHolds => JudgmentOutcomeSpec::NotHolds,
                                JudgmentOutcome::Undetermined => JudgmentOutcomeSpec::Undetermined,
                            },
                        },
                    );
                }
            }
        }

        results.push(QueryResult {
            entity_id: query.entity_id,
            period: query.period,
            outputs,
        });
    }

    Ok(ExecutionResponse { metadata, results })
}

impl ExecutionResponse {
    pub fn with_metadata(mut self, metadata: ExecutionMetadata) -> Self {
        self.metadata = metadata;
        self
    }
}
