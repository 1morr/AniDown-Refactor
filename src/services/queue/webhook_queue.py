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
    EVENT_TORRENT_FINISHED = 'torrent_finished'
    EVENT_TORRENT_ADDED = 'torrent_added'
    EVENT_TORRENT_PAUSED = 'torrent_paused'
    EVENT_TORRENT_RESUMED = 'torrent_resumed'
    EVENT_TORRENT_DELETED = 'torrent_deleted'
    EVENT_TORRENT_ERROR = 'torrent_error'

    def __init__(
        self,
        name: str = 'WebhookQueue',
        max_failures: int = 5,
        download_manager: Optional[Any] = None,
        discord_client: Optional[Any] = None
    ):
        """
        Initialize the webhook queue worker.

        Args:
            name: Worker name for logging.
            max_failures: Maximum consecutive failures.
            download_manager: Download manager instance for processing.
            discord_client: Discord client for notifications.
        """
        super().__init__(name=name, max_failures=max_failures)
        self._handlers: Dict[str, Callable[[WebhookPayload], None]] = {}
        self._download_manager = download_manager
        self._discord_client = discord_client

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

    def enqueue(
        self,
        event: QueueEvent[WebhookPayload] = None,
        event_type: str = None,
        hash_id: str = None,
        payload: Dict[str, Any] = None
    ) -> QueueEvent[WebhookPayload]:
        """
        Add an event to the queue.

        Supports both new API (event_type, hash_id, payload) and
        base class API (event object).

        Args:
            event: Pre-built QueueEvent (base class compatibility).
            event_type: Event type string.
            hash_id: Torrent hash identifier.
            payload: Event payload as dictionary.

        Returns:
            The enqueued QueueEvent with queue_id.
        """
        if event is not None:
            # Base class API - use provided event
            return super().enqueue(event)

        # New API - build event from parameters
        webhook_payload = WebhookPayload(
            hash_id=hash_id or '',
            name=payload.get('name', '') if payload else '',
            category=payload.get('category', '') if payload else '',
            status=payload.get('status', '') if payload else '',
            save_path=payload.get('save_path', '') if payload else '',
            extra_data=payload or {}
        )

        # Create QueueEvent and call parent's enqueue directly to avoid recursion
        queue_event = QueueEvent(
            event_type=event_type or self.EVENT_TORRENT_FINISHED,
            payload=webhook_payload
        )
        return super().enqueue(queue_event)

    def enqueue_completion(
        self,
        hash_id: str,
        name: str = '',
        category: str = '',
        save_path: str = ''
    ) -> QueueEvent[WebhookPayload]:
        """
        Enqueue a torrent completion event.

        Convenience method for the most common webhook event.

        Args:
            hash_id: Torrent hash.
            name: Torrent name.
            category: Torrent category.
            save_path: Save path.

        Returns:
            The enqueued event.
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
    ) -> QueueEvent[WebhookPayload]:
        """
        Enqueue a torrent error event.

        Args:
            hash_id: Torrent hash.
            error_message: Error description.
            name: Torrent name.

        Returns:
            The enqueued event.
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
# Public variable for legacy API compatibility
webhook_queue_worker: Optional[WebhookQueueWorker] = None


def get_webhook_queue() -> WebhookQueueWorker:
    """
    Get the global webhook queue instance.

    Creates the instance on first call.

    Returns:
        WebhookQueueWorker instance.
    """
    global webhook_queue_worker
    if webhook_queue_worker is None:
        webhook_queue_worker = WebhookQueueWorker()
    return webhook_queue_worker


def init_webhook_queue(
    download_manager: Optional[Any] = None,
    discord_client: Optional[Any] = None,
    completion_handler: Optional[Callable[[WebhookPayload], None]] = None
) -> WebhookQueueWorker:
    """
    Initialize the global webhook queue with handlers.

    Args:
        download_manager: Download manager instance for processing.
        discord_client: Discord client for notifications.
        completion_handler: Optional custom handler for completion events.

    Returns:
        Initialized WebhookQueueWorker.
    """
    global webhook_queue_worker

    # Create new worker with dependencies
    webhook_queue_worker = WebhookQueueWorker(
        download_manager=download_manager,
        discord_client=discord_client
    )

    # Create default completion handler if not provided
    if completion_handler is None and download_manager is not None:
        def default_completion_handler(payload: WebhookPayload) -> None:
            """Default handler that processes completed torrents."""
            try:
                logger.info(f'🔔 Processing torrent completion: {payload.hash_id[:8]}...')
                # Call download manager's handle_torrent_completion if available
                if hasattr(download_manager, 'handle_torrent_completion'):
                    download_manager.handle_torrent_completion(
                        hash_id=payload.hash_id,
                        name=payload.name,
                        category=payload.category,
                        save_path=payload.save_path
                    )
            except Exception as e:
                logger.error(f'❌ Error processing torrent completion: {e}')
                # 重新抛出异常，让 QueueWorker 正确统计失败数
                raise

        completion_handler = default_completion_handler

    # Register handlers
    if completion_handler:
        webhook_queue_worker.register_handler(
            WebhookQueueWorker.EVENT_TORRENT_COMPLETED,
            completion_handler
        )
        # Also register for 'torrent_finished' alias
        webhook_queue_worker.register_handler(
            WebhookQueueWorker.EVENT_TORRENT_FINISHED,
            completion_handler
        )

    # Start the worker
    webhook_queue_worker.start()

    return webhook_queue_worker
