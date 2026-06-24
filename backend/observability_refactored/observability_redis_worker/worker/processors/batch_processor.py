"""Batch processor — groups events by type and writes them to the database."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import exc

from shared.shared.core.database import db_manager
from observability_redis_worker.worker.processors.event_processor import EventProcessor
from observability_redis_worker.worker.services.db_service import db_service

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Process a batch of mixed telemetry events and persist them atomically."""

    def __init__(self, batch_size: int = 100) -> None:
        self.batch_size = batch_size
        self.event_processor = EventProcessor()

    async def process_batch(self, project_id: str, events: List[Dict[str, Any]]) -> bool:
        """
        Process *events* for *project_id* and write to the database.

        Returns ``True`` on success, ``False`` on failure (caller may DLQ).
        """
        if not events:
            return True

        traces: Dict[str, Dict] = {}
        spans: List[Dict] = []
        generations: List[tuple] = []
        tool_calls: List[Dict] = []
        event_logs: List[Dict] = []

        for event in events:
            etype = event.get("type")
            trace_id = event.get("trace_id")

            if etype == "trace":
                traces[trace_id] = self.event_processor.process_trace(event, project_id)
            elif etype == "span":
                spans.append(self.event_processor.process_span(event, trace_id))
            elif etype == "generation":
                generations.append(self.event_processor.process_generation(event, trace_id, project_id))
            elif etype == "tool_call":
                tool_calls.append(self.event_processor.process_tool_call(event, trace_id))
            elif etype == "event":
                event_logs.append(self.event_processor.process_event_log(event, trace_id))

        try:
            db = await db_manager.get_session_direct()
            async with db:
                trace_id_map = {}
                for external_trace_id, trace_data in traces.items():
                    db_trace_id = await db_service.upsert_trace(
                        db,
                        trace_data,
                    )

                    trace_id_map[external_trace_id] = db_trace_id

                for span in spans:
                    ext_id = span["trace_id"]
                    if ext_id in trace_id_map:
                        span["trace_id"] = trace_id_map[ext_id]
                    await db_service.insert_observation(db, span)

                for observation, llm_meta in generations:
                    ext_id = observation["trace_id"]

                    if ext_id in trace_id_map:
                        # Get the database trace ID corresponding to the external trace ID
                        db_trace_id = trace_id_map[ext_id]

                        # Update both observation and LLM metadata to use the DB trace ID
                        observation["trace_id"] = db_trace_id
                        llm_meta["trace_id"] = db_trace_id

                    # Insert the observation first
                    obs_id = await db_service.insert_observation(
                        db,
                        observation,
                    )

                    # Store the generated observation ID in the LLM metadata
                    llm_meta["observation_id"] = obs_id

                    # Insert the LLM metadata
                    await db_service.insert_llm_metadata(
                        db,
                        llm_meta,
                    )
                for tool in tool_calls:
                    ext_id = tool["trace_id"]
                    if ext_id in trace_id_map:
                        tool["trace_id"] = trace_id_map[ext_id]
                    await db_service.insert_observation(db, tool)
                for elog in event_logs:
                    ext_id = elog["trace_id"]
                    if ext_id in trace_id_map:
                        elog["trace_id"] = trace_id_map[ext_id]
                    await db_service.insert_observation(db, elog)
                await db.commit()

            logger.info(
                f"Batch written: {len(traces)} traces, {len(spans)} spans, "
                f"{len(generations)} generations, {len(tool_calls)} tools "
                f"for project '{project_id}'"
            )
            return True
        
        except Exception as exc:
            import json

            from shared.shared.core.redis_client import get_redis
            from shared.shared.constants.redis_keys import RedisKeys

            logger.error(
                f"Batch write failed for project '{project_id}': {exc}"
            )

            try:
                redis = await get_redis()

                failed_payload = {
                    "project_id": project_id,
                    "events": events,
                    "error": str(exc),
                }

                await redis.rpush(
                    RedisKeys.DLQ,
                    json.dumps(failed_payload),
                )

                logger.warning(
                    f"Moved failed batch to DLQ ({RedisKeys.DLQ})"
                )

            except Exception as dlq_error:
                logger.error(
                    f"Failed to write to DLQ: {dlq_error}"
                )

            return False
 