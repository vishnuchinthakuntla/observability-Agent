"""Worker main entry point."""

import asyncio
import logging
import signal
from typing import List

from observability_redis_worker.worker.consumers.redis_consumer import RedisConsumer
from observability_redis_worker.worker.core.config import settings
from observability_redis_worker.worker.processors.batch_processor import BatchProcessor
from shared.shared.core.database import db_manager
from shared.shared.core.redis_client import redis_manager

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class WorkerPool:
    """Manages multiple concurrent worker coroutines."""

    def __init__(self, num_workers: int) -> None:
        self.num_workers = num_workers
        self.workers: List[asyncio.Task] = []
        self.consumers: List[RedisConsumer] = []
        self.batch_processor = BatchProcessor(batch_size=settings.BATCH_SIZE)
        self._running = True

    async def worker_loop(self, worker_id: int) -> None:
        """Main loop for a single worker coroutine."""
        consumer = RedisConsumer(worker_id)
        self.consumers.append(consumer)
        logger.info(f"Worker {worker_id} started")

        while self._running:
            try:
                result = await consumer.consume()
                if result is None:
                    continue

                _key, payload = result
                project_id = payload.get("project_id")
                events = payload.get("events", [])

                success = await self.batch_processor.process_batch(project_id, events)
                if not success:
                    logger.warning(f"Worker {worker_id}: batch processing failed — consider DLQ")

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Worker {worker_id} error: {exc}")
                await asyncio.sleep(1)

        logger.info(f"Worker {worker_id} stopped")

    async def start(self) -> None:
        """Initialise connections and launch all worker coroutines."""
        await db_manager.initialize(
            database_url=settings.DATABASE_URL,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
        )
        await redis_manager.initialize(
            redis_url=settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
        )
        logger.info("Database and Redis ready")

        for i in range(self.num_workers):
            task = asyncio.create_task(self.worker_loop(i))
            self.workers.append(task)

        logger.info(f"Worker pool started with {self.num_workers} workers")
        await asyncio.gather(*self.workers, return_exceptions=True)

    async def stop(self) -> None:
        """Gracefully stop all workers and close connections."""
        logger.info("Stopping worker pool…")
        self._running = False

        for consumer in self.consumers:
            await consumer.stop()

        for task in self.workers:
            task.cancel()

        await asyncio.gather(*self.workers, return_exceptions=True)
        await db_manager.close()
        await redis_manager.close()
        logger.info("Worker pool stopped")


async def main() -> None:
    pool = WorkerPool(num_workers=settings.WORKER_COUNT)
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(pool.stop())
            )
        except NotImplementedError:
            logger.warning(
                "Signal handlers are not supported on Windows; "
                "use Ctrl+C to stop the worker."
            )
    print("REDIS_URL =", settings.REDIS_URL)
    await pool.start()


if __name__ == "__main__":
    asyncio.run(main())
