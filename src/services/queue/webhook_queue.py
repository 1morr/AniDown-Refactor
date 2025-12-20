"""
Webhook queue worker module.

Provides queue processing for webhook events (e.g., qBittorrent completion notifications).
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from src.services.queue.queue_worker import QueueEvent, QueueWorker

logger = logging.getLogger(__name__)


@dataclass
class WebhookPayload:
    """
    Webhook event payload.

    Represents data received from a webhook notification.

    Attributes:
        hash_id: Torrent hash identifier.
        name: Torrent name.
        category: Torrent category.
        status: Torrent status.
        save_path: Download save path.
        extra_data: Additional webhook data.
    """
    hash_id: str
    name: str = ''
    category: str = ''
    status: str = ''
    save_path: str = ''
    extra_data: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_data is None:
            self.extra_data = {}


class WebhookQueueWorker(QueueWorker[WebhookPayload]):
    """
    Webhook queue worker.

    Processes webhook events from qBittorrent or other download clients.
    Delegates actual processing to registered handlers.
    """

    # Event type constants
    EVENT_TORRENT_COMPLETED = 'torrent_completed'
    EVENT_TORRENT_ADDED = 'torrent_added'
    EVENT_TORRENT_PAUSED = 'torrent_paused'
    EVENT_TORRENT_RESUMED = 'torrent_resumed'
    EVENT_TORRENT_DELETED = 'torrent_deleted'
    EVENT_TORRENT_ERROR = 'torrent_error'

    def __init__(
        self,
        name: str = 'WebhookQueue',
        max_failures: int = 5
    ):
        """
        Initialize the webhook queue worker.

        Args:
            name: Worker name for logging.
            max_failures: Maximum consecutive failures.
        """
        super().__init__(name=name, max_failures=max_failures)
        self._handlers: Dict[str, Callable[[WebhookPayload], None]] = {}

    def register_handler(
        self,
        event_type: str,
        handler: Callable[[WebhookPayload], None]
    ) -> None:
        """
        Register a handler for an event type.

        Args:
            event_type: Event type to handle.
            handler: Handler function.
        """
        self._handlers[event_type] = handler
        logger.debug(f'[{self._name}] Registered handler for: {event_type}')

    def unregister_handler(self, event_type: str) -> None:
        """
        Unregister a handler for an event type.

        Args:
            event_type: Event type to unregister.
        """
        if event_type in self._handlers:
            del self._handlers[event_type]
            logger.debug(f'[{self._name}] Unregistered handler for: {event_type}')

    def _handle_event(self, event: QueueEvent[WebhookPayload]) -> None:
        """
        Handle a webhook event.

        Dispatches to registered handler based on event type.

        Args:
            event: Webhook event to handle.
        """
        handler = self._handlers.get(event.event_type)

        if handler:
            logger.info(
                f'🔔 [{self._name}] Processing {event.event_type}: '
                f'{event.payload.hash_id[:8]}...'
            )
            handler(event.payload)
        else:
            logger.warning(
                f'⚠️ [{self._name}] No handler for event type: {event.event_type}'
            )

    def enqueue_completion(
        self,
        hash_id: str,
        name: str = '',
        category: str = '',
        save_path: str = ''
    ) -> int:
        """
        Enqueue a torrent completion event.

        Convenience method for the most common webhook event.

        Args:
            hash_id: Torrent hash.
            name: Torrent name.
            category: Torrent category.
            save_path: Save path.

        Returns:
            Current queue size.
        """
        payload = WebhookPayload(
            hash_id=hash_id,
            name=name,
            category=category,
            status='completed',
            save_path=save_path
        )
        return self.enqueue_event(
            event_type=self.EVENT_TORRENT_COMPLETED,
            payload=payload
        )

    def enqueue_error(
        self,
        hash_id: str,
        error_message: str,
        name: str = ''
    ) -> int:
        """
        Enqueue a torrent error event.

        Args:
            hash_id: Torrent hash.
            error_message: Error description.
            name: Torrent name.

        Returns:
            Current queue size.
        """
        payload = WebhookPayload(
            hash_id=hash_id,
            name=name,
            status='error',
            extra_data={'error': error_message}
        )
        return self.enqueue_event(
            event_type=self.EVENT_TORRENT_ERROR,
            payload=payload
        )


# Global webhook queue instance (singleton pattern)
_webhook_queue: Optional[WebhookQueueWorker] = None


def get_webhook_queue() -> WebhookQueueWorker:
    """
    Get the global webhook queue instance.

    Creates the instance on first call.

    Returns:
        WebhookQueueWorker instance.
    """
    global _webhook_queue
    if _webhook_queue is None:
        _webhook_queue = WebhookQueueWorker()
    return _webhook_queue


def init_webhook_queue(
    completion_handler: Optional[Callable[[WebhookPayload], None]] = None
) -> WebhookQueueWorker:
    """
    Initialize the global webhook queue with handlers.

    Args:
        completion_handler: Handler for completion events.

    Returns:
        Initialized WebhookQueueWorker.
    """
    queue_worker = get_webhook_queue()

    if completion_handler:
        queue_worker.register_handler(
            WebhookQueueWorker.EVENT_TORRENT_COMPLETED,
            completion_handler
        )

    return queue_worker
