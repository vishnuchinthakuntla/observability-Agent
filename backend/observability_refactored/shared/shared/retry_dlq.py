"retry dlq"
import asyncio
import json

from shared.shared.core.redis_client import redis_manager
from shared.shared.constants.redis_keys import RedisKeys
from observability_refactored.observability_redis_worker.worker.core.config import settings


async def main():
    # Initialize Redis
    await redis_manager.initialize(settings.REDIS_URL, settings.REDIS_MAX_CONNECTIONS)

    # Get Redis client
    redis = await redis_manager.get_client()

    while True:
        item = await redis.lpop(RedisKeys.DLQ)

        if item is None:
            break

        await redis.rpush(
            RedisKeys.EVENT_QUEUE,
            item,
        )

        payload = json.loads(item)

        print(f"Retried batch for project: {payload.get('project_id')}")

    print("DLQ retry complete.")


if __name__ == "__main__":
    asyncio.run(main())