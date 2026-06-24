"""Span context for nested operations"""

import uuid
import time
from typing import Optional, Dict, Any, List


class SpanContext:
    """Represents a single nested operation within a trace."""

    def __init__(self, trace_id: str, name: str, parent_span_id: Optional[str] = None):
        self.trace_id       = trace_id
        self.name           = name
        self.parent_span_id = parent_span_id
        self.span_id        = str(uuid.uuid4())
        self.input:  Optional[Dict] = None
        self.output: Optional[Dict] = None
        self.status: str = "success"
        self._start_time    = time.time()
        self._events: List[Dict] = []

    def log_event(
        self,
        name:     str,
        level:    str  = "INFO",
        message:  str  = None,
        metadata: Dict = None,
    ) -> None:
        """Log a custom event on this span."""
        self._events.append({
            "type":      "event",
            "span_id":   self.span_id,
            "name":      name,
            "level":     level,
            "message":   message,
            "metadata":  metadata or {},
            "timestamp": time.time(),
        })

    def finalize(self) -> Dict[str, Any]:
        """Finalize and return the span event."""
        return {
            "type":           "span",
            "trace_id":       self.trace_id,
            "span_id":        self.span_id,
            "parent_span_id": self.parent_span_id,
            "name":           self.name,
            "input":          self.input,
            "output":         self.output,
            "status":         self.status,
            "latency_ms":     int((time.time() - self._start_time) * 1000),
            "events":         self._events,
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.status = "error"
        return False
