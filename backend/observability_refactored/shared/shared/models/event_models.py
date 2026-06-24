"""Pydantic models for events (shared between SDK, API, Worker)"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from enum import Enum


class EventType(str, Enum):
    TRACE = "trace"
    SPAN = "span"
    GENERATION = "generation"
    TOOL_CALL = "tool_call"
    EVENT = "event"


class BaseEvent(BaseModel):
    type: EventType
    trace_id: str
    name: Optional[str] = None
    latency_ms: Optional[int] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class TraceEvent(BaseEvent):
    type: EventType = EventType.TRACE
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    status: str = "success"


class SpanEvent(BaseEvent):
    type: EventType = EventType.SPAN
    parent_span_id: Optional[str] = None
    status: str = "success"


class GenerationEvent(BaseEvent):
    type: EventType = EventType.GENERATION
    model: str
    provider: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    finish_reason: Optional[str] = None


class ToolCallEvent(BaseEvent):
    type: EventType = EventType.TOOL_CALL
    tool_name: str
    tool_type: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class EventLog(BaseEvent):
    type: EventType = EventType.EVENT
    level: str = "INFO"
    message: str = ""


class IngestPayload(BaseModel):
    """Payload sent from SDK to API"""
    project_id: str
    events: List[Union[TraceEvent, SpanEvent, GenerationEvent, ToolCallEvent, EventLog]]