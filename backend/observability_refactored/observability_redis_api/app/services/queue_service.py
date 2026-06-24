"""Queue service for publishing events"""

import json
import logging
from typing import Optional

from observability_redis_api.app.core.config import settings
from shared.shared.core.redis_client import get_redis
from shared.shared.constants.redis_keys import RedisKeys

logger = logging.getLogger(__name__)


class QueueService:
    """Service for publishing events to queue"""
    
    def __init__(self):
        self._redis = None
    
    async def _get_redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis
    
    async def publish(self, project_id: str, events: list) -> None:
        """Publish events to queue"""
        redis = await self._get_redis()
        
        payload = {
            "project_id": project_id,
            "events": events,
            "created_at": __import__('datetime').datetime.utcnow().isoformat()
        }
        
        await redis.rpush(
            RedisKeys.EVENT_QUEUE,
            json.dumps(payload)
        )
        
        logger.debug(f"Published {len(events)} events for {project_id}")