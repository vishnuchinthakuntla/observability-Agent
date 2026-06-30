"""
SQLAlchemy ORM models for telemetry data.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Enum, Boolean,
    ForeignKey, JSON, Index, Text
)
from sqlalchemy.orm import relationship
import enum

from shared.shared.core.database import Base


class ObservationType(str, enum.Enum):
    """Type of observation."""
    CHAIN = "CHAIN"      # Span
    LLM = "LLM"          # Generation
    TOOL = "TOOL"        # Tool call
    EVENT = "EVENT"      # Event log


class Project(Base):
    """Project table - canonical project identities."""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    traces = relationship("Trace", back_populates="project")
    tokens = relationship("ApiToken", back_populates="project", cascade="all, delete-orphan")


class User(Base):
    """Application user accounts."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_admin = Column(Boolean, default=False, nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiToken(Base):
    """Issued API tokens for projects."""

    __tablename__ = "api_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    project_name = Column(String(255), nullable=False)
    environment = Column(String(100), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="tokens")

    __table_args__ = (
        Index("idx_api_tokens_project_created", "project_id", "created_at"),
    )


class Trace(Base):
    """Trace table - one per user request."""
    
    __tablename__ = "traces"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    external_trace_id = Column(String(255), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=True, index=True)
    session_id = Column(String(255), nullable=True)
    
    input = Column(JSON, nullable=True)
    output = Column(JSON, nullable=True)
    trace_metadata = Column("metadata", JSON, nullable=True)
    
    status = Column(String(50), default="success")
    latency_ms = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="traces")
    observations = relationship("Observation", back_populates="trace", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_traces_project_created", "project_id", "created_at"),
        Index("idx_traces_project_user", "project_id", "user_id"),
        Index("idx_traces_external_id", "external_trace_id"),
    )


class Observation(Base):
    """Observation table - spans, generations, tool calls, events."""
    
    __tablename__ = "observations"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id = Column(String(36), ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True)
    
    type = Column(Enum(ObservationType), nullable=False)
    name = Column(String(255), nullable=True)
    
    parent_observation_id = Column(String(36), nullable=True, index=True)
    
    input = Column(JSON, nullable=True)
    output = Column(JSON, nullable=True)
    observation_metadata = Column("metadata", JSON, nullable=True)
    
    status = Column(String(50), default="success")
    latency_ms = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    trace = relationship("Trace", back_populates="observations")
    llm_metadata = relationship("SpanLLMMetadata", back_populates="observation", uselist=False, cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_observations_trace_id", "trace_id"),
        Index("idx_observations_parent", "parent_observation_id"),
        Index("idx_observations_type", "type"),
        Index("idx_observations_created", "created_at"),
    )


class SpanLLMMetadata(Base):
    """LLM-specific metadata for generation observations."""
    
    __tablename__ = "span_llm_metadata"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    observation_id = Column(String(36), ForeignKey("observations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    trace_id = Column(String(36),ForeignKey("traces.id", ondelete="CASCADE"),nullable=False,index=True)
    
    model = Column(String(255), nullable=False)
    provider = Column(String(100), nullable=True)
    
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    
    cost_usd = Column(Float, default=0.0)
    
    finish_reason = Column(String(50), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    observation = relationship("Observation", back_populates="llm_metadata")
    
    __table_args__ = (
        Index("idx_llm_metadata_project", "project_id"),
        Index("idx_llm_metadata_model", "model"),
        Index("idx_llm_metadata_created", "created_at"),
        Index("idx_llm_metadata_trace", "trace_id")
    )
