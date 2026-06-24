"""
Admin API routes — token management and project administration.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from observability_redis_api.app.api.dependencies.auth import require_admin
from observability_redis_api.app.core.config import settings
from shared.shared.core.database import get_db
from shared.shared.core.redis_client import get_redis
from shared.shared.models.telemetry import ApiToken, Project
import redis.asyncio as aioredis

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

# ------------------------------------------------------------------ #
# Schemas
# ------------------------------------------------------------------ #

class TokenRequest(BaseModel):
    project_name: str
    expiry_days: int = 365


class TokenResponse(BaseModel):
    project_id: str
    project_name: str
    token: str
    expiry_date: str
    expires_in_days: int
    instructions: str


class TokenOut(BaseModel):
    id: str
    project_id: str
    project_name: str
    environment: str
    expires_at: datetime
    created_at: datetime
    revoked_at: Optional[datetime] = None
    is_active: bool


class TokenListResponse(BaseModel):
    data: list[TokenOut]
    total: int


class RevokeTokenResponse(BaseModel):
    id: str
    project_id: str
    project_name: str
    revoked_at: datetime
    cache_cleared: bool


class ProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime


class VerifyRequest(BaseModel):
    token: str


class VerifyResponse(BaseModel):
    token: str
    decrypted_project: str
    project_id: Optional[str] = None
    expiry_date: str
    environment: str
    is_valid: bool
    is_allowed: bool
    error_message: Optional[str] = None


# ------------------------------------------------------------------ #
# Helpers (kept internal; auth.py owns the validation logic)
# ------------------------------------------------------------------ #

def _generate_token(project: Project, expiry_days: int) -> dict:
    token_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=expiry_days)
    expiry_date = expires_at.strftime("%d-%m-%Y")
    plain = f"{settings.API_ENV}||{expiry_date}||{project.id}||{project.name}||{token_id}"
    return {
        "token_id": token_id,
        "project_id": project.id,
        "project_name": project.name,
        "token": base64.b64encode(plain.encode()).decode(),
        "expiry_date": expiry_date,
        "expires_at": expires_at,
        "expires_in_days": expiry_days,
    }


def _decode_token(token: str) -> str:
    return base64.b64decode(token.encode()).decode()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _token_id_cache_key(token_id: str) -> str:
    return f"auth:token_id:{token_id}"


def _build_token_out(token: ApiToken) -> TokenOut:
    now = datetime.utcnow()
    return TokenOut(
        id=token.id,
        project_id=token.project_id,
        project_name=token.project_name,
        environment=token.environment,
        expires_at=token.expires_at,
        created_at=token.created_at,
        revoked_at=token.revoked_at,
        is_active=token.revoked_at is None and token.expires_at >= now,
    )


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #

@router.post("/projects/token", response_model=TokenResponse)
async def generate_project_token(
    request: TokenRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """Generate an API token for a project."""
    result = await db.execute(select(Project).where(Project.name == request.project_name))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{request.project_name}' does not exist",
        )
    if not project.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"Project '{request.project_name}' is inactive",
        )

    info = _generate_token(project, request.expiry_days)
    db.add(
        ApiToken(
            id=info["token_id"],
            token_hash=_token_hash(info["token"]),
            project_id=project.id,
            project_name=project.name,
            environment=settings.API_ENV,
            expires_at=info["expires_at"],
        )
    )
    await db.flush()

    return TokenResponse(
        project_id=info["project_id"],
        project_name=info["project_name"],
        token=info["token"],
        expiry_date=info["expiry_date"],
        expires_in_days=info["expires_in_days"],
        instructions="Send this token in the X-Api-Token header with every request",
    )


@router.get("/tokens", response_model=TokenListResponse)
async def list_tokens(
    project_name: Optional[str] = None,
    include_revoked: bool = False,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """List issued API tokens."""
    query = select(ApiToken)
    if project_name:
        query = query.where(ApiToken.project_name == project_name)
    if not include_revoked:
        query = query.where(ApiToken.revoked_at.is_(None))

    query = query.order_by(ApiToken.created_at.desc())
    result = await db.execute(query)
    tokens = result.scalars().all()
    return TokenListResponse(
        data=[_build_token_out(token) for token in tokens],
        total=len(tokens),
    )


@router.post("/tokens/{token_id}/revoke", response_model=RevokeTokenResponse)
async def revoke_token(
    token_id: str,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _: bool = Depends(require_admin),
):
    """Revoke an issued API token."""
    result = await db.execute(select(ApiToken).where(ApiToken.id == token_id))
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=404, detail=f"Token '{token_id}' does not exist")

    if token.revoked_at is None:
        token.revoked_at = datetime.utcnow()
        await db.flush()

    cache_cleared = False
    pointer_key = _token_id_cache_key(token.id)
    cache_key = await redis.get(pointer_key)
    if cache_key:
        await redis.delete(cache_key)
        cache_cleared = True
    await redis.delete(pointer_key)

    return RevokeTokenResponse(
        id=token.id,
        project_id=token.project_id,
        project_name=token.project_name,
        revoked_at=token.revoked_at,
        cache_cleared=cache_cleared,
    )


@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    request: ProjectRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """Create a project that can receive API tokens."""
    result = await db.execute(select(Project).where(Project.name == request.name))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Project '{request.name}' already exists")

    project = Project(
        name=request.name,
        description=request.description,
        is_active=request.is_active,
    )
    db.add(project)
    await db.flush()
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        is_active=project.is_active,
        created_at=project.created_at,
    )


@router.get("/projects/list")
async def list_projects(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """List all allowed projects."""
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return {
        "projects": [
            {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "is_active": project.is_active,
                "created_at": project.created_at.isoformat(),
            }
            for project in projects
        ],
        "total": len(projects),
        "environment": settings.API_ENV,
    }


@router.post("/projects/verify", response_model=VerifyResponse)
async def verify_token(
    request: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """Verify and decode a token."""
    try:
        decrypted = _decode_token(request.token)
        parts = decrypted.split("||")

        if len(parts) not in (3, 4, 5):
            return VerifyResponse(
                token=request.token,
                decrypted_project="",
                project_id=None,
                expiry_date="",
                environment="",
                is_valid=False,
                is_allowed=False,
                error_message=f"Invalid format: expected 3, 4, or 5 parts, got {len(parts)}",
            )

        token_id = None
        if len(parts) == 5:
            env, expiry_str, project_id, project_name, token_id = parts
        elif len(parts) == 4:
            env, expiry_str, project_id, project_name = parts
        else:
            env, expiry_str, project_name = parts
            project_id = None

        is_valid = True
        error_message = None

        try:
            if datetime.strptime(expiry_str, "%d-%m-%Y") < datetime.now():
                is_valid = False
                error_message = f"Token expired on {expiry_str}"
        except ValueError:
            is_valid = False
            error_message = f"Invalid date format: {expiry_str}"

        token_result = await db.execute(
            select(ApiToken).where(ApiToken.token_hash == _token_hash(request.token))
        )
        stored_token = token_result.scalar_one_or_none()
        project_result = await db.execute(
            select(Project).where(Project.id == stored_token.project_id)
        ) if stored_token else None
        stored_project = project_result.scalar_one_or_none() if project_result else None
        is_allowed = bool(stored_project and stored_project.is_active)

        if stored_token is None:
            is_valid = False
            error_message = "Token was not issued by this server"
        elif stored_token.revoked_at is not None:
            is_valid = False
            error_message = "Token has been revoked"
        elif stored_token.expires_at < datetime.utcnow():
            is_valid = False
            error_message = f"Token expired on {stored_token.expires_at.strftime('%d-%m-%Y')}"
        elif token_id and stored_token.id != token_id:
            is_valid = False
            error_message = "Token id mismatch"
        elif not is_allowed:
            is_valid = False
            error_message = "Project is inactive"

        return VerifyResponse(
            token=request.token,
            decrypted_project=project_name,
            project_id=stored_token.project_id if stored_token else project_id,
            expiry_date=expiry_str,
            environment=env,
            is_valid=is_valid,
            is_allowed=is_allowed,
            error_message=error_message,
        )

    except Exception as exc:
        return VerifyResponse(
            token=request.token,
            decrypted_project="",
            project_id=None,
            expiry_date="",
            environment="",
            is_valid=False,
            is_allowed=False,
            error_message=str(exc),
        )


@router.get("/health")
async def admin_health(_: bool = Depends(require_admin)):
    return {
        "status": "healthy",
        "environment": settings.API_ENV,
        "queue_backend": settings.QUEUE_BACKEND,
        "auth_cache_ttl": settings.AUTH_CACHE_TTL_SECONDS,
    }
