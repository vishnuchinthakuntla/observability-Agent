"""
Trace repository for database operations.
"""

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Tuple
from datetime import datetime

from shared.shared.models.telemetry import Trace, Observation, SpanLLMMetadata, ObservationType


class TraceRepository:
    """Repository for trace-related database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_trace(self, trace_data: dict) -> Trace:
        """Create a new trace."""
        trace = Trace(**trace_data)
        self.db.add(trace)
        await self.db.flush()
        return trace
    
    async def upsert_trace(self, trace_data: dict) -> Trace:
        """Update existing trace or create new one."""
        external_id = trace_data.get("external_trace_id")
        
        if external_id:
            # Check if trace exists
            result = await self.db.execute(
                select(Trace).where(Trace.external_trace_id == external_id)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing trace
                for key, value in trace_data.items():
                    if value is not None and hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
                await self.db.flush()
                return existing
        
        # Create new trace
        return await self.create_trace(trace_data)
    
    async def get_trace(self, trace_id: str, project_id: str) -> Optional[Trace]:
        """Get a trace by ID."""
        result = await self.db.execute(
            select(Trace).where(
                Trace.id == trace_id,
                Trace.project_id == project_id
            )
        )
        return result.scalar_one_or_none()
    
    async def get_traces(
        self,
        project_id: str,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Trace], int]:
        """Get paginated traces for a project."""
        
        query = select(Trace).where(Trace.project_id == project_id)
        
        if user_id:
            query = query.where(Trace.user_id == user_id)
        if status:
            query = query.where(Trace.status == status)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar_one()
        
        # Get paginated results
        query = query.order_by(desc(Trace.created_at)).offset(offset).limit(limit)
        result = await self.db.execute(query)
        traces = result.scalars().all()
        
        return traces, total
    
    async def create_observation(self, observation_data: dict) -> Observation:
        """Create a new observation."""
        observation = Observation(**observation_data)
        self.db.add(observation)
        await self.db.flush()
        return observation
    
    async def create_llm_metadata(self, metadata_data: dict) -> SpanLLMMetadata:
        """Create LLM metadata for a generation."""
        metadata = SpanLLMMetadata(**metadata_data)
        self.db.add(metadata)
        await self.db.flush()
        return metadata
    
    async def get_observations_for_trace(self, trace_id: str) -> List[Observation]:
        """Get all observations for a trace."""
        result = await self.db.execute(
            select(Observation)
            .where(Observation.trace_id == trace_id)
            .order_by(Observation.created_at)
        )
        return result.scalars().all()
    
    async def get_cost_summary(self, project_id: str) -> dict:
        """Get cost summary for a project."""
        
        # Get totals
        total_result = await self.db.execute(
            select(
                func.coalesce(func.sum(SpanLLMMetadata.cost_usd), 0).label("total_cost"),
                func.coalesce(func.sum(SpanLLMMetadata.total_tokens), 0).label("total_tokens"),
                func.count(SpanLLMMetadata.id).label("total_calls"),
            ).where(SpanLLMMetadata.project_id == project_id)
        )
        totals = total_result.one()
        
        # Get trace count
        trace_count_result = await self.db.execute(
            select(func.count(Trace.id)).where(Trace.project_id == project_id)
        )
        trace_count = trace_count_result.scalar_one()
        
        # Get breakdown by model
        model_result = await self.db.execute(
            select(
                SpanLLMMetadata.model,
                func.coalesce(func.sum(SpanLLMMetadata.cost_usd), 0).label("cost"),
                func.coalesce(func.sum(SpanLLMMetadata.total_tokens), 0).label("tokens"),
                func.count(SpanLLMMetadata.id).label("calls"),
            )
            .where(SpanLLMMetadata.project_id == project_id)
            .group_by(SpanLLMMetadata.model)
            .order_by(desc("cost"))
        )
        models = model_result.all()
        
        return {
            "total_cost_usd": float(totals.total_cost),
            "total_tokens": int(totals.total_tokens),
            "total_traces": trace_count,
            "total_llm_calls": int(totals.total_calls),
            "breakdown_by_model": [
                {
                    "model": m.model,
                    "cost_usd": float(m.cost),
                    "tokens": int(m.tokens),
                    "calls": int(m.calls),
                }
                for m in models
            ],
        }