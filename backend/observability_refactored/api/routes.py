
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from api.database import get_db


router = APIRouter(
    prefix="/custom-api/v1",
    tags=["Observability"],
)


# ===========================================================
# DATE RANGE HELPER
# Presets: 5m 30m 1h 3h 1d 7d 30d 90d 1y
# Or custom: from_time / to_time (ISO 8601)
# None passed -> return (None, None) meaning "no filter / all data"
# ===========================================================

PRESET_MAP = {
    "5m":  timedelta(minutes=5),
    "30m": timedelta(minutes=30),
    "1h":  timedelta(hours=1),
    "3h":  timedelta(hours=3),
    "1d":  timedelta(days=1),
    "7d":  timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "1y":  timedelta(days=365),
}

DateRangePreset = Literal["5m", "30m", "1h", "3h", "1d", "7d", "30d", "90d", "1y"]


def resolve_date_range(
    date_range: Optional[str],
    from_time: Optional[str],
    to_time: Optional[str],
):
    """
    Returns (from_dt, to_dt) as UTC-aware datetimes, OR (None, None) if no
    filter was requested (so callers can show ALL data, like Langfuse default).

    These stay timezone-AWARE on purpose, so API response fields
    (from_time/to_time) keep a correct UTC offset for the caller.
    Use _to_naive_utc() right before binding to SQL — see below.
    """
    now = datetime.now(timezone.utc)

    if date_range:
        if date_range not in PRESET_MAP:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid date_range '{date_range}'. "
                    f"Valid options: {', '.join(PRESET_MAP.keys())}"
                ),
            )
        return now - PRESET_MAP[date_range], now

    if from_time or to_time:
        try:
            from_dt = datetime.fromisoformat(from_time).astimezone(timezone.utc) if from_time else None
            to_dt   = datetime.fromisoformat(to_time).astimezone(timezone.utc)   if to_time   else now
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="from_time/to_time must be valid ISO 8601 datetimes, e.g. 2026-06-18T10:00:00Z",
            )
        return from_dt, to_dt

    return None, None  # no filter -> all data


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Strip tzinfo right before binding to SQL.

    Why this exists: resolve_date_range() always returns timezone-AWARE
    UTC datetimes. But your `created_at` columns in Postgres are
    TIMESTAMP WITHOUT TIME ZONE (naive) — that's why you hit:

        asyncpg.exceptions.DataError: invalid input for query argument $1
        (can't subtract offset-naive and offset-aware datetimes)

    asyncpg's codec for a naive-typed column can't accept a tz-aware
    Python datetime; it does internal arithmetic that assumes naive on
    both sides. This converts to UTC first (so the instant stays
    correct), then drops the tzinfo so it matches what's actually stored.

    If you later migrate created_at columns to TIMESTAMPTZ via Alembic,
    delete this function and bind from_dt/to_dt directly instead.
    """
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _time_filter_sql(alias: str = "") -> str:
    """Returns the WHERE/AND clause fragment for optional time filtering."""
    col = f"{alias}.created_at" if alias else "created_at"
    return f"{col} >= :from_dt AND {col} <= :to_dt"


def _add_time_params(params: dict, from_dt, to_dt):
    if from_dt:
        params["from_dt"] = _to_naive_utc(from_dt)
    if to_dt:
        params["to_dt"] = _to_naive_utc(to_dt)


def _bucket_granularity(from_dt, to_dt) -> str:
    if from_dt is None:
        return "day"
    delta = to_dt - from_dt
    if delta <= timedelta(hours=1):
        return "minute"
    if delta <= timedelta(days=2):
        return "hour"
    if delta <= timedelta(days=60):
        return "day"
    return "week"


# ===========================================================
# 1. TRACING PAGE  —  GET ALL TRACES
#    Like Langfuse "Tracing > Traces" tab
#    Shows every trace with its total spans, latency, cost
# ===========================================================

@router.get("/traces")
async def get_traces(
    date_range: Optional[DateRangePreset] = Query(None, description="5m 30m 1h 3h 1d 7d 30d 90d 1y"),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    search:     Optional[str] = Query(None, description="Search by trace name or id"),
    page:       int            = Query(1, ge=1),
    page_size:  int            = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)

    where_clauses = []
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}

    if from_dt:
        where_clauses.append("t.created_at >= :from_dt")
        params["from_dt"] = _to_naive_utc(from_dt)
    if to_dt:
        where_clauses.append("t.created_at <= :to_dt")
        params["to_dt"] = _to_naive_utc(to_dt)
    if search:
        where_clauses.append("(t.id::text ILIKE :search OR t.name ILIKE :search)")
        params["search"] = f"%{search}%"

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    query = text(f"""
        SELECT
            t.id                                        AS trace_id,
            t.project_id,
            t.external_trace_id,
            t.name,
            t.user_id,
            t.session_id,
            t.input,
            t.output,
            t.status,
            t.created_at,
            t.updated_at,
            COUNT(DISTINCT o.id)                        AS total_spans,
            COUNT(DISTINCT s.observation_id)            AS total_llm_spans,
            COALESCE(SUM(s.total_tokens), 0)            AS total_tokens,
            COALESCE(SUM(s.cost_usd), 0)                AS total_cost_usd,
            COALESCE(SUM(o.latency_ms), 0)              AS total_latency_ms,
            COALESCE(
                json_agg(
                    json_build_object(
                        'id',           o.id,
                        'name',         o.name,
                        'type',         o.type,
                        'status',       o.status,
                        'latency_ms',   o.latency_ms,
                        'created_at',   o.created_at,
                        'llm_metadata', CASE
                            WHEN s.observation_id IS NOT NULL THEN
                                json_build_object(
                                    'model',              s.model,
                                    'provider',           s.provider,
                                    'prompt_tokens',      s.prompt_tokens,
                                    'completion_tokens',  s.completion_tokens,
                                    'total_tokens',       s.total_tokens,
                                    'cost_usd',           s.cost_usd
                                )
                            ELSE NULL
                        END
                    )
                    ORDER BY o.created_at ASC
                ) FILTER (WHERE o.id IS NOT NULL),
                '[]'::json
            )                                           AS observations
        FROM traces t
        LEFT JOIN observations  o ON t.id = o.trace_id
        LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
        {where_sql}
        GROUP BY t.id
        ORDER BY t.created_at DESC
        LIMIT :limit OFFSET :offset;
    """)

    count_query = text(f"""
        SELECT COUNT(*) AS total FROM traces t {where_sql};
    """)

    result       = await db.execute(query, params)
    count_result = await db.execute(count_query, {k: v for k, v in params.items() if k not in ("limit", "offset")})

    rows  = result.mappings().all()
    total = count_result.scalar()

    return {
        "data":      rows,
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "from_time": from_dt.isoformat() if from_dt else None,
        "to_time":   to_dt.isoformat()   if to_dt   else None,
    }


# ===========================================================
# 2. SINGLE TRACE DETAIL
#    GET /traces/{trace_id}
#    Returns trace row + all its spans
# ===========================================================

@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
    query = text("""
        SELECT
            t.*,
            COUNT(DISTINCT o.id)             AS total_spans,
            COALESCE(SUM(s.total_tokens), 0) AS total_tokens,
            COALESCE(SUM(s.cost_usd), 0)     AS total_cost_usd,
            COALESCE(
                json_agg(
                    json_build_object(
                        'id',           o.id,
                        'trace_id',     o.trace_id,
                        'name',         o.name,
                        'type',         o.type,
                        'status',       o.status,
                        'latency_ms',   o.latency_ms,
                        'created_at',   o.created_at,
                        'input',        o.input,
                        'output',       o.output,
                        'llm_metadata', CASE
                            WHEN s.observation_id IS NOT NULL THEN
                                json_build_object(
                                    'model',             s.model,
                                    'provider',          s.provider,
                                    'prompt_tokens',     s.prompt_tokens,
                                    'completion_tokens', s.completion_tokens,
                                    'total_tokens',      s.total_tokens,
                                    'cost_usd',          s.cost_usd,
                                    'created_at',        s.created_at
                                )
                            ELSE NULL
                        END
                    )
                    ORDER BY o.created_at ASC
                ) FILTER (WHERE o.id IS NOT NULL),
                '[]'::json
            ) AS observations
        FROM traces t
        LEFT JOIN observations  o ON t.id = o.trace_id
        LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
        WHERE t.id = :trace_id
        GROUP BY t.id;
    """)

    result = await db.execute(query, {"trace_id": trace_id})
    return result.mappings().first()


# ===========================================================
# 3. TRACING PAGE — OBSERVATIONS TAB
#    GET /observations
#    Like Langfuse "Tracing > Observations" tab
# ===========================================================

@router.get("/observations")
async def get_observations(
    date_range:  Optional[DateRangePreset] = Query(None),
    from_time:   Optional[str] = Query(None),
    to_time:     Optional[str] = Query(None),
    trace_id:    Optional[str] = Query(None, description="Filter by trace"),
    agent_name:  Optional[str] = Query(None, description="Filter by span name (agent)"),
    obs_type:    Optional[str] = Query(None, description="Filter by type: CHAIN / LLM"),
    status:      Optional[str] = Query(None, description="Filter by status: success / error"),
    page:        int            = Query(1, ge=1),
    page_size:   int            = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)

    where_clauses = []
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}

    if from_dt:
        where_clauses.append("o.created_at >= :from_dt")
        params["from_dt"] = _to_naive_utc(from_dt)
    if to_dt:
        where_clauses.append("o.created_at <= :to_dt")
        params["to_dt"] = _to_naive_utc(to_dt)
    if trace_id:
        where_clauses.append("o.trace_id = :trace_id")
        params["trace_id"] = trace_id
    if agent_name:
        where_clauses.append("o.name ILIKE :agent_name")
        params["agent_name"] = f"%{agent_name}%"
    if obs_type:
        where_clauses.append("o.type = :obs_type")
        params["obs_type"] = obs_type.upper()
    if status:
        where_clauses.append("o.status = :status")
        params["status"] = status

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    query = text(f"""
        SELECT
            o.id,
            o.trace_id,
            o.type,
            o.name,
            o.status,
            o.latency_ms,
            o.input,
            o.output,
            o.created_at,
            t.name          AS trace_name,
            t.project_id,
            s.model,
            s.provider,
            s.prompt_tokens,
            s.completion_tokens,
            s.total_tokens,
            s.cost_usd
        FROM observations o
        LEFT JOIN traces            t ON o.trace_id = t.id
        LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
        {where_sql}
        ORDER BY o.created_at DESC
        LIMIT :limit OFFSET :offset;
    """)

    count_query = text(f"""
        SELECT COUNT(*) AS total FROM observations o {where_sql};
    """)

    result       = await db.execute(query, params)
    count_result = await db.execute(count_query, {k: v for k, v in params.items() if k not in ("limit", "offset")})

    return {
        "data":      result.mappings().all(),
        "total":     count_result.scalar(),
        "page":      page,
        "page_size": page_size,
        "from_time": from_dt.isoformat() if from_dt else None,
        "to_time":   to_dt.isoformat()   if to_dt   else None,
    }


# ===========================================================
# 4. SPANS FOR A TRACE  (click a trace → see its spans)
#    GET /traces/{trace_id}/spans
# ===========================================================

@router.get("/traces/{trace_id}/spans")
async def get_trace_spans(trace_id: str, db: AsyncSession = Depends(get_db)):
    query = text("""
        SELECT
            o.id,
            o.trace_id,
            o.type,
            o.name,
            o.status,
            o.latency_ms,
            o.input,
            o.output,
            o.created_at,
            json_build_object(
                'model',             s.model,
                'provider',          s.provider,
                'prompt_tokens',     s.prompt_tokens,
                'completion_tokens', s.completion_tokens,
                'total_tokens',      s.total_tokens,
                'cost_usd',          s.cost_usd,
                'created_at',        s.created_at
            ) AS llm_metadata
        FROM observations o
        LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
        WHERE o.trace_id = :trace_id
        ORDER BY o.created_at ASC;
    """)

    result = await db.execute(query, {"trace_id": trace_id})
    return result.mappings().all()


# ===========================================================
# 5. SINGLE SPAN DETAIL
#    GET /spans/{observation_id}
# ===========================================================

@router.get("/spans/{observation_id}")
async def get_span(observation_id: str, db: AsyncSession = Depends(get_db)):
    query = text("""
        SELECT
            o.*,
            json_build_object(
                'model',             s.model,
                'provider',          s.provider,
                'prompt_tokens',     s.prompt_tokens,
                'completion_tokens', s.completion_tokens,
                'total_tokens',      s.total_tokens,
                'cost_usd',          s.cost_usd,
                'created_at',        s.created_at
            ) AS llm_metadata
        FROM observations o
        LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
        WHERE o.id = :observation_id;
    """)

    result = await db.execute(query, {"observation_id": observation_id})
    return result.mappings().first()


# ===========================================================
# 6. LLM SPANS — all / single / by trace
# ===========================================================

@router.get("/llm-spans")
async def get_llm_spans(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
    where_clauses, params = [], {}
    if from_dt:
        where_clauses.append("created_at >= :from_dt"); params["from_dt"] = _to_naive_utc(from_dt)
    if to_dt:
        where_clauses.append("created_at <= :to_dt");   params["to_dt"] = _to_naive_utc(to_dt)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    result = await db.execute(text(f"SELECT * FROM span_llm_metadata {where_sql} ORDER BY created_at DESC;"), params)
    return result.mappings().all()


@router.get("/llm-spans/{observation_id}")
async def get_llm_span(observation_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM span_llm_metadata WHERE observation_id = :oid;"),
        {"oid": observation_id}
    )
    return result.mappings().first()


@router.get("/traces/{trace_id}/llm-spans")
async def get_trace_llm_spans(trace_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM span_llm_metadata WHERE trace_id = :trace_id ORDER BY created_at ASC;"),
        {"trace_id": trace_id}
    )
    return result.mappings().all()


# ===========================================================
# 7. TRACE TREE  (full span + LLM join)
#    GET /traces/{trace_id}/tree
# ===========================================================

@router.get("/traces/{trace_id}/tree")
async def get_trace_tree(trace_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT
            o.id, o.trace_id, o.name, o.type, o.status, o.latency_ms, o.created_at,
            o.input, o.output,
            s.model, s.provider, s.prompt_tokens, s.completion_tokens, s.total_tokens, s.cost_usd
        FROM observations o
        LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
        WHERE o.trace_id = :trace_id
        ORDER BY o.created_at ASC;
    """), {"trace_id": trace_id})
    return result.mappings().all()


# ===========================================================
# 8. HOME DASHBOARD  —  single endpoint, all cards
#    No filter  → all data (like Langfuse default)
#    With filter → scoped to that time range
# ===========================================================

@router.get("/dashboard/home")
async def dashboard_home(
    date_range: Optional[DateRangePreset] = Query(None, description="5m 30m 1h 3h 1d 7d 30d 90d 1y — omit for all data"),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
    trunc = _bucket_granularity(from_dt, to_dt)

    # Build WHERE clause for time filter (empty string = no filter)
    if from_dt and to_dt:
        time_where = "WHERE created_at BETWEEN :from_dt AND :to_dt"
        time_and   = "AND created_at BETWEEN :from_dt AND :to_dt"
        params = {"from_dt": _to_naive_utc(from_dt), "to_dt": _to_naive_utc(to_dt)}
    else:
        time_where = ""
        time_and   = ""
        params     = {}

    summary_q = text(f"""
        SELECT
            (SELECT COUNT(*) FROM traces            {time_where}) AS total_traces,
            (SELECT COUNT(*) FROM observations      {time_where}) AS total_spans,
            (SELECT COUNT(*) FROM span_llm_metadata {time_where}) AS total_llm_spans,
            (SELECT COALESCE(SUM(cost_usd),    0) FROM span_llm_metadata {time_where}) AS total_cost_usd,
            (SELECT COALESCE(SUM(total_tokens),0) FROM span_llm_metadata {time_where}) AS total_tokens;
    """)

    model_costs_q = text(f"""
        SELECT
            model, provider,
            COUNT(*)          AS llm_calls,
            SUM(total_tokens) AS total_tokens,
            SUM(cost_usd)     AS total_cost_usd
        FROM span_llm_metadata
        {time_where}
        GROUP BY model, provider
        ORDER BY total_cost_usd DESC;
    """)

    traces_time_q = text(f"""
        SELECT
            date_trunc('{trunc}', created_at) AS bucket,
            COUNT(*)                           AS trace_count
        FROM traces
        {time_where}
        GROUP BY bucket
        ORDER BY bucket ASC;
    """)

    obs_level_q = text(f"""
        SELECT
            date_trunc('{trunc}', created_at) AS bucket,
            status,
            COUNT(*)                           AS count
        FROM observations
        {time_where}
        GROUP BY bucket, status
        ORDER BY bucket ASC;
    """)

    model_usage_q = text(f"""
        SELECT
            date_trunc('{trunc}', created_at) AS bucket,
            model, provider,
            SUM(total_tokens)                  AS total_tokens,
            SUM(cost_usd)                      AS total_cost_usd
        FROM span_llm_metadata
        {time_where}
        GROUP BY bucket, model, provider
        ORDER BY bucket ASC;
    """)

    summary_r      = await db.execute(summary_q,     params)
    model_costs_r  = await db.execute(model_costs_q, params)
    traces_time_r  = await db.execute(traces_time_q, params)
    obs_level_r    = await db.execute(obs_level_q,   params)
    model_usage_r  = await db.execute(model_usage_q, params)

    return {
        "from_time":            from_dt.isoformat() if from_dt else None,
        "to_time":              to_dt.isoformat()   if to_dt   else None,
        "granularity":          trunc,
        "summary":              dict(summary_r.mappings().first()),
        "model_costs":          model_costs_r.mappings().all(),
        "traces_by_time":       traces_time_r.mappings().all(),
        "observations_by_level":obs_level_r.mappings().all(),
        "model_usage_by_time":  model_usage_r.mappings().all(),
    }


# ===========================================================
# 9. DASHBOARD SUMMARY  (standalone card endpoint)
# ===========================================================

@router.get("/dashboard/summary")
async def dashboard_summary(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)

    if from_dt and to_dt:
        w = "WHERE created_at BETWEEN :from_dt AND :to_dt"
        p = {"from_dt": _to_naive_utc(from_dt), "to_dt": _to_naive_utc(to_dt)}
    else:
        w, p = "", {}

    result = await db.execute(text(f"""
        SELECT
            (SELECT COUNT(*) FROM traces            {w}) AS total_traces,
            (SELECT COUNT(*) FROM observations      {w}) AS total_spans,
            (SELECT COUNT(*) FROM span_llm_metadata {w}) AS total_llm_spans,
            (SELECT COALESCE(SUM(cost_usd),    0) FROM span_llm_metadata {w}) AS total_cost_usd,
            (SELECT COALESCE(SUM(total_tokens),0) FROM span_llm_metadata {w}) AS total_tokens;
    """), p)

    return {
        **dict(result.mappings().first()),
        "from_time": from_dt.isoformat() if from_dt else None,
        "to_time":   to_dt.isoformat()   if to_dt   else None,
    }


# ===========================================================
# 10. MODEL USAGE  (standalone)
# ===========================================================

@router.get("/dashboard/model-usage")
async def model_usage(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)

    if from_dt and to_dt:
        w = "WHERE created_at BETWEEN :from_dt AND :to_dt"
        p = {"from_dt": _to_naive_utc(from_dt), "to_dt": _to_naive_utc(to_dt)}
    else:
        w, p = "", {}

    result = await db.execute(text(f"""
        SELECT
            model, provider,
            COUNT(*)               AS llm_calls,
            SUM(prompt_tokens)     AS prompt_tokens,
            SUM(completion_tokens) AS completion_tokens,
            SUM(total_tokens)      AS total_tokens,
            SUM(cost_usd)          AS total_cost_usd
        FROM span_llm_metadata
        {w}
        GROUP BY model, provider
        ORDER BY total_cost_usd DESC;
    """), p)

    return {
        "data":      result.mappings().all(),
        "from_time": from_dt.isoformat() if from_dt else None,
        "to_time":   to_dt.isoformat()   if to_dt   else None,
    }





    # ===========================================================
# NEW APIS — OVERVIEW DASHBOARD  (Human-Readable Version)
#
# HOW TO READ THIS FILE:
#   Every endpoint has a plain-English docstring explaining:
#     • What it returns
#     • How each value is calculated
#     • What "delta" / "previous window" means
#
# Add these at the END of the existing router file,
# replacing the old endpoints 11–18.
# ===========================================================


# ===========================================================
# 11. LIVE KPI CARDS  —  Top summary numbers
#     GET /dashboard/overview/metrics
#
#     Returns 5 numbers for the selected time window:
#       - total_traces       → COUNT(*) from traces table
#       - success_rate       → (successful observations / all observations) × 100
#       - avg_latency_ms     → AVG(latency_ms) across all observations
#       - total_tokens       → SUM(total_tokens) from span_llm_metadata
#       - estimated_cost_usd → SUM(cost_usd) from span_llm_metadata
#
#     DELTA LOGIC ("▲ 12.4% vs yesterday"):
#       We compare the CURRENT window against the PREVIOUS window
#       of the same length immediately before it.
#       Example — if you select "last 24 h" (window = 24 h):
#         current  window = [now-24h  → now]
#         previous window = [now-48h  → now-24h]
#       The delta is: ((current - previous) / previous) × 100
# ===========================================================

@router.get("/dashboard/overview/metrics")
async def overview_metrics(
    date_range: Optional[DateRangePreset] = Query(None, description="1h 24h 7d 30d — omit for all data"),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Powers the 5 KPI cards at the top of the Overview page.

    CURRENT WINDOW  = the time range the user selected (e.g. last 24 h).
    PREVIOUS WINDOW = an equal-length window immediately before the current one.
                      Used to compute the "vs yesterday" percentage change.

    If no time range is given, returns all-time totals with no delta.
    """
    current_window_start, current_window_end = resolve_date_range(date_range, from_time, to_time)

    # ── Build SQL WHERE clauses ──────────────────────────────────────

    if current_window_start and current_window_end:
        current_window_sql  = "WHERE created_at BETWEEN :from_dt AND :to_dt"
        current_window_params = {
            "from_dt": _to_naive_utc(current_window_start),
            "to_dt":   _to_naive_utc(current_window_end),
        }

        # Previous window = same duration, ending exactly when current window starts
        window_duration = current_window_end - current_window_start
        previous_window_start = current_window_start - window_duration
        previous_window_end   = current_window_start   # previous ends where current begins

        previous_window_sql    = "WHERE created_at BETWEEN :prev_from AND :prev_to"
        previous_window_params = {
            "prev_from": _to_naive_utc(previous_window_start),
            "prev_to":   _to_naive_utc(previous_window_end),
        }
    else:
        # "All data" mode — no time filter, no delta
        current_window_sql     = ""
        current_window_params  = {}
        previous_window_sql    = "WHERE 1=0"   # returns zero rows intentionally
        previous_window_params = {}

    # ── Query: current window KPIs ───────────────────────────────────
    current_kpi_query = text(f"""
        SELECT
            -- How many traces ran in this window?
            (SELECT COUNT(*) FROM traces {current_window_sql})
                AS total_traces,

            -- What % of observations completed successfully?
            -- Formula: (COUNT WHERE status='success') / COUNT(*) × 100
            (
                SELECT ROUND(
                    100.0
                    * COUNT(*) FILTER (WHERE status = 'success')
                    / NULLIF(COUNT(*), 0),
                    1   -- round to 1 decimal place
                )
                FROM observations {current_window_sql}
            )   AS success_rate,

            -- Average time (ms) an observation took to complete
            (
                SELECT ROUND(AVG(latency_ms)::numeric, 0)
                FROM observations {current_window_sql}
            )   AS avg_latency_ms,

            -- Total LLM tokens consumed (prompt + completion)
            (SELECT COALESCE(SUM(total_tokens), 0) FROM span_llm_metadata {current_window_sql})
                AS total_tokens,

            -- Total USD cost of all LLM calls
            (SELECT COALESCE(SUM(cost_usd), 0) FROM span_llm_metadata {current_window_sql})
                AS estimated_cost_usd;
    """)

    # ── Query: previous window KPIs (same shape, different time range) ──
    previous_kpi_query = text(f"""
        SELECT
            (SELECT COUNT(*) FROM traces {previous_window_sql})
                AS total_traces,
            (
                SELECT ROUND(
                    100.0
                    * COUNT(*) FILTER (WHERE status = 'success')
                    / NULLIF(COUNT(*), 0), 1
                )
                FROM observations {previous_window_sql}
            )   AS success_rate,
            (
                SELECT ROUND(AVG(latency_ms)::numeric, 0)
                FROM observations {previous_window_sql}
            )   AS avg_latency_ms,
            (SELECT COALESCE(SUM(total_tokens), 0) FROM span_llm_metadata {previous_window_sql})
                AS total_tokens,
            (SELECT COALESCE(SUM(cost_usd), 0) FROM span_llm_metadata {previous_window_sql})
                AS estimated_cost_usd;
    """)

    current_result  = await db.execute(current_kpi_query,  current_window_params)
    previous_result = await db.execute(previous_kpi_query, previous_window_params)

    current_kpis  = dict(current_result.mappings().first())
    previous_kpis = dict(previous_result.mappings().first())

    def percentage_change(metric_name: str) -> float | None:
        """
        Returns the % change from previous to current.
        Formula: ((current - previous) / previous) × 100
        Returns None when previous is 0 (can't divide by zero).
        """
        current_value  = float(current_kpis.get(metric_name)  or 0)
        previous_value = float(previous_kpis.get(metric_name) or 0)
        if previous_value == 0:
            return None
        return round((current_value - previous_value) / previous_value * 100, 1)

    return {
        "from_time": current_window_start.isoformat() if current_window_start else None,
        "to_time":   current_window_end.isoformat()   if current_window_end   else None,
        "current":   current_kpis,
        "previous":  previous_kpis,
        "deltas": {
            # % change in number of traces  (e.g. +12.4 means 12.4% more traces than last window)
            "total_traces_pct": percentage_change("total_traces"),

            # Percentage-point change in success rate (NOT a % of %)
            # e.g. +0.3 means success rate went from 98.4% → 98.7%
            "success_rate_pp": round(
                float(current_kpis.get("success_rate") or 0)
                - float(previous_kpis.get("success_rate") or 0),
                1
            ),

            # Absolute change in avg latency in milliseconds
            # e.g. -80 means avg latency dropped by 80 ms (improvement)
            "avg_latency_ms_delta": round(
                float(current_kpis.get("avg_latency_ms") or 0)
                - float(previous_kpis.get("avg_latency_ms") or 0),
                0
            ),

            # % change in total tokens consumed
            "total_tokens_pct": percentage_change("total_tokens"),

            # % change in estimated USD cost
            "estimated_cost_usd_pct": percentage_change("estimated_cost_usd"),
        },
    }


# ===========================================================
# 12. TRACE VOLUME OVER TIME  —  Line chart data
#     GET /dashboard/overview/trace-volume
#
#     Returns a list of (time_bucket, trace_count) pairs
#     so the frontend can draw the "Trace Volume · 24h" chart.
#
#     BUCKET SIZE (auto-selected based on window length):
#       window ≤ 1 h   → bucket = 1 minute
#       window ≤ 2 d   → bucket = 1 hour
#       window ≤ 60 d  → bucket = 1 day
#       window > 60 d  → bucket = 1 week
# ===========================================================

@router.get("/dashboard/overview/trace-volume")
async def overview_trace_volume(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Powers the Trace Volume line chart.

    Each row in the response represents one time bucket:
      bucket      = start of the time period (e.g. "2026-06-23 14:00:00")
      trace_count = how many traces were created in that bucket

    The bucket size auto-scales with the selected window so the
    chart always has a readable number of data points.
    """
    window_start, window_end = resolve_date_range(date_range, from_time, to_time)
    bucket_size = _bucket_granularity(window_start, window_end)  # "minute" / "hour" / "day" / "week"

    if window_start and window_end:
        time_filter_sql    = "WHERE created_at BETWEEN :from_dt AND :to_dt"
        time_filter_params = {
            "from_dt": _to_naive_utc(window_start),
            "to_dt":   _to_naive_utc(window_end),
        }
    else:
        time_filter_sql    = ""
        time_filter_params = {}

    volume_query = text(f"""
        SELECT
            -- Truncate each trace's created_at to the nearest bucket boundary
            -- e.g. 14:37 → 14:00 when bucket_size = 'hour'
            date_trunc('{bucket_size}', created_at) AS bucket,

            -- Count how many traces fall into each bucket
            COUNT(*) AS trace_count

        FROM traces
        {time_filter_sql}
        GROUP BY bucket
        ORDER BY bucket ASC;   -- oldest → newest so chart renders left-to-right
    """)

    result = await db.execute(volume_query, time_filter_params)

    return {
        "granularity": bucket_size,   # tells the frontend what each X-axis tick represents
        "from_time":   window_start.isoformat() if window_start else None,
        "to_time":     window_end.isoformat()   if window_end   else None,
        "data":        result.mappings().all(),
    }


# ===========================================================
# 13. RECENT TRACES TABLE
#     GET /dashboard/overview/recent-traces
#
#     Returns the last N traces with their key stats so the
#     "Recent Traces" widget can show a quick-glance table.
#
#     Each row includes:
#       trace_id        → unique identifier
#       name            → human-readable trace name (e.g. "rag-pipeline")
#       status          → success / error / running
#       created_at      → when the trace started
#       total_latency_ms→ SUM of all span latencies inside that trace
#       total_cost_usd  → SUM of LLM costs for all spans in that trace
#       span_count      → how many observations (spans) the trace contains
# ===========================================================

@router.get("/dashboard/overview/recent-traces")
async def overview_recent_traces(
    limit: int = Query(10, ge=1, le=50, description="How many recent traces to return (default 10, max 50)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the most recent traces for the Recent Traces table widget.

    total_latency_ms is the SUM of every span's latency within the trace,
    NOT the wall-clock duration — it reflects cumulative processing time.
    """
    recent_traces_query = text("""
        SELECT
            t.id                                        AS trace_id,
            t.name,
            t.status,
            t.created_at,

            -- Total time spent across all spans in this trace (sum, not wall clock)
            COALESCE(SUM(o.latency_ms), 0)             AS total_latency_ms,

            -- Total USD cost of all LLM calls made within this trace
            COALESCE(SUM(s.cost_usd),   0)             AS total_cost_usd,

            -- How many individual spans (observations) this trace has
            COUNT(DISTINCT o.id)                        AS span_count

        FROM traces t
        LEFT JOIN observations      o ON t.id = o.trace_id
        LEFT JOIN span_llm_metadata s ON o.id  = s.observation_id

        GROUP BY t.id
        ORDER BY t.created_at DESC   -- newest traces first
        LIMIT :limit;
    """)

    result = await db.execute(recent_traces_query, {"limit": limit})
    return {"data": result.mappings().all()}


# ===========================================================
# 14. TOKEN DISTRIBUTION  —  Donut chart
#     GET /dashboard/overview/token-distribution
#
#     Returns token usage broken down by model so the frontend
#     can draw the "Token Distribution" donut chart.
#
#     Each slice shows:
#       model           → e.g. "gpt-4o", "claude-3-5"
#       provider        → e.g. "openai", "anthropic"
#       total_tokens    → raw token count for that model
#       token_share_pct → (model_tokens / all_tokens) × 100
#                         calculated using a SQL window function
# ===========================================================

@router.get("/dashboard/overview/token-distribution")
async def overview_token_distribution(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Powers the Token Distribution donut chart.

    token_share_pct for each model =
        SUM(tokens for this model) / SUM(tokens for ALL models) × 100

    The denominator uses a SQL window function (SUM(...) OVER ()) so all
    rows can see the grand total in a single query pass — no subquery needed.
    """
    window_start, window_end = resolve_date_range(date_range, from_time, to_time)

    if window_start and window_end:
        time_filter_sql    = "WHERE created_at BETWEEN :from_dt AND :to_dt"
        time_filter_params = {
            "from_dt": _to_naive_utc(window_start),
            "to_dt":   _to_naive_utc(window_end),
        }
    else:
        time_filter_sql    = ""
        time_filter_params = {}

    token_distribution_query = text(f"""
        SELECT
            model,
            provider,

            -- Raw token count for this model
            SUM(total_tokens) AS total_tokens,

            -- Share of this model's tokens out of ALL tokens consumed
            -- SUM(SUM(total_tokens)) OVER () = grand total across all models (window function)
            ROUND(
                100.0 * SUM(total_tokens)
                / NULLIF(SUM(SUM(total_tokens)) OVER (), 0),
                1
            ) AS token_share_pct

        FROM span_llm_metadata
        {time_filter_sql}
        GROUP BY model, provider
        ORDER BY total_tokens DESC;   -- largest slice first
    """)

    result = await db.execute(token_distribution_query, time_filter_params)
    rows   = result.mappings().all()

    # Compute grand total in Python so the frontend can display "84.2M tokens" in the donut center
    grand_total_tokens = sum(row["total_tokens"] or 0 for row in rows)

    return {
        "from_time":           window_start.isoformat() if window_start else None,
        "to_time":             window_end.isoformat()   if window_end   else None,
        "grand_total_tokens":  grand_total_tokens,
        "data":                rows,
    }


# ===========================================================
# 15. MODEL USAGE SHARE  —  Bar list widget
#     GET /dashboard/overview/model-usage-share
#
#     Same idea as token distribution but adds cost and call count,
#     used for the "Model Usage Share" bar list in System Status.
#
#     Each row shows:
#       model           → model name
#       provider        → provider name
#       llm_calls       → COUNT(*) — how many LLM calls used this model
#       total_tokens    → SUM(total_tokens)
#       total_cost_usd  → SUM(cost_usd)
#       usage_share_pct → (model_tokens / all_tokens) × 100
# ===========================================================

@router.get("/dashboard/overview/model-usage-share")
async def overview_model_usage_share(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Powers the Model Usage Share bar list (gpt-4o 62%, claude-3-5 24%, …).

    usage_share_pct = SUM(tokens for this model) / SUM(all tokens) × 100
    """
    window_start, window_end = resolve_date_range(date_range, from_time, to_time)

    if window_start and window_end:
        time_filter_sql    = "WHERE created_at BETWEEN :from_dt AND :to_dt"
        time_filter_params = {
            "from_dt": _to_naive_utc(window_start),
            "to_dt":   _to_naive_utc(window_end),
        }
    else:
        time_filter_sql    = ""
        time_filter_params = {}

    model_usage_query = text(f"""
        SELECT
            model,
            provider,

            -- Total number of individual LLM API calls for this model
            COUNT(*) AS llm_calls,

            -- Total tokens consumed across all calls for this model
            SUM(total_tokens) AS total_tokens,

            -- Total USD cost for this model
            SUM(cost_usd) AS total_cost_usd,

            -- Token share % (same window-function trick as token distribution)
            ROUND(
                100.0 * SUM(total_tokens)
                / NULLIF(SUM(SUM(total_tokens)) OVER (), 0),
                1
            ) AS usage_share_pct

        FROM span_llm_metadata
        {time_filter_sql}
        GROUP BY model, provider
        ORDER BY total_tokens DESC;   -- highest usage first
    """)

    result = await db.execute(model_usage_query, time_filter_params)

    return {
        "from_time": window_start.isoformat() if window_start else None,
        "to_time":   window_end.isoformat()   if window_end   else None,
        "data":      result.mappings().all(),
    }

# ===========================================================
# UPDATED ENDPOINTS: 16 & 17
#
# ENDPOINT 16 — /dashboard/overview/drift-alerts
#   → FULLY STATIC: always returns the 4 Figma alerts directly.
#     No DB query at all. This is intentional — these are
#     display-only demo alerts for the widget.
#
# ENDPOINT 17 — /dashboard/overview/system-status
#   → MCP SERVERS, ACTIVE TOOLS, QUEUE DEPTH, CIRCUIT BREAKERS
#     cards are STATIC (hardcoded Figma values).
#   → MODEL USAGE SHARE bar list is REAL — queries span_llm_metadata
#     and returns actual models used, sorted by token consumption.
#     Only falls back to empty list [] if no LLM data exists.
# ===========================================================


# ===========================================================
# 16. DRIFT ALERTS  —  Alert feed widget
#     GET /dashboard/overview/drift-alerts
#
#     FULLY STATIC — returns the 4 Figma alerts always.
#     No DB query. The widget is display-only for now.
# ===========================================================

@router.get("/dashboard/overview/drift-alerts")
async def overview_drift_alerts(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    limit:      int           = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the Drift Alerts feed.
    Currently returns static demo data matching the Figma design.
    Replace with real DB queries once drift detection is implemented.
    """
    # Resolve time range just for the response envelope
    # (no DB query is made against it)
    window_start, window_end = resolve_date_range(date_range, from_time, to_time)

    # ── Static alerts — exactly as shown in the Figma ─────────────────
    static_alerts = [
        {
            "alert_type":    "latency_spike",
            "severity":      "CRIT",
            "display_title": "sql_query tool spike — 3.2× baseline",
            "source":        "tool_usage_baselines",
            "last_seen":     "4m ago",
        },
        {
            "alert_type":    "model_drift",
            "severity":      "WARN",
            "display_title": "Model drift: gpt-4o → gpt-4o-mini",
            "source":        "observations",
            "last_seen":     "22m ago",
        },
        {
            "alert_type":    "prompt_mismatch",
            "severity":      "WARN",
            "display_title": "Prompt version mismatch in session #9f2a",
            "source":        "prompt_versions",
            "last_seen":     "1h ago",
        },
        {
            "alert_type":    "circuit_breaker",
            "severity":      "INFO",
            "display_title": "Circuit breaker reset — openai-api",
            "source":        "circuit_breaker_states",
            "last_seen":     "3h ago",
        },
    ]

    return {
        "from_time":      window_start.isoformat() if window_start else None,
        "to_time":        window_end.isoformat()   if window_end   else None,
        "is_static_demo": True,
        "alerts":         static_alerts,
    }


# ===========================================================
# 17. SYSTEM STATUS  —  Status card
#     GET /dashboard/overview/system-status
#
#     STATIC cards (hardcoded Figma values):
#       MCP SERVERS      → 8
#       ACTIVE TOOLS     → 34
#       QUEUE DEPTH      → 1,204
#       CIRCUIT BREAKERS → 7 OK
#
#     REAL data — MODEL USAGE SHARE bar list:
#       Queries span_llm_metadata grouped by model + provider.
#       Sorted by SUM(total_tokens) DESC so the most-used model
#       is always at the top.
#
#       usage_share_pct for each model =
#           SUM(tokens for this model) / SUM(ALL tokens) × 100
#
#       This is the ONLY section that reads from the database.
#       If no LLM spans exist yet, model_usage_share = [].
# ===========================================================

@router.get("/dashboard/overview/system-status")
async def overview_system_status(
    date_range: Optional[DateRangePreset] = Query(None),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Powers the System Status card.

    STATIC SECTION (MCP Servers / Active Tools / Queue Depth / Circuit Breakers):
      These four numbers are hardcoded to the Figma values.
      They do NOT come from the database.

    REAL SECTION (Model Usage Share bar list):
      Queries span_llm_metadata for the selected time window.
      Groups by (model, provider) and calculates each model's
      share of total tokens consumed.

      How usage_share_pct is calculated:
        Step 1 — SUM(total_tokens) per model  (GROUP BY model, provider)
        Step 2 — Grand total = SUM of all models' tokens  (window function)
        Step 3 — share = (model_tokens / grand_total) × 100

      Result is sorted highest-token model first, which is what
      drives the bar lengths in the UI (longer bar = more tokens used).

      Example: if your DB has only gemini calls, you will see only
      gemini here — no anthropic, no openai — because it queries
      YOUR actual data, not a hardcoded list.
    """
    # Resolve time window for the model usage share query
    window_start, window_end = resolve_date_range(date_range, from_time, to_time)

    if window_start and window_end:
        time_filter_sql    = "WHERE created_at BETWEEN :from_dt AND :to_dt"
        time_filter_params = {
            "from_dt": _to_naive_utc(window_start),
            "to_dt":   _to_naive_utc(window_end),
        }
    else:
        # No time filter — query all data
        time_filter_sql    = ""
        time_filter_params = {}

    # ── REAL query: model usage share from span_llm_metadata ─────────
    # This is the ONLY DB query in this endpoint.
    # It reads from your actual span_llm_metadata table.
    #
    # Columns returned:
    #   model           → e.g. "gemini-2.0-flash"  (whatever is in YOUR DB)
    #   provider        → e.g. "google"
    #   llm_calls       → COUNT(*) total LLM calls for this model
    #   total_tokens    → SUM(total_tokens) — input + output tokens combined
    #   total_cost_usd  → SUM(cost_usd)
    #   usage_share_pct → this model's tokens as % of ALL tokens
    #                      calculated with a SQL window function so
    #                      no second query is needed for the grand total
    model_usage_query = text(f"""
        SELECT
            model,
            provider,

            -- How many individual LLM API calls used this model?
            COUNT(*)          AS llm_calls,

            -- Total tokens (prompt + completion) for this model
            SUM(total_tokens) AS total_tokens,

            -- Total USD cost for this model
            SUM(cost_usd)     AS total_cost_usd,

            -- Share of total tokens: (this model's tokens / all tokens) × 100
            -- SUM(SUM(total_tokens)) OVER () = grand total across ALL models
            ROUND(
                100.0 * SUM(total_tokens)
                / NULLIF(SUM(SUM(total_tokens)) OVER (), 0),
                1
            ) AS usage_share_pct

        FROM span_llm_metadata
        {time_filter_sql}
        GROUP BY model, provider
        ORDER BY total_tokens DESC;   -- most-used model first → longest bar at top
    """)

    model_usage_result = await db.execute(model_usage_query, time_filter_params)
    model_usage_rows   = model_usage_result.mappings().all()

    # ── Response ──────────────────────────────────────────────────────
    return {
        "from_time": window_start.isoformat() if window_start else None,
        "to_time":   window_end.isoformat()   if window_end   else None,

        # ── STATIC: these 4 values are always the Figma numbers ───────
        "is_static_demo": True,   # for the top 4 cards only
        "mcp_servers":    8,      # MCP SERVERS  card
        "active_tools":   34,     # ACTIVE TOOLS card
        "queue_depth":    1204,   # QUEUE DEPTH  card  (UI formats as "1,204")
        "circuit_breakers": {
            "tripped_count":  7,  # CIRCUIT BREAKERS card (shown as "7 OK")
            "tripped_agents": [],
            "status":         "OK",
        },
        "overall_health": "OK",

        # ── REAL: actual model usage from your DB ─────────────────────
        # Will be [] if no LLM spans exist in the selected window.
        # Will show ONLY the models that actually appear in span_llm_metadata.
        # No hardcoded model names — 100% driven by your data.
        "model_usage_share": model_usage_rows,
    }


# ===========================================================
# 18. FULL OVERVIEW  —  Single call that powers every widget
#     GET /dashboard/overview
#
#     Fires all sub-queries in one request so the frontend only
#     needs ONE API call to hydrate the entire Overview page.
#
#     Response sections:
#       metrics          → KPI cards (traces, success rate, latency, tokens, cost)
#                          + deltas vs previous window
#       trace_volume     → (bucket, trace_count) list for the line chart
#       recent_traces    → last 10 traces for the table widget
#       token_distribution → per-model token share for the donut chart
#       model_usage_share  → per-model bar list with cost
#       system_status    → active tools, queue depth, total errors
#       drift_alerts     → agents with errors in this window
# ===========================================================

@router.get("/dashboard/overview")
async def dashboard_overview(
    date_range: Optional[DateRangePreset] = Query(None, description="1h 24h 7d 30d — omit for all data"),
    from_time:  Optional[str] = Query(None),
    to_time:    Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Master endpoint that returns ALL data needed by the Overview page in one round-trip.

    Internally runs 8 queries against:
      traces            — trace-level records
      observations      — span-level records (one per agent/tool call)
      span_llm_metadata — LLM-specific metadata (model, tokens, cost)

    All queries share the same time filter so every widget shows
    data for the same window.
    """
    window_start, window_end = resolve_date_range(date_range, from_time, to_time)
    bucket_size = _bucket_granularity(window_start, window_end)

    if window_start and window_end:
        time_filter_sql    = "WHERE created_at BETWEEN :from_dt AND :to_dt"
        current_window_params = {
            "from_dt": _to_naive_utc(window_start),
            "to_dt":   _to_naive_utc(window_end),
        }

        # Previous window for KPI deltas
        window_duration        = window_end - window_start
        previous_window_start  = window_start - window_duration
        previous_window_sql    = "WHERE created_at BETWEEN :prev_from AND :prev_to"
        previous_window_params = {
            "prev_from": _to_naive_utc(previous_window_start),
            "prev_to":   _to_naive_utc(window_start),
        }
    else:
        time_filter_sql        = ""
        current_window_params  = {}
        previous_window_sql    = "WHERE 1=0"
        previous_window_params = {}

    # ── 1. KPI cards — current window ────────────────────────────────
    current_kpi_query = text(f"""
        SELECT
            (SELECT COUNT(*) FROM traces {time_filter_sql})
                AS total_traces,
            (
                SELECT ROUND(
                    100.0 * COUNT(*) FILTER (WHERE status = 'success')
                    / NULLIF(COUNT(*), 0), 1
                )
                FROM observations {time_filter_sql}
            )   AS success_rate,
            (
                SELECT ROUND(AVG(latency_ms)::numeric, 0)
                FROM observations {time_filter_sql}
            )   AS avg_latency_ms,
            (SELECT COALESCE(SUM(total_tokens), 0) FROM span_llm_metadata {time_filter_sql})
                AS total_tokens,
            (SELECT COALESCE(SUM(cost_usd), 0) FROM span_llm_metadata {time_filter_sql})
                AS estimated_cost_usd;
    """)

    # ── 2. KPI cards — previous window (for delta calculation) ───────
    previous_kpi_query = text(f"""
        SELECT
            (SELECT COUNT(*) FROM traces {previous_window_sql})
                AS total_traces,
            (
                SELECT ROUND(
                    100.0 * COUNT(*) FILTER (WHERE status = 'success')
                    / NULLIF(COUNT(*), 0), 1
                )
                FROM observations {previous_window_sql}
            )   AS success_rate,
            (
                SELECT ROUND(AVG(latency_ms)::numeric, 0)
                FROM observations {previous_window_sql}
            )   AS avg_latency_ms,
            (SELECT COALESCE(SUM(total_tokens), 0) FROM span_llm_metadata {previous_window_sql})
                AS total_tokens,
            (SELECT COALESCE(SUM(cost_usd), 0) FROM span_llm_metadata {previous_window_sql})
                AS estimated_cost_usd;
    """)

    # ── 3. Trace volume — (bucket, count) pairs for the line chart ───
    trace_volume_query = text(f"""
        SELECT
            date_trunc('{bucket_size}', created_at) AS bucket,
            COUNT(*) AS trace_count
        FROM traces {time_filter_sql}
        GROUP BY bucket ORDER BY bucket ASC;
    """)

    # ── 4. Recent traces — last 10 rows for the table widget ─────────
    recent_traces_query = text(f"""
        SELECT
            t.id         AS trace_id,
            t.name,
            t.status,
            t.created_at,
            COALESCE(SUM(o.latency_ms), 0) AS total_latency_ms,
            COUNT(DISTINCT o.id)            AS span_count
        FROM traces t
        LEFT JOIN observations o ON t.id = o.trace_id
        {'WHERE t.created_at BETWEEN :from_dt AND :to_dt' if window_start and window_end else ''}
        GROUP BY t.id
        ORDER BY t.created_at DESC
        LIMIT 10;
    """)

    # ── 5. Token distribution — per-model share for the donut chart ──
    token_distribution_query = text(f"""
        SELECT
            model,
            provider,
            SUM(total_tokens) AS total_tokens,
            ROUND(
                100.0 * SUM(total_tokens)
                / NULLIF(SUM(SUM(total_tokens)) OVER (), 0), 1
            ) AS token_share_pct
        FROM span_llm_metadata {time_filter_sql}
        GROUP BY model, provider
        ORDER BY total_tokens DESC;
    """)

    # ── 6. Model usage share — for the bar list in System Status ─────
    model_usage_share_query = text(f"""
        SELECT
            model,
            provider,
            SUM(total_tokens) AS total_tokens,
            ROUND(
                100.0 * SUM(total_tokens)
                / NULLIF(SUM(SUM(total_tokens)) OVER (), 0), 1
            ) AS usage_share_pct,
            SUM(cost_usd) AS total_cost_usd
        FROM span_llm_metadata {time_filter_sql}
        GROUP BY model, provider
        ORDER BY total_tokens DESC;
    """)

    # ── 7. System status counters ─────────────────────────────────────
    system_status_query = text(f"""
        SELECT
            -- Number of unique agent/tool names active in this window
            COUNT(DISTINCT name)                                        AS active_tools,

            -- Spans that haven't finished yet (not success or error)
            COUNT(*) FILTER (WHERE status NOT IN ('success', 'error')) AS queue_depth,

            -- Total failed spans in this window
            COUNT(*) FILTER (WHERE status = 'error')                   AS total_errors

        FROM observations {time_filter_sql};
    """)

    # ── 8. Drift alerts — agents with errors (top 5) ─────────────────
    drift_alerts_query = text(f"""
        SELECT
            name                                              AS source,
            COUNT(*) FILTER (WHERE status = 'error')          AS error_count,
            COUNT(*)                                          AS total_count,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE status = 'error')
                / NULLIF(COUNT(*), 0), 1
            ) AS error_rate_pct,
            MAX(created_at) AS last_seen
        FROM observations {time_filter_sql}
        GROUP BY name
        HAVING COUNT(*) FILTER (WHERE status = 'error') > 0
        ORDER BY error_count DESC
        LIMIT 5;
    """)

    # ── Execute all 8 queries ─────────────────────────────────────────
    current_kpi_result       = await db.execute(current_kpi_query,       current_window_params)
    previous_kpi_result      = await db.execute(previous_kpi_query,      previous_window_params)
    trace_volume_result      = await db.execute(trace_volume_query,       current_window_params)
    recent_traces_result     = await db.execute(recent_traces_query,      current_window_params)
    token_distribution_result= await db.execute(token_distribution_query, current_window_params)
    model_usage_share_result = await db.execute(model_usage_share_query,  current_window_params)
    system_status_result     = await db.execute(system_status_query,      current_window_params)
    drift_alerts_result      = await db.execute(drift_alerts_query,       current_window_params)

    current_kpis  = dict(current_kpi_result.mappings().first())
    previous_kpis = dict(previous_kpi_result.mappings().first())
    system_status_row = dict(system_status_result.mappings().first())

    def percentage_change(metric_name: str) -> float | None:
        """((current - previous) / previous) × 100. Returns None when previous is 0."""
        current_value  = float(current_kpis.get(metric_name)  or 0)
        previous_value = float(previous_kpis.get(metric_name) or 0)
        if previous_value == 0:
            return None
        return round((current_value - previous_value) / previous_value * 100, 1)

    return {
        "from_time":   window_start.isoformat() if window_start else None,
        "to_time":     window_end.isoformat()   if window_end   else None,
        "granularity": bucket_size,

        # ── KPI cards (top row of the Overview page) ──────────────
        "metrics": {
            "current":  current_kpis,
            "previous": previous_kpis,
            "deltas": {
                # % change in total traces vs previous window
                "total_traces_pct": percentage_change("total_traces"),

                # Percentage-point change in success rate (e.g. +0.3pp)
                "success_rate_pp": round(
                    float(current_kpis.get("success_rate") or 0)
                    - float(previous_kpis.get("success_rate") or 0),
                    1
                ),

                # Absolute change in avg latency ms (negative = faster = good)
                "avg_latency_ms_delta": round(
                    float(current_kpis.get("avg_latency_ms") or 0)
                    - float(previous_kpis.get("avg_latency_ms") or 0),
                    0
                ),

                # % change in total tokens consumed
                "total_tokens_pct": percentage_change("total_tokens"),

                # % change in estimated cost
                "estimated_cost_usd_pct": percentage_change("estimated_cost_usd"),
            },
        },

        # ── Line chart: (bucket, trace_count) ─────────────────────
        "trace_volume": trace_volume_result.mappings().all(),

        # ── Recent Traces table ────────────────────────────────────
        "recent_traces": recent_traces_result.mappings().all(),

        # ── Token Distribution donut chart ────────────────────────
        "token_distribution": token_distribution_result.mappings().all(),

        # ── Model Usage Share bar list ────────────────────────────
        "model_usage_share": model_usage_share_result.mappings().all(),

        # ── System Status card ────────────────────────────────────
        "system_status": {
            "active_tools": system_status_row.get("active_tools", 0),
            "queue_depth":  system_status_row.get("queue_depth",  0),
            "total_errors": system_status_row.get("total_errors", 0),
        },

        # ── Drift Alerts feed ─────────────────────────────────────
        "drift_alerts": drift_alerts_result.mappings().all(),
    }



@router.get("/rca/summary")
async def rca_summary(
    db: AsyncSession = Depends(get_db)
):

    query = text("""
        SELECT *
        FROM rca_daily_evaluation_summary
        ORDER BY evaluation_date DESC
        LIMIT 1
    """)

    result = await db.execute(query)

    row = result.mappings().first()

    return dict(row) if row else {}



@router.get("/decision/summary")
async def decision_summary(
    db: AsyncSession = Depends(get_db)
):

    query = text("""
        SELECT *
        FROM decision_daily_evaluation_summary
        ORDER BY evaluation_date DESC
        LIMIT 1
    """)

    result = await db.execute(query)

    row = result.mappings().first()

    return dict(row) if row else {}



@router.get("/comparison/latest")
async def comparison_latest(
    db: AsyncSession = Depends(get_db)
):

    rca_query = text("""
        SELECT *
        FROM rca_daily_evaluation_summary
        ORDER BY evaluation_date DESC
        LIMIT 1
    """)

    decision_query = text("""
        SELECT *
        FROM decision_daily_evaluation_summary
        ORDER BY evaluation_date DESC
        LIMIT 1
    """)

    rca = (
        await db.execute(rca_query)
    ).mappings().first()

    decision = (
        await db.execute(decision_query)
    ).mappings().first()

    return {
        "relevancy": {
            "rca": rca["relevancy_avg"],
            "decision": decision["relevancy_avg"]
        },
        "safety": {
            "rca": rca["safety_avg"],
            "decision": decision["safety_avg"]
        },
        "coherence": {
            "rca": rca["coherence_avg"],
            "decision": decision["coherence_avg"]
        },
        "helpfulness": {
            "rca": rca["helpfulness_avg"],
            "decision": decision["helpfulness_avg"]
        },
        "toxicity": {
            "rca": rca["toxicity_avg"],
            "decision": decision["toxicity_avg"]
        }
    }



@router.get("/rca/weekly")
async def rca_weekly_average(
    db: AsyncSession = Depends(get_db)
):
    query = text("""
        SELECT
            ROUND(AVG(relevancy_avg)::numeric, 4)   AS relevancy_avg,
            ROUND(AVG(safety_avg)::numeric, 4)      AS safety_avg,
            ROUND(AVG(coherence_avg)::numeric, 4)   AS coherence_avg,
            ROUND(AVG(helpfulness_avg)::numeric, 4) AS helpfulness_avg,
            ROUND(AVG(toxicity_avg)::numeric, 4)    AS toxicity_avg,
            SUM(total_rca_evaluated)                AS total_rca
        FROM rca_daily_evaluation_summary
        WHERE evaluation_date >= CURRENT_DATE - INTERVAL '7 days'
    """)

    result = await db.execute(query)

    row = result.mappings().first()

    return dict(row) if row else {}


@router.get("/decision/weekly")
async def decision_weekly_average(
    db: AsyncSession = Depends(get_db)
):
    query = text("""
        SELECT
            ROUND(AVG(relevancy_avg)::numeric, 4)   AS relevancy_avg,
            ROUND(AVG(safety_avg)::numeric, 4)      AS safety_avg,
            ROUND(AVG(coherence_avg)::numeric, 4)   AS coherence_avg,
            ROUND(AVG(helpfulness_avg)::numeric, 4) AS helpfulness_avg,
            ROUND(AVG(toxicity_avg)::numeric, 4)    AS toxicity_avg,
            SUM(total_decision_evaluated)           AS total_decision
        FROM decision_daily_evaluation_summary
        WHERE evaluation_date >= CURRENT_DATE - INTERVAL '7 days'
    """)

    result = await db.execute(query)

    row = result.mappings().first()

    return dict(row) if row else {}