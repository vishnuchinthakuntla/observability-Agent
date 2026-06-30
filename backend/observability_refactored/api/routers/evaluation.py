"""
Evaluation routes — agent daily trends, weekly aggregations, dashboard overview,
project filter, latest score, and summary stats.

All DB access via EvaluationRepository — zero raw SQL.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.repositories.telemetry_repository import EvaluationRepository

router = APIRouter(prefix="/api/evaluation", tags=["Evaluation"])


def _repo(db: AsyncSession) -> EvaluationRepository:
    return EvaluationRepository(db)


# ── 1. Daily trend ───────────────────────────────────────────────────────────

@router.get("/{agent_name}/daily")
async def get_agent_daily_evaluation(
    agent_name: str,
    project_id: Optional[str] = Query(None, description="Filter by project_id (e.g. GCP, GCP1)"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns one row per calendar day for the selected agent.
    Intended for line graphs that show daily metric trends.

    Example usage:
      GET /api/evaluation/rca_agent/daily?days=30
      GET /api/evaluation/rca_agent/daily?project_id=GCP&days=7
    """
    data = await _repo(db).daily(agent_name=agent_name, days=days, project_id=project_id)
    return {
        "status":        "success",
        "agent_name":    agent_name,
        "project_id":    project_id or "ALL",
        "days":          days,
        "total_records": len(data),
        "data":          data,
    }


# ── 2. Weekly aggregation ────────────────────────────────────────────────────

@router.get("/{agent_name}/weekly")
async def get_agent_weekly_evaluation(
    agent_name: str,
    project_id: Optional[str] = Query(None, description="Filter by project_id (e.g. GCP, GCP1)"),
    weeks: int = Query(4, ge=1, le=52, description="Number of weeks to look back"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns one aggregated row per ISO week (Monday–Sunday) for the selected agent.
    All metrics are averaged across days; total_evaluated is summed.
    Intended for bar graphs showing weekly performance.

    Example usage:
      GET /api/evaluation/rca_agent/weekly?weeks=4
      GET /api/evaluation/decision_agent/weekly?project_id=GCP&weeks=8
    """
    data = await _repo(db).weekly(agent_name=agent_name, weeks=weeks, project_id=project_id)
    return {
        "status":        "success",
        "agent_name":    agent_name,
        "project_id":    project_id or "ALL",
        "weeks":         weeks,
        "total_records": len(data),
        "data":          data,
    }


# ── 3. All agents — latest evaluation (dashboard overview) ───────────────────
# NOTE: This route MUST be defined BEFORE /{agent_name}/latest to prevent
#       FastAPI from matching the literal "latest" as an agent_name path param.

@router.get("/latest/all")
async def get_all_agents_latest_evaluation(
    project_id: Optional[str] = Query(None, description="Filter by project_id"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the most recent evaluation row for every agent.
    Intended for the dashboard overview cards.

    Example usage:
      GET /api/evaluation/latest/all
      GET /api/evaluation/latest/all?project_id=GCP
    """
    data = await _repo(db).latest_all(project_id=project_id)
    return {
        "status":       "success",
        "project_id":   project_id or "ALL",
        "total_agents": len(data),
        "data":         data,
    }


# ── 4. Available projects for an agent (filter dropdown) ─────────────────────

@router.get("/{agent_name}/projects")
async def get_agent_projects(
    agent_name: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all distinct project_ids that have evaluation data for the agent.
    Intended for populating the project filter dropdown in the UI.

    Example usage:
      GET /api/evaluation/rca_agent/projects
    """
    projects = await _repo(db).agent_projects(agent_name=agent_name)
    return {
        "status":     "success",
        "agent_name": agent_name,
        "projects":   projects,
    }


# ── 5. Single agent — latest evaluation ──────────────────────────────────────

@router.get("/{agent_name}/latest")
async def get_agent_latest_evaluation(
    agent_name: str,
    project_id: Optional[str] = Query(None, description="Filter by project_id"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the single most recent evaluation row for the given agent.
    Intended for dashboard cards that display current metric scores.

    Example usage:
      GET /api/evaluation/rca_agent/latest
      GET /api/evaluation/rca_agent/latest?project_id=GCP
    """
    data = await _repo(db).agent_latest(agent_name=agent_name, project_id=project_id)
    if data is None:
        return {
            "status":     "success",
            "agent_name": agent_name,
            "project_id": project_id or "ALL",
            "data":       None,
            "message":    "No evaluation data found for this agent",
        }
    return {
        "status":     "success",
        "agent_name": agent_name,
        "project_id": project_id or "ALL",
        "data":       data,
    }


# ── 6. Agent summary statistics ──────────────────────────────────────────────

@router.get("/{agent_name}/stats")
async def get_agent_evaluation_stats(
    agent_name: str,
    project_id: Optional[str] = Query(None, description="Filter by project_id"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns aggregate statistics (avg/min/max, totals) for an agent
    over a configurable rolling window.
    Intended for the stats summary cards.

    Example usage:
      GET /api/evaluation/rca_agent/stats
      GET /api/evaluation/rca_agent/stats?project_id=GCP&days=14
    """
    data = await _repo(db).agent_stats(
        agent_name=agent_name, days=days, project_id=project_id
    )
    if data is None:
        return {
            "status":     "success",
            "agent_name": agent_name,
            "project_id": project_id or "ALL",
            "days":       days,
            "data":       None,
            "message":    "No evaluation data found for this agent/window",
        }
    return {
        "status":     "success",
        "agent_name": agent_name,
        "project_id": project_id or "ALL",
        "days":       days,
        "data":       data,
    }
