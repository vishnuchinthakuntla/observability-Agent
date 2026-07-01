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

    id = Column(Integer, primary_key=True, index=True)
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
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiToken(Base):
    """Issued API tokens for projects."""

    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
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
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
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
    
    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(Integer, ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True)
    
    type = Column(Enum(ObservationType), nullable=False)
    name = Column(String(255), nullable=True)
    
    parent_observation_id = Column(Integer, nullable=True, index=True)
    
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
    
    id = Column(Integer, primary_key=True, index=True)
    observation_id = Column(Integer, ForeignKey("observations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    trace_id = Column(Integer, ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True)

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


# ===========================================================
# NEW MODELS FOR DYNAMIC EVALUATION FRAMEWORK
# Add these at the end of your models.py file
# ===========================================================


class MetricMaster(Base):
    """
    Master table for all evaluation metrics.
    Stores generic metric definitions that can be reused across agents.
    """
    __tablename__ = "metric_master"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    metric_name = Column(String(100), nullable=False, unique=True, index=True)
    metric_description = Column(Text, nullable=False)
    default_threshold = Column(Float, nullable=False, default=0.7)
    category = Column(String(50), nullable=True)
    
    active = Column(Boolean, default=True, nullable=False, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_metric_master_name_active", "metric_name", "active"),
        Index("idx_metric_master_category", "category"),
    )


class EvaluationProfile(Base):
    """
    Maps agents to metrics with agent-specific evaluation prompts.
    Each agent can have different prompts for the same metric.
    """
    __tablename__ = "evaluation_profile"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    profile_name = Column(String(100), nullable=False)
    observation_name = Column(String(100), nullable=False, index=True)
    metric_id = Column(String(36), ForeignKey("metric_master.id", ondelete="CASCADE"), nullable=False, index=True)
    
    evaluation_prompt = Column(Text, nullable=False)
    threshold = Column(Float, nullable=True)
    
    active = Column(Boolean, default=True, nullable=False, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_eval_profile_agent", "observation_name"),
        Index("idx_eval_profile_agent_active", "observation_name", "active"),
        Index("idx_eval_profile_metric", "metric_id"),
        Index("idx_eval_profile_unique", "profile_name", "observation_name", "metric_id", unique=True),
    )


class EvaluationResult(Base):
    """
    Stores individual evaluation results for each observation.
    Generic table that works for ALL agents (rca_agent, decision_agent, chatbot_agent, etc.)
    """
    __tablename__ = "evaluation_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    observation_id = Column(String(36), ForeignKey("observations.id", ondelete="CASCADE"), nullable=False, index=True)
    trace_id = Column(String(36), ForeignKey("traces.id", ondelete="CASCADE"), nullable=True, index=True)
    
    agent_name = Column(String(100), nullable=False, index=True)
    project_id = Column(String(100), nullable=True, index=True)  # ✅ From traces table
    
    metric_name = Column(String(100), nullable=False, index=True)
    
    score = Column(Float, nullable=False)
    reason = Column(Text, nullable=True)
    threshold = Column(Float, nullable=True)
    passed = Column(Boolean, nullable=True, index=True)
    
    evaluated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_eval_results_agent", "agent_name"),
        Index("idx_eval_results_agent_metric", "agent_name", "metric_name"),
        Index("idx_eval_results_agent_project", "agent_name", "project_id"),
        Index("idx_eval_results_project", "project_id"),
        Index("idx_eval_results_evaluated_at", "evaluated_at"),
        Index("idx_eval_results_observation", "observation_id"),
        Index("idx_eval_results_passed", "passed"),
        Index("idx_eval_results_agent_date", "agent_name", "evaluated_at"),
    )


class Averages(Base):
    """
    Stores daily aggregated averages for each agent and project.
    Contains separate columns for each metric average.
    """
    __tablename__ = "averages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    agent_name = Column(String(100), nullable=False, index=True)
    project_id = Column(String(100), nullable=True, index=True)  # ✅ Project ID for filtering
    evaluation_date = Column(DateTime, nullable=False, index=True)  # ✅ Date type in DB
    
    # Individual metric averages as separate columns
    relevancy_avg = Column(Float, default=0)
    safety_avg = Column(Float, default=0)
    coherence_avg = Column(Float, default=0)
    helpfulness_avg = Column(Float, default=0)
    toxicity_avg = Column(Float, default=0)
    
    # Summary columns
    total_evaluated = Column(Integer, default=0)
    passed_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    overall_score = Column(Float, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_averages_agent", "agent_name"),
        Index("idx_averages_agent_date", "agent_name", "evaluation_date"),
        Index("idx_averages_date", "evaluation_date"),
        Index("idx_averages_project", "project_id"),
        Index("idx_averages_agent_project", "agent_name", "project_id"),
        Index("idx_averages_unique", "agent_name", "project_id", "evaluation_date", unique=True),
    )