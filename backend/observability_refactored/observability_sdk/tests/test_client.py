"""
Tests for the SH Observability SDK client.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime

from observability_sdk.client import SHClient
from observability_sdk.config import Config
from observability_sdk.tracing.trace import TraceContext


class TestSHClient(unittest.TestCase):
    """Test cases for SHClient."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = Config(
            api_url="http://localhost:8000",
            project_id="test-project",
            api_token="test-token",
            enabled=True,
            batch_size=10,
            flush_interval=1,
        )
        self.client = SHClient(self.config)
    
    def tearDown(self):
        """Clean up after tests."""
        self.client.close()
    
    def test_client_initialization(self):
        """Test client initialization."""
        self.assertEqual(self.client.config.project_id, "test-project")
        self.assertEqual(self.client.config.api_url, "http://localhost:8000")
        self.assertTrue(self.client.config.enabled)
    
    def test_trace_context_manager(self):
        """Test trace context manager creation."""
        with self.client.trace("test-trace", user_id="user-123") as trace:
            self.assertIsInstance(trace, TraceContext)
            self.assertEqual(trace.name, "test-trace")
            self.assertEqual(trace.user_id, "user-123")
            trace.output = {"result": "success"}
    
    def test_add_event(self):
        """Test adding events to batch."""
        event = {
            "type": "trace",
            "trace_id": "test-123",
            "name": "test-event",
        }
        
        result = self.client.add_event(event)
        self.assertTrue(result)
        
        with self.client._batch_lock:
            self.assertEqual(len(self.client._batch), 1)
    
    @patch('observability_sdk.client.httpx.Client')
    def test_flush_sends_batch(self, mock_client_class):
        """Test that flush sends batch to API."""
        # Setup mock
        mock_response = Mock()
        mock_response.status_code = 202
        mock_client = Mock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        # Add events
        for i in range(5):
            self.client.add_event({
                "type": "trace",
                "trace_id": f"test-{i}",
                "name": f"event-{i}",
            })
        
        # Flush
        self.client.flush()
        
        # Verify API called
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        self.assertEqual(call_args[0][0], "http://localhost:8000/api/v1/ingest")
        
        # Verify headers
        headers = call_args[1]["headers"]
        self.assertEqual(headers["x-project-id"], "test-project")
        self.assertEqual(headers["X-Api-Token"], "test-token")
    
    def test_disabled_client_does_nothing(self):
        """Test that disabled client does not send events."""
        disabled_config = Config(
            api_url="http://localhost:8000",
            project_id="test-project",
            enabled=False,
        )
        disabled_client = SHClient(disabled_config)
        
        result = disabled_client.add_event({"type": "trace", "trace_id": "test"})
        self.assertFalse(result)
        
        disabled_client.close()
    
    def test_batch_size_limit(self):
        """Test that batch flushes when reaching size limit."""
        with patch.object(self.client, '_send_batch') as mock_send:
            # Add events up to batch size
            for i in range(self.config.batch_size):
                self.client.add_event({
                    "type": "trace",
                    "trace_id": f"test-{i}",
                })
            
            # Should have flushed at batch_size
            mock_send.assert_called_once()
    
    def test_client_context_manager(self):
        """Test client as context manager."""
        with SHClient(self.config) as client:
            self.assertIsNotNone(client)
            client.add_event({"type": "trace", "trace_id": "test"})


class TestConfig(unittest.TestCase):
    """Test cases for Config."""
    
    def test_config_defaults(self):
        """Test default configuration values."""
        config = Config(
            api_url="http://localhost:8000",
            project_id="test",
        )
        
        self.assertEqual(config.api_url, "http://localhost:8000")
        self.assertEqual(config.project_id, "test")
        self.assertIsNone(config.api_token)
        self.assertEqual(config.timeout, 5.0)
        self.assertEqual(config.batch_size, 100)
        self.assertEqual(config.flush_interval, 5.0)
        self.assertTrue(config.enabled)
        self.assertTrue(config.capture_input)
        self.assertTrue(config.capture_output)
    
    def test_config_custom_values(self):
        """Test custom configuration values."""
        config = Config(
            api_url="http://custom:9000",
            project_id="custom-project",
            api_token="custom-token",
            timeout=10.0,
            batch_size=50,
            flush_interval=2.0,
            enabled=False,
            capture_input=False,
            capture_output=False,
        )
        
        self.assertEqual(config.api_url, "http://custom:9000")
        self.assertEqual(config.project_id, "custom-project")
        self.assertEqual(config.api_token, "custom-token")
        self.assertEqual(config.timeout, 10.0)
        self.assertEqual(config.batch_size, 50)
        self.assertEqual(config.flush_interval, 2.0)
        self.assertFalse(config.enabled)
        self.assertFalse(config.capture_input)
        self.assertFalse(config.capture_output)
    
    def test_ingest_url_property(self):
        """Test ingest_url property."""
        config = Config(api_url="http://localhost:8000", project_id="test")
        self.assertEqual(config.ingest_url, "http://localhost:8000/api/v1/ingest")
        
        config = Config(api_url="http://localhost:8000/", project_id="test")
        self.assertEqual(config.ingest_url, "http://localhost:8000/api/v1/ingest")


if __name__ == "__main__":
    unittest.main()