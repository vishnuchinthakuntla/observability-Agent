"""
Response schemas for trace queries.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ObservationOut(BaseModel):
    """Observation response schema."""
    
    id: str
    type: str
    name: Optional[str] = None
    status: str = "success"
    latency_ms: Optional[int] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    # LLM-specific fields (only for generation type)
    llm_model: Optional[str] = None
    llm_provider: Optional[str] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None


class TraceOut(BaseModel):
    """Trace response schema."""
    
    id: str
    external_trace_id: Optional[str] = None
    name: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    status: str = "success"
    latency_ms: Optional[int] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    observations: List[ObservationOut] = []


class TraceListResponse(BaseModel):
    """Paginated trace list response."""
    
    data: List[TraceOut]
    total: int
    limit: int
    offset: int
    has_next: bool


class CostByModel(BaseModel):
    """Cost breakdown by model."""
    
    model: str
    cost_usd: float
    tokens: int
    calls: int


class CostSummaryResponse(BaseModel):
    """Cost summary response."""
    
    total_cost_usd: float
    total_tokens: int
    total_traces: int
    total_llm_calls: int
    breakdown_by_model: List[CostByModel] = []