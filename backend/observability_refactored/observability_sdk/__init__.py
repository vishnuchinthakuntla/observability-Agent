"""
Observability SDK - Production Grade Final v2
Copy this file into any Python project and import it.

Usage:
    from observability_sdk import init_client, observe, capture_generation_response

    init_client(
        endpoint="http://localhost:8001",
        api_key="your-token",
        service_name="my-app",
        debug=True,  # Optional: enables debug warnings
    )

    @observe(as_type="generation", model="gpt-4o", provider="openai")
    def process_query(query: str):
        response = llm.invoke(query)
        capture_generation_response(response)  # ← Explicit hook
        return parse_response(response)        # ← Return business object
"""

import atexit
import contextvars
import dataclasses
import enum
import functools
import inspect
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, date
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from uuid import UUID

import requests


# ============================================================================
# SAFE SERIALIZER
# ============================================================================

def _safe_serialize(obj: Any) -> Any:
    """Recursively convert obj to a JSON-serialisable value."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return _safe_serialize(obj.model_dump())
        except Exception:
            pass

    # Pydantic v1
    if hasattr(obj, "dict") and callable(obj.dict):
        try:
            return _safe_serialize(obj.dict())
        except Exception:
            pass

    # Dataclass
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        try:
            return _safe_serialize(dataclasses.asdict(obj))
        except Exception:
            pass

    if isinstance(obj, enum.Enum):
        return obj.value

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, UUID):
        return str(obj)

    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [_safe_serialize(v) for v in obj]

    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


# ============================================================================
# CONFIGURATION
# ============================================================================

class ObservabilityConfig:
    """Global configuration — set via init_client() or environment variables."""

    def __init__(self):
        self.endpoint = os.getenv("OBSERVABILITY_URL", "http://localhost:8001")
        self.api_key = os.getenv("OBSERVABILITY_API_KEY", "")
        self.service_name = os.getenv("SERVICE_NAME", "python-app")
        self.environment = os.getenv("ENV", "development")
        self.batch_size = int(os.getenv("OBSERVABILITY_BATCH_SIZE", "10"))
        self.flush_interval = int(os.getenv("OBSERVABILITY_FLUSH_INTERVAL", "5"))
        self.enabled = os.getenv("OBSERVABILITY_ENABLED", "true").lower() == "true"
        self.debug = os.getenv("OBSERVABILITY_DEBUG", "false").lower() == "true"

    @property
    def ingest_url(self) -> str:
        return f"{self.endpoint.rstrip('/')}/ingest"


_config = ObservabilityConfig()


# ============================================================================
# COST CALCULATOR
# ============================================================================

# Pricing per 1K tokens (USD)
_MODEL_COSTS: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
    "gpt-3.5-turbo-16k": {"prompt": 0.001, "completion": 0.002},
    # Anthropic
    "claude-3-5-sonnet": {"prompt": 0.003, "completion": 0.015},
    "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
    "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
    "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
    "claude-2": {"prompt": 0.008, "completion": 0.024},
    # Google
    "gemini-2.5-pro": {"prompt": 0.0025, "completion": 0.0075},
    "gemini-2.5-flash": {"prompt": 0.0001, "completion": 0.0004},
    "gemini-2.0-flash": {"prompt": 0.000075, "completion": 0.0003},
    "gemini-1.5-pro": {"prompt": 0.00125, "completion": 0.005},
    "gemini-1.5-flash": {"prompt": 0.0001, "completion": 0.0003},
    "gemini-1.0-pro": {"prompt": 0.0005, "completion": 0.0015},
    # Azure (same as OpenAI)
    "azure-gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "azure-gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "azure-gpt-4": {"prompt": 0.03, "completion": 0.06},
    "azure-gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
    # Cohere
    "command": {"prompt": 0.0015, "completion": 0.002},
    "command-r": {"prompt": 0.0005, "completion": 0.0015},
    "command-light": {"prompt": 0.0003, "completion": 0.0006},
    # Local / Ollama (free)
    "ollama": {"prompt": 0.0, "completion": 0.0},
    "llama3": {"prompt": 0.0, "completion": 0.0},
    "llama2": {"prompt": 0.0, "completion": 0.0},
    "mistral": {"prompt": 0.0, "completion": 0.0},
}

_FALLBACK_PRICING = {"prompt": 0.0005, "completion": 0.0015}


def _compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate USD cost for an LLM call (per 1K tokens).
    Tries exact match first, then partial match, then falls back to default.
    """
    # Fix: Handle None model
    model_lower = (model or "").lower()
    
    if not model_lower:
        return 0.0

    pricing = _MODEL_COSTS.get(model_lower)

    # Partial match — handles versioned names like "gpt-4o-2024-11-20"
    if not pricing:
        for known, costs in _MODEL_COSTS.items():
            if known in model_lower or model_lower in known:
                pricing = costs
                break

    if not pricing:
        pricing = _FALLBACK_PRICING

    return round(
        (prompt_tokens / 1000) * pricing["prompt"] +
        (completion_tokens / 1000) * pricing["completion"],
        8,
    )


class CostCalculator:
    """Public API for cost calculation."""

    PRICING = _MODEL_COSTS

    @classmethod
    def compute_cost(cls, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        return _compute_cost(model, prompt_tokens, completion_tokens)


# ============================================================================
# TRACING CONTEXT VARS
# ============================================================================

_trace_context: contextvars.ContextVar = contextvars.ContextVar(
    "observability_trace", default=None
)

_generation_context: contextvars.ContextVar = contextvars.ContextVar(
    "observability_generation", default=None
)


def get_current_trace():
    """Get the currently active TraceContext."""
    return _trace_context.get()


def get_current_generation():
    """Get the currently active GenerationContext."""
    return _generation_context.get()


def set_current_trace(trace):
    return _trace_context.set(trace)


def reset_current_trace(token) -> None:
    _trace_context.reset(token)


def set_current_generation(gen):
    return _generation_context.set(gen)


def reset_current_generation(token) -> None:
    _generation_context.reset(token)


# ============================================================================
# LLM RESPONSE NORMALIZATION
# ============================================================================

def _normalize_openai_response(response: Any) -> Dict[str, Any]:
    """Normalize OpenAI/Azure response."""
    result = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "finish_reason": None,
        "output_text": None
    }

    try:
        # LangChain AIMessage with usage_metadata
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            if isinstance(usage, dict):
                result["prompt_tokens"] = usage.get("input_tokens", 0)
                result["completion_tokens"] = usage.get("output_tokens", 0)
                result["total_tokens"] = usage.get("total_tokens", 0)
            else:
                result["prompt_tokens"] = getattr(usage, "prompt_tokens", 0) or 0
                result["completion_tokens"] = getattr(usage, "completion_tokens", 0) or 0
                result["total_tokens"] = getattr(usage, "total_tokens", 0) or 0

        # Raw OpenAI response
        elif hasattr(response, "usage"):
            usage = response.usage
            result["prompt_tokens"] = getattr(usage, "prompt_tokens", 0) or 0
            result["completion_tokens"] = getattr(usage, "completion_tokens", 0) or 0
            result["total_tokens"] = getattr(usage, "total_tokens", 0) or 0

        # Extract finish reason and output text
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            result["finish_reason"] = getattr(choice, "finish_reason", None)

            message = getattr(choice, "message", None)
            if message:
                result["output_text"] = getattr(message, "content", "")
            elif hasattr(choice, "text"):
                result["output_text"] = getattr(choice, "text", "")

    except Exception:
        pass

    return result


def _normalize_anthropic_response(response: Any) -> Dict[str, Any]:
    """Normalize Anthropic response."""
    result = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "finish_reason": None,
        "output_text": None
    }

    try:
        if hasattr(response, "usage"):
            usage = response.usage
            result["prompt_tokens"] = getattr(usage, "input_tokens", 0) or 0
            result["completion_tokens"] = getattr(usage, "output_tokens", 0) or 0
            result["total_tokens"] = result["prompt_tokens"] + result["completion_tokens"]

        result["finish_reason"] = getattr(response, "stop_reason", None)

        if hasattr(response, "content") and response.content:
            first = response.content[0]
            if isinstance(first, dict):
                result["output_text"] = first.get("text", "")
            else:
                result["output_text"] = getattr(first, "text", "")

    except Exception:
        pass

    return result


def _normalize_gemini_response(response: Any) -> Dict[str, Any]:
    """Normalize Gemini/Google response."""
    result = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "finish_reason": None,
        "output_text": None
    }

    try:
        if hasattr(response, "usage_metadata"):
            meta = response.usage_metadata
            if isinstance(meta, dict):
                result["prompt_tokens"] = meta.get("input_tokens", 0) or meta.get("prompt_tokens", 0)
                result["completion_tokens"] = meta.get("output_tokens", 0) or meta.get("completion_tokens", 0)
                result["total_tokens"] = meta.get("total_tokens", 0) or result["prompt_tokens"] + result["completion_tokens"]
            else:
                result["prompt_tokens"] = getattr(meta, "prompt_token_count", 0) or 0
                result["completion_tokens"] = getattr(meta, "candidates_token_count", 0) or 0
                result["total_tokens"] = getattr(meta, "total_token_count", 0) or 0

        result["output_text"] = getattr(response, "text", "") or getattr(response, "content", "")
        result["finish_reason"] = getattr(response, "finish_reason", None)

    except Exception:
        pass

    return result


def _normalize_langchain_response(response: Any) -> Dict[str, Any]:
    """Normalize LangChain AIMessage response."""
    result = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "finish_reason": None,
        "output_text": None
    }

    try:
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            if isinstance(usage, dict):
                result["prompt_tokens"] = usage.get("input_tokens", 0)
                result["completion_tokens"] = usage.get("output_tokens", 0)
                result["total_tokens"] = usage.get("total_tokens", 0)
            else:
                result["prompt_tokens"] = getattr(usage, "input_tokens", 0)
                result["completion_tokens"] = getattr(usage, "output_tokens", 0)
                result["total_tokens"] = getattr(usage, "total_tokens", 0)

        result["output_text"] = getattr(response, "content", "")

        if hasattr(response, "response_metadata"):
            result["finish_reason"] = response.response_metadata.get("finish_reason")

    except Exception:
        pass

    return result


def _detect_azure_from_response(response: Any) -> bool:
    """
    Detect if a response is from Azure OpenAI.
    
    Uses multiple signals since Azure can report as 'openai' in model_provider.
    """
    # Signal 1: Raw Azure responses have _request_id
    if hasattr(response, "_request_id"):
        return True
    
    # Signal 2: Check model string for 'azure'
    if hasattr(response, "model") and "azure" in str(response.model).lower():
        return True
    
    # Signal 3: LangChain Azure reports model_provider='azure' in some cases
    if hasattr(response, "response_metadata"):
        meta = response.response_metadata
        if isinstance(meta, dict):
            if meta.get("model_provider") == "azure":
                return True
            if meta.get("azure") is True:
                return True
            # Check deployment_name field (Azure-specific)
            if meta.get("deployment_name") is not None:
                return True
            # Check if model name contains 'azure' or 'gpt-35' or 'gpt-4' with deployment
            model_name = meta.get("model", "")
            if "azure" in model_name.lower():
                return True
            # Azure deployments often have custom names like 'my-gpt-4-deployment'
            # Check if there's a deployment field
            if meta.get("deployment") is not None:
                return True
    
    # Signal 4: Check if it's a LangChain AzureChatOpenAI instance
    if hasattr(response, "generation_info"):
        info = response.generation_info
        if isinstance(info, dict):
            if info.get("azure") is True:
                return True
    
    return False


def _extract_usage_from_response(response: Any) -> Dict[str, Any]:
    """
    Universal normalization with correct provider detection.

    Detection order:
    1. Gemini raw SDK (usage_metadata with prompt_token_count attribute)
    2. OpenAI SDK (usage + choices) - with Azure detection
    3. Anthropic SDK (usage + content, no choices)
    4. Gemini via LangChain (usage_metadata dict + response_metadata with "gemini")
    5. LangChain catch-all
    """
    if response is None:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "finish_reason": None,
            "output_text": None,
            "provider": "unknown"
        }

    try:
        # 1. GEMINI RAW SDK
        if hasattr(response, "usage_metadata") and not hasattr(response, "choices"):
            meta = response.usage_metadata
            if hasattr(meta, "prompt_token_count"):
                result = _normalize_gemini_response(response)
                result["provider"] = "gemini"
                return result

        # 2. OPENAI / AZURE
        if hasattr(response, "usage") and hasattr(response, "choices"):
            result = _normalize_openai_response(response)
            # Use comprehensive Azure detection
            result["provider"] = "azure" if _detect_azure_from_response(response) else "openai"
            return result

        # 3. ANTHROPIC
        if hasattr(response, "usage") and hasattr(response, "content") and not hasattr(response, "choices"):
            result = _normalize_anthropic_response(response)
            result["provider"] = "anthropic"
            return result

        # 4. GEMINI VIA LANGCHAIN
        if hasattr(response, "usage_metadata") and hasattr(response, "content"):
            if hasattr(response, "response_metadata"):
                meta = response.response_metadata
                if isinstance(meta, dict):
                    model_name = meta.get("model", "")
                    if "gemini" in model_name.lower():
                        result = _normalize_gemini_response(response)
                        result["provider"] = "gemini"
                        return result

        # 5. LANGCHAIN CATCH-ALL
        if hasattr(response, "usage_metadata") and hasattr(response, "content"):
            result = _normalize_langchain_response(response)
            
            # Check if it's actually Azure via response_metadata
            if _detect_azure_from_response(response):
                result["provider"] = "azure"
            elif hasattr(response, "response_metadata"):
                provider = response.response_metadata.get("model_provider", "langchain")
                result["provider"] = provider
            else:
                result["provider"] = "langchain"
            return result

        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "finish_reason": None,
            "output_text": None,
            "provider": "unknown"
        }

    except Exception as e:
        if _config.debug:
            print(f"[observability] _extract_usage_from_response failed: {e}")
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "finish_reason": None,
            "output_text": None,
            "provider": "unknown"
        }


# ============================================================================
# GENERATION CONTEXT
# ============================================================================

class GenerationContext:
    """LLM generation span with explicit response capture."""

    def __init__(self, trace_id: str, model: str, provider: Optional[str] = None):
        self.trace_id = trace_id
        self.model = model
        self.provider = provider
        self._event: Dict[str, Any] = {
            "type": "generation",
            "trace_id": trace_id,
            "model": model,
            "provider": provider,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "finish_reason": None,
            "input": None,
            "output": None,          # Raw LLM output
            "parsed_output": None,   # Parsed business object
            "status": "success",
        }
        self._start_time = time.time()
        self._captured = False

    def capture(self, response: Any) -> None:
        """Capture usage from a raw LLM response."""
        if self._captured:
            return

        try:
            normalized = _extract_usage_from_response(response)

            if normalized and (normalized.get("prompt_tokens") > 0 or normalized.get("completion_tokens") > 0):
                self._event["prompt_tokens"] = normalized.get("prompt_tokens", 0)
                self._event["completion_tokens"] = normalized.get("completion_tokens", 0)
                self._event["total_tokens"] = normalized.get("total_tokens", 0)
                self._event["finish_reason"] = normalized.get("finish_reason")

                output_text = normalized.get("output_text")
                if output_text is not None:
                    self._event["output"] = {"text": output_text}

                detected_provider = normalized.get("provider")
                if detected_provider and detected_provider not in (None, "unknown") and not self.provider:
                    self.provider = detected_provider
                    self._event["provider"] = detected_provider

                if self._event["prompt_tokens"] > 0 or self._event["completion_tokens"] > 0:
                    self._event["cost_usd"] = _compute_cost(
                        self.model,
                        self._event["prompt_tokens"],
                        self._event["completion_tokens"],
                    )

                self._captured = True
                self._event["status"] = "success"

        except Exception as e:
            if _config.debug:
                print(f"[observability] GenerationContext.capture failed: {e}")
            self._event["status"] = "error"

    def set_input(self, input_data: Any) -> None:
        """Set the input data."""
        self._event["input"] = _safe_serialize(input_data)

    def set_parsed_output(self, output: Any) -> None:
        """Set the parsed business object output."""
        self._event["parsed_output"] = _safe_serialize(output)

    def set(self, **kwargs) -> None:
        """Manually set any event field."""
        self._event.update(kwargs)

    def finalize(self) -> Dict[str, Any]:
        self._event["latency_ms"] = int((time.time() - self._start_time) * 1000)
        return self._event

    def __enter__(self):
        self._token = set_current_generation(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._event["status"] = "error"
        reset_current_generation(self._token)
        return False


# ============================================================================
# PUBLIC HOOK - capture_generation_response
# ============================================================================

def capture_generation_response(response: Any) -> None:
    """
    Capture an LLM response for the currently active generation.

    Use this immediately after calling an LLM, BEFORE parsing the response.

    Example:
        @observe(as_type="generation", model="gpt-4o", provider="openai")
        def process_query(query: str):
            response = llm.invoke(query)
            capture_generation_response(response)  # ← Capture tokens
            return parse_response(response)        # ← Return business object
    """
    gen = _generation_context.get()
    if gen is None:
        if _config.debug:
            print("[observability] capture_generation_response: No active generation context")
        return

    gen.capture(response)


# ============================================================================
# SPAN CONTEXT
# ============================================================================

class SpanContext:
    """Represents a single nested operation within a trace."""

    def __init__(self, trace_id: str, name: str, parent_span_id: Optional[str] = None):
        self.trace_id = trace_id
        self.name = name
        self.parent_span_id = parent_span_id
        self.span_id = str(uuid.uuid4())
        self.input: Optional[Dict] = None
        self.output: Optional[Dict] = None
        self.status: str = "success"
        self._start_time = time.time()
        self._events: List[Dict] = []

    def log_event(
        self,
        name: str,
        level: str = "INFO",
        message: str = None,
        metadata: Dict = None,
    ) -> None:
        self._events.append({
            "type": "event",
            "span_id": self.span_id,
            "name": name,
            "level": level,
            "message": message,
            "metadata": metadata or {},
            "timestamp": time.time(),
        })

    def finalize(self) -> Dict[str, Any]:
        return {
            "type": "span",
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "latency_ms": int((time.time() - self._start_time) * 1000),
            "events": self._events,
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.status = "error"
        return False


# ============================================================================
# TRACE CONTEXT
# ============================================================================

class TraceContext:
    """Root trace context for a single user request or pipeline run."""

    def __init__(
        self,
        client: "ObservabilityClient",
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        input_data: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
    ):
        self._client = client
        self.trace_id = str(uuid.uuid4())
        self.name = name
        self.user_id = user_id
        self.session_id = session_id
        self.input = input_data
        self.metadata = metadata
        self.output: Optional[Dict] = None
        self.status: str = "success"
        self._events: List[Dict] = []
        self._start_time = time.time()

    @contextmanager
    def span(self, name: str, parent_span_id: Optional[str] = None):
        span = SpanContext(self.trace_id, name, parent_span_id)
        try:
            yield span
        except Exception:
            span.status = "error"
            raise
        finally:
            self._events.append(span.finalize())

    @contextmanager
    def generation(self, model: str, provider: Optional[str] = None):
        """
        Create an LLM generation span.
        
        FIX: Enter the GenerationContext to set the generation contextvar.
        """
        gen = GenerationContext(self.trace_id, model, provider)
        with gen:  # ← CRITICAL FIX: Enter the context manager
            try:
                yield gen
            finally:
                self._events.append(gen.finalize())

    def log_event(
        self,
        name: str,
        level: str = "INFO",
        message: str = None,
        metadata: Dict = None,
    ) -> None:
        self._events.append({
            "type": "event",
            "trace_id": self.trace_id,
            "name": name,
            "level": level,
            "message": message,
            "metadata": metadata or {},
            "timestamp": time.time(),
        })

    def finalize(self) -> Dict[str, Any]:
        return {
            "type": "trace",
            "trace_id": self.trace_id,
            "name": self.name,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "input": self.input,
            "output": self.output,
            "metadata": self.metadata,
            "status": self.status,
            "latency_ms": int((time.time() - self._start_time) * 1000),
            "service_name": _config.service_name,
            "environment": _config.environment,
            "timestamp": time.time(),
        }

    def __enter__(self):
        self._token = set_current_trace(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.status = "error"

        trace_event = self.finalize()
        all_events = [trace_event] + self._events
        self._client._add_events(all_events)

        reset_current_trace(self._token)
        return False


# ============================================================================
# OBSERVABILITY CLIENT
# ============================================================================

class ObservabilityClient:
    """Buffers events and flushes them to the API."""

    def __init__(self):
        self._buffer: List[Dict] = []
        self._lock = threading.Lock()
        self._flush_thread: Optional[threading.Thread] = None
        self._running = False
        self._total_events_sent = 0
        self._total_failures = 0

    def trace(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        input_data: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
    ) -> TraceContext:
        return TraceContext(self, name, user_id, session_id, input_data, metadata)

    def _add_events(self, events: List[Dict]) -> None:
        if not _config.enabled:
            return
        with self._lock:
            self._buffer.extend(_safe_serialize(events))
            if len(self._buffer) >= _config.batch_size:
                self._flush_sync()

    def _flush_sync(self) -> None:
        if not self._buffer:
            return
        events = self._buffer[:]
        self._buffer.clear()
        thread = threading.Thread(
            target=self._send_events,
            args=(events,),
            daemon=True,
        )
        thread.start()

    def _send_events(self, events: List[Dict]) -> None:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    _config.ingest_url,
                    json={"events": _safe_serialize(events)},
                    headers={
                        "x-api-token": _config.api_key,
                    },
                    timeout=10,
                )

                if response.status_code == 202:
                    self._total_events_sent += len(events)
                    return

                if response.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue

                if _config.debug:
                    print(
                        f"[observability] send failed: "
                        f"{response.status_code} {response.text[:200]}"
                    )
                self._total_failures += 1
                return

            except requests.exceptions.Timeout:
                if attempt == max_retries - 1:
                    self._total_failures += 1
                else:
                    time.sleep(2 ** attempt)

            except Exception as e:
                self._total_failures += 1
                if _config.debug:
                    print(f"[observability] send error: {e}")
                return

    def flush_sync(self) -> None:
        with self._lock:
            self._flush_sync()

    def start_background_flush(self) -> None:
        if self._running:
            return
        self._running = True

        def _loop():
            while self._running:
                time.sleep(_config.flush_interval)
                with self._lock:
                    if self._buffer:
                        self._flush_sync()

        self._flush_thread = threading.Thread(target=_loop, daemon=True)
        self._flush_thread.start()

    def get_stats(self) -> Dict[str, int]:
        return {
            "buffered_events": len(self._buffer),
            "total_events_sent": self._total_events_sent,
            "total_failures": self._total_failures,
        }

    def stop(self) -> None:
        self._running = False
        if self._flush_thread:
            self._flush_thread.join(timeout=5)
        self.flush_sync()


# ============================================================================
# SINGLETON CLIENT
# ============================================================================

_client: Optional[ObservabilityClient] = None


def init_client(
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    service_name: Optional[str] = None,
    environment: Optional[str] = None,
    batch_size: Optional[int] = None,
    flush_interval: Optional[int] = None,
    enabled: Optional[bool] = None,
    debug: Optional[bool] = None,
) -> ObservabilityClient:
    global _client, _config

    if endpoint is not None:
        _config.endpoint = endpoint
    if api_key is not None:
        _config.api_key = api_key
    if service_name is not None:
        _config.service_name = service_name
    if environment is not None:
        _config.environment = environment
    if batch_size is not None:
        _config.batch_size = batch_size
    if flush_interval is not None:
        _config.flush_interval = flush_interval
    if enabled is not None:
        _config.enabled = enabled
    if debug is not None:
        _config.debug = debug

    if _client is None:
        _client = ObservabilityClient()
        if _config.enabled:
            _client.start_background_flush()

    return _client


def get_client() -> ObservabilityClient:
    global _client
    if _client is None:
        _client = ObservabilityClient()
        if _config.enabled:
            _client.start_background_flush()
    return _client


def flush() -> None:
    get_client().flush_sync()


def get_stats() -> Dict[str, int]:
    return get_client().get_stats()


# ============================================================================
# @observe DECORATOR
# ============================================================================

class observe:
    """
    Decorator for automatic trace / span / generation capture.

    Generation Pattern:
        @observe(as_type="generation", model="gpt-4o")
        def process(query: str):
            response = llm.invoke(query)
            capture_generation_response(response)  # ← Explicit hook
            return parse_response(response)        # ← Business object

    The hook is explicit, simple, and works with any return type.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        as_type: str = "auto",
        model: Optional[str] = None,
        provider: Optional[str] = None,
        capture_input: bool = True,
        capture_output: bool = True,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.name = name
        self.as_type = as_type
        self.model = model
        self.provider = provider
        self.capture_input = capture_input
        self.capture_output = capture_output
        self.user_id = user_id
        self.session_id = session_id

    def __call__(self, func: Callable) -> Callable:
        dec = self

        def _capture_input(*args, **kwargs) -> Optional[dict]:
            if not dec.capture_input:
                return None
            try:
                sig = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                return {
                    k: _safe_serialize(v)
                    for k, v in bound.arguments.items()
                    if k != "self"
                }
            except Exception:
                return None

        def _capture_output(result: Any) -> Optional[dict]:
            if not dec.capture_output:
                return None
            try:
                serialized = _safe_serialize(result)
                return serialized if isinstance(serialized, dict) else {"result": serialized}
            except Exception:
                return {"result": str(result)}

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            client = get_client()
            fn_name = dec.name or func.__name__.replace("_", "-")
            input_data = _capture_input(*args, **kwargs)
            current_trace = get_current_trace()
            etype = dec.as_type
            if etype == "auto":
                etype = "trace" if current_trace is None else "span"

            # TRACE
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

            # GENERATION
            elif etype == "generation":
                if not dec.model:
                    raise ValueError("@observe(as_type='generation') requires model=")

                def _run_gen(trace):
                    with trace.generation(dec.model, provider=dec.provider) as gen:
                        gen._event["name"] = fn_name
                        gen._event["input"] = input_data
                        try:
                            result = func(*args, **kwargs)

                            # Store parsed output separately (preserves raw output)
                            out = _capture_output(result)
                            if out:
                                gen.set_parsed_output(result)

                            # Check if generation captured anything
                            if gen._event.get("prompt_tokens", 0) == 0:
                                if _config.debug:
                                    print(f"[observability] WARNING: No usage captured for {fn_name}. "
                                          f"Call capture_generation_response(response) in your function.")

                            return result
                        except Exception:
                            gen._event["status"] = "error"
                            raise

                if current_trace is not None:
                    return _run_gen(current_trace)
                else:
                    with client.trace(name=f"{fn_name}-auto", input_data=input_data) as auto_trace:
                        return _run_gen(auto_trace)

            # SPAN
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

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            client = get_client()
            fn_name = dec.name or func.__name__.replace("_", "-")
            input_data = _capture_input(*args, **kwargs)
            current_trace = get_current_trace()
            etype = dec.as_type
            if etype == "auto":
                etype = "trace" if current_trace is None else "span"

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

            elif etype == "generation":
                if not dec.model:
                    raise ValueError("@observe(as_type='generation') requires model=")

                async def _run_gen(trace):
                    with trace.generation(dec.model, provider=dec.provider) as gen:
                        gen._event["name"] = fn_name
                        gen._event["input"] = input_data
                        try:
                            result = await func(*args, **kwargs)

                            # Store parsed output separately (preserves raw output)
                            out = _capture_output(result)
                            if out:
                                gen.set_parsed_output(result)

                            if gen._event.get("prompt_tokens", 0) == 0 and _config.debug:
                                print(f"[observability] WARNING: No usage captured for {fn_name}. "
                                      f"Call capture_generation_response(response) in your function.")

                            return result
                        except Exception:
                            gen._event["status"] = "error"
                            raise

                if current_trace is not None:
                    return await _run_gen(current_trace)
                else:
                    with client.trace(name=f"{fn_name}-auto", input_data=input_data) as auto_trace:
                        return await _run_gen(auto_trace)

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


# ============================================================================
# CLEANUP
# ============================================================================

def _cleanup():
    if _client:
        if _config.debug:
            stats = _client.get_stats()
            print(f"[observability] Shutting down. Stats: {stats}")
        _client.stop()


atexit.register(_cleanup)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "init_client",
    "get_client",
    "flush",
    "get_stats",
    "observe",
    "capture_generation_response",
    "TraceContext",
    "SpanContext",
    "GenerationContext",
    "get_current_trace",
    "get_current_generation",
    "CostCalculator"
]
