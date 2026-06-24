"""
HTTP Exporter for sending telemetry data to the SH Observability API.
"""

import json
import logging
import threading
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx

from observability_sdk.utils.serializer import safe_serialize

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles batching and periodic flushing of events."""
    
    def __init__(
        self,
        api_url: str,
        project_id: str,
        api_token: Optional[str] = None,
        batch_size: int = 100,
        flush_interval: float = 5.0,
        max_queue_size: int = 10000,
        timeout: float = 5.0,
    ):
        self.api_url = api_url.rstrip("/")
        self.project_id = project_id
        self.api_token = api_token
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_queue_size = max_queue_size
        self.timeout = timeout
        
        self._batch: List[Dict[str, Any]] = []
        self._batch_lock = threading.Lock()
        self._client: Optional[httpx.Client] = None
        self._running = True
        self._flush_timer: Optional[threading.Timer] = None
        
        # Start background flusher
        self._start_background_flusher()
    
    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client
    
    def _start_background_flusher(self):
        """Start background thread for periodic flushing."""
        def flush_loop():
            while self._running:
                time.sleep(self.flush_interval)
                if len(self._batch) > 0:
                    self.flush()
        
        thread = threading.Thread(target=flush_loop, daemon=True)
        thread.start()
    
    def add_event(self, event: Dict[str, Any]) -> bool:
        """
        Add an event to the batch.
        Returns True if added, False if queue is full.
        """
        if not self._running:
            return False
        
        # Add timestamp if not present
        if "created_at" not in event:
            event["created_at"] = datetime.utcnow().isoformat()
        
        with self._batch_lock:
            # Check queue size limit
            if len(self._batch) >= self.max_queue_size:
                logger.warning(f"Batch queue full ({self.max_queue_size}), dropping event")
                return False
            
            self._batch.append(event)
            
            # Flush if batch is full
            if len(self._batch) >= self.batch_size:
                self._flush_sync()
        
        return True
    
    def add_events(self, events: List[Dict[str, Any]]) -> int:
        """
        Add multiple events to the batch.
        Returns number of events successfully added.
        """
        added = 0
        for event in events:
            if self.add_event(event):
                added += 1
        return added
    
    def _flush_sync(self):
        """Synchronous flush (called from background thread)."""
        with self._batch_lock:
            if not self._batch:
                return
            batch = self._batch.copy()
            self._batch.clear()
        
        self._send_batch(batch)
    
    def flush(self):
        """Public flush method."""
        self._flush_sync()
    
    def _send_batch(self, events: List[Dict[str, Any]]):
        """Send a batch of events to the API."""
        if not events:
            return
        
        # Prepare payload
        payload = {
            "project_id": self.project_id,
            "events": safe_serialize(events),
        }
        
        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "x-project-id": self.project_id,
        }
        if self.api_token:
            headers["X-Api-Token"] = self.api_token
        
        # Send with retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = self._get_client()
                response = client.post(
                    f"{self.api_url}/api/v1/ingest",
                    json=payload,
                    headers=headers,
                )
                
                if response.status_code == 202:
                    logger.debug(f"Sent {len(events)} events successfully")
                    return
                elif response.status_code == 429:
                    # Rate limited - backoff
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.warning(f"Failed to send: {response.status_code} - {response.text[:200]}")
                    return
                    
            except httpx.TimeoutException:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                if attempt == max_retries - 1:
                    logger.error("Max retries reached, dropping batch")
                else:
                    time.sleep(2 ** attempt)
                    
            except Exception as e:
                logger.error(f"Error sending batch: {e}")
                if attempt == max_retries - 1:
                    logger.error("Max retries reached, dropping batch")
                else:
                    time.sleep(2 ** attempt)
    
    def close(self):
        """Close the exporter and flush remaining events."""
        self._running = False
        self.flush()
        if self._client:
            self._client.close()
            self._client = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


class HttpExporter:
    """
    HTTP exporter for sending telemetry data.
    Wrapper around BatchProcessor with a simpler interface.
    """
    
    def __init__(
        self,
        api_url: str,
        project_id: str,
        api_token: Optional[str] = None,
        batch_size: int = 100,
        flush_interval: float = 5.0,
        timeout: float = 5.0,
    ):
        self.batch_processor = BatchProcessor(
            api_url=api_url,
            project_id=project_id,
            api_token=api_token,
            batch_size=batch_size,
            flush_interval=flush_interval,
            timeout=timeout,
        )
    
    def export(self, events: List[Dict[str, Any]]) -> bool:
        """
        Export events to the API.
        Returns True if accepted, False otherwise.
        """
        if not events:
            return True
        
        count = self.batch_processor.add_events(events)
        return count == len(events)
    
    def export_single(self, event: Dict[str, Any]) -> bool:
        """Export a single event."""
        return self.batch_processor.add_event(event)
    
    def flush(self):
        """Force flush of pending events."""
        self.batch_processor.flush()
    
    def close(self):
        """Close the exporter."""
        self.batch_processor.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()