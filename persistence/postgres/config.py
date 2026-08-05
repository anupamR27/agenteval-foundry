import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_DATABASE_URL = "postgresql+psycopg://agenteval:agenteval@localhost:5432/agenteval"


@dataclass(frozen=True)
class PostgresConfig:
    database_url: str = DEFAULT_DATABASE_URL

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> "PostgresConfig":
        values = os.environ if environment is None else environment
        return cls(database_url=values.get("DATABASE_URL") or DEFAULT_DATABASE_URL)
