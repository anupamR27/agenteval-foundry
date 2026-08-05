from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from persistence.models import RunBundle
from persistence.postgres.config import PostgresConfig
from persistence.postgres.models import (
    FaultActivationRecordRow,
    GradeResultRecord,
    RunRecord,
    TraceSpanRecord,
)
from persistence.repository import DuplicateRunError, PersistenceError, RunSummary
from persistence.serialization import bundle_from_dict, bundle_to_dict


class PostgresRunRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._owned_engine: AsyncEngine | None = None

    @classmethod
    def from_config(cls, config: PostgresConfig) -> "PostgresRunRepository":
        from persistence.postgres.session import create_engine, create_session_factory

        try:
            engine = create_engine(config)
        except (SQLAlchemyError, ValueError) as exc:
            raise PersistenceError(f"Could not configure PostgreSQL persistence: {exc}") from exc
        repository = cls(create_session_factory(engine))
        repository._owned_engine = engine
        return repository

    async def close(self) -> None:
        if self._owned_engine is not None:
            try:
                await self._owned_engine.dispose()
            except (SQLAlchemyError, ValueError) as exc:
                raise PersistenceError(f"Could not close PostgreSQL persistence: {exc}") from exc
            finally:
                self._owned_engine = None

    async def save(self, bundle: RunBundle) -> None:
        run_id = self._uuid(bundle.run_id)
        try:
            async with self._session_factory() as session, session.begin():
                if await session.get(RunRecord, run_id) is not None:
                    raise DuplicateRunError(f"Run already exists: {run_id}")
                session.add(self._build_run_row(bundle, run_id))
                session.add_all(self._build_child_rows(bundle, run_id))
        except DuplicateRunError:
            raise
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise DuplicateRunError(f"Run already exists: {run_id}") from exc
            raise PersistenceError(f"Could not save run {run_id}: {exc}") from exc
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not save run {run_id}: {exc}") from exc

    async def get(self, run_id: UUID | str) -> RunBundle | None:
        resolved = self._uuid(run_id)
        try:
            async with self._session_factory() as session:
                row = await session.get(RunRecord, resolved)
                return bundle_from_dict(row.bundle_json) if row is not None else None
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not retrieve run {resolved}: {exc}") from exc

    async def list_recent(self, limit: int = 20) -> list[RunSummary]:
        if limit < 1:
            raise ValueError("limit must be positive")
        statement = (
            select(
                RunRecord.run_id,
                RunRecord.created_at,
                RunRecord.scenario_id,
                RunRecord.scenario_version,
                RunRecord.agent_name,
                RunRecord.agent_version,
                RunRecord.overall_verdict,
                RunRecord.taxonomy_version,
                RunRecord.root_cause_count,
                RunRecord.classification_count,
            )
            .order_by(RunRecord.created_at.desc(), RunRecord.run_id.desc())
            .limit(limit)
        )
        try:
            async with self._session_factory() as session:
                rows = (await session.execute(statement)).all()
                return [RunSummary.model_validate(row._mapping) for row in rows]
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not list recent runs: {exc}") from exc

    async def exists(self, run_id: UUID | str) -> bool:
        resolved = self._uuid(run_id)
        try:
            async with self._session_factory() as session:
                return await session.get(RunRecord, resolved) is not None
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not check run {resolved}: {exc}") from exc

    def _build_run_row(self, bundle: RunBundle, run_id: UUID) -> RunRecord:
        return RunRecord(
            run_id=run_id,
            created_at=bundle.created_at,
            schema_version=bundle.schema_version,
            scenario_id=bundle.scenario.id,
            scenario_version=bundle.scenario.version,
            agent_name=bundle.agent_name,
            agent_version=bundle.agent_version,
            overall_verdict=bundle.evaluation_report.overall_verdict,
            taxonomy_version=bundle.failure_classification_report.taxonomy_version,
            root_cause_count=len(bundle.root_cause_report.attributions),
            classification_count=len(bundle.failure_classification_report.classifications),
            bundle_json=bundle_to_dict(bundle),
        )

    def _build_child_rows(self, bundle: RunBundle, run_id: UUID) -> list[object]:
        rows: list[object] = []
        for position, span in enumerate(bundle.execution_trace.spans):
            span_json = span.model_dump(mode="json")
            rows.append(TraceSpanRecord(
                span_id=span.span_id,
                run_id=run_id,
                parent_span_id=span.parent_span_id,
                node_type=span.node_type,
                name=span.name,
                status=span.status,
                started_at=span.started_at,
                ended_at=span.ended_at,
                latency_ms=span.latency_ms,
                input_data=span_json["input_data"],
                output_data=span_json["output_data"],
                error=span.error,
                metadata_json=span_json["metadata"],
                position=position,
            ))
        for position, grade in enumerate(bundle.evaluation_report.grades):
            rows.append(GradeResultRecord(
                id=self._child_id(run_id, "grade", position),
                run_id=run_id,
                target_span_id=grade.target_span_id,
                grader_name=grade.grader_name,
                grader_version=grade.grader_version,
                evaluation_level=grade.level,
                verdict=grade.verdict,
                score=grade.score,
                summary=grade.summary,
                evidence=[item.model_dump(mode="json") for item in grade.evidence],
                metadata_json=grade.metadata,
                position=position,
            ))
        for position, fault in enumerate(bundle.fault_activation_records):
            rows.append(FaultActivationRecordRow(
                id=self._child_id(run_id, "fault", position),
                run_id=run_id,
                fault_id=fault.fault_id,
                fault_type=fault.fault_type,
                target_tool=fault.target_tool,
                call_number=fault.call_number,
                activated=fault.activated,
                reason=fault.reason,
                parameters=fault.parameters,
                activated_at=fault.timestamp,
                position=position,
            ))
        return rows

    @staticmethod
    def _child_id(run_id: UUID, kind: str, position: int) -> UUID:
        return uuid5(NAMESPACE_URL, f"agenteval:{run_id}:{kind}:{position}")

    @staticmethod
    def _uuid(value: UUID | str) -> UUID:
        try:
            return value if isinstance(value, UUID) else UUID(value)
        except ValueError as exc:
            raise PersistenceError(f"PostgreSQL persistence requires a UUID run ID: {value}") from exc
