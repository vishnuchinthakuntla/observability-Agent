"""
Shared async Redis connection manager.

Both the API and the worker import this class. Each service supplies its own
``redis_url`` and ``max_connections`` when calling ``initialize()``.
"""

from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisManager:
    """Singleton async Redis connection manager."""

    _instance: RedisManager | None = None
    _client: aioredis.Redis | None = None

    def __new__(cls) -> "RedisManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(
        self,
        redis_url: str,
        max_connections: int = 50,
        socket_connect_timeout: int = 5,
        socket_timeout: int = None,
    ) -> None:
        """Create the Redis client (idempotent)."""
        if self._client is not None:
            return
        self._client = await aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=max_connections,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            retry_on_timeout=True,
        )
        logger.info("Redis client initialised")

    async def get_client(self) -> aioredis.Redis:
        """Return the Redis client, raising if not yet initialised."""
        if self._client is None:
            raise RuntimeError("RedisManager not initialised — call initialize() first.")
        return self._client

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Redis client closed")


# Module-level singleton
redis_manager = RedisManager()


async def get_redis() -> aioredis.Redis:
    """Convenience helper / FastAPI dependency."""
    return await redis_manager.get_client()
