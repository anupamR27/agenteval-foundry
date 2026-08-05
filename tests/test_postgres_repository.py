import os
from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select

from faults.models import FaultActivationRecord, FaultType
from persistence.postgres.config import PostgresConfig
from persistence.postgres.models import (
    FaultActivationRecordRow,
    GradeResultRecord,
    RunRecord,
    TraceSpanRecord,
)
from persistence.postgres.repository import PostgresRunRepository
from persistence.postgres.session import create_engine, create_session_factory
from persistence.repository import DuplicateRunError, PersistenceError
from tests.persistence_helpers import build_bundle, replace_run_id

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration_db,
    pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"),
]


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> Iterator[None]:
    assert TEST_DATABASE_URL is not None
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")
    yield
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous


@pytest_asyncio.fixture
async def repository() -> AsyncIterator[PostgresRunRepository]:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(PostgresConfig(TEST_DATABASE_URL))
    instance = PostgresRunRepository(create_session_factory(engine))
    yield instance
    await engine.dispose()


async def delete_runs(repository: PostgresRunRepository, run_ids: list[UUID]) -> None:
    async with repository._session_factory() as session, session.begin():
        await session.execute(delete(RunRecord).where(RunRecord.run_id.in_(run_ids)))


@pytest.mark.asyncio
async def test_save_get_round_trip(repository, evaluation_context) -> None:
    bundle = replace_run_id(build_bundle(evaluation_context), uuid4())
    try:
        await repository.save(bundle)
        assert await repository.get(bundle.run_id) == bundle
        assert await repository.exists(bundle.run_id)
    finally:
        await delete_runs(repository, [UUID(str(bundle.run_id))])


@pytest.mark.asyncio
async def test_normalized_rows_are_inserted(repository, evaluation_context) -> None:
    bundle = replace_run_id(build_bundle(evaluation_context), uuid4())
    fault = FaultActivationRecord(
        fault_id="integration-fault",
        fault_type=FaultType.TOOL_TIMEOUT,
        target_tool="search_policy",
        call_number=1,
        activated=True,
        reason="normalized row integration test",
    )
    bundle = bundle.model_copy(update={"fault_activation_records": (fault,)})
    run_id = UUID(str(bundle.run_id))
    try:
        await repository.save(bundle)
        async with repository._session_factory() as session:
            span_count = await session.scalar(
                select(func.count()).select_from(TraceSpanRecord).where(
                    TraceSpanRecord.run_id == run_id
                )
            )
            grade_count = await session.scalar(
                select(func.count()).select_from(GradeResultRecord).where(
                    GradeResultRecord.run_id == run_id
                )
            )
            fault_count = await session.scalar(
                select(func.count()).select_from(FaultActivationRecordRow).where(
                    FaultActivationRecordRow.run_id == run_id
                )
            )
        assert span_count == len(bundle.execution_trace.spans)
        assert grade_count == len(bundle.evaluation_report.grades)
        assert fault_count == len(bundle.fault_activation_records)
    finally:
        await delete_runs(repository, [run_id])


@pytest.mark.asyncio
async def test_duplicate_run_is_rejected(repository, evaluation_context) -> None:
    bundle = replace_run_id(build_bundle(evaluation_context), uuid4())
    try:
        await repository.save(bundle)
        with pytest.raises(DuplicateRunError):
            await repository.save(bundle)
    finally:
        await delete_runs(repository, [UUID(str(bundle.run_id))])


@pytest.mark.asyncio
async def test_transaction_rolls_back_on_child_failure(repository, evaluation_context) -> None:
    class BrokenRepository(PostgresRunRepository):
        def _build_child_rows(self, bundle, run_id):
            rows = super()._build_child_rows(bundle, run_id)
            rows[0].name = None
            return rows

    bundle = replace_run_id(build_bundle(evaluation_context), uuid4())
    broken = BrokenRepository(repository._session_factory)
    with pytest.raises(PersistenceError):
        await broken.save(bundle)
    assert not await repository.exists(bundle.run_id)


@pytest.mark.asyncio
async def test_list_recent_ordering(repository, evaluation_context) -> None:
    first = replace_run_id(build_bundle(evaluation_context), uuid4())
    second = replace_run_id(build_bundle(evaluation_context), uuid4())
    second = second.model_copy(update={"created_at": first.created_at.replace(year=2027)})
    ids = [UUID(str(first.run_id)), UUID(str(second.run_id))]
    try:
        await repository.save(first)
        await repository.save(second)
        recent_ids = [str(item.run_id) for item in await repository.list_recent(limit=2)]
        assert recent_ids == [str(second.run_id), str(first.run_id)]
    finally:
        await delete_runs(repository, ids)
