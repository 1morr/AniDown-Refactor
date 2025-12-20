"""
RSS queue worker module.

Provides queue processing for RSS feed processing events.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.services.queue.queue_worker import QueueEvent, QueueWorker

logger = logging.getLogger(__name__)


@dataclass
class RSSPayload:
    """
    RSS event payload.

    Represents data for RSS feed processing.

    Attributes:
        rss_url: URL of the RSS feed.
        trigger_type: How the processing was triggered.
        anime_id: Optional anime ID for fixed subscriptions.
        title: Optional feed title.
        items: Optional pre-fetched RSS items.
        extra_data: Additional metadata.
    """
    rss_url: str
    trigger_type: str = 'scheduled'
    anime_id: Optional[int] = None
    title: Optional[str] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    extra_data: Dict[str, Any] = field(default_factory=dict)


class RSSQueueWorker(QueueWorker[RSSPayload]):
    """
    RSS queue worker.

    Processes RSS feed events for anime download discovery.
    Supports scheduled, manual, and fixed subscription triggers.
    """

    # Event type constants
    EVENT_SCHEDULED_CHECK = 'scheduled_check'
    EVENT_MANUAL_CHECK = 'manual_check'
    EVENT_FIXED_SUBSCRIPTION = 'fixed_subscription'
    EVENT_SINGLE_FEED = 'single_feed'

    def __init__(
        self,
        name: str = 'RSSQueue',
        max_failures: int = 5
    ):
        """
        Initialize the RSS queue worker.

        Args:
            name: Worker name for logging.
            max_failures: Maximum consecutive failures.
        """
        super().__init__(name=name, max_failures=max_failures)
        self._handlers: Dict[str, Callable[[RSSPayload], None]] = {}

    def register_handler(
        self,
        event_type: str,
        handler: Callable[[RSSPayload], None]
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

    def _handle_event(self, event: QueueEvent[RSSPayload]) -> None:
        """
        Handle an RSS event.

        Dispatches to registered handler based on event type.

        Args:
            event: RSS event to handle.
        """
        handler = self._handlers.get(event.event_type)

        if handler:
            logger.info(
                f'📡 [{self._name}] Processing {event.event_type}: '
                f'{event.payload.rss_url[:50]}...'
            )
            handler(event.payload)
        else:
            logger.warning(
                f'⚠️ [{self._name}] No handler for event type: {event.event_type}'
            )

    def enqueue_scheduled_check(self, rss_url: str) -> int:
        """
        Enqueue a scheduled RSS check.

        Args:
            rss_url: RSS feed URL.

        Returns:
            Current queue size.
        """
        payload = RSSPayload(
            rss_url=rss_url,
            trigger_type='scheduled'
        )
        return self.enqueue_event(
            event_type=self.EVENT_SCHEDULED_CHECK,
            payload=payload
        )

    def enqueue_manual_check(self, rss_url: str, title: Optional[str] = None) -> int:
        """
        Enqueue a manual RSS check.

        Args:
            rss_url: RSS feed URL.
            title: Optional feed title.

        Returns:
            Current queue size.
        """
        payload = RSSPayload(
            rss_url=rss_url,
            trigger_type='manual',
            title=title
        )
        return self.enqueue_event(
            event_type=self.EVENT_MANUAL_CHECK,
            payload=payload
        )

    def enqueue_fixed_subscription(
        self,
        rss_url: str,
        anime_id: int,
        title: str
    ) -> int:
        """
        Enqueue a fixed subscription check.

        Args:
            rss_url: RSS feed URL.
            anime_id: Associated anime ID.
            title: Anime title.

        Returns:
            Current queue size.
        """
        payload = RSSPayload(
            rss_url=rss_url,
            trigger_type='fixed',
            anime_id=anime_id,
            title=title
        )
        return self.enqueue_event(
            event_type=self.EVENT_FIXED_SUBSCRIPTION,
            payload=payload
        )

    def enqueue_single_feed(
        self,
        rss_url: str,
        items: List[Dict[str, Any]],
        trigger_type: str = 'manual'
    ) -> int:
        """
        Enqueue pre-fetched RSS items for processing.

        Args:
            rss_url: RSS feed URL.
            items: Pre-fetched RSS items.
            trigger_type: Trigger type.

        Returns:
            Current queue size.
        """
        payload = RSSPayload(
            rss_url=rss_url,
            trigger_type=trigger_type,
            items=items
        )
        return self.enqueue_event(
            event_type=self.EVENT_SINGLE_FEED,
            payload=payload
        )


# Global RSS queue instance (singleton pattern)
_rss_queue: Optional[RSSQueueWorker] = None


def get_rss_queue() -> RSSQueueWorker:
    """
    Get the global RSS queue instance.

    Creates the instance on first call.

    Returns:
        RSSQueueWorker instance.
    """
    global _rss_queue
    if _rss_queue is None:
        _rss_queue = RSSQueueWorker()
    return _rss_queue


def init_rss_queue(
    scheduled_handler: Optional[Callable[[RSSPayload], None]] = None,
    manual_handler: Optional[Callable[[RSSPayload], None]] = None,
    fixed_handler: Optional[Callable[[RSSPayload], None]] = None
) -> RSSQueueWorker:
    """
    Initialize the global RSS queue with handlers.

    Args:
        scheduled_handler: Handler for scheduled checks.
        manual_handler: Handler for manual checks.
        fixed_handler: Handler for fixed subscriptions.

    Returns:
        Initialized RSSQueueWorker.
    """
    queue_worker = get_rss_queue()

    if scheduled_handler:
        queue_worker.register_handler(
            RSSQueueWorker.EVENT_SCHEDULED_CHECK,
            scheduled_handler
        )

    if manual_handler:
        queue_worker.register_handler(
            RSSQueueWorker.EVENT_MANUAL_CHECK,
            manual_handler
        )
        # Also use for single feed events
        queue_worker.register_handler(
            RSSQueueWorker.EVENT_SINGLE_FEED,
            manual_handler
        )

    if fixed_handler:
        queue_worker.register_handler(
            RSSQueueWorker.EVENT_FIXED_SUBSCRIPTION,
            fixed_handler
        )

    return queue_worker
