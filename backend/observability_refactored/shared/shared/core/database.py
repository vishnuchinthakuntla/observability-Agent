"""
Shared async database connection manager.

Both the API and the worker import this class directly.
Each service passes its own ``settings`` object so the connection URL and
pool sizes remain configurable per-service.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()


class DatabaseManager:
    """Async SQLAlchemy connection-pool manager (singleton per process)."""

    _instance: DatabaseManager | None = None
    _engine: AsyncEngine | None = None
    _sessionmaker: async_sessionmaker | None = None

    # ------------------------------------------------------------------ #
    # Singleton
    # ------------------------------------------------------------------ #
    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def initialize(
        self,
        database_url: str,
        pool_size: int = 10,
        max_overflow: int = 20,
        echo: bool = False,
    ) -> None:
        """Create the engine and session factory (idempotent)."""
        if self._engine is not None:
            return

        self._engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self._sessionmaker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("Database engine initialised")

    async def close(self) -> None:
        """Dispose the engine and reset state."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None
            logger.info("Database engine closed")

    # ------------------------------------------------------------------ #
    # Session helpers
    # ------------------------------------------------------------------ #
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Async-generator that yields a session, commits on success, rolls back on error.
        Designed for use as a FastAPI dependency.
        """
        assert self._sessionmaker, "DatabaseManager not initialised — call initialize() first."
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_session_direct(self) -> AsyncSession:
        """
        Return a bare session for callers that manage commit/rollback themselves
        (e.g. batch processors).
        """
        assert self._sessionmaker, "DatabaseManager not initialised."
        return self._sessionmaker()

    async def create_tables(self) -> None:
        """Create all ORM-registered tables (idempotent via ``checkfirst``)."""
        assert self._engine, "DatabaseManager not initialised."
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


# Module-level singleton
db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a managed session."""
    async for session in db_manager.get_session():
        yield session
