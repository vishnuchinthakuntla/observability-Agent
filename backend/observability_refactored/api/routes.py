# # from datetime import datetime, timedelta, timezone
# from datetime import datetime, timedelta, timezone
# from typing import Optional
# from fastapi import APIRouter, Depends, Query
# from sqlalchemy import text
# from sqlalchemy.ext.asyncio import AsyncSession
# from apis.database import get_db


# router = APIRouter(
#     prefix="/custom-api/v1",
#     tags=["Observability"],
# )


# # ===========================================================
# # DATE RANGE HELPER
# # Presets: 5m 30m 1h 3h 1d 7d 30d 90d 1y
# # Or custom: from_time / to_time (ISO 8601)
# # None passed → return (None, None) meaning "no filter / all data"
# # ===========================================================

# PRESET_MAP = {
#     "5m":  timedelta(minutes=5),
#     "30m": timedelta(minutes=30),
#     "1h":  timedelta(hours=1),
#     "3h":  timedelta(hours=3),
#     "1d":  timedelta(days=1),
#     "7d":  timedelta(days=7),
#     "30d": timedelta(days=30),
#     "90d": timedelta(days=90),
#     "1y":  timedelta(days=365),
# }


# def resolve_date_range(
#     date_range: Optional[str],
#     from_time: Optional[str],
#     to_time: Optional[str],
# ):
#     """
#     Returns (from_dt, to_dt) as UTC-aware datetimes, OR (None, None) if no
#     filter was requested (so callers can show ALL data, like Langfuse default).
#     """
#     now = datetime.now(timezone.utc)

#     if date_range and date_range in PRESET_MAP:
#         return now - PRESET_MAP[date_range], now

#     if from_time or to_time:
#         from_dt = datetime.fromisoformat(from_time).astimezone(timezone.utc) if from_time else None
#         to_dt   = datetime.fromisoformat(to_time).astimezone(timezone.utc)   if to_time   else now
#         return from_dt, to_dt

#     return None, None  # no filter → all data


# def _time_filter_sql(alias: str = "") -> str:
#     """Returns the WHERE/AND clause fragment for optional time filtering."""
#     col = f"{alias}.created_at" if alias else "created_at"
#     return f"{col} >= :from_dt AND {col} <= :to_dt"


# def _add_time_params(params: dict, from_dt, to_dt):
#     if from_dt:
#         params["from_dt"] = from_dt
#     if to_dt:
#         params["to_dt"] = to_dt


# def _bucket_granularity(from_dt, to_dt) -> str:
#     if from_dt is None:
#         return "day"
#     delta = to_dt - from_dt
#     if delta <= timedelta(hours=1):
#         return "minute"
#     if delta <= timedelta(days=2):
#         return "hour"
#     if delta <= timedelta(days=60):
#         return "day"
#     return "week"


# # ===========================================================
# # 1. TRACING PAGE  —  GET ALL TRACES
# #    Like Langfuse "Tracing > Traces" tab
# #    Shows every trace with its total spans, latency, cost
# # ===========================================================

# @router.get("/traces")
# async def get_traces(
#     date_range: Optional[str] = Query(None, description="5m 30m 1h 3h 1d 7d 30d 90d 1y"),
#     from_time:  Optional[str] = Query(None),
#     to_time:    Optional[str] = Query(None),
#     search:     Optional[str] = Query(None, description="Search by trace name or id"),
#     page:       int            = Query(1, ge=1),
#     page_size:  int            = Query(50, ge=1, le=200),
#     db: AsyncSession = Depends(get_db),
# ):
#     from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)

#     where_clauses = []
#     params: dict = {"limit": page_size, "offset": (page - 1) * page_size}

#     if from_dt:
#         where_clauses.append("t.created_at >= :from_dt")
#         params["from_dt"] = from_dt
#     if to_dt:
#         where_clauses.append("t.created_at <= :to_dt")
#         params["to_dt"] = to_dt
#     if search:
#         where_clauses.append("(t.id::text ILIKE :search OR t.name ILIKE :search)")
#         params["search"] = f"%{search}%"

#     where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

#     query = text(f"""
#         SELECT
#             t.id                                        AS trace_id,
#             t.project_id,
#             t.external_trace_id,
#             t.name,
#             t.user_id,
#             t.session_id,
#             t.input,
#             t.output,
#             t.status,
#             t.created_at,
#             t.updated_at,
#             COUNT(DISTINCT o.id)                        AS total_spans,
#             COUNT(DISTINCT s.observation_id)            AS total_llm_spans,
#             COALESCE(SUM(s.total_tokens), 0)            AS total_tokens,
#             COALESCE(SUM(s.cost_usd), 0)                AS total_cost_usd,
#             COALESCE(SUM(o.latency_ms), 0)              AS total_latency_ms,
#             COALESCE(
#                 json_agg(
#                     json_build_object(
#                         'id',           o.id,
#                         'name',         o.name,
#                         'type',         o.type,
#                         'status',       o.status,
#                         'latency_ms',   o.latency_ms,
#                         'created_at',   o.created_at,
#                         'llm_metadata', CASE
#                             WHEN s.observation_id IS NOT NULL THEN
#                                 json_build_object(
#                                     'model',              s.model,
#                                     'provider',           s.provider,
#                                     'prompt_tokens',      s.prompt_tokens,
#                                     'completion_tokens',  s.completion_tokens,
#                                     'total_tokens',       s.total_tokens,
#                                     'cost_usd',           s.cost_usd
#                                 )
#                             ELSE NULL
#                         END
#                     )
#                     ORDER BY o.created_at ASC
#                 ) FILTER (WHERE o.id IS NOT NULL),
#                 '[]'::json
#             )                                           AS observations
#         FROM traces t
#         LEFT JOIN observations  o ON t.id = o.trace_id
#         LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
#         {where_sql}
#         GROUP BY t.id
#         ORDER BY t.created_at DESC
#         LIMIT :limit OFFSET :offset;
#     """)

#     count_query = text(f"""
#         SELECT COUNT(*) AS total FROM traces t {where_sql};
#     """)

#     result       = await db.execute(query, params)
#     count_result = await db.execute(count_query, {k: v for k, v in params.items() if k not in ("limit", "offset")})

#     rows  = result.mappings().all()
#     total = count_result.scalar()

#     return {
#         "data":      rows,
#         "total":     total,
#         "page":      page,
#         "page_size": page_size,
#         "pages":     (total + page_size - 1) // page_size,
#         "from_time": from_dt.isoformat() if from_dt else None,
#         "to_time":   to_dt.isoformat()   if to_dt   else None,
#     }


# # ===========================================================
# # 2. SINGLE TRACE DETAIL
# #    GET /traces/{trace_id}
# #    Returns trace row + all its spans
# # ===========================================================

# @router.get("/traces/{trace_id}")
# async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
#     query = text("""
#         SELECT
#             t.*,
#             COUNT(DISTINCT o.id)             AS total_spans,
#             COALESCE(SUM(s.total_tokens), 0) AS total_tokens,
#             COALESCE(SUM(s.cost_usd), 0)     AS total_cost_usd,
#             COALESCE(
#                 json_agg(
#                     json_build_object(
#                         'id',           o.id,
#                         'trace_id',     o.trace_id,
#                         'name',         o.name,
#                         'type',         o.type,
#                         'status',       o.status,
#                         'latency_ms',   o.latency_ms,
#                         'created_at',   o.created_at,
#                         'input',        o.input,
#                         'output',       o.output,
#                         'llm_metadata', CASE
#                             WHEN s.observation_id IS NOT NULL THEN
#                                 json_build_object(
#                                     'model',             s.model,
#                                     'provider',          s.provider,
#                                     'prompt_tokens',     s.prompt_tokens,
#                                     'completion_tokens', s.completion_tokens,
#                                     'total_tokens',      s.total_tokens,
#                                     'cost_usd',          s.cost_usd,
#                                     'created_at',        s.created_at
#                                 )
#                             ELSE NULL
#                         END
#                     )
#                     ORDER BY o.created_at ASC
#                 ) FILTER (WHERE o.id IS NOT NULL),
#                 '[]'::json
#             ) AS observations
#         FROM traces t
#         LEFT JOIN observations  o ON t.id = o.trace_id
#         LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
#         WHERE t.id = :trace_id
#         GROUP BY t.id;
#     """)

#     result = await db.execute(query, {"trace_id": trace_id})
#     return result.mappings().first()


# # ===========================================================
# # 3. TRACING PAGE — OBSERVATIONS TAB
# #    GET /observations
# #    Like Langfuse "Tracing > Observations" tab
# # ===========================================================

# @router.get("/observations")
# async def get_observations(
#     date_range:  Optional[str] = Query(None),
#     from_time:   Optional[str] = Query(None),
#     to_time:     Optional[str] = Query(None),
#     trace_id:    Optional[str] = Query(None, description="Filter by trace"),
#     agent_name:  Optional[str] = Query(None, description="Filter by span name (agent)"),
#     obs_type:    Optional[str] = Query(None, description="Filter by type: CHAIN / LLM"),
#     status:      Optional[str] = Query(None, description="Filter by status: success / error"),
#     page:        int            = Query(1, ge=1),
#     page_size:   int            = Query(50, ge=1, le=200),
#     db: AsyncSession = Depends(get_db),
# ):
#     from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)

#     where_clauses = []
#     params: dict = {"limit": page_size, "offset": (page - 1) * page_size}

#     if from_dt:
#         where_clauses.append("o.created_at >= :from_dt")
#         params["from_dt"] = from_dt
#     if to_dt:
#         where_clauses.append("o.created_at <= :to_dt")
#         params["to_dt"] = to_dt
#     if trace_id:
#         where_clauses.append("o.trace_id = :trace_id")
#         params["trace_id"] = trace_id
#     if agent_name:
#         where_clauses.append("o.name ILIKE :agent_name")
#         params["agent_name"] = f"%{agent_name}%"
#     if obs_type:
#         where_clauses.append("o.type = :obs_type")
#         params["obs_type"] = obs_type.upper()
#     if status:
#         where_clauses.append("o.status = :status")
#         params["status"] = status

#     where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

#     query = text(f"""
#         SELECT
#             o.id,
#             o.trace_id,
#             o.type,
#             o.name,
#             o.status,
#             o.latency_ms,
#             o.input,
#             o.output,
#             o.created_at,
#             t.name          AS trace_name,
#             t.project_id,
#             s.model,
#             s.provider,
#             s.prompt_tokens,
#             s.completion_tokens,
#             s.total_tokens,
#             s.cost_usd
#         FROM observations o
#         LEFT JOIN traces            t ON o.trace_id = t.id
#         LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
#         {where_sql}
#         ORDER BY o.created_at DESC
#         LIMIT :limit OFFSET :offset;
#     """)

#     count_query = text(f"""
#         SELECT COUNT(*) AS total FROM observations o {where_sql};
#     """)

#     result       = await db.execute(query, params)
#     count_result = await db.execute(count_query, {k: v for k, v in params.items() if k not in ("limit", "offset")})

#     return {
#         "data":      result.mappings().all(),
#         "total":     count_result.scalar(),
#         "page":      page,
#         "page_size": page_size,
#         "from_time": from_dt.isoformat() if from_dt else None,
#         "to_time":   to_dt.isoformat()   if to_dt   else None,
#     }


# # ===========================================================
# # 4. SPANS FOR A TRACE  (click a trace → see its spans)
# #    GET /traces/{trace_id}/spans
# # ===========================================================

# @router.get("/traces/{trace_id}/spans")
# async def get_trace_spans(trace_id: str, db: AsyncSession = Depends(get_db)):
#     query = text("""
#         SELECT
#             o.id,
#             o.trace_id,
#             o.type,
#             o.name,
#             o.status,
#             o.latency_ms,
#             o.input,
#             o.output,
#             o.created_at,
#             json_build_object(
#                 'model',             s.model,
#                 'provider',          s.provider,
#                 'prompt_tokens',     s.prompt_tokens,
#                 'completion_tokens', s.completion_tokens,
#                 'total_tokens',      s.total_tokens,
#                 'cost_usd',          s.cost_usd,
#                 'created_at',        s.created_at
#             ) AS llm_metadata
#         FROM observations o
#         LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
#         WHERE o.trace_id = :trace_id
#         ORDER BY o.created_at ASC;
#     """)

#     result = await db.execute(query, {"trace_id": trace_id})
#     return result.mappings().all()


# # ===========================================================
# # 5. SINGLE SPAN DETAIL
# #    GET /spans/{observation_id}
# # ===========================================================

# @router.get("/spans/{observation_id}")
# async def get_span(observation_id: str, db: AsyncSession = Depends(get_db)):
#     query = text("""
#         SELECT
#             o.*,
#             json_build_object(
#                 'model',             s.model,
#                 'provider',          s.provider,
#                 'prompt_tokens',     s.prompt_tokens,
#                 'completion_tokens', s.completion_tokens,
#                 'total_tokens',      s.total_tokens,
#                 'cost_usd',          s.cost_usd,
#                 'created_at',        s.created_at
#             ) AS llm_metadata
#         FROM observations o
#         LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
#         WHERE o.id = :observation_id;
#     """)

#     result = await db.execute(query, {"observation_id": observation_id})
#     return result.mappings().first()


# # ===========================================================
# # 6. LLM SPANS — all / single / by trace
# # ===========================================================

# @router.get("/llm-spans")
# async def get_llm_spans(
#     date_range: Optional[str] = Query(None),
#     from_time:  Optional[str] = Query(None),
#     to_time:    Optional[str] = Query(None),
#     db: AsyncSession = Depends(get_db),
# ):
#     from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
#     where_clauses, params = [], {}
#     if from_dt:
#         where_clauses.append("created_at >= :from_dt"); params["from_dt"] = from_dt
#     if to_dt:
#         where_clauses.append("created_at <= :to_dt");   params["to_dt"] = to_dt
#     where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

#     result = await db.execute(text(f"SELECT * FROM span_llm_metadata {where_sql} ORDER BY created_at DESC;"), params)
#     return result.mappings().all()


# @router.get("/llm-spans/{observation_id}")
# async def get_llm_span(observation_id: str, db: AsyncSession = Depends(get_db)):
#     result = await db.execute(
#         text("SELECT * FROM span_llm_metadata WHERE observation_id = :oid;"),
#         {"oid": observation_id}
#     )
#     return result.mappings().first()


# @router.get("/traces/{trace_id}/llm-spans")
# async def get_trace_llm_spans(trace_id: str, db: AsyncSession = Depends(get_db)):
#     result = await db.execute(
#         text("SELECT * FROM span_llm_metadata WHERE trace_id = :trace_id ORDER BY created_at ASC;"),
#         {"trace_id": trace_id}
#     )
#     return result.mappings().all()


# # ===========================================================
# # 7. TRACE TREE  (full span + LLM join)
# #    GET /traces/{trace_id}/tree
# # ===========================================================

# @router.get("/traces/{trace_id}/tree")
# async def get_trace_tree(trace_id: str, db: AsyncSession = Depends(get_db)):
#     result = await db.execute(text("""
#         SELECT
#             o.id, o.trace_id, o.name, o.type, o.status, o.latency_ms, o.created_at,
#             o.input, o.output,
#             s.model, s.provider, s.prompt_tokens, s.completion_tokens, s.total_tokens, s.cost_usd
#         FROM observations o
#         LEFT JOIN span_llm_metadata s ON o.id = s.observation_id
#         WHERE o.trace_id = :trace_id
#         ORDER BY o.created_at ASC;
#     """), {"trace_id": trace_id})
#     return result.mappings().all()


# # ===========================================================
# # 8. HOME DASHBOARD  —  single endpoint, all cards
# #    No filter  → all data (like Langfuse default)
# #    With filter → scoped to that time range
# # ===========================================================

# @router.get("/dashboard/home")
# async def dashboard_home(
#     date_range: Optional[str] = Query(None, description="5m 30m 1h 3h 1d 7d 30d 90d 1y — omit for all data"),
#     from_time:  Optional[str] = Query(None),
#     to_time:    Optional[str] = Query(None),
#     db: AsyncSession = Depends(get_db),
# ):
#     from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)
#     trunc = _bucket_granularity(from_dt, to_dt)

#     # Build WHERE clause for time filter (empty string = no filter)
#     if from_dt and to_dt:
#         time_where = "WHERE created_at BETWEEN :from_dt AND :to_dt"
#         time_and   = "AND created_at BETWEEN :from_dt AND :to_dt"
#         params = {"from_dt": from_dt, "to_dt": to_dt}
#     else:
#         time_where = ""
#         time_and   = ""
#         params     = {}

#     summary_q = text(f"""
#         SELECT
#             (SELECT COUNT(*) FROM traces            {time_where}) AS total_traces,
#             (SELECT COUNT(*) FROM observations      {time_where}) AS total_spans,
#             (SELECT COUNT(*) FROM span_llm_metadata {time_where}) AS total_llm_spans,
#             (SELECT COALESCE(SUM(cost_usd),    0) FROM span_llm_metadata {time_where}) AS total_cost_usd,
#             (SELECT COALESCE(SUM(total_tokens),0) FROM span_llm_metadata {time_where}) AS total_tokens;
#     """)

#     model_costs_q = text(f"""
#         SELECT
#             model, provider,
#             COUNT(*)          AS llm_calls,
#             SUM(total_tokens) AS total_tokens,
#             SUM(cost_usd)     AS total_cost_usd
#         FROM span_llm_metadata
#         {time_where}
#         GROUP BY model, provider
#         ORDER BY total_cost_usd DESC;
#     """)

#     traces_time_q = text(f"""
#         SELECT
#             date_trunc('{trunc}', created_at) AS bucket,
#             COUNT(*)                           AS trace_count
#         FROM traces
#         {time_where}
#         GROUP BY bucket
#         ORDER BY bucket ASC;
#     """)

#     obs_level_q = text(f"""
#         SELECT
#             date_trunc('{trunc}', created_at) AS bucket,
#             status,
#             COUNT(*)                           AS count
#         FROM observations
#         {time_where}
#         GROUP BY bucket, status
#         ORDER BY bucket ASC;
#     """)

#     model_usage_q = text(f"""
#         SELECT
#             date_trunc('{trunc}', created_at) AS bucket,
#             model, provider,
#             SUM(total_tokens)                  AS total_tokens,
#             SUM(cost_usd)                      AS total_cost_usd
#         FROM span_llm_metadata
#         {time_where}
#         GROUP BY bucket, model, provider
#         ORDER BY bucket ASC;
#     """)

#     summary_r      = await db.execute(summary_q,     params)
#     model_costs_r  = await db.execute(model_costs_q, params)
#     traces_time_r  = await db.execute(traces_time_q, params)
#     obs_level_r    = await db.execute(obs_level_q,   params)
#     model_usage_r  = await db.execute(model_usage_q, params)

#     return {
#         "from_time":            from_dt.isoformat() if from_dt else None,
#         "to_time":              to_dt.isoformat()   if to_dt   else None,
#         "granularity":          trunc,
#         "summary":              dict(summary_r.mappings().first()),
#         "model_costs":          model_costs_r.mappings().all(),
#         "traces_by_time":       traces_time_r.mappings().all(),
#         "observations_by_level":obs_level_r.mappings().all(),
#         "model_usage_by_time":  model_usage_r.mappings().all(),
#     }


# # ===========================================================
# # 9. DASHBOARD SUMMARY  (standalone card endpoint)
# # ===========================================================

# @router.get("/dashboard/summary")
# async def dashboard_summary(
#     date_range: Optional[str] = Query(None),
#     from_time:  Optional[str] = Query(None),
#     to_time:    Optional[str] = Query(None),
#     db: AsyncSession = Depends(get_db),
# ):
#     from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)

#     if from_dt and to_dt:
#         w = "WHERE created_at BETWEEN :from_dt AND :to_dt"
#         p = {"from_dt": from_dt, "to_dt": to_dt}
#     else:
#         w, p = "", {}

#     result = await db.execute(text(f"""
#         SELECT
#             (SELECT COUNT(*) FROM traces            {w}) AS total_traces,
#             (SELECT COUNT(*) FROM observations      {w}) AS total_spans,
#             (SELECT COUNT(*) FROM span_llm_metadata {w}) AS total_llm_spans,
#             (SELECT COALESCE(SUM(cost_usd),    0) FROM span_llm_metadata {w}) AS total_cost_usd,
#             (SELECT COALESCE(SUM(total_tokens),0) FROM span_llm_metadata {w}) AS total_tokens;
#     """), p)

#     return {
#         **dict(result.mappings().first()),
#         "from_time": from_dt.isoformat() if from_dt else None,
#         "to_time":   to_dt.isoformat()   if to_dt   else None,
#     }


# # ===========================================================
# # 10. MODEL USAGE  (standalone)
# # ===========================================================

# @router.get("/dashboard/model-usage")
# async def model_usage(
#     date_range: Optional[str] = Query(None),
#     from_time:  Optional[str] = Query(None),
#     to_time:    Optional[str] = Query(None),
#     db: AsyncSession = Depends(get_db),
# ):
#     from_dt, to_dt = resolve_date_range(date_range, from_time, to_time)

#     if from_dt and to_dt:
#         w = "WHERE created_at BETWEEN :from_dt AND :to_dt"
#         p = {"from_dt": from_dt, "to_dt": to_dt}
#     else:
#         w, p = "", {}

#     result = await db.execute(text(f"""
#         SELECT
#             model, provider,
#             COUNT(*)               AS llm_calls,
#             SUM(prompt_tokens)     AS prompt_tokens,
#             SUM(completion_tokens) AS completion_tokens,
#             SUM(total_tokens)      AS total_tokens,
#             SUM(cost_usd)          AS total_cost_usd
#         FROM span_llm_metadata
#         {w}
#         GROUP BY model, provider
#         ORDER BY total_cost_usd DESC;
#     """), p)

#     return {
#         "data":      result.mappings().all(),
#         "from_time": from_dt.isoformat() if from_dt else None,
#         "to_time":   to_dt.isoformat()   if to_dt   else None,
#     }


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