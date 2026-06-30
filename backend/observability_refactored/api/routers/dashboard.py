"""
Dashboard routes — home, summary, model-usage, overview metrics,
trace-volume, recent-traces, token-distribution, model-usage-share,
drift-alerts, system-status, and the full overview endpoint.

All DB access via TelemetryRepository — zero raw SQL.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.helpers import DateRangePreset, bucket_granularity, resolve_date_range
from api.repositories.telemetry_repository import TelemetryRepository

router = APIRouter(tags=["Dashboard"])


def _repo(db: AsyncSession) -> TelemetryRepository:
    return TelemetryRepository(db)


def _pct_change(current: dict, previous: dict, key: str) -> Optional[float]:
    cur = float(current.get(key) or 0)
    prev = float(previous.get(key) or 0)
    if prev == 0:
        return None
    return round((cur - prev) / prev * 100, 1)


# ── 8. Dashboard home ────────────────────────────────────────────────

@router.get("/dashboard/home")
async def dashboard_home(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
    trunc = bucket_granularity(from_dt, to_dt)
    repo = _repo(db)

    summary = await repo.dashboard_summary(from_dt, to_dt)
    model_costs = await repo.model_usage(from_dt, to_dt)
    traces_time = await repo.trace_volume(from_dt, to_dt, trunc)

    return {
        "from_time":             from_dt.isoformat() if from_dt else None,
        "to_time":               to_dt.isoformat()   if to_dt   else None,
        "granularity":           trunc,
        "summary":               summary,
        "model_costs":           model_costs,
        "traces_by_time":        traces_time,
    }


# ── 9. Dashboard summary ─────────────────────────────────────────────

@router.get("/dashboard/summary")
async def dashboard_summary(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
    summary = await _repo(db).dashboard_summary(from_dt, to_dt)
    return {
        **summary,
        "from_time": from_dt.isoformat() if from_dt else None,
        "to_time":   to_dt.isoformat()   if to_dt   else None,
    }


# ── 10. Model usage ──────────────────────────────────────────────────

@router.get("/dashboard/model-usage")
async def model_usage(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
    data = await _repo(db).model_usage(from_dt, to_dt)
    return {
        "data":      data,
        "from_time": from_dt.isoformat() if from_dt else None,
        "to_time":   to_dt.isoformat()   if to_dt   else None,
    }


# ── 11. Overview metrics ─────────────────────────────────────────────

@router.get("/dashboard/overview/metrics")
async def overview_metrics(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    cur_start, cur_end = resolve_date_range(date_range, from_time, to_time)
    repo = _repo(db)

    current_kpis = await repo.kpi_metrics(cur_start, cur_end)

    if cur_start and cur_end:
        delta = cur_end - cur_start
        prev_start = cur_start - delta
        prev_end = cur_start
    else:
        prev_start = prev_end = None

    previous_kpis = await repo.kpi_metrics(prev_start, prev_end)

    return {
        "from_time": cur_start.isoformat() if cur_start else None,
        "to_time":   cur_end.isoformat()   if cur_end   else None,
        "current":   current_kpis,
        "previous":  previous_kpis,
        "deltas": {
            "total_traces_pct":       _pct_change(current_kpis, previous_kpis, "total_traces"),
            "success_rate_pp":        round(float(current_kpis.get("success_rate") or 0) - float(previous_kpis.get("success_rate") or 0), 1),
            "avg_latency_ms_delta":   round(float(current_kpis.get("avg_latency_ms") or 0) - float(previous_kpis.get("avg_latency_ms") or 0), 0),
            "total_tokens_pct":       _pct_change(current_kpis, previous_kpis, "total_tokens"),
            "estimated_cost_usd_pct": _pct_change(current_kpis, previous_kpis, "estimated_cost_usd"),
        },
    }


# ── 12. Trace volume ─────────────────────────────────────────────────

@router.get("/dashboard/overview/trace-volume")
async def overview_trace_volume(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    ws, we = resolve_date_range(date_range, from_time, to_time)
    trunc = bucket_granularity(ws, we)
    data = await _repo(db).trace_volume(ws, we, trunc)
    return {
        "granularity": trunc,
        "from_time":   ws.isoformat() if ws else None,
        "to_time":     we.isoformat() if we else None,
        "data":        data,
    }


# ── 13. Recent traces ────────────────────────────────────────────────

@router.get("/dashboard/overview/recent-traces")
async def overview_recent_traces(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    data = await _repo(db).recent_traces(None, None, limit)
    return {"data": data}


# ── 14. Token distribution ───────────────────────────────────────────

@router.get("/dashboard/overview/token-distribution")
async def overview_token_distribution(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    ws, we = resolve_date_range(date_range, from_time, to_time)
    rows = await _repo(db).token_distribution(ws, we)
    grand_total = sum(row["total_tokens"] or 0 for row in rows)
    return {
        "from_time":          ws.isoformat() if ws else None,
        "to_time":            we.isoformat() if we else None,
        "grand_total_tokens": grand_total,
        "data":               rows,
    }


# ── 15. Model usage share ────────────────────────────────────────────

@router.get("/dashboard/overview/model-usage-share")
async def overview_model_usage_share(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    ws, we = resolve_date_range(date_range, from_time, to_time)
    data = await _repo(db).model_usage_share(ws, we)
    return {
        "from_time": ws.isoformat() if ws else None,
        "to_time":   we.isoformat() if we else None,
        "data":      data,
    }


# ── 16. Drift alerts (static demo) ───────────────────────────────────

@router.get("/dashboard/overview/drift-alerts")
async def overview_drift_alerts(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    limit:      int           = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    ws, we = resolve_date_range(date_range, from_time, to_time)
    static_alerts = [
        {"alert_type": "latency_spike",   "severity": "CRIT", "display_title": "sql_query tool spike — 3.2× baseline",      "source": "tool_usage_baselines",  "last_seen": "4m ago"},
        {"alert_type": "model_drift",     "severity": "WARN", "display_title": "Model drift: gpt-4o → gpt-4o-mini",         "source": "observations",          "last_seen": "22m ago"},
        {"alert_type": "prompt_mismatch", "severity": "WARN", "display_title": "Prompt version mismatch in session #9f2a",  "source": "prompt_versions",       "last_seen": "1h ago"},
        {"alert_type": "circuit_breaker", "severity": "INFO", "display_title": "Circuit breaker reset — openai-api",        "source": "circuit_breaker_states", "last_seen": "3h ago"},
    ]
    return {
        "from_time":      ws.isoformat() if ws else None,
        "to_time":        we.isoformat() if we else None,
        "is_static_demo": True,
        "alerts":         static_alerts,
    }


# ── 17. System status ────────────────────────────────────────────────

@router.get("/dashboard/overview/system-status")
async def overview_system_status(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    ws, we = resolve_date_range(date_range, from_time, to_time)
    model_rows = await _repo(db).model_usage_share(ws, we)
    return {
        "from_time":        ws.isoformat() if ws else None,
        "to_time":          we.isoformat() if we else None,
        "is_static_demo":   True,
        "mcp_servers":      8,
        "active_tools":     34,
        "queue_depth":      1204,
        "circuit_breakers": {"tripped_count": 7, "tripped_agents": [], "status": "OK"},
        "overall_health":   "OK",
        "model_usage_share": model_rows,
    }


# ── 18. Full overview ────────────────────────────────────────────────

@router.get("/dashboard/overview")
async def dashboard_overview(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    ws, we = resolve_date_range(date_range, from_time, to_time)
    trunc = bucket_granularity(ws, we)
    repo = _repo(db)

    if ws and we:
        delta = we - ws
        prev_start, prev_end = ws - delta, ws
    else:
        prev_start = prev_end = None

    current_kpis  = await repo.kpi_metrics(ws, we)
    previous_kpis = await repo.kpi_metrics(prev_start, prev_end)
    trace_vol     = await repo.trace_volume(ws, we, trunc)
    recent        = await repo.recent_traces(ws, we, 10)
    token_dist    = await repo.token_distribution(ws, we)
    model_share   = await repo.model_usage_share(ws, we)
    sys_status    = await repo.system_status(ws, we)
    drift         = await repo.drift_alerts(ws, we, 5)

    return {
        "from_time":   ws.isoformat() if ws else None,
        "to_time":     we.isoformat() if we else None,
        "granularity": trunc,
        "metrics": {
            "current":  current_kpis,
            "previous": previous_kpis,
            "deltas": {
                "total_traces_pct":       _pct_change(current_kpis, previous_kpis, "total_traces"),
                "success_rate_pp":        round(float(current_kpis.get("success_rate") or 0) - float(previous_kpis.get("success_rate") or 0), 1),
                "avg_latency_ms_delta":   round(float(current_kpis.get("avg_latency_ms") or 0) - float(previous_kpis.get("avg_latency_ms") or 0), 0),
                "total_tokens_pct":       _pct_change(current_kpis, previous_kpis, "total_tokens"),
                "estimated_cost_usd_pct": _pct_change(current_kpis, previous_kpis, "estimated_cost_usd"),
            },
        },
        "trace_volume":       trace_vol,
        "recent_traces":      recent,
        "token_distribution": token_dist,
        "model_usage_share":  model_share,
        "system_status":      sys_status,
        "drift_alerts":       drift,
    }
