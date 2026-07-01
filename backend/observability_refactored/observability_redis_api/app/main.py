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

# Domain routers — one file per concern, zero raw SQL
from api.routers import auth, dashboard, traces as custom_traces, users, evaluation
from api.database import get_db
from sqlalchemy import select

from shared.shared.models.telemetry import Project, User
from api.routers.auth import verify_password, hash_password 

# Shared prefix for all custom API routes
_PREFIX = "/custom-api/v1"


logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
async def create_default_data():
    session = await db_manager.get_session_direct()

    try:
        project = await session.scalar(
            select(Project).where(Project.name == "Default Project")
        )

        if project is None:
            project = Project(
                name="Default Project",
                description="Default project created on startup",
            )
            session.add(project)
            await session.flush()

        user = await session.scalar(
            select(User).where(User.username == "admin")
        )

        if user is None:
            user = User(
                username="admin",
                email="admin@example.com",
                password_hash=hash_password("Admin@123"),
                is_admin=True,
                project_id=project.id,
            )
            session.add(user)

        await session.commit()

    except:
        await session.rollback()
        raise

    finally:
        await session.close()

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
    await create_default_data()
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

# Custom domain routers — all prefixed under /custom-api/v1
app.include_router(auth.router,           prefix=_PREFIX)
app.include_router(custom_traces.router,  prefix=_PREFIX)
app.include_router(dashboard.router,      prefix=_PREFIX)
app.include_router(users.router,          prefix=_PREFIX)
app.include_router(evaluation.router,     prefix=_PREFIX)



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
