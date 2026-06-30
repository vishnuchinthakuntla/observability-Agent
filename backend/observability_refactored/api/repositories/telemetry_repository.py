"""
Telemetry Repository
====================
All database access for the custom observability API lives here.
Zero raw SQL — every query uses SQLAlchemy Core / ORM expressions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import (
    case,
    cast,
    desc,
    distinct,
    func,
    literal_column,
    null,
    select,
    Integer,
    Numeric,
)
from sqlalchemy.ext.asyncio import AsyncSession

from shared.shared.models.telemetry import (
    Observation,
    SpanLLMMetadata,
    Trace,
    User,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Strip tzinfo before binding to a naive TIMESTAMP column."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Trace queries
# ---------------------------------------------------------------------------

class TelemetryRepository:
    """Read-only repository for all observability queries."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── 1. Trace list ──────────────────────────────────────────────────────

    async def list_traces(
        self,
        *,
        project_id: Optional[str],
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> dict:
        # Aggregate columns
        total_spans = func.count(distinct(Observation.id)).label("total_spans")
        total_llm_spans = func.count(distinct(SpanLLMMetadata.observation_id)).label("total_llm_spans")
        total_tokens = func.coalesce(func.sum(SpanLLMMetadata.total_tokens), 0).label("total_tokens")
        total_cost_usd = func.coalesce(func.sum(SpanLLMMetadata.cost_usd), 0).label("total_cost_usd")
        total_latency_ms = func.coalesce(func.sum(Observation.latency_ms), 0).label("total_latency_ms")

        stmt = (
            select(
                Trace.id.label("trace_id"),
                Trace.project_id,
                Trace.external_trace_id,
                Trace.name,
                Trace.user_id,
                Trace.session_id,
                Trace.input,
                Trace.output,
                Trace.status,
                Trace.created_at,
                Trace.updated_at,
                total_spans,
                total_llm_spans,
                total_tokens,
                total_cost_usd,
                total_latency_ms,
            )
            .outerjoin(Observation, Observation.trace_id == Trace.id)
            .outerjoin(SpanLLMMetadata, SpanLLMMetadata.observation_id == Observation.id)
            .group_by(Trace.id)
            .order_by(desc(Trace.created_at))
        )

        if project_id:
            stmt = stmt.where(Trace.project_id == project_id)
        if from_dt:
            stmt = stmt.where(Trace.created_at >= _utc_naive(from_dt))
        if to_dt:
            stmt = stmt.where(Trace.created_at <= _utc_naive(to_dt))
        if search:
            stmt = stmt.where(
                Trace.name.ilike(f"%{search}%") | cast(Trace.id, type_=None).ilike(f"%{search}%")
            )

        # Count
        count_sub = stmt.subquery()
        count_stmt = select(func.count()).select_from(count_sub)
        total = (await self.db.execute(count_stmt)).scalar_one()

        # Paginate
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(stmt)).mappings().all()

        return {"rows": rows, "total": total}

    # ── 2. Single trace ────────────────────────────────────────────────────

    async def get_trace(self, trace_id: str) -> Any:
        total_spans = func.count(distinct(Observation.id)).label("total_spans")
        total_tokens = func.coalesce(func.sum(SpanLLMMetadata.total_tokens), 0).label("total_tokens")
        total_cost_usd = func.coalesce(func.sum(SpanLLMMetadata.cost_usd), 0).label("total_cost_usd")

        stmt = (
            select(
                Trace,
                total_spans,
                total_tokens,
                total_cost_usd,
            )
            .outerjoin(Observation, Observation.trace_id == Trace.id)
            .outerjoin(SpanLLMMetadata, SpanLLMMetadata.observation_id == Observation.id)
            .where(Trace.id == trace_id)
            .group_by(Trace.id)
        )
        return (await self.db.execute(stmt)).mappings().first()

    # ── 3. Observations list ───────────────────────────────────────────────

    async def list_observations(
        self,
        *,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
        trace_id: Optional[str],
        agent_name: Optional[str],
        obs_type: Optional[str],
        status: Optional[str],
        page: int,
        page_size: int,
    ) -> dict:
        stmt = (
            select(
                Observation.id,
                Observation.trace_id,
                Observation.type,
                Observation.name,
                Observation.status,
                Observation.latency_ms,
                Observation.input,
                Observation.output,
                Observation.created_at,
                Trace.name.label("trace_name"),
                Trace.project_id,
                SpanLLMMetadata.model,
                SpanLLMMetadata.provider,
                SpanLLMMetadata.prompt_tokens,
                SpanLLMMetadata.completion_tokens,
                SpanLLMMetadata.total_tokens,
                SpanLLMMetadata.cost_usd,
            )
            .outerjoin(Trace, Trace.id == Observation.trace_id)
            .outerjoin(SpanLLMMetadata, SpanLLMMetadata.observation_id == Observation.id)
            .order_by(desc(Observation.created_at))
        )

        if from_dt:
            stmt = stmt.where(Observation.created_at >= _utc_naive(from_dt))
        if to_dt:
            stmt = stmt.where(Observation.created_at <= _utc_naive(to_dt))
        if trace_id:
            stmt = stmt.where(Observation.trace_id == trace_id)
        if agent_name:
            stmt = stmt.where(Observation.name.ilike(f"%{agent_name}%"))
        if obs_type:
            stmt = stmt.where(Observation.type == obs_type.upper())
        if status:
            stmt = stmt.where(Observation.status == status)

        count_sub = stmt.subquery()
        count_stmt = select(func.count()).select_from(count_sub)
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(stmt)).mappings().all()
        return {"rows": rows, "total": total}

    # ── 4. Spans for a trace ───────────────────────────────────────────────

    async def get_trace_spans(self, trace_id: str) -> Sequence:
        stmt = (
            select(
                Observation.id,
                Observation.trace_id,
                Observation.type,
                Observation.name,
                Observation.status,
                Observation.latency_ms,
                Observation.input,
                Observation.output,
                Observation.created_at,
                SpanLLMMetadata.model,
                SpanLLMMetadata.provider,
                SpanLLMMetadata.prompt_tokens,
                SpanLLMMetadata.completion_tokens,
                SpanLLMMetadata.total_tokens,
                SpanLLMMetadata.cost_usd,
            )
            .outerjoin(SpanLLMMetadata, SpanLLMMetadata.observation_id == Observation.id)
            .where(Observation.trace_id == trace_id)
            .order_by(Observation.created_at)
        )
        return (await self.db.execute(stmt)).mappings().all()

    # ── 5. Single span ─────────────────────────────────────────────────────

    async def get_span(self, observation_id: str) -> Any:
        stmt = (
            select(
                Observation,
                SpanLLMMetadata.model,
                SpanLLMMetadata.provider,
                SpanLLMMetadata.prompt_tokens,
                SpanLLMMetadata.completion_tokens,
                SpanLLMMetadata.total_tokens,
                SpanLLMMetadata.cost_usd,
            )
            .outerjoin(SpanLLMMetadata, SpanLLMMetadata.observation_id == Observation.id)
            .where(Observation.id == observation_id)
        )
        return (await self.db.execute(stmt)).mappings().first()

    # ── 6. LLM spans ───────────────────────────────────────────────────────

    async def list_llm_spans(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
    ) -> Sequence:
        stmt = select(SpanLLMMetadata).order_by(desc(SpanLLMMetadata.created_at))
        if from_dt:
            stmt = stmt.where(SpanLLMMetadata.created_at >= _utc_naive(from_dt))
        if to_dt:
            stmt = stmt.where(SpanLLMMetadata.created_at <= _utc_naive(to_dt))
        return (await self.db.execute(stmt)).scalars().all()

    async def get_llm_span(self, observation_id: str) -> Any:
        stmt = select(SpanLLMMetadata).where(
            SpanLLMMetadata.observation_id == observation_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_trace_llm_spans(self, trace_id: str) -> Sequence:
        stmt = (
            select(SpanLLMMetadata)
            .where(SpanLLMMetadata.trace_id == trace_id)
            .order_by(SpanLLMMetadata.created_at)
        )
        return (await self.db.execute(stmt)).scalars().all()

    # ── 7. Dashboard summary ───────────────────────────────────────────────

    async def dashboard_summary(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
    ) -> dict:
        t_filter = self._time_filter(Trace.created_at, from_dt, to_dt)
        o_filter = self._time_filter(Observation.created_at, from_dt, to_dt)
        l_filter = self._time_filter(SpanLLMMetadata.created_at, from_dt, to_dt)

        total_traces = (
            await self.db.execute(
                select(func.count(Trace.id)).where(*t_filter)
            )
        ).scalar_one()

        total_spans = (
            await self.db.execute(
                select(func.count(Observation.id)).where(*o_filter)
            )
        ).scalar_one()

        llm_row = (
            await self.db.execute(
                select(
                    func.count(SpanLLMMetadata.id).label("total_llm_spans"),
                    func.coalesce(func.sum(SpanLLMMetadata.cost_usd), 0).label("total_cost_usd"),
                    func.coalesce(func.sum(SpanLLMMetadata.total_tokens), 0).label("total_tokens"),
                ).where(*l_filter)
            )
        ).mappings().first()

        return {
            "total_traces": total_traces,
            "total_spans": total_spans,
            "total_llm_spans": llm_row["total_llm_spans"],
            "total_cost_usd": float(llm_row["total_cost_usd"]),
            "total_tokens": int(llm_row["total_tokens"]),
        }

    # ── 8. Model usage ─────────────────────────────────────────────────────

    async def model_usage(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
    ) -> Sequence:
        l_filter = self._time_filter(SpanLLMMetadata.created_at, from_dt, to_dt)
        stmt = (
            select(
                SpanLLMMetadata.model,
                SpanLLMMetadata.provider,
                func.count(SpanLLMMetadata.id).label("llm_calls"),
                func.sum(SpanLLMMetadata.prompt_tokens).label("prompt_tokens"),
                func.sum(SpanLLMMetadata.completion_tokens).label("completion_tokens"),
                func.sum(SpanLLMMetadata.total_tokens).label("total_tokens"),
                func.sum(SpanLLMMetadata.cost_usd).label("total_cost_usd"),
            )
            .where(*l_filter)
            .group_by(SpanLLMMetadata.model, SpanLLMMetadata.provider)
            .order_by(desc(func.sum(SpanLLMMetadata.cost_usd)))
        )
        return (await self.db.execute(stmt)).mappings().all()

    # ── 9. KPI metrics (current or previous window) ────────────────────────

    async def kpi_metrics(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
    ) -> dict:
        t_filter = self._time_filter(Trace.created_at, from_dt, to_dt)
        o_filter = self._time_filter(Observation.created_at, from_dt, to_dt)
        l_filter = self._time_filter(SpanLLMMetadata.created_at, from_dt, to_dt)

        total_traces = (
            await self.db.execute(select(func.count(Trace.id)).where(*t_filter))
        ).scalar_one()

        obs_row = (
            await self.db.execute(
                select(
                    func.round(
                        cast(
                            100.0
                            * func.count(case((Observation.status == "success", 1)))
                            / func.nullif(func.count(Observation.id), 0),
                            Numeric
                        ),
                        1,
                    ).label("success_rate"),
                    func.round(cast(func.avg(Observation.latency_ms), Numeric), 0).label("avg_latency_ms"),
                ).where(*o_filter)
            )
        ).mappings().first()

        llm_row = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(SpanLLMMetadata.total_tokens), 0).label("total_tokens"),
                    func.coalesce(func.sum(SpanLLMMetadata.cost_usd), 0).label("estimated_cost_usd"),
                ).where(*l_filter)
            )
        ).mappings().first()

        return {
            "total_traces": total_traces,
            "success_rate": float(obs_row["success_rate"] or 0),
            "avg_latency_ms": float(obs_row["avg_latency_ms"] or 0),
            "total_tokens": int(llm_row["total_tokens"]),
            "estimated_cost_usd": float(llm_row["estimated_cost_usd"]),
        }

    # ── 10. Trace volume over time ─────────────────────────────────────────

    async def trace_volume(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
        granularity: str,
    ) -> Sequence:
        bucket = func.date_trunc(granularity, Trace.created_at).label("bucket")
        t_filter = self._time_filter(Trace.created_at, from_dt, to_dt)
        stmt = (
            select(bucket, func.count(Trace.id).label("trace_count"))
            .where(*t_filter)
            .group_by(bucket)
            .order_by(bucket)
        )
        return (await self.db.execute(stmt)).mappings().all()

    # ── 11. Recent traces ─────────────────────────────────────────────────

    async def recent_traces(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
        limit: int,
    ) -> Sequence:
        t_filter = self._time_filter(Trace.created_at, from_dt, to_dt)
        stmt = (
            select(
                Trace.id.label("trace_id"),
                Trace.name,
                Trace.status,
                Trace.created_at,
                func.coalesce(func.sum(Observation.latency_ms), 0).label("total_latency_ms"),
                func.coalesce(func.sum(SpanLLMMetadata.cost_usd), 0).label("total_cost_usd"),
                func.count(distinct(Observation.id)).label("span_count"),
            )
            .outerjoin(Observation, Observation.trace_id == Trace.id)
            .outerjoin(SpanLLMMetadata, SpanLLMMetadata.observation_id == Observation.id)
            .where(*t_filter)
            .group_by(Trace.id)
            .order_by(desc(Trace.created_at))
            .limit(limit)
        )
        return (await self.db.execute(stmt)).mappings().all()

    # ── 12. Token distribution ─────────────────────────────────────────────

    async def token_distribution(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
    ) -> Sequence:
        l_filter = self._time_filter(SpanLLMMetadata.created_at, from_dt, to_dt)
        tokens_per_model = func.sum(SpanLLMMetadata.total_tokens)
        grand_total = func.nullif(func.sum(tokens_per_model).over(), 0)

        stmt = (
            select(
                SpanLLMMetadata.model,
                SpanLLMMetadata.provider,
                tokens_per_model.label("total_tokens"),
                func.round(cast(100.0 * tokens_per_model / grand_total, Numeric), 1).label("token_share_pct"),
            )
            .where(*l_filter)
            .group_by(SpanLLMMetadata.model, SpanLLMMetadata.provider)
            .order_by(desc(tokens_per_model))
        )
        return (await self.db.execute(stmt)).mappings().all()

    # ── 13. Model usage share ──────────────────────────────────────────────

    async def model_usage_share(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
    ) -> Sequence:
        l_filter = self._time_filter(SpanLLMMetadata.created_at, from_dt, to_dt)
        tokens_per_model = func.sum(SpanLLMMetadata.total_tokens)
        grand_total = func.nullif(func.sum(tokens_per_model).over(), 0)

        stmt = (
            select(
                SpanLLMMetadata.model,
                SpanLLMMetadata.provider,
                func.count(SpanLLMMetadata.id).label("llm_calls"),
                tokens_per_model.label("total_tokens"),
                func.sum(SpanLLMMetadata.cost_usd).label("total_cost_usd"),
                func.round(cast(100.0 * tokens_per_model / grand_total, Numeric), 1).label("usage_share_pct"),
            )
            .where(*l_filter)
            .group_by(SpanLLMMetadata.model, SpanLLMMetadata.provider)
            .order_by(desc(tokens_per_model))
        )
        return (await self.db.execute(stmt)).mappings().all()

    # ── 14. System status ──────────────────────────────────────────────────

    async def system_status(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
    ) -> dict:
        o_filter = self._time_filter(Observation.created_at, from_dt, to_dt)
        stmt = select(
            func.count(distinct(Observation.name)).label("active_tools"),
            func.count(
                case(
                    (Observation.status.notin_(["success", "error"]), 1)
                )
            ).label("queue_depth"),
            func.count(
                case((Observation.status == "error", 1))
            ).label("total_errors"),
        ).where(*o_filter)
        return dict((await self.db.execute(stmt)).mappings().first())

    # ── 15. Drift alerts ───────────────────────────────────────────────────

    async def drift_alerts(
        self,
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
        limit: int,
    ) -> Sequence:
        o_filter = self._time_filter(Observation.created_at, from_dt, to_dt)
        error_count = func.count(
            case((Observation.status == "error", 1))
        ).label("error_count")
        total_count = func.count(Observation.id).label("total_count")
        error_rate = func.round(
            cast(
                100.0
                * func.count(case((Observation.status == "error", 1)))
                / func.nullif(func.count(Observation.id), 0),
                Numeric
            ),
            1,
        ).label("error_rate_pct")
        last_seen = func.max(Observation.created_at).label("last_seen")

        stmt = (
            select(
                Observation.name.label("source"),
                error_count,
                total_count,
                error_rate,
                last_seen,
            )
            .where(*o_filter)
            .group_by(Observation.name)
            .having(
                func.count(case((Observation.status == "error", 1))) > 0
            )
            .order_by(desc(error_count))
            .limit(limit)
        )
        return (await self.db.execute(stmt)).mappings().all()

    # ── 16. Users ──────────────────────────────────────────────────────────

    async def list_users(self) -> Sequence:
        return (await self.db.execute(select(User))).scalars().all()

    async def get_user(self, user_id: int) -> Optional[User]:
        return (
            await self.db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _time_filter(column, from_dt, to_dt) -> list:
        """Return a list of WHERE conditions (possibly empty)."""
        conds = []
        if from_dt:
            conds.append(column >= _utc_naive(from_dt))
        if to_dt:
            conds.append(column <= _utc_naive(to_dt))
        return conds


# ---------------------------------------------------------------------------
# Averages table (lightweight Table object — no full ORM model needed)
# ---------------------------------------------------------------------------
# The `averages` table is created externally (e.g. by the evaluation pipeline).
# We reflect just enough columns for SQLAlchemy Core queries.

from sqlalchemy import Column, Date, Float, Integer as SAInteger, MetaData, String, Table  # noqa: E402

_meta = MetaData()

averages_table = Table(
    "averages",
    _meta,
    Column("agent_name",      String),
    Column("project_id",      String,  nullable=True),
    Column("evaluation_date", Date),
    Column("relevancy_avg",   Float,   nullable=True),
    Column("safety_avg",      Float,   nullable=True),
    Column("coherence_avg",   Float,   nullable=True),
    Column("helpfulness_avg", Float,   nullable=True),
    Column("toxicity_avg",    Float,   nullable=True),
    Column("overall_score",   Float,   nullable=True),
    Column("total_evaluated", SAInteger, nullable=True),
)

_a = averages_table.c   # shorthand alias


# ---------------------------------------------------------------------------
# EvaluationRepository
# ---------------------------------------------------------------------------

class EvaluationRepository:
    """
    All evaluation queries against the `averages` table.
    Zero raw SQL — every query uses SQLAlchemy Core expressions.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── 1. Daily trend ──────────────────────────────────────────────────────

    async def daily(
        self,
        agent_name: str,
        days: int,
        project_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Return one row per evaluation_date for the given agent,
        ordered oldest-first.  Dates are formatted as 'YYYY-MM-DD' strings.
        """
        from datetime import date, timedelta
        cutoff = date.today() - timedelta(days=days)

        stmt = (
            select(
                _a.agent_name,
                _a.project_id,
                _a.evaluation_date,
                _a.relevancy_avg,
                _a.safety_avg,
                _a.coherence_avg,
                _a.helpfulness_avg,
                _a.toxicity_avg,
                _a.overall_score,
                _a.total_evaluated,
            )
            .where(_a.agent_name == agent_name)
            .where(_a.evaluation_date >= cutoff)
            .order_by(_a.evaluation_date)
        )
        if project_id:
            stmt = stmt.where(_a.project_id == project_id)

        rows = (await self.db.execute(stmt)).mappings().all()
        return [
            {
                **dict(r),
                "evaluation_date": r["evaluation_date"].strftime("%Y-%m-%d")
                if r.get("evaluation_date")
                else None,
            }
            for r in rows
        ]

    # ── 2. Weekly aggregation ───────────────────────────────────────────────

    async def weekly(
        self,
        agent_name: str,
        weeks: int,
        project_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Return one row per ISO week (Monday-Sunday) for the given agent.
        All metric columns are averaged; total_evaluated is summed.
        Dates are formatted as 'YYYY-MM-DD' strings.
        """
        from datetime import date, timedelta

        cutoff = date.today() - timedelta(weeks=weeks)

        # IMPORTANT: use literal_column("'week'") so PostgreSQL sees the string
        # inlined in SQL (not as a bound parameter $N::VARCHAR). When parameterised,
        # PostgreSQL cannot match the GROUP BY / ORDER BY expression to the SELECT
        # expression and raises a GroupingError.
        _week_lit = literal_column("'week'")
        week_trunc = func.date_trunc(_week_lit, _a.evaluation_date)
        week_start = week_trunc.label("week_start")

        def _avg_round(col):
            return func.round(func.cast(func.avg(col), Numeric), 4)

        stmt = (
            select(
                week_start,
                _avg_round(_a.relevancy_avg).label("relevancy_avg"),
                _avg_round(_a.safety_avg).label("safety_avg"),
                _avg_round(_a.coherence_avg).label("coherence_avg"),
                _avg_round(_a.helpfulness_avg).label("helpfulness_avg"),
                _avg_round(_a.toxicity_avg).label("toxicity_avg"),
                _avg_round(_a.overall_score).label("overall_score"),
                func.sum(_a.total_evaluated).label("total_evaluated"),
                func.count().label("days_in_week"),
            )
            .where(_a.agent_name == agent_name)
            .where(_a.evaluation_date >= cutoff)
            .group_by(week_trunc)
            .order_by(week_trunc)
        )
        if project_id:
            stmt = stmt.where(_a.project_id == project_id)

        rows = (await self.db.execute(stmt)).mappings().all()

        def _fmt(d):
            return d.strftime("%Y-%m-%d") if d else None

        result = []
        for r in rows:
            row_dict = dict(r)
            ws = row_dict.get("week_start")
            row_dict["week_start"] = _fmt(ws)
            # Compute week_end (Sunday): date_trunc returns datetime, so guard with hasattr
            if ws is not None:
                ws_date = ws.date() if hasattr(ws, "date") and callable(ws.date) else ws
                row_dict["week_end"] = _fmt(ws_date + timedelta(days=6))
            else:
                row_dict["week_end"] = None
            result.append(row_dict)
        return result

    # ── 3. Latest evaluation for every agent ───────────────────────────────

    async def latest_all(self, project_id: Optional[str] = None) -> list[dict]:
        """
        Return the most recent evaluation row per (agent_name, project_id).
        Uses a ROW_NUMBER() window via SQLAlchemy ORM window functions.
        """
        rn = func.row_number().over(
            partition_by=[_a.agent_name, func.coalesce(_a.project_id, "")],
            order_by=_a.evaluation_date.desc(),
        ).label("rn")

        sub = select(
            _a.agent_name,
            _a.project_id,
            _a.evaluation_date,
            _a.relevancy_avg,
            _a.safety_avg,
            _a.coherence_avg,
            _a.helpfulness_avg,
            _a.toxicity_avg,
            _a.overall_score,
            _a.total_evaluated,
            rn,
        )
        if project_id:
            sub = sub.where(_a.project_id == project_id)

        sub = sub.subquery("ranked")

        stmt = (
            select(sub)
            .where(sub.c.rn == 1)
            .order_by(sub.c.agent_name, sub.c.project_id)
        )

        rows = (await self.db.execute(stmt)).mappings().all()
        return [
            {
                **{k: v for k, v in dict(r).items() if k != "rn"},
                "evaluation_date": r["evaluation_date"].strftime("%Y-%m-%d")
                if r.get("evaluation_date")
                else None,
            }
            for r in rows
        ]

    # ── 4. Available projects for an agent ─────────────────────────────────

    async def agent_projects(self, agent_name: str) -> list[str]:
        """Return distinct non-null project_ids for the given agent."""
        stmt = (
            select(_a.project_id)
            .distinct()
            .where(_a.agent_name == agent_name)
            .where(_a.project_id.isnot(None))
            .order_by(_a.project_id)
        )
        rows = (await self.db.execute(stmt)).all()
        return [r[0] for r in rows if r[0]]

    # ── 5. Latest single-agent evaluation ──────────────────────────────────

    async def agent_latest(
        self,
        agent_name: str,
        project_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Return the single most recent evaluation row for an agent."""
        stmt = (
            select(
                _a.agent_name,
                _a.project_id,
                _a.evaluation_date,
                _a.relevancy_avg,
                _a.safety_avg,
                _a.coherence_avg,
                _a.helpfulness_avg,
                _a.toxicity_avg,
                _a.overall_score,
                _a.total_evaluated,
            )
            .where(_a.agent_name == agent_name)
            .order_by(_a.evaluation_date.desc())
            .limit(1)
        )
        if project_id:
            stmt = stmt.where(_a.project_id == project_id)

        row = (await self.db.execute(stmt)).mappings().first()
        if not row:
            return None
        data = dict(row)
        if data.get("evaluation_date"):
            data["evaluation_date"] = data["evaluation_date"].strftime("%Y-%m-%d")
        return data

    # ── 6. Summary stats ───────────────────────────────────────────────────

    async def agent_stats(
        self,
        agent_name: str,
        days: int,
        project_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Return aggregate summary statistics for an agent over a rolling window.
        Returns None when no data exists for the requested window.
        """
        from datetime import date, timedelta
        cutoff = date.today() - timedelta(days=days)

        def _avg(col):
            return func.round(func.cast(func.avg(col), Numeric), 4)

        def _min(col):
            return func.round(func.cast(func.min(col), Numeric), 4)

        def _max(col):
            return func.round(func.cast(func.max(col), Numeric), 4)

        stmt = (
            select(
                func.count().label("total_days"),
                _avg(_a.relevancy_avg).label("avg_relevancy"),
                _avg(_a.safety_avg).label("avg_safety"),
                _avg(_a.coherence_avg).label("avg_coherence"),
                _avg(_a.helpfulness_avg).label("avg_helpfulness"),
                _avg(_a.toxicity_avg).label("avg_toxicity"),
                _avg(_a.overall_score).label("avg_overall"),
                _min(_a.overall_score).label("min_overall"),
                _max(_a.overall_score).label("max_overall"),
                func.sum(_a.total_evaluated).label("total_evaluated"),
                func.round(
                    func.cast(func.avg(_a.total_evaluated), Numeric), 2
                ).label("avg_daily_evaluated"),
            )
            .where(_a.agent_name == agent_name)
            .where(_a.evaluation_date >= cutoff)
        )
        if project_id:
            stmt = stmt.where(_a.project_id == project_id)

        row = (await self.db.execute(stmt)).mappings().first()
        if not row or not row["total_days"]:
            return None
        return dict(row)

