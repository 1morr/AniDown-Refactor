"""
Queue worker base module.

Provides base class for background queue processing with pause/resume/stop functionality.
"""

import logging
import queue
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class QueueEvent(Generic[T]):
    """
    Queue event data class.

    Represents an event in the processing queue.

    Attributes:
        queue_id: Unique identifier for the event.
        event_type: Type identifier for the event.
        payload: Event data/payload.
        received_at: UTC timestamp when event was received.
        metadata: Optional additional metadata.
    """
    event_type: str
    payload: T
    queue_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary representation."""
        result = {
            'queue_id': self.queue_id,
            'event_type': self.event_type,
            'received_at_utc': self.received_at.isoformat(),
            'metadata': self.metadata
        }
        # 尝试从 payload 中获取 name 作为 display_name
        if hasattr(self.payload, 'name') and self.payload.name:
            result['display_name'] = self.payload.name
        return result


@dataclass
class QueueStats:
    """
    Queue statistics data class.

    Tracks processing statistics for the queue.
    """
    total_processed: int = 0
    total_success: int = 0
    total_failed: int = 0
    processing_start_time: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_processed == 0:
            return 0.0
        return (self.total_success / self.total_processed) * 100


class QueueWorker(ABC, Generic[T]):
    """
    Abstract base class for queue workers.

    Provides background queue processing with:
    - Pause/resume functionality (thread keeps running but doesn't process)
    - Stop/start functionality (completely stops/starts the worker thread)
    - Event statistics tracking
    - Thread-safe operations

    Subclasses must implement the _handle_event method.
    """

    def __init__(self, name: str, max_failures: int = 5):
        """
        Initialize the queue worker.

        Args:
            name: Worker name for logging.
            max_failures: Maximum consecutive failures before logging warning.
        """
        self._name = name
        self._queue: queue.Queue[QueueEvent[T]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._current_event: Optional[QueueEvent[T]] = None
        self._processing_started_at: Optional[datetime] = None
        self._consecutive_failures = 0
        self._max_failures = max_failures
        self._lock = threading.Lock()

        # Statistics
        self._stats = QueueStats()

    @property
    def name(self) -> str:
        """Return the worker name."""
        return self._name

    def start(self) -> None:
        """
        Start the worker thread.

        If the thread is already running, this is a no-op.
        """
        if self._thread and self._thread.is_alive():
            logger.debug(f'[{self._name}] Worker already running')
            return

        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=self._name)
        self._thread.start()
        logger.info(f'🚀 [{self._name}] Worker started')

    def stop(self) -> None:
        """
        Stop the worker thread completely.

        The queue is preserved but the thread exits.
        Use start() to restart processing.
        """
        self._stop_event.set()
        self._pause_event.set()  # Unblock pause wait
        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning(f'⚠️ [{self._name}] Worker thread did not stop cleanly')
        logger.info(f'🛑 [{self._name}] Worker stopped')

    def pause(self) -> None:
        """
        Pause queue processing.

        The thread continues running but doesn't process new events.
        Events can still be added to the queue.
        """
        self._pause_event.set()
        logger.info(f'⏸️ [{self._name}] Worker paused')

    def resume(self) -> None:
        """
        Resume queue processing after pause.

        Has no effect if the worker is not paused.
        """
        self._pause_event.clear()
        logger.info(f'▶️ [{self._name}] Worker resumed')

    def is_paused(self) -> bool:
        """
        Check if the worker is paused.

        Returns:
            True if paused but not stopped.
        """
        return self._pause_event.is_set() and not self._stop_event.is_set()

    def is_running(self) -> bool:
        """
        Check if the worker thread is running.

        Returns:
            True if thread is alive and not stopped.
        """
        return (
            self._thread is not None and
            self._thread.is_alive() and
            not self._stop_event.is_set()
        )

    def is_stopped(self) -> bool:
        """
        Check if the worker is stopped.

        Returns:
            True if stop event is set.
        """
        return self._stop_event.is_set()

    def qsize(self) -> int:
        """
        Get the current queue size.

        Returns:
            Number of events in the queue.
        """
        return self._queue.qsize()

    def enqueue(self, event: QueueEvent[T]) -> QueueEvent[T]:
        """
        Add an event to the queue.

        Args:
            event: Event to add.

        Returns:
            The enqueued event with queue_id.
        """
        self._queue.put(event)
        queue_size = self._queue.qsize()
        logger.debug(f'📥 [{self._name}] Event enqueued, queue size: {queue_size}')
        return event

    def enqueue_event(self, event_type: str, payload: T, **metadata) -> QueueEvent[T]:
        """
        Create and enqueue an event.

        Convenience method that creates a QueueEvent and enqueues it.

        Args:
            event_type: Type identifier for the event.
            payload: Event data.
            **metadata: Additional metadata.

        Returns:
            The enqueued event with queue_id.
        """
        event = QueueEvent(
            event_type=event_type,
            payload=payload,
            metadata=metadata
        )
        return self.enqueue(event)

    def _run(self) -> None:
        """
        Main worker loop.

        Processes events from the queue until stopped.
        Respects pause state by waiting without exiting.
        """
        logger.debug(f'[{self._name}] Worker thread started')

        while not self._stop_event.is_set():
            # Handle pause state - wait without exiting
            while self._pause_event.is_set() and not self._stop_event.is_set():
                time.sleep(0.5)

            if self._stop_event.is_set():
                break

            try:
                # Try to get an event with timeout
                event = self._queue.get(timeout=1.0)
                self._process_event(event)
            except queue.Empty:
                # No event available, continue loop
                continue
            except Exception as e:
                logger.exception(f'❌ [{self._name}] Unexpected error in worker loop: {e}')
                self._on_failure()

        logger.debug(f'[{self._name}] Worker thread exiting')

    def _process_event(self, event: QueueEvent[T]) -> None:
        """
        Process a single event.

        Args:
            event: Event to process.
        """
        with self._lock:
            self._current_event = event
            self._processing_started_at = datetime.now(timezone.utc)

        try:
            logger.debug(
                f'🔄 [{self._name}] Processing event: {event.event_type}'
            )
            self._handle_event(event)
            self._on_success()
        except Exception as e:
            logger.error(f'❌ [{self._name}] Event processing failed: {e}')
            self._on_failure()
        finally:
            with self._lock:
                self._current_event = None
                self._processing_started_at = None
                self._stats.total_processed += 1

    @abstractmethod
    def _handle_event(self, event: QueueEvent[T]) -> None:
        """
        Handle a queue event.

        Subclasses must implement this method to process events.

        Args:
            event: Event to handle.
        """
        pass

    def _on_success(self) -> None:
        """Called when event processing succeeds."""
        with self._lock:
            self._consecutive_failures = 0
            self._stats.total_success += 1

    def _on_failure(self) -> None:
        """Called when event processing fails."""
        with self._lock:
            self._consecutive_failures += 1
            self._stats.total_failed += 1

            if self._consecutive_failures >= self._max_failures:
                logger.warning(
                    f'⚠️ [{self._name}] {self._consecutive_failures} consecutive failures '
                    f'(max: {self._max_failures})'
                )

    def get_status(self) -> Dict[str, Any]:
        """
        Get worker status.

        Returns:
            Dictionary with worker status information.
        """
        with self._lock:
            # Get pending events (preview of first 10)
            pending_events = []
            try:
                temp_list = list(self._queue.queue)[:10]
                for evt in temp_list:
                    pending_events.append(evt.to_dict())
            except Exception:
                pass

            # Current event info
            current = None
            if self._current_event:
                current = self._current_event.to_dict()
                if self._processing_started_at:
                    current['started_at_utc'] = self._processing_started_at.isoformat()

            return {
                'name': self._name,
                'queue_len': self._queue.qsize(),
                'thread_alive': self._thread.is_alive() if self._thread else False,
                'stopped': self._stop_event.is_set(),
                'paused': self.is_paused(),
                'consecutive_failures': self._consecutive_failures,
                'max_consecutive_failures': self._max_failures,
                'current_event': current,
                'pending_events': pending_events,
                'stats': {
                    'total_processed': self._stats.total_processed,
                    'total_success': self._stats.total_success,
                    'total_failed': self._stats.total_failed,
                    'success_rate': round(self._stats.success_rate, 2)
                }
            }

    def clear_queue(self) -> Dict[str, Any]:
        """
        Clear all pending events from the queue.

        Returns:
            Dictionary containing:
            - count: Number of events cleared
            - history_ids: List of unique history IDs from cleared events
            - cleared_items: List of dicts with {history_id, item_title} for detail records
        """
        count = 0
        history_ids = set()
        cleared_items = []
        while True:
            try:
                event = self._queue.get_nowait()
                count += 1
                # 尝试从事件中提取 history_id 和 item_title
                if hasattr(event, 'payload'):
                    payload = event.payload
                    item_title = None
                    history_id = None

                    # 获取 item_title
                    if hasattr(payload, 'item_title'):
                        item_title = payload.item_title
                    elif hasattr(payload, 'title'):
                        item_title = payload.title

                    # 获取 history_id
                    if hasattr(payload, 'extra_data') and isinstance(payload.extra_data, dict):
                        history_id = payload.extra_data.get('history_id')

                    if history_id:
                        history_ids.add(history_id)
                        if item_title:
                            cleared_items.append({
                                'history_id': history_id,
                                'item_title': item_title
                            })
            except queue.Empty:
                break
        logger.info(f'🗑️ [{self._name}] Cleared {count} events from queue')
        return {
            'count': count,
            'history_ids': list(history_ids),
            'cleared_items': cleared_items
        }

    def get_queue_size(self) -> int:
        """
        Get current queue size.

        Returns:
            Number of pending events.
        """
        return self._queue.qsize()
