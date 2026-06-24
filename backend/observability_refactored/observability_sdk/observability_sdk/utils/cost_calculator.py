"""
Cost calculator — standalone implementation, no shared dependency.
Pricing is per 1K tokens (USD).
"""

MODEL_COSTS: dict = {
    # OpenAI
    "gpt-4o":              {"prompt": 0.005,    "completion": 0.015},
    "gpt-4o-mini":         {"prompt": 0.00015,  "completion": 0.0006},
    "gpt-4-turbo":         {"prompt": 0.01,     "completion": 0.03},
    "gpt-4":               {"prompt": 0.03,     "completion": 0.06},
    "gpt-3.5-turbo":       {"prompt": 0.0005,   "completion": 0.0015},
    "gpt-3.5-turbo-16k":   {"prompt": 0.001,    "completion": 0.002},
    # Anthropic
    "claude-3-5-sonnet":   {"prompt": 0.003,    "completion": 0.015},
    "claude-3-opus":       {"prompt": 0.015,    "completion": 0.075},
    "claude-3-sonnet":     {"prompt": 0.003,    "completion": 0.015},
    "claude-3-haiku":      {"prompt": 0.00025,  "completion": 0.00125},
    "claude-2":            {"prompt": 0.008,    "completion": 0.024},
    # Google
    "gemini-2.5-pro":      {"prompt": 0.0025,   "completion": 0.0075},
    "gemini-2.5-flash":    {"prompt": 0.0001,   "completion": 0.0004},
    "gemini-2.0-flash":    {"prompt": 0.000075, "completion": 0.0003},
    "gemini-1.5-pro":      {"prompt": 0.00125,  "completion": 0.005},
    "gemini-1.5-flash":    {"prompt": 0.0001,   "completion": 0.0003},
    "gemini-1.0-pro":      {"prompt": 0.0005,   "completion": 0.0015},
    # Azure
    "azure-gpt-4o":        {"prompt": 0.005,    "completion": 0.015},
    "azure-gpt-4o-mini":   {"prompt": 0.00015,  "completion": 0.0006},
    "azure-gpt-4":         {"prompt": 0.03,     "completion": 0.06},
    "azure-gpt-3.5-turbo": {"prompt": 0.0005,   "completion": 0.0015},
    # Cohere
    "command":             {"prompt": 0.0015,   "completion": 0.002},
    "command-r":           {"prompt": 0.0005,   "completion": 0.0015},
    "command-light":       {"prompt": 0.0003,   "completion": 0.0006},
    # Local / Ollama (free)
    "ollama":              {"prompt": 0.0,      "completion": 0.0},
    "llama3":              {"prompt": 0.0,      "completion": 0.0},
    "llama2":              {"prompt": 0.0,      "completion": 0.0},
    "mistral":             {"prompt": 0.0,      "completion": 0.0},
}

_FALLBACK = {"prompt": 0.0005, "completion": 0.0015}


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate USD cost for an LLM call.
    Tries exact match first, then partial match, then falls back to default pricing.
    """
    model_lower = (model or "").lower()
    if not model_lower:
        return 0.0
    pricing = MODEL_COSTS.get(model_lower)
    if not pricing:
        for known_model, costs in MODEL_COSTS.items():
            if known_model in model_lower or model_lower in known_model:
                pricing = costs
                break
    if not pricing:
        pricing = _FALLBACK
    return round(
        (prompt_tokens / 1000) * pricing["prompt"] +
        (completion_tokens / 1000) * pricing["completion"],
        8,
    )


def calculate_tokens_from_chars(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return len(text) // 4 if text else 0


def format_cost(cost_usd: float) -> str:
    """Format a USD cost with appropriate decimal precision."""
    if cost_usd >= 1:
        return f"${cost_usd:.2f}"
    if cost_usd >= 0.001:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.6f}"


__all__ = ["MODEL_COSTS", "compute_cost", "calculate_tokens_from_chars", "format_cost"]
