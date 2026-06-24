"""
Database service for worker operations using shared ORM models.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from shared.shared.models.telemetry import (
    Trace,
    Observation,
    SpanLLMMetadata,
)

logger = logging.getLogger(__name__)


def parse_datetime(value):
    """Convert ISO string -> datetime."""
    if value is None:
        return datetime.utcnow()

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            logger.warning(f"Failed to parse datetime: {value}")
            return datetime.utcnow()

    return value


class DatabaseService:
    """ORM-based database operations."""

    async def upsert_trace(
        self,
        db: AsyncSession,
        trace_data: Dict[str, Any],
    ) -> str:
        """Insert or update a trace, return its ID."""
        external_id: Optional[str] = trace_data.get("external_trace_id")
        project_id: Optional[str] = trace_data.get("project_id")

        if not project_id:
            logger.error("Cannot upsert trace without project_id")
            raise ValueError("project_id is required")

        trace = None

        # Try to find existing trace by external ID
        if external_id:
            result = await db.execute(
                select(Trace).where(
                    Trace.external_trace_id == external_id,
                    Trace.project_id == project_id
                )
            )
            trace = result.scalar_one_or_none()

        if trace:
            # Update existing trace
            trace.name = trace_data.get("name")
            trace.user_id = trace_data.get("user_id")
            trace.session_id = trace_data.get("session_id")
            trace.input = trace_data.get("input")
            trace.output = trace_data.get("output")
            trace.trace_metadata = trace_data.get("metadata")
            trace.status = trace_data.get("status", "success")
            trace.latency_ms = trace_data.get("latency_ms")
            trace.updated_at = datetime.utcnow()

            await db.flush()
            logger.debug(f"Updated trace: {trace.id}")
            return trace.id

        # Create new trace
        trace = Trace(
            project_id=project_id,
            external_trace_id=external_id,
            name=trace_data.get("name"),
            user_id=trace_data.get("user_id"),
            session_id=trace_data.get("session_id"),
            input=trace_data.get("input"),
            output=trace_data.get("output"),
            trace_metadata=trace_data.get("metadata"),
            status=trace_data.get("status", "success"),
            latency_ms=trace_data.get("latency_ms"),
            created_at=parse_datetime(trace_data.get("created_at")),
            updated_at=datetime.utcnow(),
        )

        db.add(trace)
        await db.flush()

        logger.debug(f"Created new trace: {trace.id}")
        return trace.id

    async def insert_observation(
        self,
        db: AsyncSession,
        obs: Dict[str, Any],
    ) -> str:
        """Insert an observation, return its ID."""
        trace_id = obs.get("trace_id")
        if not trace_id:
            logger.error("Cannot insert observation without trace_id")
            raise ValueError("trace_id is required")

        # Check if trace exists
        if not await self.trace_exists(db, trace_id):
            logger.warning(f"Trace {trace_id} does not exist, skipping observation")
            return None

        observation = Observation(
            id=obs.get("id"),
            trace_id=trace_id,
            type=obs.get("type"),
            name=obs.get("name"),
            parent_observation_id=obs.get("parent_observation_id"),
            input=obs.get("input"),
            output=obs.get("output"),
            observation_metadata=obs.get("metadata"),
            status=obs.get("status", "success"),
            latency_ms=obs.get("latency_ms"),
            created_at=parse_datetime(obs.get("created_at")),
        )

        db.add(observation)
        await db.flush()

        logger.debug(f"Inserted observation: {observation.id}")
        return observation.id

    async def insert_llm_metadata(
        self,
        db: AsyncSession,
        meta: Dict[str, Any],
    ) -> Optional[str]:
        """Insert LLM metadata, return its ID."""
        observation_id = meta.get("observation_id")
        if not observation_id:
            logger.error("Cannot insert LLM metadata without observation_id")
            raise ValueError("observation_id is required")

        project_id = meta.get("project_id")
        if not project_id:
            logger.error("Cannot insert LLM metadata without project_id")
            raise ValueError("project_id is required")

        llm_meta = SpanLLMMetadata(
            observation_id=observation_id,
            trace_id=meta.get("trace_id"),
            project_id=project_id,
            model=meta.get("model"),
            provider=meta.get("provider"),
            prompt_tokens=meta.get("prompt_tokens", 0),
            completion_tokens=meta.get("completion_tokens", 0),
            total_tokens=meta.get("total_tokens", 0),
            cost_usd=meta.get("cost_usd", 0.0),
            finish_reason=meta.get("finish_reason"),
        )

        db.add(llm_meta)
        await db.flush()

        logger.debug(f"Inserted LLM metadata for observation: {observation_id}")
        return llm_meta.id

    async def trace_exists(
        self,
        db: AsyncSession,
        trace_id: str,
    ) -> bool:
        """Check if a trace exists."""
        if not trace_id:
            return False

        result = await db.execute(
            select(Trace.id).where(Trace.id == trace_id)
        )
        return result.scalar_one_or_none() is not None

    async def get_trace_by_external_id(
        self,
        db: AsyncSession,
        external_id: str,
        project_id: str,
    ) -> Optional[Trace]:
        """Get a trace by external ID and project ID."""
        if not external_id or not project_id:
            return None

        result = await db.execute(
            select(Trace).where(
                Trace.external_trace_id == external_id,
                Trace.project_id == project_id
            )
        )
        return result.scalar_one_or_none()

    async def get_observations_by_trace(
        self,
        db: AsyncSession,
        trace_id: str,
    ) -> list:
        """Get all observations for a trace."""
        if not trace_id:
            return []

        result = await db.execute(
            select(Observation).where(
                Observation.trace_id == trace_id
            ).order_by(Observation.created_at)
        )
        return result.scalars().all()


db_service = DatabaseService()