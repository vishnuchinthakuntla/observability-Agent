"""Authentication dependencies"""

import hashlib
import base64
import logging
from datetime import datetime
from fastapi import Header, HTTPException, status, Depends
from typing import Optional

from observability_redis_api.app.core.config import settings
from shared.shared.core.database import get_db
from shared.shared.core.redis_client import get_redis
from shared.shared.models.telemetry import ApiToken, Project
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def decrypt_token(token: str) -> str:
    """Decode base64 token"""
    return base64.b64decode(token.encode()).decode()


async def validate_token(
    token: str,
    project_name: Optional[str],
    db: AsyncSession,
) -> tuple[bool, str, Optional[str], Optional[str], Optional[str]]:
    """
    Validate token and return (is_valid, error_message, db_project_id, token_id, project_name)
    
    Token format: ENV||EXPIRY_DATE||PROJECT_ID||PROJECT_NAME||TOKEN_ID
    """
    try:
        decoded = decrypt_token(token)
        parts = decoded.split("||")
        
        if len(parts) not in (3, 4, 5):
            return False, "Invalid token format", None, None, None
        
        token_id = None
        if len(parts) == 5:
            env, expiry_str, token_project_id, token_project_name, token_id = parts
        elif len(parts) == 4:
            env, expiry_str, token_project_id, token_project_name = parts
        else:
            env, expiry_str, token_project_name = parts
            token_project_id = None
        
        # Check environment
        if env != settings.API_ENV:
            return False, f"Invalid environment (expected {settings.API_ENV})", None, None, None
        
        # Check expiry
        expiry_date = datetime.strptime(expiry_str, "%d-%m-%Y")
        if expiry_date < datetime.now():
            return False, f"Token expired on {expiry_str}", None, None, None
        
        if project_name and token_project_name != project_name:
            return False, f"Project mismatch (token: {token_project_name}, header: {project_name})", None, None, None
        
        result = await db.execute(
            select(ApiToken, Project)
            .join(Project, ApiToken.project_id == Project.id)
            .where(ApiToken.token_hash == _token_hash(token))
        )
        row = result.one_or_none()
        if row is None:
            return False, "Token was not issued by this server", None, None, None

        api_token, project = row
        if api_token is None:
            return False, "Token was not issued by this server", None, None, None
        if not project.is_active:
            return False, "Project is inactive", None, None, None
        if api_token.revoked_at is not None:
            return False, "Token has been revoked", None, None, None
        if api_token.expires_at < datetime.utcnow():
            return False, f"Token expired on {api_token.expires_at.strftime('%d-%m-%Y')}", None, None, None
        if api_token.environment != settings.API_ENV:
            return False, f"Invalid environment (expected {settings.API_ENV})", None, None, None
        if project_name and api_token.project_name != project_name:
            return False, f"Project mismatch (token: {api_token.project_name}, header: {project_name})", None, None, None
        if api_token.project_name != token_project_name:
            return False, "Token project name mismatch", None, None, None
        if token_project_id and api_token.project_id != token_project_id:
            return False, "Token project id mismatch", None, None, None
        if token_id and api_token.id != token_id:
            return False, "Token id mismatch", None, None, None
        
        return True, "", api_token.project_id, api_token.id, api_token.project_name
        
    except Exception as e:
        return False, f"Token decode error: {e}", None, None, None


def _token_cache_key(token: str) -> str:
    """Create cache key for token"""
    digest = hashlib.sha256(token.encode()).hexdigest()
    return f"auth:token:{digest}"


def _token_id_cache_key(token_id: str) -> str:
    return f"auth:token_id:{token_id}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def require_project(
    x_api_token: str = Header(..., description="Base64-encoded authentication token"),
    x_project_id: Optional[str] = Header(None, description="Project identifier"),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    FastAPI dependency for authentication.
    Validates token and returns the database project_id.
    """
    # Check cache first
    cache_key = _token_cache_key(x_api_token)
    cached = await redis.get(cache_key)
    
    if cached:
        logger.debug(f"Auth cache hit for {cache_key[:20]}...")
        if "||" not in cached:
            await redis.delete(cache_key)
            cached = None
        else:
            cached_project_id, cached_project_name = cached.split("||", 1)
            if x_project_id and cached_project_name != x_project_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Project mismatch with cached token"
                )
            return cached_project_id
    
    # Validate token
    is_valid, error, project_id, token_id, project_name = await validate_token(x_api_token, x_project_id, db)
    
    if not is_valid:
        logger.warning(f"Auth failed: {error}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error
        )
    
    # Cache the result
    await redis.setex(cache_key, settings.AUTH_CACHE_TTL_SECONDS, f"{project_id}||{project_name}")
    await redis.setex(_token_id_cache_key(token_id), settings.AUTH_CACHE_TTL_SECONDS, cache_key)
    logger.debug(f"Cached auth for project {project_name} ({project_id})")
    
    return project_id


async def require_admin(
    x_admin_key: str = Header(..., description="Admin secret key")
) -> bool:
    """Admin authentication dependency"""
    if x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin key"
        )
    return True
