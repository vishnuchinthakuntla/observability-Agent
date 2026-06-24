"""Trace context - root of the observability tree"""

import uuid
import time
from typing import Optional, Dict, Any, Generator
from contextlib import contextmanager

from observability_sdk.tracing.span import SpanContext
from observability_sdk.tracing.generation import GenerationContext
from observability_sdk.tracing.context import set_current_trace, reset_current_trace


class TraceContext:
    """Root trace context for a single user request or pipeline run."""

    def __init__(
        self,
        client: "SHClient",
        name: str,
        user_id:    Optional[str]  = None,
        session_id: Optional[str]  = None,
        input_data: Optional[Dict] = None,
        metadata:   Optional[Dict] = None,
    ):
        self._client    = client
        self.trace_id   = str(uuid.uuid4())
        self.name       = name
        self.user_id    = user_id
        self.session_id = session_id
        self.input      = input_data
        self.metadata   = metadata
        self.output:  Optional[Dict] = None
        self.status:  str = "success"
        self._events: list = []
        self._start_time = time.time()

    @contextmanager
    def span(self, name: str, parent_span_id: Optional[str] = None) -> Generator[SpanContext, None, None]:
        """Create a nested span."""
        span = SpanContext(self.trace_id, name, parent_span_id)
        try:
            yield span
        except Exception:
            span.status = "error"
            raise
        finally:
            self._events.append(span.finalize())

    @contextmanager
    def generation(self, model: str, provider: Optional[str] = None) -> Generator[GenerationContext, None, None]:
        """
        Create an LLM generation span.

        IMPORTANT: GenerationContext is entered as a context manager so that
        the _generation_context contextvar is active during the user's function.
        This is what makes capture_generation_response() work — it looks up
        the contextvar to find the active generation.
        """
        gen = GenerationContext(self.trace_id, model, provider)
        with gen:  # ← sets _generation_context so capture_generation_response() can find it
            try:
                yield gen
            finally:
                self._events.append(gen.finalize())

    def log_event(
        self,
        name: str,
        level:    str  = "INFO",
        message:  str  = None,
        metadata: Dict = None,
    ) -> None:
        """Log a custom event on this trace."""
        self._events.append({
            "type":     "event",
            "trace_id": self.trace_id,
            "name":     name,
            "level":    level,
            "message":  message,
            "metadata": metadata or {},
        })

    def finalize(self) -> Dict[str, Any]:
        """Finalize and return the trace event."""
        return {
            "type":       "trace",
            "trace_id":   self.trace_id,
            "name":       self.name,
            "user_id":    self.user_id,
            "session_id": self.session_id,
            "input":      self.input,
            "output":     self.output,
            "metadata":   self.metadata,
            "status":     self.status,
            "latency_ms": int((time.time() - self._start_time) * 1000),
        }

    def __enter__(self):
        self._token = set_current_trace(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.status = "error"

        trace_event = self.finalize()
        all_events  = [trace_event] + self._events
        self._client.add_events(all_events)

        reset_current_trace(self._token)
        return False
