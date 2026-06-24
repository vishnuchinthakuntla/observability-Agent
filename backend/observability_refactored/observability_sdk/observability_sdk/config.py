"""SDK Configuration"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """SDK configuration"""
    
    # API configuration
    api_url: str
    project_id: str
    api_token: Optional[str] = None
    
    # HTTP configuration
    timeout: float = 5.0
    max_retries: int = 3
    
    # Batching configuration
    batch_size: int = 100
    flush_interval: float = 5.0
    
    # Queue configuration (for offline buffering)
    max_queue_size: int = 10000
    
    # Feature flags
    enabled: bool = True
    capture_input: bool = True
    capture_output: bool = True
    debug: bool = False
    
    # Environment
    environment: str = "production"
    service_name: str = "unknown"
    
    @property
    def ingest_url(self) -> str:
        return f"{self.api_url.rstrip('/')}/api/v1/ingest"