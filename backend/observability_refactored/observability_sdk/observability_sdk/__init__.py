"""
SH Observability SDK
"""

import atexit
from typing import Optional

from observability_sdk.client import SHClient
from observability_sdk.decorators.observe import observe
from observability_sdk.config import Config
from observability_sdk.tracing.trace import TraceContext
from observability_sdk.tracing.span import SpanContext
from observability_sdk.tracing.generation import GenerationContext, get_current_generation
from observability_sdk.tracing.context import get_current_trace

__all__ = [
    # Init
    "init",
    "init_client",
    "get_client",
    "flush",
    "get_stats",
    # Decorator
    "observe",
    # Explicit hook
    "capture_generation_response",
    # Context classes
    "SHClient",
    "Config",
    "TraceContext",
    "SpanContext",
    "GenerationContext",
    # Context helpers
    "get_current_trace",
    "get_current_generation",
]

_default_client: Optional[SHClient] = None


def init(
    api_url:        str,
    project_id:     str,
    api_token:      Optional[str]   = None,
    timeout:        float           = 5.0,
    batch_size:     int             = 100,
    flush_interval: float           = 5.0,
    enabled:        bool            = True,
    debug:          bool            = False,
) -> SHClient:
    """
    Initialize the global SDK client.

    Args:
        api_url:        Observability API endpoint (e.g. http://localhost:8000)
        project_id:     Your project identifier
        api_token:      Authentication token
        timeout:        HTTP timeout in seconds
        batch_size:     Events to buffer before auto-flush
        flush_interval: Seconds between background flushes
        enabled:        Set False to disable all observability (useful in tests)
        debug:          Print warnings when tokens are not captured
    """
    global _default_client

    config = Config(
        api_url        = api_url,
        project_id     = project_id,
        api_token      = api_token,
        timeout        = timeout,
        batch_size     = batch_size,
        flush_interval = flush_interval,
        enabled        = enabled,
        debug          = debug,
    )

    _default_client = SHClient(config)
    return _default_client


# Alias so both import styles work:
#   observability_sdk.init(...)
#   observability_sdk.init_client(...)
init_client = init


def get_client() -> SHClient:
    """
    Get the global SDK client.
    Raises RuntimeError if init() / init_client() has not been called.
    """
    if _default_client is None:
        raise RuntimeError(
            "SH SDK not initialized. Call init() first:\n"
            "    import observability_sdk as obs\n"
            "    obs.init(api_url='http://localhost:8000', project_id='my-project', api_token='...')"
        )
    return _default_client


def flush() -> None:
    """Flush all pending events to the API immediately."""
    if _default_client is not None:
        _default_client.flush()


def get_stats() -> dict:
    """Return basic stats from the active client."""
    if _default_client is None:
        return {"error": "SDK not initialized"}
    return _default_client.get_stats()


def capture_generation_response(response) -> None:
    """
    Capture an LLM response for the currently active generation.

    Call this immediately after calling an LLM, BEFORE parsing the response,
    so that tokens and cost are recorded regardless of what your function returns.

    Example:
        @observe(as_type="generation", model="gpt-4o", provider="openai")
        def process_query(query: str):
            response = llm.invoke(query)
            capture_generation_response(response)  # ← tokens captured here
            return parse_response(response)        # ← return your business object
    """
    gen = get_current_generation()
    if gen is None:
        if _default_client is not None and getattr(_default_client.config, "debug", False):
            print("[observability] capture_generation_response: no active generation context")
        return
    gen.capture(response)


def _cleanup():
    if _default_client:
        if getattr(_default_client.config, "debug", False):
            stats = _default_client.get_stats()
            print(f"[observability] Shutting down. Stats: {stats}")
        _default_client.close()


atexit.register(_cleanup)
