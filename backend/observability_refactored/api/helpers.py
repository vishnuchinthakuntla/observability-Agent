"""
Shared helpers for the custom API routes.
Date-range resolution, time-bucket granularity, naive-UTC conversion.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Tuple

from fastapi import HTTPException

# ------------------------------------------------------------------ #
# Preset map
# ------------------------------------------------------------------ #

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
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Returns (from_dt, to_dt) as UTC-aware datetimes, OR (None, None) if no
    filter was requested (so callers can show ALL data, like Langfuse default).
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

    return None, None


def bucket_granularity(from_dt, to_dt) -> str:
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
