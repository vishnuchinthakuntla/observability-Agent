"""Worker configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    # App
    WORKER_NAME: str = "sh-worker"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/observability"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20
    REDIS_QUEUE_KEY: str = "sh:queue:events"

    # Processing
    BATCH_SIZE: int = 100
    WORKER_COUNT: int = 4
    POLL_TIMEOUT: int = 5  # seconds

    # Retry
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 1

    model_config = SettingsConfigDict(
    env_file=".env",
    case_sensitive=True,
    extra="ignore",
    )


settings = WorkerSettings()
