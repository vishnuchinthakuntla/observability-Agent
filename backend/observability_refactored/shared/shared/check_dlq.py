import asyncio

from shared.shared.core.redis_client import redis_manager
from shared.shared.constants.redis_keys import RedisKeys
from observability_refactored.observability_redis_worker.worker.core.config import settings


async def main():
    await redis_manager.initialize(settings.REDIS_URL, settings.REDIS_MAX_CONNECTIONS)

    redis = await redis_manager.get_client()

    items = await redis.lrange(RedisKeys.DLQ, 0, -1)

    print(f"DLQ count: {len(items)}")

    for i, item in enumerate(items, 1):
        print(f"\n===== DLQ Item {i} =====")
        print(item)


if __name__ == "__main__":
    asyncio.run(main())
 