from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from evaluation.models import Verdict
from persistence.models import RunBundle


class PersistenceError(RuntimeError):
    pass


class DuplicateRunError(PersistenceError):
    pass


class RunSummary(BaseModel):
    run_id: UUID | str
    created_at: datetime
    scenario_id: str
    scenario_version: int
    agent_name: str
    agent_version: str
    overall_verdict: Verdict
    taxonomy_version: str
    root_cause_count: int
    classification_count: int


class RunRepository(Protocol):
    async def save(self, bundle: RunBundle) -> None:
        ...

    async def get(self, run_id: UUID | str) -> RunBundle | None:
        ...

    async def list_recent(self, limit: int = 20) -> list[RunSummary]:
        ...

    async def exists(self, run_id: UUID | str) -> bool:
        ...
