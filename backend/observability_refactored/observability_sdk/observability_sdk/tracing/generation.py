"""Generation context for LLM calls"""

import time
from typing import Optional, Dict, Any

from observability_sdk.utils.cost_calculator import compute_cost


# ── LLM Response Normalisers ─────────────────────────────────────────────────

def _normalize_openai_response(response: Any) -> Dict[str, Any]:
    result = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
              "finish_reason": None, "output_text": None}
    try:
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            if isinstance(usage, dict):
                result["prompt_tokens"]     = usage.get("input_tokens", 0)
                result["completion_tokens"] = usage.get("output_tokens", 0)
                result["total_tokens"]      = usage.get("total_tokens", 0)
            else:
                result["prompt_tokens"]     = getattr(usage, "prompt_tokens",     0) or 0
                result["completion_tokens"] = getattr(usage, "completion_tokens", 0) or 0
                result["total_tokens"]      = getattr(usage, "total_tokens",      0) or 0
        elif hasattr(response, "usage"):
            usage = response.usage
            result["prompt_tokens"]     = getattr(usage, "prompt_tokens",     0) or 0
            result["completion_tokens"] = getattr(usage, "completion_tokens", 0) or 0
            result["total_tokens"]      = getattr(usage, "total_tokens",      0) or 0

        if hasattr(response, "choices") and response.choices:
            choice  = response.choices[0]
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
    result = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
              "finish_reason": None, "output_text": None}
    try:
        if hasattr(response, "usage"):
            usage = response.usage
            result["prompt_tokens"]     = getattr(usage, "input_tokens",  0) or 0
            result["completion_tokens"] = getattr(usage, "output_tokens", 0) or 0
            result["total_tokens"]      = result["prompt_tokens"] + result["completion_tokens"]
        result["finish_reason"] = getattr(response, "stop_reason", None)
        if hasattr(response, "content") and response.content:
            first = response.content[0]
            result["output_text"] = first.get("text", "") if isinstance(first, dict) else getattr(first, "text", "")
    except Exception:
        pass
    return result


def _normalize_gemini_response(response: Any) -> Dict[str, Any]:
    result = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
              "finish_reason": None, "output_text": None}
    try:
        if hasattr(response, "usage_metadata"):
            meta = response.usage_metadata
            if isinstance(meta, dict):
                result["prompt_tokens"]     = meta.get("input_tokens",  0) or meta.get("prompt_tokens",     0)
                result["completion_tokens"] = meta.get("output_tokens", 0) or meta.get("completion_tokens", 0)
                result["total_tokens"]      = meta.get("total_tokens",  0) or result["prompt_tokens"] + result["completion_tokens"]
            else:
                result["prompt_tokens"]     = getattr(meta, "prompt_token_count",     0) or 0
                result["completion_tokens"] = getattr(meta, "candidates_token_count", 0) or 0
                result["total_tokens"]      = getattr(meta, "total_token_count",      0) or 0
        result["output_text"]  = getattr(response, "text", "") or getattr(response, "content", "")
        result["finish_reason"] = getattr(response, "finish_reason", None)
    except Exception:
        pass
    return result


def _normalize_langchain_response(response: Any) -> Dict[str, Any]:
    result = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
              "finish_reason": None, "output_text": None}
    try:
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            if isinstance(usage, dict):
                result["prompt_tokens"]     = usage.get("input_tokens",  0)
                result["completion_tokens"] = usage.get("output_tokens", 0)
                result["total_tokens"]      = usage.get("total_tokens",  0)
            else:
                result["prompt_tokens"]     = getattr(usage, "input_tokens",  0)
                result["completion_tokens"] = getattr(usage, "output_tokens", 0)
                result["total_tokens"]      = getattr(usage, "total_tokens",  0)
        result["output_text"] = getattr(response, "content", "")
        if hasattr(response, "response_metadata"):
            result["finish_reason"] = response.response_metadata.get("finish_reason")
    except Exception:
        pass
    return result


def _detect_azure(response: Any) -> bool:
    """Detect Azure OpenAI response via multiple signals."""
    if hasattr(response, "_request_id"):
        return True
    if hasattr(response, "model") and "azure" in str(response.model).lower():
        return True
    if hasattr(response, "response_metadata"):
        meta = response.response_metadata
        if isinstance(meta, dict):
            if meta.get("model_provider") == "azure":
                return True
            if meta.get("azure") is True or meta.get("deployment_name") is not None:
                return True
            if "azure" in meta.get("model", "").lower():
                return True
    return False


def _extract_usage(response: Any) -> Dict[str, Any]:
    """
    Universal response normaliser.
    Detection order:
      1. Gemini raw SDK  (usage_metadata object with prompt_token_count)
      2. OpenAI/Azure    (usage + choices)
      3. Anthropic       (usage + content, no choices)
      4. Gemini via LC   (usage_metadata dict + response_metadata with 'gemini')
      5. LangChain catch-all
    """
    empty = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
             "finish_reason": None, "output_text": None, "provider": "unknown"}

    if response is None:
        return empty

    try:
        # 1. Gemini raw SDK
        if hasattr(response, "usage_metadata") and not hasattr(response, "choices"):
            meta = response.usage_metadata
            if hasattr(meta, "prompt_token_count"):
                r = _normalize_gemini_response(response)
                r["provider"] = "gemini"
                return r

        # 2. OpenAI / Azure
        if hasattr(response, "usage") and hasattr(response, "choices"):
            r = _normalize_openai_response(response)
            r["provider"] = "azure" if _detect_azure(response) else "openai"
            return r

        # 3. Anthropic
        if hasattr(response, "usage") and hasattr(response, "content") and not hasattr(response, "choices"):
            r = _normalize_anthropic_response(response)
            r["provider"] = "anthropic"
            return r

        # 4. Gemini via LangChain
        if hasattr(response, "usage_metadata") and hasattr(response, "content"):
            if hasattr(response, "response_metadata"):
                meta = response.response_metadata
                if isinstance(meta, dict) and "gemini" in meta.get("model", "").lower():
                    r = _normalize_gemini_response(response)
                    r["provider"] = "gemini"
                    return r

        # 5. LangChain catch-all
        if hasattr(response, "usage_metadata") and hasattr(response, "content"):
            r = _normalize_langchain_response(response)
            r["provider"] = "azure" if _detect_azure(response) else (
                response.response_metadata.get("model_provider", "langchain")
                if hasattr(response, "response_metadata") else "langchain"
            )
            return r

    except Exception:
        pass

    return empty


# ── GenerationContext ─────────────────────────────────────────────────────────

# Avoid circular import — context.py must not import from here
import contextvars as _cv
_generation_context: _cv.ContextVar = _cv.ContextVar("observability_generation", default=None)


def get_current_generation():
    """Get the currently active GenerationContext."""
    return _generation_context.get()


class GenerationContext:
    """LLM generation span with universal token extraction and cost calculation."""

    def __init__(self, trace_id: str, model: str, provider: Optional[str] = None):
        self.trace_id = trace_id
        self.model    = model
        self.provider = provider
        self._event: Dict[str, Any] = {
            "type":             "generation",
            "trace_id":         trace_id,
            "model":            model,
            "provider":         provider,
            "prompt_tokens":    0,
            "completion_tokens": 0,
            "total_tokens":     0,
            "cost_usd":         0.0,
            "finish_reason":    None,
            "input":            None,
            "output":           None,
            "parsed_output":    None,
            "status":           "success",
        }
        self._start_time = time.time()
        self._captured   = False
        self._token      = None  # contextvar reset token

    # ── capture methods ──────────────────────────────────────────────────

    def capture(self, response: Any) -> None:
        """
        Capture token usage and cost from any LLM response.
        Auto-detects provider. Safe to call multiple times — only captures once.

        Example:
            with trace.generation(model="gpt-4o", provider="openai") as gen:
                response = openai_client.chat.completions.create(...)
                gen.capture(response)
        """
        if self._captured:
            return

        try:
            normalized = _extract_usage(response)
            pt = normalized.get("prompt_tokens",     0)
            ct = normalized.get("completion_tokens", 0)

            if pt > 0 or ct > 0:
                self._event["prompt_tokens"]     = pt
                self._event["completion_tokens"] = ct
                self._event["total_tokens"]      = normalized.get("total_tokens", pt + ct)
                self._event["finish_reason"]     = normalized.get("finish_reason")

                out_text = normalized.get("output_text")
                if out_text is not None:
                    self._event["output"] = {"text": out_text}

                detected = normalized.get("provider")
                if detected and detected not in (None, "unknown") and not self.provider:
                    self.provider              = detected
                    self._event["provider"]    = detected

                self._event["cost_usd"] = compute_cost(
                    self.model or "", pt, ct
                )
                self._captured        = True
                self._event["status"] = "success"

        except Exception as e:
            print(f"[observability] GenerationContext.capture failed: {e}")
            self._event["status"] = "error"

    # Keep individual capture_* methods for manual use / backward compat
    def capture_openai(self, response) -> None:
        """Capture from OpenAI / Azure response."""
        try:
            r = _normalize_openai_response(response)
            self._apply_normalized(r)
            self._event["status"] = "success"
        except Exception as e:
            print(f"[observability] capture_openai failed: {e}")
            self._event["status"] = "error"

    def capture_anthropic(self, response) -> None:
        """Capture from Anthropic response."""
        try:
            r = _normalize_anthropic_response(response)
            self._apply_normalized(r)
            self._event["status"] = "success"
        except Exception as e:
            print(f"[observability] capture_anthropic failed: {e}")
            self._event["status"] = "error"

    def capture_gemini(self, response) -> None:
        """Capture from Gemini (raw SDK or LangChain) response."""
        try:
            r = _normalize_gemini_response(response)
            self._apply_normalized(r)
            self._event["status"] = "success"
        except Exception as e:
            print(f"[observability] capture_gemini failed: {e}")
            self._event["status"] = "error"

    def _apply_normalized(self, r: Dict[str, Any]) -> None:
        pt = r.get("prompt_tokens",     0) or 0
        ct = r.get("completion_tokens", 0) or 0
        self._event["prompt_tokens"]     = pt
        self._event["completion_tokens"] = ct
        self._event["total_tokens"]      = r.get("total_tokens", pt + ct)
        self._event["finish_reason"]     = r.get("finish_reason")
        out = r.get("output_text")
        if out is not None:
            self._event["output"] = {"text": out}
        self._event["cost_usd"] = compute_cost(self.model or "", pt, ct)
        self._captured = True

    # ── helpers ──────────────────────────────────────────────────────────

    def set_input(self, input_data: Any) -> None:
        """Set the input data for this generation."""
        from observability_sdk.utils.serializer import safe_serialize
        self._event["input"] = safe_serialize(input_data)

    def set_parsed_output(self, output: Any) -> None:
        """Set the parsed business-object output (separate from raw LLM output)."""
        from observability_sdk.utils.serializer import safe_serialize
        self._event["parsed_output"] = safe_serialize(output)

    def set(self, **kwargs) -> None:
        """Manually set any event field."""
        self._event.update(kwargs)

    def finalize(self) -> Dict[str, Any]:
        self._event["latency_ms"] = int((time.time() - self._start_time) * 1000)
        return self._event

    # ── context manager ──────────────────────────────────────────────────

    def __enter__(self):
        self._token = _generation_context.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._event["status"] = "error"
        if self._token is not None:
            _generation_context.reset(self._token)
        return False
