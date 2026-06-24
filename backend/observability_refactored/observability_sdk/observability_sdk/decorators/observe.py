"""@observe decorator for automatic instrumentation"""

import functools
import inspect
from typing import Any, Callable, Optional

# get_client imported lazily inside wrapper to avoid circular import
from observability_sdk.tracing.context import get_current_trace
from observability_sdk.utils.serializer import safe_serialize


class observe:
    """
    Decorator for automatic trace / span / generation capture.

    Behaviour (as_type="auto"):
        - Root call (no active trace)  → creates a TRACE
        - Nested call (inside a trace) → creates a SPAN

    Generation pattern — use the explicit hook for best results:

        @observe(as_type="generation", model="gpt-4o", provider="openai")
        def process_query(query: str):
            response = llm.invoke(query)
            capture_generation_response(response)  # ← tokens captured here
            return parse_response(response)        # ← business object returned

    Parameters:
        name          : Override observation name (default: function name)
        as_type       : "auto" | "trace" | "span" | "generation"
        model         : Required when as_type="generation"
        provider      : "openai" | "anthropic" | "gemini" | "google" | "azure" | "vertex"
        capture_input : Record function arguments (default: True)
        capture_output: Record return value as parsed_output (default: True)
        user_id       : Attach a user identifier to the root trace
        session_id    : Attach a session identifier to the root trace
    """

    def __init__(
        self,
        name:           Optional[str]  = None,
        as_type:        str            = "auto",
        model:          Optional[str]  = None,
        provider:       Optional[str]  = None,
        capture_input:  bool           = True,
        capture_output: bool           = True,
        user_id:        Optional[str]  = None,
        session_id:     Optional[str]  = None,
    ):
        self.name           = name
        self.as_type        = as_type
        self.model          = model
        self.provider       = provider
        self.capture_input  = capture_input
        self.capture_output = capture_output
        self.user_id        = user_id
        self.session_id     = session_id

    def __call__(self, func: Callable) -> Callable:
        dec = self

        # ── helpers ──────────────────────────────────────────────────────

        def _capture_input(*args, **kwargs) -> Optional[dict]:
            if not dec.capture_input:
                return None
            try:
                sig   = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                return {
                    k: safe_serialize(v)
                    for k, v in bound.arguments.items()
                    if k != "self"
                }
            except Exception:
                return None

        def _capture_output(result: Any) -> Optional[dict]:
            if not dec.capture_output:
                return None
            try:
                serialized = safe_serialize(result)
                return serialized if isinstance(serialized, dict) else {"result": serialized}
            except Exception:
                return {"result": str(result)}

        # ── sync wrapper ─────────────────────────────────────────────────

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            from observability_sdk import get_client
            from observability_sdk.config import Config as _Config
            client        = get_client()
            fn_name       = dec.name or func.__name__.replace("_", "-")
            input_data    = _capture_input(*args, **kwargs)
            current_trace = get_current_trace()
            etype         = dec.as_type
            if etype == "auto":
                etype = "trace" if current_trace is None else "span"

            # TRACE ────────────────────────────────────────────────────────
            if etype == "trace":
                with client.trace(
                    name=fn_name,
                    user_id=dec.user_id,
                    session_id=dec.session_id,
                    input_data=input_data,
                ) as trace:
                    try:
                        result = func(*args, **kwargs)
                        trace.output = _capture_output(result)
                        return result
                    except Exception:
                        trace.status = "error"
                        raise

            # GENERATION ───────────────────────────────────────────────────
            elif etype == "generation":
                if not dec.model:
                    raise ValueError("@observe(as_type='generation') requires model=")

                def _run_gen(trace):
                    with trace.generation(dec.model, provider=dec.provider) as gen:
                        gen._event["name"]  = fn_name
                        gen._event["input"] = input_data
                        try:
                            result = func(*args, **kwargs)
                            # Store the return value as parsed_output
                            # (tokens come via capture_generation_response() hook inside the fn)
                            out = _capture_output(result)
                            if out:
                                gen.set_parsed_output(result)
                            # Warn if nothing was captured
                            if gen._event.get("prompt_tokens", 0) == 0:
                                if getattr(client.config, "debug", False):
                                    print(
                                        f"[observability] WARNING: No usage captured for '{fn_name}'. "
                                        "Call capture_generation_response(response) inside your function."
                                    )
                            return result
                        except Exception:
                            gen._event["status"] = "error"
                            raise

                if current_trace is not None:
                    return _run_gen(current_trace)
                else:
                    with client.trace(name=f"{fn_name}-auto", input_data=input_data) as auto_trace:
                        return _run_gen(auto_trace)

            # SPAN ─────────────────────────────────────────────────────────
            else:
                if current_trace is not None:
                    with current_trace.span(fn_name) as span:
                        span.input = input_data
                        try:
                            result = func(*args, **kwargs)
                            span.output = _capture_output(result)
                            return result
                        except Exception:
                            span.status = "error"
                            raise
                else:
                    with client.trace(name=fn_name, input_data=input_data) as trace:
                        try:
                            result = func(*args, **kwargs)
                            trace.output = _capture_output(result)
                            return result
                        except Exception:
                            trace.status = "error"
                            raise

        # ── async wrapper ────────────────────────────────────────────────

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            from observability_sdk import get_client
            client        = get_client()
            fn_name       = dec.name or func.__name__.replace("_", "-")
            input_data    = _capture_input(*args, **kwargs)
            current_trace = get_current_trace()
            etype         = dec.as_type
            if etype == "auto":
                etype = "trace" if current_trace is None else "span"

            # TRACE ────────────────────────────────────────────────────────
            if etype == "trace":
                with client.trace(
                    name=fn_name,
                    user_id=dec.user_id,
                    session_id=dec.session_id,
                    input_data=input_data,
                ) as trace:
                    try:
                        result = await func(*args, **kwargs)
                        trace.output = _capture_output(result)
                        return result
                    except Exception:
                        trace.status = "error"
                        raise

            # GENERATION ───────────────────────────────────────────────────
            elif etype == "generation":
                if not dec.model:
                    raise ValueError("@observe(as_type='generation') requires model=")

                async def _run_gen(trace):
                    with trace.generation(dec.model, provider=dec.provider) as gen:
                        gen._event["name"]  = fn_name
                        gen._event["input"] = input_data
                        try:
                            result = await func(*args, **kwargs)
                            out = _capture_output(result)
                            if out:
                                gen.set_parsed_output(result)
                            if gen._event.get("prompt_tokens", 0) == 0:
                                if getattr(client.config, "debug", False):
                                    print(
                                        f"[observability] WARNING: No usage captured for '{fn_name}'. "
                                        "Call capture_generation_response(response) inside your function."
                                    )
                            return result
                        except Exception:
                            gen._event["status"] = "error"
                            raise

                if current_trace is not None:
                    return await _run_gen(current_trace)
                else:
                    with client.trace(name=f"{fn_name}-auto", input_data=input_data) as auto_trace:
                        return await _run_gen(auto_trace)

            # SPAN ─────────────────────────────────────────────────────────
            else:
                if current_trace is not None:
                    with current_trace.span(fn_name) as span:
                        span.input = input_data
                        try:
                            result = await func(*args, **kwargs)
                            span.output = _capture_output(result)
                            return result
                        except Exception:
                            span.status = "error"
                            raise
                else:
                    with client.trace(name=fn_name, input_data=input_data) as trace:
                        try:
                            result = await func(*args, **kwargs)
                            trace.output = _capture_output(result)
                            return result
                        except Exception:
                            trace.status = "error"
                            raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
