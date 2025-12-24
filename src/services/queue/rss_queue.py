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
        title: Optional feed title or item title.
        items: Optional pre-fetched RSS items.
        extra_data: Additional metadata.
    """
    rss_url: str
    trigger_type: str = 'scheduled'
    anime_id: Optional[int] = None
    title: Optional[str] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def get_display_name(self) -> str:
        """获取用于显示的名称"""
        if self.title:
            return self.title[:60] + '...' if len(self.title) > 60 else self.title
        return self.rss_url[:60] + '...' if len(self.rss_url) > 60 else self.rss_url


@dataclass
class RSSItemPayload:
    """
    单个 RSS 项目的载荷。

    用于处理单个 RSS 项目。

    Attributes:
        item_title: 项目标题
        torrent_url: 种子链接
        hash_id: 种子 hash
        rss_url: 来源 RSS URL
        media_type: 媒体类型 (anime/live_action)
        extra_data: 额外数据
    """
    item_title: str
    torrent_url: str
    hash_id: str = ''
    rss_url: str = ''
    media_type: str = 'anime'
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def get_display_name(self) -> str:
        """获取用于显示的名称"""
        if self.item_title:
            return self.item_title[:60] + '...' if len(self.item_title) > 60 else self.item_title
        return 'Unknown Item'


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
    EVENT_SINGLE_ITEM = 'single_item'  # 新增：单个项目处理

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
        self._handlers: Dict[str, Callable] = {}

        # 分类统计：Feed级别 vs Item级别
        self._feed_success: int = 0
        self._feed_failed: int = 0
        self._item_success: int = 0
        self._item_failed: int = 0

    def register_handler(
        self,
        event_type: str,
        handler: Callable
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

    def _handle_event(self, event: QueueEvent) -> None:
        """
        Handle an RSS event.

        Dispatches to registered handler based on event type.

        Args:
            event: RSS event to handle.
        """
        handler = self._handlers.get(event.event_type)

        if handler:
            # 获取显示名称
            if hasattr(event.payload, 'get_display_name'):
                display_name = event.payload.get_display_name()
            else:
                display_name = str(event.payload)[:50]

            logger.info(
                f'📡 [{self._name}] Processing {event.event_type}: '
                f'{display_name}'
            )
            handler(event.payload)
        else:
            logger.warning(
                f'⚠️ [{self._name}] No handler for event type: {event.event_type}'
            )

    def _is_item_event(self, event_type: str) -> bool:
        """判断是否为 Item 级别事件"""
        return event_type == self.EVENT_SINGLE_ITEM

    def _on_success(self) -> None:
        """重写：在更新总统计的同时更新分类统计"""
        super()._on_success()
        if self._current_event:
            if self._is_item_event(self._current_event.event_type):
                self._item_success += 1
            else:
                self._feed_success += 1

    def _on_failure(self) -> None:
        """重写：在更新总统计的同时更新分类统计"""
        super()._on_failure()
        if self._current_event:
            if self._is_item_event(self._current_event.event_type):
                self._item_failed += 1
            else:
                self._feed_failed += 1

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

    def enqueue_single_item(
        self,
        item_title: str,
        torrent_url: str,
        hash_id: str = '',
        rss_url: str = '',
        media_type: str = 'anime',
        extra_data: Dict[str, Any] = None
    ) -> int:
        """
        将单个 RSS 项目加入队列。

        Args:
            item_title: 项目标题
            torrent_url: 种子链接
            hash_id: 种子 hash
            rss_url: 来源 RSS URL
            media_type: 媒体类型
            extra_data: 额外数据

        Returns:
            当前队列大小
        """
        payload = RSSItemPayload(
            item_title=item_title,
            torrent_url=torrent_url,
            hash_id=hash_id,
            rss_url=rss_url,
            media_type=media_type,
            extra_data=extra_data or {}
        )
        return self.enqueue_event(
            event_type=self.EVENT_SINGLE_ITEM,
            payload=payload
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Get worker status with enhanced display names.

        Returns:
            Dictionary with worker status information.
        """
        status = super().get_status()

        # 增强 pending_events 的显示信息
        enhanced_pending = []
        try:
            temp_list = list(self._queue.queue)[:10]
            for evt in temp_list:
                event_info = evt.to_dict()
                if hasattr(evt.payload, 'get_display_name'):
                    event_info['display_name'] = evt.payload.get_display_name()
                elif hasattr(evt.payload, 'item_title'):
                    event_info['display_name'] = evt.payload.item_title[:60]
                elif hasattr(evt.payload, 'title') and evt.payload.title:
                    event_info['display_name'] = evt.payload.title[:60]
                elif hasattr(evt.payload, 'rss_url'):
                    event_info['display_name'] = evt.payload.rss_url[:60]
                else:
                    event_info['display_name'] = str(evt.payload)[:60]
                enhanced_pending.append(event_info)
        except Exception:
            pass

        status['pending_events'] = enhanced_pending

        # 增强 current_event 的显示信息
        if status.get('current_event') and self._current_event:
            if hasattr(self._current_event.payload, 'get_display_name'):
                status['current_event']['display_name'] = self._current_event.payload.get_display_name()

        # 添加分类统计
        status['stats']['feed_success'] = self._feed_success
        status['stats']['feed_failed'] = self._feed_failed
        status['stats']['item_success'] = self._item_success
        status['stats']['item_failed'] = self._item_failed

        return status


# Global RSS queue instance (singleton pattern)
# Public variable for legacy API compatibility
rss_queue_worker: Optional[RSSQueueWorker] = None


def get_rss_queue() -> RSSQueueWorker:
    """
    Get the global RSS queue instance.

    Creates the instance on first call.

    Returns:
        RSSQueueWorker instance.
    """
    global rss_queue_worker
    if rss_queue_worker is None:
        rss_queue_worker = RSSQueueWorker()
    return rss_queue_worker


def init_rss_queue(
    scheduled_handler: Optional[Callable[[RSSPayload], None]] = None,
    manual_handler: Optional[Callable[[RSSPayload], None]] = None,
    fixed_handler: Optional[Callable[[RSSPayload], None]] = None,
    item_handler: Optional[Callable[[RSSItemPayload], None]] = None
) -> RSSQueueWorker:
    """
    Initialize the global RSS queue with handlers.

    Args:
        scheduled_handler: Handler for scheduled checks.
        manual_handler: Handler for manual checks.
        fixed_handler: Handler for fixed subscriptions.
        item_handler: Handler for single item processing.

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

    if item_handler:
        queue_worker.register_handler(
            RSSQueueWorker.EVENT_SINGLE_ITEM,
            item_handler
        )

    return queue_worker
