"""Redis consumer for event queue"""

import json
import asyncio
import logging
from typing import Optional, Tuple

from observability_redis_worker.worker.core.config import settings
from shared.shared.core.redis_client import get_redis
from shared.shared.constants.redis_keys import RedisKeys

logger = logging.getLogger(__name__)


class RedisConsumer:
    """Consumer that reads events from Redis queue"""
    
    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self._redis = None
        self._running = True
    
    async def _get_redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis
    
    async def consume(self) -> Optional[Tuple[str, dict]]:
        """
        Consume one message from the queue.
        Returns (message_id, payload) or None if timeout.
        """
        redis = await self._get_redis()
        
        try:
            # BLPOP with timeout (blocks until data or timeout)
            result = await redis.blpop(
                RedisKeys.EVENT_QUEUE,
                timeout=settings.POLL_TIMEOUT
            )
            
            if result is None:
                return None
            
            key, raw_data = result
            payload = json.loads(raw_data)
            
            logger.debug(f"Worker {self.worker_id} consumed message for {payload.get('project_id')}")
            return key, payload
            
        except Exception as e:
            logger.error(f"Worker {self.worker_id} consume error: {e}")
            return None
    
    async def stop(self):
        """Stop the consumer"""
        self._running = False
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.stop()