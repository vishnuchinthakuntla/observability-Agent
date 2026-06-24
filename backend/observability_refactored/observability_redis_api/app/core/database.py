"""
API database setup — re-exports from shared.core.database.

The ORM models (Trace, Observation, SpanLLMMetadata) import ``Base``
from here, so we expose it directly.
"""
from shared.core.database import (  # noqa: F401
    Base,
    DatabaseManager,
    db_manager,
    get_db,
)

__all__ = ["Base", "DatabaseManager", "db_manager", "get_db"]
