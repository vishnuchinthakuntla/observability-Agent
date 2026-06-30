"""
Trace, observation, span, and LLM-span routes.
All DB access via TelemetryRepository — zero raw SQL.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.helpers import DateRangePreset, resolve_date_range
from api.repositories.telemetry_repository import TelemetryRepository
from api.routers.auth import get_current_user
from shared.shared.models.telemetry import User

router = APIRouter(tags=["Traces & Spans"])


def _repo(db: AsyncSession) -> TelemetryRepository:
    return TelemetryRepository(db)


# ── 1. List traces ────────────────────────────────────────────────────

@router.get("/traces")
async def get_traces(
    date_range: Optional[DateRangePreset] = Query(None, description="5m 30m 1h 3h 1d 7d 30d 90d 1y"),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    search:     Optional[str] = Query(None, description="Search by trace name or id"),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
    repo = _repo(db)

    project_id = None if current_user.is_admin else current_user.project_id

    result = await repo.list_traces(
        project_id=project_id,
        from_dt=from_dt,
        to_dt=to_dt,
        search=search,
        page=page,
        page_size=page_size,
    )
    return {
        "data":      result["rows"],
        "total":     result["total"],
        "page":      page,
        "page_size": page_size,
        "pages":     (result["total"] + page_size - 1) // page_size,
        "from_time": from_dt.isoformat() if from_dt else None,
        "to_time":   to_dt.isoformat()   if to_dt   else None,
    }


# ── 2. Single trace detail ───────────────────────────────────────────

@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
    return await _repo(db).get_trace(trace_id)


# ── 3. Observations list ─────────────────────────────────────────────

@router.get("/observations")
async def get_observations(
    date_range:  Optional[DateRangePreset] = Query(None),
    from_time:   Optional[str] = Query(None),
    to_time:     Optional[str] = Query(None),
    trace_id:    Optional[str] = Query(None, description="Filter by trace"),
    agent_name:  Optional[str] = Query(None, description="Filter by span name (agent)"),
    obs_type:    Optional[str] = Query(None, description="Filter by type: CHAIN / LLM"),
    status:      Optional[str] = Query(None, description="Filter by status: success / error"),
    page:        int           = Query(1, ge=1),
    page_size:   int           = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
    result = await _repo(db).list_observations(
        from_dt=from_dt, to_dt=to_dt,
        trace_id=trace_id, agent_name=agent_name,
        obs_type=obs_type, status=status,
        page=page, page_size=page_size,
    )
    return {
        "data":      result["rows"],
        "total":     result["total"],
        "page":      page,
        "page_size": page_size,
        "from_time": from_dt.isoformat() if from_dt else None,
        "to_time":   to_dt.isoformat()   if to_dt   else None,
    }


# ── 4. Spans for a trace ─────────────────────────────────────────────

@router.get("/traces/{trace_id}/spans")
async def get_trace_spans(trace_id: str, db: AsyncSession = Depends(get_db)):
    return await _repo(db).get_trace_spans(trace_id)


# ── 5. Single span ───────────────────────────────────────────────────

@router.get("/spans/{observation_id}")
async def get_span(observation_id: str, db: AsyncSession = Depends(get_db)):
    return await _repo(db).get_span(observation_id)


# ── 6. LLM spans ─────────────────────────────────────────────────────

@router.get("/llm-spans")
async def get_llm_spans(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
    return await _repo(db).list_llm_spans(from_dt, to_dt)


@router.get("/llm-spans/{observation_id}")
async def get_llm_span(observation_id: str, db: AsyncSession = Depends(get_db)):
    return await _repo(db).get_llm_span(observation_id)


@router.get("/traces/{trace_id}/llm-spans")
async def get_trace_llm_spans(trace_id: str, db: AsyncSession = Depends(get_db)):
    return await _repo(db).get_trace_llm_spans(trace_id)


# ── 7. Trace tree ────────────────────────────────────────────────────

@router.get("/traces/{trace_id}/tree")
async def get_trace_tree(trace_id: str, db: AsyncSession = Depends(get_db)):
    return await _repo(db).get_trace_spans(trace_id)
