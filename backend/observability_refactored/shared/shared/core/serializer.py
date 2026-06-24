"""
JSON serialisation utilities — single source of truth.

Handles Pydantic v1/v2, dataclasses, enums, datetimes, and nested
dicts/lists so that any service can safely convert arbitrary Python
objects before sending them over the wire or storing them.
"""

from __future__ import annotations

import dataclasses
import enum
import json
from datetime import date, datetime
from typing import Any


def safe_serialize(obj: Any) -> Any:
    """
    Recursively convert *obj* to a JSON-serialisable value.

    Handles, in order:
    - Primitives (``None``, ``bool``, ``int``, ``float``, ``str``)
    - Pydantic v2 models (``model_dump``)
    - Pydantic v1 models (``dict``)
    - Dataclasses (``dataclasses.asdict``)
    - Enums (returns ``value``)
    - ``datetime`` / ``date`` (returns ISO-8601 string)
    - ``dict`` (recurses on keys and values)
    - ``list``, ``tuple``, ``set`` (recurses on items)
    - Fallback: ``str(obj)``
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

    if isinstance(obj, dict):
        return {str(k): safe_serialize(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [safe_serialize(i) for i in obj]

    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


def to_json(obj: Any, **kwargs: Any) -> str:
    """Serialise *obj* to a JSON string using :func:`safe_serialize`."""
    return json.dumps(safe_serialize(obj), **kwargs)
