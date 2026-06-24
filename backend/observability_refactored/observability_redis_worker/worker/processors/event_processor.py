"""Event processor for different event types"""

import uuid
import logging
from typing import Dict, Any, List
from datetime import datetime

from observability_redis_worker.worker.services.db_service import db_service
from shared.shared.core.cost_calculator import compute_cost

logger = logging.getLogger(__name__)


class EventProcessor:
    """Process individual events and prepare for DB insertion"""

    @staticmethod
    def process_trace(event: Dict[str, Any], project_id: str) -> Dict[str, Any]:
        """Process trace event"""
        return {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "external_trace_id": event.get("trace_id"),
            "name": event.get("name"),
            "user_id": event.get("user_id"),
            "session_id": event.get("session_id"),
            "input": event.get("input"),
            "output": event.get("output"),
            "metadata": event.get("metadata"),
            "status": event.get("status", "success"),
            "latency_ms": event.get("latency_ms"),
            "created_at": event.get("created_at", datetime.utcnow().isoformat())
        }

    @staticmethod
    def process_span(event: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        """Process span event"""
        return {
            "id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "external_span_id": event.get("span_id"),
            "parent_span_id": event.get("parent_span_id"),
            "name": event.get("name"),
            "type": "CHAIN",
            "input": event.get("input"),
            "output": event.get("output"),
            "status": event.get("status", "success"),
            "latency_ms": event.get("latency_ms"),
            "created_at": event.get("created_at", datetime.utcnow().isoformat())
        }

    @staticmethod
    def process_generation(event: Dict[str, Any], trace_id: str, project_id: str) -> tuple:
        """Process generation event - returns (observation, llm_metadata)"""
        observation_id = str(uuid.uuid4())

        observation = {
            "id": observation_id,
            "trace_id": trace_id,
            "name": event.get("name", "llm-call"),
            "type": "LLM",
            "input": event.get("input"),
            "output": event.get("output"),
            "latency_ms": event.get("latency_ms"),
            "created_at": event.get("created_at", datetime.utcnow().isoformat())
        }

        # Calculate cost if not provided
        cost = event.get("cost_usd")
        if not cost and event.get("prompt_tokens") and event.get("completion_tokens"):
            cost = compute_cost(
                event.get("model", ""),
                event.get("prompt_tokens", 0),
                event.get("completion_tokens", 0)
            )

        llm_metadata = {
            "observation_id": observation_id,
            "trace_id": trace_id,  

            "project_id": project_id,
            "model": event.get("model"),
            "provider": event.get("provider"),
            "prompt_tokens": event.get("prompt_tokens", 0),
            "completion_tokens": event.get("completion_tokens", 0),
            "total_tokens": event.get("total_tokens", 0),
            "cost_usd": cost,
            "finish_reason": event.get("finish_reason"),
            "created_at": datetime.utcnow().isoformat()
        }

        return observation, llm_metadata

    @staticmethod
    def process_tool_call(event: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        """Process tool call event"""
        return {
            "id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "name": event.get("tool_name"),
            "type": "TOOL",
            "input": event.get("input"),
            "output": event.get("output"),
            "metadata": {
                "tool_type": event.get("tool_type"),
                "success": event.get("success", True),
                "error_message": event.get("error_message")
            },
            "latency_ms": event.get("latency_ms"),
            "created_at": event.get("created_at", datetime.utcnow().isoformat())
        }

    @staticmethod
    def process_event_log(event: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        """Process event log"""
        return {
            "id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "name": event.get("name"),
            "type": "EVENT",
            "metadata": {
                "level": event.get("level", "INFO"),
                "message": event.get("message")
            },
            "created_at": event.get("created_at", datetime.utcnow().isoformat())
        }