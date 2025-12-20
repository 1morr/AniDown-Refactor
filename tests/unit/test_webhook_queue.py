"""
Tests for webhook handler and queue functionality.

Tests webhook event processing and queue worker behavior.
"""

import json
import pytest
import time
import uuid
from unittest.mock import MagicMock, patch

from tests.fixtures.test_data import QUEUE_TEST_EVENTS


class TestWebhookHandler:
    """Tests for webhook handler."""

    @pytest.fixture
    def webhook_app(self):
        """Create Flask app with webhook blueprint."""
        from flask import Flask
        from src.interface.webhook.handler import create_webhook_blueprint

        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(create_webhook_blueprint())

        return app

    @pytest.fixture
    def client(self, webhook_app):
        """Create test client."""
        return webhook_app.test_client()

    def test_webhook_health_check(self, client):
        """Test webhook health check endpoint."""
        response = client.get('/webhook/health')

        assert response.status_code == 200

    def test_webhook_qbit_torrent_completed(self, client):
        """Test qBittorrent torrent completed webhook."""
        data = {
            'event_type': 'torrent_completed',
            'hash': 'abc123def456789012345678901234567890',
            'name': 'Test Torrent',
            'save_path': '/downloads/test'
        }

        with patch('src.interface.webhook.handler.get_webhook_queue') as mock_queue:
            mock_instance = MagicMock()
            mock_instance.enqueue_event.return_value = 1  # Return queue length
            mock_queue.return_value = mock_instance

            response = client.post(
                '/webhook/qbit',
                data=json.dumps(data),
                content_type='application/json'
            )

        # Should return 200 or 202 (accepted)
        assert response.status_code in [200, 202, 204]

    def test_webhook_qbit_torrent_added(self, client):
        """Test qBittorrent torrent added webhook."""
        data = {
            'event_type': 'torrent_added',
            'hash': 'abc123def456789012345678901234567890',
            'name': 'Test Torrent'
        }

        with patch('src.interface.webhook.handler.get_webhook_queue') as mock_queue:
            mock_instance = MagicMock()
            mock_instance.enqueue_event.return_value = 1  # Return queue length
            mock_queue.return_value = mock_instance

            response = client.post(
                '/webhook/qbit',
                data=json.dumps(data),
                content_type='application/json'
            )

        assert response.status_code in [200, 202, 204]

    def test_webhook_qbit_torrent_error(self, client):
        """Test qBittorrent torrent error webhook."""
        data = {
            'event_type': 'torrent_error',
            'hash': 'abc123def456789012345678901234567890',
            'name': 'Test Torrent',
            'error': 'Download failed'
        }

        with patch('src.interface.webhook.handler.get_webhook_queue') as mock_queue:
            mock_instance = MagicMock()
            mock_instance.enqueue_event.return_value = 1  # Return queue length
            mock_queue.return_value = mock_instance

            response = client.post(
                '/webhook/qbit',
                data=json.dumps(data),
                content_type='application/json'
            )

        assert response.status_code in [200, 202, 204]

    def test_webhook_qbit_invalid_json(self, client):
        """Test webhook with invalid JSON."""
        response = client.post(
            '/webhook/qbit',
            data='invalid json',
            content_type='application/json'
        )

        assert response.status_code in [400, 500]

    def test_webhook_qbit_missing_event(self, client):
        """Test webhook with missing event field."""
        data = {
            'hash': 'abc123',
            'name': 'Test'
        }

        response = client.post(
            '/webhook/qbit',
            data=json.dumps(data),
            content_type='application/json'
        )

        # Should handle gracefully
        assert response.status_code in [200, 202, 400]


class TestWebhookQueue:
    """Tests for webhook queue worker."""

    @pytest.fixture
    def webhook_queue(self):
        """Create webhook queue worker."""
        from src.services.queue.webhook_queue import get_webhook_queue

        queue = get_webhook_queue()
        return queue

    def test_webhook_queue_initialization(self, webhook_queue):
        """Test webhook queue initializes correctly."""
        assert webhook_queue is not None

    def test_register_handler(self, webhook_queue):
        """Test registering event handler."""
        handler = MagicMock()

        webhook_queue.register_handler('test_event', handler)

        # Handler should be registered
        assert 'test_event' in webhook_queue._handlers

    def test_enqueue_event(self, webhook_queue):
        """Test enqueueing an event."""
        from src.services.queue.webhook_queue import WebhookPayload

        payload = WebhookPayload(
            hash_id='abc123def456789012345678901234567890',
            name='Test Torrent',
            save_path='/downloads/test'
        )

        # Should not raise exception
        webhook_queue.enqueue_event('torrent_completed', payload)

    def test_queue_start_stop(self, webhook_queue):
        """Test starting and stopping the queue."""
        # Start queue
        webhook_queue.start()
        assert webhook_queue.is_running() is True

        # Stop queue
        webhook_queue.stop()
        assert webhook_queue.is_running() is False


class TestRSSQueue:
    """Tests for RSS queue worker."""

    @pytest.fixture
    def rss_queue(self):
        """Create RSS queue worker."""
        from src.services.queue.rss_queue import get_rss_queue

        queue = get_rss_queue()
        return queue

    def test_rss_queue_initialization(self, rss_queue):
        """Test RSS queue initializes correctly."""
        assert rss_queue is not None

    def test_register_rss_handler(self, rss_queue):
        """Test registering RSS event handler."""
        handler = MagicMock()

        rss_queue.register_handler('scheduled_check', handler)

        assert 'scheduled_check' in rss_queue._handlers

    def test_enqueue_rss_event(self, rss_queue):
        """Test enqueueing an RSS event."""
        from src.services.queue.rss_queue import RSSPayload

        payload = RSSPayload(
            rss_url='https://example.com/rss',
            trigger_type='定时触发'
        )

        # Should not raise exception
        rss_queue.enqueue_event('scheduled_check', payload)

    def test_rss_queue_start_stop(self, rss_queue):
        """Test starting and stopping RSS queue."""
        rss_queue.start()
        assert rss_queue.is_running() is True

        rss_queue.stop()
        assert rss_queue.is_running() is False


class TestQueueWorkerBase:
    """Tests for base queue worker functionality."""

    def test_queue_worker_pause_resume(self):
        """Test pausing and resuming queue worker."""
        from src.services.queue.queue_worker import QueueWorker

        class TestWorker(QueueWorker):
            def _handle_event(self, event_type: str, payload):
                pass

        worker = TestWorker(name='test_worker')
        worker.start()

        # Pause
        worker.pause()
        assert worker.is_paused() is True

        # Resume
        worker.resume()
        assert worker.is_paused() is False

        worker.stop()

    def test_queue_worker_status(self):
        """Test getting queue worker status."""
        from src.services.queue.queue_worker import QueueWorker

        class TestWorker(QueueWorker):
            def _handle_event(self, event_type: str, payload):
                pass

        worker = TestWorker(name='test_worker')

        status = worker.get_status()

        # Check for correct status keys (thread_alive instead of running)
        assert 'thread_alive' in status or 'running' in status
        assert 'paused' in status
        assert 'queue_len' in status


@pytest.mark.integration
class TestQueueIntegration:
    """Integration tests for queue functionality."""

    def test_webhook_queue_processes_event(self):
        """Test that webhook queue processes events correctly."""
        from src.services.queue.webhook_queue import (
            get_webhook_queue,
            WebhookPayload,
            WebhookQueueWorker
        )

        queue = get_webhook_queue()
        processed = []

        def handler(payload):
            processed.append(payload)

        queue.register_handler(WebhookQueueWorker.EVENT_TORRENT_COMPLETED, handler)
        queue.start()

        # Use unique hash to identify our event
        test_hash = f'unique_test_{uuid.uuid4().hex[:20]}'
        payload = WebhookPayload(
            hash_id=test_hash,
            name='Test Torrent',
            save_path='/downloads/test'
        )

        queue.enqueue_event(WebhookQueueWorker.EVENT_TORRENT_COMPLETED, payload)

        # Wait for processing
        time.sleep(0.5)

        queue.stop()

        # Our specific event should have been processed
        our_events = [p for p in processed if p.hash_id == test_hash]
        assert len(our_events) == 1
        assert our_events[0].hash_id == test_hash

    def test_rss_queue_processes_event(self):
        """Test that RSS queue processes events correctly."""
        from src.services.queue.rss_queue import (
            get_rss_queue,
            RSSPayload,
            RSSQueueWorker
        )

        queue = get_rss_queue()
        processed = []

        def handler(payload):
            processed.append(payload)

        queue.register_handler(RSSQueueWorker.EVENT_MANUAL_CHECK, handler)
        queue.start()

        payload = RSSPayload(
            rss_url='https://example.com/rss',
            trigger_type='手动触发'
        )

        queue.enqueue_event(RSSQueueWorker.EVENT_MANUAL_CHECK, payload)

        # Wait for processing
        time.sleep(0.5)

        queue.stop()

        # Event should have been processed
        assert len(processed) == 1
        assert processed[0].rss_url == 'https://example.com/rss'
