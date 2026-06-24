"""Ingest request/response schemas"""

from pydantic import BaseModel, Field
from typing import List, Union, Dict, Any, Optional
from datetime import datetime


class TraceEvent(BaseModel):
    type: str = "trace"
    trace_id: str
    name: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    status: str = "success"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SpanEvent(BaseModel):
    type: str = "span"
    trace_id: str
    name: str
    parent_span_id: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    status: str = "success"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GenerationEvent(BaseModel):
    type: str = "generation"
    trace_id: str
    name: Optional[str] = None
    model: str
    provider: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: Optional[int] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ToolCallEvent(BaseModel):
    type: str = "tool_call"
    trace_id: str
    tool_name: str
    tool_type: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EventLog(BaseModel):
    type: str = "event"
    trace_id: str
    name: str
    level: str = "INFO"
    message: str = ""
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IngestRequest(BaseModel):
    events: List[Union[TraceEvent, SpanEvent, GenerationEvent, ToolCallEvent, EventLog]]


class IngestResponse(BaseModel):
    accepted: int
    message: str = "Events queued successfully"