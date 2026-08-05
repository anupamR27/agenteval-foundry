from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from persistence.postgres.config import PostgresConfig


def create_engine(config: PostgresConfig, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(config.database_url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
