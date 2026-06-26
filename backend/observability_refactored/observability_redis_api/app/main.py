"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from observability_redis_api.app.api.routes import admin, ingest, traces
from observability_redis_api.app.core.config import settings
from shared.shared.core.database import db_manager
from shared.shared.core.redis_client import redis_manager
from api.routes import router as custom_router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.APP_ENV} | Queue: {settings.QUEUE_BACKEND}")

    await db_manager.initialize(
        database_url=settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        echo=settings.DEBUG,
    )
    await db_manager.create_tables()
    logger.info("Database ready")

    await redis_manager.initialize(
        redis_url=settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
    )
    logger.info("Redis ready")

    yield

    await db_manager.close()
    await redis_manager.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(traces.router)
app.include_router(admin.router)
app.include_router(custom_router)


class CUSTOMStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except (HTTPException, StarletteHTTPException) as ex:
            if ex.status_code == 404:
                return await super().get_response("index.html", scope)
            else:
                raise ex


# Mount the frontend static folder
static_path = Path(__file__).resolve().parents[2] / "static"
if static_path.exists():
    app.mount("/", CUSTOMStaticFiles(directory=str(static_path), html=True), name="static")
    logger.info(f"Mounted static folder at: {static_path}")
else:
    logger.warning(f"Static folder not found at: {static_path}")


@app.get("/health")
async def health():
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.get("/ready")
async def ready():
    return {"status": "ready"}
