from copy import deepcopy

import pytest

from evaluation.models import Verdict
from persistence.serialization import (
    RunSerializationError,
    bundle_from_dict,
    bundle_from_json,
    bundle_to_dict,
    bundle_to_json,
)
from tests.persistence_helpers import build_bundle, execute_bundle


def test_bundle_round_trip_preserves_typed_values(evaluation_context) -> None:
    bundle = build_bundle(evaluation_context)
    restored = bundle_from_json(bundle_to_json(bundle))
    assert restored == bundle
    assert restored.created_at.tzinfo is not None
    assert restored.evaluation_report.overall_verdict == Verdict.PASS
    assert restored.execution_trace.trace_id == bundle.execution_trace.trace_id


@pytest.mark.asyncio
async def test_failed_bad_retrieval_bundle_round_trips() -> None:
    bundle = await execute_bundle("bad_retrieval.yaml")
    assert bundle_from_dict(bundle_to_dict(bundle)) == bundle
    assert bundle.evaluation_report.overall_verdict == Verdict.FAIL
    assert bundle.failure_classification_report.classifications[0].taxonomy_path.level1 == (
        "RETRIEVAL"
    )


def test_malformed_bundle_data_is_rejected() -> None:
    with pytest.raises(RunSerializationError, match="Malformed RunBundle"):
        bundle_from_dict({"run_id": "incomplete"})
    with pytest.raises(RunSerializationError, match="root value must be an object"):
        bundle_from_json("[]")


def test_serialized_bundle_has_no_obvious_secret_fields(evaluation_context) -> None:
    data = deepcopy(bundle_to_dict(build_bundle(evaluation_context)))
    serialized = str(data).casefold()
    assert "database_url" not in serialized
    assert "groq" not in serialized
    assert "api_key" not in serialized
