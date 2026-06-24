"""Redis key constants - single source of truth for all services"""

class RedisKeys:
    """Centralized Redis key management"""
    
    # Queue keys
    EVENT_QUEUE = "sh:queue:events"
    DLQ = "sh:dlq:failed"
    
    # Stream keys (for enterprise version)
    EVENT_STREAM = "sh:stream:events"
    CONSUMER_GROUP = "sh:consumer:group"
    
    # Cache keys
    AUTH_CACHE_PREFIX = "sh:auth:"
    TRACE_CACHE_PREFIX = "sh:trace:"
    
    # Metrics keys
    METRICS_PREFIX = "sh:metrics:"
    
    @classmethod
    def auth_token_key(cls, token_hash: str) -> str:
        return f"{cls.AUTH_CACHE_PREFIX}token:{token_hash}"
    
    @classmethod
    def trace_cache_key(cls, project_id: str, trace_id: str) -> str:
        return f"{cls.TRACE_CACHE_PREFIX}{project_id}:{trace_id}"
    
    @classmethod
    def rate_limit_key(cls, project_id: str) -> str:
        return f"{cls.METRICS_PREFIX}ratelimit:{project_id}"