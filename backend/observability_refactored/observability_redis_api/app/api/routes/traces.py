"""
Traces Query API — read telemetry from database via TraceRepository.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from shared.shared.core.database import get_db
from shared.shared.models.telemetry import Observation

from observability_redis_api.app.api.dependencies.auth import require_project
from observability_redis_api.app.repositories.trace_repository import TraceRepository
from observability_redis_api.app.schemas.traces import (
    CostByModel,
    CostSummaryResponse,
    ObservationOut,
    TraceListResponse,
    TraceOut,
)

router = APIRouter(prefix="/api/v1", tags=["Traces & Analytics"])


def _build_observation_out(obs: Observation) -> ObservationOut:
    llm = obs.llm_metadata
    return ObservationOut(
        id=obs.id,
        type=obs.type.value,
        name=obs.name,
        status=obs.status,
        latency_ms=obs.latency_ms,
        input=obs.input,
        output=obs.output,
        created_at=obs.created_at,
        llm_model=llm.model if llm else None,
        llm_provider=llm.provider if llm else None,
        total_tokens=llm.total_tokens if llm else None,
        cost_usd=llm.cost_usd if llm else None,
    )


@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    x_project_id: str = Query(..., description="Your project ID"),
    user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    project_id: str = Depends(require_project),
):
    """List all traces for a project with pagination."""
    repo = TraceRepository(db)
    traces, total = await repo.get_traces(
        project_id=project_id,
        user_id=user_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    data = []
    for trace in traces:
        observations = await repo.get_observations_for_trace(trace.id)
        data.append(
            TraceOut(
                id=trace.id,
                external_trace_id=trace.external_trace_id,
                name=trace.name,
                user_id=trace.user_id,
                session_id=trace.session_id,
                status=trace.status,
                latency_ms=trace.latency_ms,
                input=trace.input,
                output=trace.output,
                created_at=trace.created_at,
                observations=[_build_observation_out(o) for o in observations],
            )
        )

    return TraceListResponse(
        data=data,
        total=total,
        limit=limit,
        offset=offset,
        has_next=(offset + limit) < total,
    )


@router.get("/traces/{trace_id}", response_model=TraceOut)
async def get_trace(
    trace_id: str,
    x_project_id: str = Query(..., description="Your project ID"),
    db: AsyncSession = Depends(get_db),
    project_id: str = Depends(require_project),
):
    """Get a single trace by ID with all its observations."""
    repo = TraceRepository(db)
    trace = await repo.get_trace(trace_id, project_id)

    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    observations = await repo.get_observations_for_trace(trace.id)
    return TraceOut(
        id=trace.id,
        external_trace_id=trace.external_trace_id,
        name=trace.name,
        user_id=trace.user_id,
        session_id=trace.session_id,
        status=trace.status,
        latency_ms=trace.latency_ms,
        input=trace.input,
        output=trace.output,
        created_at=trace.created_at,
        observations=[_build_observation_out(o) for o in observations],
    )


@router.get("/cost-summary", response_model=CostSummaryResponse)
async def get_cost_summary(
    x_project_id: str = Query(..., description="Your project ID"),
    db: AsyncSession = Depends(get_db),
    project_id: str = Depends(require_project),
):
    """Get token usage and cost summary for a project."""
    repo = TraceRepository(db)
    summary = await repo.get_cost_summary(project_id)

    return CostSummaryResponse(
        total_cost_usd=summary["total_cost_usd"],
        total_tokens=summary["total_tokens"],
        total_traces=summary["total_traces"],
        total_llm_calls=summary["total_llm_calls"],
        breakdown_by_model=[CostByModel(**m) for m in summary["breakdown_by_model"]],
    )
