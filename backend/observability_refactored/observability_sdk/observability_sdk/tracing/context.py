"""
Context propagation for nested traces and generations.
Deliberately does NOT import TraceContext or GenerationContext to avoid
circular imports. trace.py and generation.py import from here; we must
never import from those modules here.
"""

import contextvars
from typing import Optional

_active_trace: contextvars.ContextVar = contextvars.ContextVar(
    "_active_trace", default=None
)


def get_current_trace():
    """Get the currently active trace (returns TraceContext or None)."""
    return _active_trace.get()


def set_current_trace(trace):
    """Set the current active trace. Returns a token for reset."""
    return _active_trace.set(trace)


def reset_current_trace(token) -> None:
    """Reset the active trace to its previous value using the token."""
    _active_trace.reset(token)


def get_current_generation():
    """
    Get the currently active GenerationContext (or None).
    Delegates to generation.py's contextvar to avoid duplication.
    """
    from observability_sdk.tracing.generation import get_current_generation as _get
    return _get()


__all__ = [
    "get_current_trace",
    "set_current_trace",
    "reset_current_trace",
    "get_current_generation",
]
