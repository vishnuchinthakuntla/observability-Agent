"""Configuration management"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""
    
    # App
    APP_NAME: str = "SH Observability API"
    APP_ENV: str = "development"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/observability"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    
    # Queue
    QUEUE_BACKEND: str = "redis"  # local, redis, pubsub
    QUEUE_BATCH_SIZE: int = 100
    
    # Auth
    API_ENV: str = "SH_OBSERVABILITY"
    ADMIN_SECRET_KEY: str = "change-me-in-production"
    AUTH_CACHE_TTL_SECONDS: int = 60
    
    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_PROJECT: int = 1000  # per minute
    
    # CORS
    CORS_ALLOWED_ORIGINS: str = "*"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    model_config = SettingsConfigDict(
            env_file=".env",
            case_sensitive=True,
            extra="ignore",
        )
    @property
    def cors_origins(self) -> List[str]:
        if self.CORS_ALLOWED_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",")]
    
    


settings = Settings()
