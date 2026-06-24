"""
JSON serialisation utilities — standalone, no shared dependency.
Handles Pydantic v1/v2, dataclasses, enums, datetimes, UUIDs,
and nested dicts/lists.
"""

import dataclasses
import enum
import json
from datetime import date, datetime
from typing import Any
from uuid import UUID


def safe_serialize(obj: Any) -> Any:
    """
    Recursively convert obj to a JSON-serialisable value.
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return safe_serialize(obj.model_dump())
        except Exception:
            pass

    # Pydantic v1
    if hasattr(obj, "dict") and callable(obj.dict):
        try:
            return safe_serialize(obj.dict())
        except Exception:
            pass

    # Dataclasses
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        try:
            return safe_serialize(dataclasses.asdict(obj))
        except Exception:
            pass

    if isinstance(obj, enum.Enum):
        return obj.value

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, UUID):
        return str(obj)

    if isinstance(obj, dict):
        return {str(k): safe_serialize(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [safe_serialize(i) for i in obj]

    # Last resort — try JSON round-trip, then str
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


def to_json(obj: Any, **kwargs: Any) -> str:
    """Serialise obj to a JSON string."""
    return json.dumps(safe_serialize(obj), **kwargs)


__all__ = ["safe_serialize", "to_json"]
