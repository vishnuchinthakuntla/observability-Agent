"""Event ingestion routes"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from fastapi.encoders import jsonable_encoder

from observability_redis_api.app.api.dependencies.auth import require_project
from observability_redis_api.app.services.queue_service import QueueService
from observability_redis_api.app.schemas.ingest import IngestRequest, IngestResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


@router.post("", status_code=202, response_model=IngestResponse)
async def ingest_events(
    request: IngestRequest,
    project_id: str = Depends(require_project),
    queue_service: QueueService = Depends(QueueService)
):
    """
    Ingest telemetry events.
    
    Returns 202 Accepted immediately. Events are queued for async processing.
    """
    try:
        # Convert events to dict
        events_data = [
                jsonable_encoder(event)
                for event in request.events
            ]
        
        # Publish to queue
        await queue_service.publish(project_id, events_data)
        
        logger.info(f"Queued {len(events_data)} events for project {project_id}")
        
        return IngestResponse(
            accepted=len(events_data),
            message="Events queued successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to ingest events: {e}")
        raise HTTPException(status_code=500, detail=str(e))