"""JSON schemas for validation"""

TRACE_EVENT_SCHEMA = {
    "type": "object",
    "required": ["type", "trace_id", "name"],
    "properties": {
        "type": {"const": "trace"},
        "trace_id": {"type": "string"},
        "name": {"type": "string"},
        "user_id": {"type": "string"},
        "session_id": {"type": "string"},
        "input": {"type": "object"},
        "output": {"type": "object"},
        "metadata": {"type": "object"},
        "latency_ms": {"type": "integer", "minimum": 0},
        "status": {"type": "string", "enum": ["success", "error"]}
    }
}

GENERATION_SCHEMA = {
    "type": "object",
    "required": ["type", "trace_id", "model"],
    "properties": {
        "type": {"const": "generation"},
        "trace_id": {"type": "string"},
        "name": {"type": "string"},
        "model": {"type": "string"},
        "provider": {"type": "string"},
        "prompt_tokens": {"type": "integer", "minimum": 0},
        "completion_tokens": {"type": "integer", "minimum": 0},
        "total_tokens": {"type": "integer", "minimum": 0},
        "cost_usd": {"type": "number", "minimum": 0},
        "latency_ms": {"type": "integer", "minimum": 0},
        "input": {"type": "object"},
        "output": {"type": "object"},
        "finish_reason": {"type": "string"}
    }
}

SPAN_SCHEMA = {
    "type": "object",
    "required": ["type", "trace_id", "name"],
    "properties": {
        "type": {"const": "span"},
        "trace_id": {"type": "string"},
        "name": {"type": "string"},
        "parent_span_id": {"type": "string"},
        "latency_ms": {"type": "integer", "minimum": 0},
        "input": {"type": "object"},
        "output": {"type": "object"},
        "status": {"type": "string", "enum": ["success", "error"]}
    }
}