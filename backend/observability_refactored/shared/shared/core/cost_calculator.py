"""
LLM cost calculation utilities.
Single source of truth — used by worker, SDK, and any future service.
"""

# Cost per 1K tokens (USD)
MODEL_COSTS: dict[str, dict[str, float]] = {
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
    "claude-instant-1": {"prompt": 0.0008, "completion": 0.0024},

    # Google
    "gemini-2.5-pro": {"prompt": 0.0025, "completion": 0.0075},
    "gemini-2.5-flash": {"prompt": 0.0001, "completion": 0.0004},
    "gemini-2.0-flash": {"prompt": 0.000075, "completion": 0.0003},
    "gemini-1.5-pro": {"prompt": 0.0025, "completion": 0.0075},
    "gemini-1.5-flash": {"prompt": 0.0001, "completion": 0.0004},
    "gemini-1.0-pro": {"prompt": 0.0005, "completion": 0.0015},

    # Azure (same as OpenAI)
    "azure-gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "azure-gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "azure-gpt-4": {"prompt": 0.03, "completion": 0.06},
    "azure-gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},

    # Ollama (local — free)
    "ollama": {"prompt": 0.0, "completion": 0.0},
    "llama3": {"prompt": 0.0, "completion": 0.0},
    "llama2": {"prompt": 0.0, "completion": 0.0},
    "mistral": {"prompt": 0.0, "completion": 0.0},

    # Vertex AI (Google Cloud)
    "vertex-gemini-pro": {"prompt": 0.0005, "completion": 0.0015},
    "vertex-gemini-flash": {"prompt": 0.0001, "completion": 0.0004},

    # Cohere
    "command": {"prompt": 0.0015, "completion": 0.002},
    "command-light": {"prompt": 0.0003, "completion": 0.0006},
    "embed-english-v3": {"prompt": 0.0001, "completion": 0.0},

    # AI21 Labs
    "j2-ultra": {"prompt": 0.015, "completion": 0.015},
    "j2-mid": {"prompt": 0.01, "completion": 0.01},
    "j2-light": {"prompt": 0.003, "completion": 0.003},
}

_FALLBACK_PRICING = {"prompt": 0.0005, "completion": 0.0015}


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate the USD cost for an LLM call.

    Args:
        model: Model name, e.g. ``"gpt-4o"`` or ``"claude-3-5-sonnet"``.
        prompt_tokens: Number of input/prompt tokens.
        completion_tokens: Number of output/completion tokens.

    Returns:
        Cost in USD, rounded to 8 decimal places.
    """
    model_lower = model.lower()

    # Exact match first
    pricing = MODEL_COSTS.get(model_lower)

    # Partial match (e.g. "gpt-4" matches "gpt-4-turbo")
    if not pricing:
        for known_model, costs in MODEL_COSTS.items():
            if known_model in model_lower or model_lower in known_model:
                pricing = costs
                break

    if not pricing:
        pricing = _FALLBACK_PRICING

    prompt_cost = (prompt_tokens / 1000) * pricing["prompt"]
    completion_cost = (completion_tokens / 1000) * pricing["completion"]
    return round(prompt_cost + completion_cost, 8)


def calculate_tokens_from_chars(text: str) -> int:
    """Rough token estimate: ~4 characters per token for English text."""
    return len(text) // 4 if text else 0


def format_cost(cost_usd: float) -> str:
    """Format a USD cost with appropriate precision."""
    if cost_usd >= 1:
        return f"${cost_usd:.2f}"
    if cost_usd >= 0.001:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.6f}"
