import pytest
from pydantic import ValidationError

from dag.models import EvaluationDAG, RootCauseReport
from evaluation.models import EvaluationReport
from evaluation.taxonomy.models import FailureClassificationReport
from persistence.models import RunBundle
from persistence.serialization import bundle_to_dict
from tests.persistence_helpers import build_bundle
from tracing.models import ExecutionTrace


def test_bundle_preserves_complete_pipeline(evaluation_context) -> None:
    bundle = build_bundle(evaluation_context)
    assert bundle.run_id == evaluation_context.execution_trace.run_id
    assert bundle.schema_version == "1.0"
    assert isinstance(bundle.execution_trace, ExecutionTrace)
    assert isinstance(bundle.evaluation_report, EvaluationReport)
    assert isinstance(bundle.evaluation_dag, EvaluationDAG)
    assert isinstance(bundle.root_cause_report, RootCauseReport)
    assert isinstance(bundle.failure_classification_report, FailureClassificationReport)
    assert bundle.agent_name == evaluation_context.agent_result.agent_metadata.name


def test_bundle_factory_does_not_retain_runtime_references(evaluation_context) -> None:
    bundle = build_bundle(evaluation_context)
    evaluation_context.agent_result.answer = "changed after snapshot"
    assert bundle.agent_result.answer != evaluation_context.agent_result.answer


def test_bundle_rejects_inconsistent_run_ids(evaluation_context) -> None:
    data = bundle_to_dict(build_bundle(evaluation_context))
    data["evaluation_report"]["run_id"] = "another-run"
    with pytest.raises(ValidationError, match="inconsistent run IDs"):
        RunBundle.model_validate(data)
