"""Main SDK Client — delegates all batching/sending to BatchProcessor in http_exporter."""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from observability_sdk.config import Config
from observability_sdk.tracing.trace import TraceContext
from observability_sdk.exporters.http_exporter import BatchProcessor

logger = logging.getLogger(__name__)


class SHClient:
    """
    Enterprise SDK Client.

    Batching, retries, background flushing, and HTTP transport are all
    handled by BatchProcessor (exporters/http_exporter.py).
    SHClient owns the public API: trace(), add_events(), flush(), close().
    """

    def __init__(self, config: Config):
        self.config = config
        self._processor = BatchProcessor(
            api_url=config.api_url,
            project_id=config.project_id,
            api_token=config.api_token,
            batch_size=config.batch_size,
            flush_interval=config.flush_interval,
            max_queue_size=config.max_queue_size,
            timeout=config.timeout,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def trace(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        input_data: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
    ) -> TraceContext:
        """Create a new trace context manager."""
        return TraceContext(
            client=self,
            name=name,
            user_id=user_id,
            session_id=session_id,
            input_data=input_data,
            metadata=metadata,
        )

    def add_events(self, events: List[Dict[str, Any]]) -> None:
        """
        Add a list of events to the outbound batch.
        Called automatically by TraceContext.__exit__().
        """
        if not self.config.enabled:
            return
        # Stamp created_at on any event that doesn't have it
        for event in events:
            if "created_at" not in event:
                event["created_at"] = datetime.utcnow().isoformat()
        self._processor.add_events(events)

    def add_event(self, event: Dict[str, Any]) -> None:
        """Add a single event — convenience wrapper around add_events()."""
        self.add_events([event])

    def flush(self) -> None:
        """Force-flush all buffered events to the API immediately."""
        self._processor.flush()

    def close(self) -> None:
        """Flush remaining events and shut down the background thread."""
        self._processor.close()

    def get_stats(self) -> dict:
        """Return basic stats from the batch processor."""
        return {
            "buffered_events": len(self._processor._batch),
            "running": self._processor._running,
        }

    # ------------------------------------------------------------------ #
    # Context manager support
    # ------------------------------------------------------------------ #

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
