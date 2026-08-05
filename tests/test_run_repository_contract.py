from copy import deepcopy
from uuid import UUID, uuid4

import pytest

from persistence.models import RunBundle
from persistence.repository import DuplicateRunError, RunSummary
from persistence.serialization import bundle_from_dict, bundle_to_dict
from tests.persistence_helpers import build_bundle, replace_run_id


class FakeRunRepository:
    def __init__(self) -> None:
        self._bundles: dict[str, RunBundle] = {}

    async def save(self, bundle: RunBundle) -> None:
        key = str(bundle.run_id)
        if key in self._bundles:
            raise DuplicateRunError(f"Run already exists: {key}")
        self._bundles[key] = bundle_from_dict(bundle_to_dict(bundle))

    async def get(self, run_id: UUID | str) -> RunBundle | None:
        bundle = self._bundles.get(str(run_id))
        return deepcopy(bundle) if bundle is not None else None

    async def exists(self, run_id: UUID | str) -> bool:
        return str(run_id) in self._bundles

    async def list_recent(self, limit: int = 20) -> list[RunSummary]:
        bundles = sorted(
            self._bundles.values(),
            key=lambda bundle: (bundle.created_at, str(bundle.run_id)),
            reverse=True,
        )[:limit]
        return [RunSummary(
            run_id=bundle.run_id,
            created_at=bundle.created_at,
            scenario_id=bundle.scenario.id,
            scenario_version=bundle.scenario.version,
            agent_name=bundle.agent_name,
            agent_version=bundle.agent_version,
            overall_verdict=bundle.evaluation_report.overall_verdict,
            taxonomy_version=bundle.failure_classification_report.taxonomy_version,
            root_cause_count=len(bundle.root_cause_report.attributions),
            classification_count=len(bundle.failure_classification_report.classifications),
        ) for bundle in bundles]


@pytest.mark.asyncio
async def test_fake_repository_save_get_exists_and_duplicate(evaluation_context) -> None:
    repository = FakeRunRepository()
    bundle = replace_run_id(build_bundle(evaluation_context), uuid4())
    assert not await repository.exists(bundle.run_id)
    await repository.save(bundle)
    assert await repository.exists(bundle.run_id)
    assert await repository.get(bundle.run_id) == bundle
    with pytest.raises(DuplicateRunError, match="already exists"):
        await repository.save(bundle)


@pytest.mark.asyncio
async def test_fake_repository_recent_order_is_stable(evaluation_context) -> None:
    repository = FakeRunRepository()
    first = replace_run_id(build_bundle(evaluation_context), uuid4())
    second = replace_run_id(build_bundle(evaluation_context), uuid4())
    await repository.save(first)
    await repository.save(second)
    expected = sorted([str(first.run_id), str(second.run_id)], reverse=True)
    assert [str(item.run_id) for item in await repository.list_recent()] == expected
    assert len(await repository.list_recent(limit=1)) == 1
