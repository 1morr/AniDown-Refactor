"""
熔断器模块。

提供服务熔断功能，当服务出现大量错误时自动熔断，
保护系统免受级联故障影响。
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    熔断器。

    当服务出现大量错误时自动熔断，防止继续调用失败的服务。
    支持自动恢复和手动重置。

    状态：
    - CLOSED（关闭）: 正常状态，允许请求通过
    - OPEN（开启）: 熔断状态，拒绝所有请求

    Example:
        >>> breaker = CircuitBreaker('title_parse')
        >>> if breaker.is_open():
        ...     raise AICircuitBreakerError('熔断器已开启')
        >>> # 调用 API...
        >>> # 如果所有 Key 都失败
        >>> breaker.trip(duration=300)
    """

    # 默认熔断持续时间（秒）
    DEFAULT_OPEN_DURATION = 300  # 5 分钟

    def __init__(self, purpose: str):
        """
        初始化熔断器。

        Args:
            purpose: 熔断器用途标识（如 'title_parse', 'multi_file_rename'）
        """
        self._purpose = purpose
        self._is_open = False
        self._open_until: float = 0
        self._trip_count: int = 0
        self._last_trip_time: Optional[float] = None
        self._last_trip_reason: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def purpose(self) -> str:
        """获取熔断器用途标识。"""
        return self._purpose

    def trip(
        self,
        duration: Optional[float] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        触发熔断。

        Args:
            duration: 熔断持续时间（秒），默认使用 DEFAULT_OPEN_DURATION
            reason: 熔断原因
        """
        with self._lock:
            duration = duration or self.DEFAULT_OPEN_DURATION
            self._is_open = True
            self._open_until = time.time() + duration
            self._trip_count += 1
            self._last_trip_time = time.time()
            self._last_trip_reason = reason

            logger.error(
                f'🔴 [{self._purpose}] 熔断器已触发，持续 {duration}s'
                + (f'，原因: {reason}' if reason else '')
            )

    def reset(self) -> None:
        """
        手动重置熔断器。

        将熔断器状态从 OPEN 恢复到 CLOSED。
        """
        with self._lock:
            was_open = self._is_open
            self._is_open = False
            self._open_until = 0
            if was_open:
                logger.info(f'🟢 [{self._purpose}] 熔断器已手动重置')

    def is_open(self) -> bool:
        """
        检查熔断器是否开启。

        如果熔断时间已过，会自动恢复。

        Returns:
            bool: True 表示熔断中，False 表示正常
        """
        with self._lock:
            if self._is_open:
                if time.time() >= self._open_until:
                    # 自动恢复
                    self._is_open = False
                    self._open_until = 0
                    logger.info(f'🟢 [{self._purpose}] 熔断器已自动恢复')
                    return False
                return True
            return False

    def get_remaining_seconds(self) -> float:
        """
        获取熔断剩余时间。

        Returns:
            float: 剩余秒数，如果未熔断则返回 0
        """
        with self._lock:
            if self._is_open:
                remaining = self._open_until - time.time()
                return max(0, remaining)
            return 0

    def get_status(self) -> Dict[str, Any]:
        """
        获取熔断器状态。

        Returns:
            包含熔断状态信息的字典
        """
        with self._lock:
            remaining = 0
            if self._is_open:
                remaining = max(0, self._open_until - time.time())
                # 检查是否应该自动恢复
                if remaining <= 0:
                    self._is_open = False
                    self._open_until = 0

            return {
                'purpose': self._purpose,
                'is_open': self._is_open and remaining > 0,
                'remaining_seconds': round(remaining, 1),
                'open_until_utc': (
                    datetime.fromtimestamp(
                        self._open_until,
                        tz=timezone.utc
                    ).isoformat()
                    if self._is_open and remaining > 0 else None
                ),
                'trip_count': self._trip_count,
                'last_trip_time_utc': (
                    datetime.fromtimestamp(
                        self._last_trip_time,
                        tz=timezone.utc
                    ).isoformat()
                    if self._last_trip_time else None
                ),
                'last_trip_reason': self._last_trip_reason
            }


# 全局熔断器实例（按用途）
_breakers: Dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_breaker(purpose: str) -> Optional[CircuitBreaker]:
    """
    获取指定用途的熔断器。

    Args:
        purpose: 熔断器用途标识

    Returns:
        CircuitBreaker 实例或 None
    """
    with _breakers_lock:
        return _breakers.get(purpose)


def register_breaker(breaker: CircuitBreaker) -> None:
    """
    注册熔断器。

    Args:
        breaker: CircuitBreaker 实例
    """
    with _breakers_lock:
        _breakers[breaker.purpose] = breaker
        logger.info(f'🔌 注册熔断器: {breaker.purpose}')


def get_all_breakers() -> Dict[str, CircuitBreaker]:
    """
    获取所有已注册的熔断器。

    Returns:
        {purpose: CircuitBreaker} 字典
    """
    with _breakers_lock:
        return dict(_breakers)
