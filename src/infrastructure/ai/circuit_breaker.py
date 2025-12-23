"""
熔断器模块。

提供服务熔断功能，当服务出现大量错误时自动熔断，
保护系统免受级联故障影响。

支持三种状态：
- CLOSED（关闭）: 正常状态，允许请求通过
- OPEN（开启）: 熔断状态，拒绝所有请求
- HALF_OPEN（半开）: 探测状态，允许少量请求探测服务是否恢复
"""

import logging
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BreakerState(Enum):
    """
    熔断器状态枚举。

    Attributes:
        CLOSED: 关闭状态（正常）
        OPEN: 开启状态（熔断中）
        HALF_OPEN: 半开状态（探测中）
    """
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


class CircuitBreaker:
    """
    熔断器。

    当服务出现大量错误时自动熔断，防止继续调用失败的服务。
    支持三种状态和探测恢复机制。

    状态转换:
    - CLOSED → OPEN: 错误率超过阈值或手动触发
    - OPEN → HALF_OPEN: 熔断超时后自动转换
    - HALF_OPEN → CLOSED: 探测请求成功
    - HALF_OPEN → OPEN: 探测请求失败

    Example:
        >>> breaker = CircuitBreaker('title_parse')
        >>> if breaker.allow_request():
        ...     try:
        ...         # 调用 API...
        ...         breaker.report_success()
        ...     except Exception as e:
        ...         breaker.report_failure(str(e))
        ... else:
        ...     raise AICircuitBreakerError('熔断器已开启')
    """

    # 默认配置
    DEFAULT_OPEN_DURATION = 300       # 熔断持续时间（秒）
    DEFAULT_HALF_OPEN_MAX_PROBES = 3  # 半开状态最大探测请求数
    DEFAULT_SUCCESS_THRESHOLD = 2     # 探测成功阈值（成功几次后恢复）

    def __init__(
        self,
        purpose: str,
        open_duration: Optional[float] = None,
        half_open_max_probes: Optional[int] = None,
        success_threshold: Optional[int] = None
    ):
        """
        初始化熔断器。

        Args:
            purpose: 熔断器用途标识（如 'title_parse', 'multi_file_rename'）
            open_duration: 熔断持续时间（秒）
            half_open_max_probes: 半开状态最大探测请求数
            success_threshold: 探测成功阈值
        """
        self._purpose = purpose
        self._open_duration = open_duration or self.DEFAULT_OPEN_DURATION
        self._half_open_max_probes = (
            half_open_max_probes or self.DEFAULT_HALF_OPEN_MAX_PROBES
        )
        self._success_threshold = success_threshold or self.DEFAULT_SUCCESS_THRESHOLD

        # 状态
        self._state = BreakerState.CLOSED
        self._open_until: float = 0
        self._trip_count: int = 0
        self._last_trip_time: Optional[float] = None
        self._last_trip_reason: Optional[str] = None

        # 半开状态计数
        self._probe_count: int = 0
        self._probe_success_count: int = 0
        self._probe_failure_count: int = 0

        self._lock = threading.Lock()

    @property
    def purpose(self) -> str:
        """获取熔断器用途标识。"""
        return self._purpose

    @property
    def state(self) -> BreakerState:
        """获取当前状态（会检查是否需要状态转换）。"""
        with self._lock:
            self._check_state_transition()
            return self._state

    def allow_request(self) -> bool:
        """
        检查是否允许请求通过。

        Returns:
            bool: True 表示允许请求，False 表示拒绝
        """
        with self._lock:
            self._check_state_transition()

            if self._state == BreakerState.CLOSED:
                return True

            if self._state == BreakerState.OPEN:
                return False

            if self._state == BreakerState.HALF_OPEN:
                # 半开状态，检查是否还有探测配额
                if self._probe_count < self._half_open_max_probes:
                    self._probe_count += 1
                    logger.info(
                        f'🔍 [{self._purpose}] 探测请求 '
                        f'{self._probe_count}/{self._half_open_max_probes}'
                    )
                    return True
                else:
                    # 探测配额用完，等待结果
                    return False

            return False

    def report_success(self) -> None:
        """
        报告请求成功。

        在半开状态下，成功的请求会累积，达到阈值后恢复正常。
        """
        with self._lock:
            if self._state == BreakerState.HALF_OPEN:
                self._probe_success_count += 1
                logger.info(
                    f'✅ [{self._purpose}] 探测成功 '
                    f'{self._probe_success_count}/{self._success_threshold}'
                )

                if self._probe_success_count >= self._success_threshold:
                    self._transition_to_closed()

    def report_failure(self, reason: Optional[str] = None) -> None:
        """
        报告请求失败。

        在半开状态下，任何失败都会导致重新熔断。

        Args:
            reason: 失败原因
        """
        with self._lock:
            if self._state == BreakerState.HALF_OPEN:
                self._probe_failure_count += 1
                logger.warning(
                    f'❌ [{self._purpose}] 探测失败，重新熔断'
                )
                self._transition_to_open(reason or '探测请求失败')

    def trip(
        self,
        duration: Optional[float] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        手动触发熔断。

        Args:
            duration: 熔断持续时间（秒），默认使用配置值
            reason: 熔断原因
        """
        with self._lock:
            self._do_trip(duration, reason)

    def _do_trip(
        self,
        duration: Optional[float] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        内部触发熔断（不加锁）。

        Args:
            duration: 熔断持续时间（秒）
            reason: 熔断原因
        """
        duration = duration or self._open_duration
        self._state = BreakerState.OPEN
        self._open_until = time.time() + duration
        self._trip_count += 1
        self._last_trip_time = time.time()
        self._last_trip_reason = reason

        # 重置探测计数
        self._probe_count = 0
        self._probe_success_count = 0
        self._probe_failure_count = 0

        logger.error(
            f'🔴 [{self._purpose}] 熔断器已触发，持续 {duration}s'
            + (f'，原因: {reason}' if reason else '')
        )

    def reset(self) -> None:
        """
        手动重置熔断器。

        将熔断器状态强制恢复到 CLOSED。
        """
        with self._lock:
            was_open = self._state != BreakerState.CLOSED
            self._transition_to_closed()
            if was_open:
                logger.info(f'🟢 [{self._purpose}] 熔断器已手动重置')

    def _check_state_transition(self) -> None:
        """
        检查是否需要状态转换（不加锁）。

        OPEN → HALF_OPEN: 当熔断时间结束时
        """
        if self._state == BreakerState.OPEN:
            if time.time() >= self._open_until:
                self._transition_to_half_open()

    def _transition_to_open(self, reason: Optional[str] = None) -> None:
        """
        转换到 OPEN 状态（不加锁）。

        Args:
            reason: 熔断原因
        """
        self._do_trip(reason=reason)

    def _transition_to_half_open(self) -> None:
        """
        转换到 HALF_OPEN 状态（不加锁）。
        """
        self._state = BreakerState.HALF_OPEN
        self._probe_count = 0
        self._probe_success_count = 0
        self._probe_failure_count = 0
        logger.info(f'🟡 [{self._purpose}] 熔断器进入半开状态，开始探测')

    def _transition_to_closed(self) -> None:
        """
        转换到 CLOSED 状态（不加锁）。
        """
        self._state = BreakerState.CLOSED
        self._open_until = 0
        self._probe_count = 0
        self._probe_success_count = 0
        self._probe_failure_count = 0
        logger.info(f'🟢 [{self._purpose}] 熔断器已恢复正常')

    def is_open(self) -> bool:
        """
        检查熔断器是否处于熔断状态。

        注意：HALF_OPEN 状态也返回 True，因为服务仍不稳定。

        Returns:
            bool: True 表示熔断中或探测中，False 表示正常
        """
        with self._lock:
            self._check_state_transition()
            return self._state != BreakerState.CLOSED

    def get_remaining_seconds(self) -> float:
        """
        获取熔断剩余时间。

        Returns:
            float: 剩余秒数，如果未熔断则返回 0
        """
        with self._lock:
            if self._state == BreakerState.OPEN:
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
            self._check_state_transition()

            remaining = 0
            if self._state == BreakerState.OPEN:
                remaining = max(0, self._open_until - time.time())

            return {
                'purpose': self._purpose,
                'state': self._state.value,
                'is_open': self._state != BreakerState.CLOSED,
                'remaining_seconds': round(remaining, 1),
                'open_until_utc': (
                    datetime.fromtimestamp(
                        self._open_until,
                        tz=timezone.utc
                    ).isoformat()
                    if self._state == BreakerState.OPEN else None
                ),
                'trip_count': self._trip_count,
                'last_trip_time_utc': (
                    datetime.fromtimestamp(
                        self._last_trip_time,
                        tz=timezone.utc
                    ).isoformat()
                    if self._last_trip_time else None
                ),
                'last_trip_reason': self._last_trip_reason,
                # 半开状态信息
                'probe_count': self._probe_count,
                'probe_success_count': self._probe_success_count,
                'probe_failure_count': self._probe_failure_count,
                'half_open_max_probes': self._half_open_max_probes,
                'success_threshold': self._success_threshold,
            }


# 全局熔断器实例（按用途）
_breakers: Dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()

# 命名熔断器注册表（与命名 Key Pool 对应）
_named_breakers: Dict[str, CircuitBreaker] = {}


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


def register_named_breaker(breaker: CircuitBreaker, pool_name: str) -> None:
    """
    注册命名熔断器（与命名 Key Pool 对应）。

    Args:
        breaker: CircuitBreaker 实例
        pool_name: Pool 唯一名称
    """
    with _breakers_lock:
        _named_breakers[pool_name] = breaker
        logger.info(f'🔌 注册命名熔断器: {pool_name}')


def get_named_breaker(pool_name: str) -> Optional[CircuitBreaker]:
    """
    获取指定名称的命名熔断器。

    Args:
        pool_name: Pool 名称

    Returns:
        CircuitBreaker 实例或 None
    """
    with _breakers_lock:
        return _named_breakers.get(pool_name)


def get_all_named_breakers() -> Dict[str, CircuitBreaker]:
    """
    获取所有已注册的命名熔断器。

    Returns:
        {pool_name: CircuitBreaker} 字典
    """
    with _breakers_lock:
        return dict(_named_breakers)


def get_breaker_for_purpose(purpose: str) -> Optional[CircuitBreaker]:
    """
    获取任务用途对应的熔断器。

    优先查找绑定的命名熔断器（通过 key_pool 的 purpose-to-pool 映射），
    如果没有则回退到用途熔断器。

    Args:
        purpose: 任务用途标识

    Returns:
        CircuitBreaker 实例或 None
    """
    # 导入在函数内部避免循环引用
    from src.infrastructure.ai.key_pool import _purpose_to_pool, _pools_lock

    with _breakers_lock:
        # 优先查找绑定的命名熔断器
        with _pools_lock:
            pool_name = _purpose_to_pool.get(purpose)

        if pool_name:
            breaker = _named_breakers.get(pool_name)
            if breaker:
                return breaker
            else:
                logger.warning(
                    f'⚠️ 任务 {purpose} 绑定的熔断器 "{pool_name}" 不存在，回退到独立配置'
                )

        # 回退到用途熔断器
        return _breakers.get(purpose)


def get_breakers_grouped_by_name() -> Dict[str, Dict[str, Any]]:
    """
    获取按 Pool 名称分组的熔断器信息（用于 UI 显示）。

    Returns:
        {
            'MiMo': {
                'breaker': CircuitBreaker 实例,
                'pool_name': 'MiMo',
                'tasks': ['title_parse', 'multi_file_rename', 'subtitle_match']
            },
            ...
        }
    """
    # 导入在函数内部避免循环引用
    from src.infrastructure.ai.key_pool import _purpose_to_pool, _pools_lock

    with _breakers_lock:
        result = {}

        # 1. 处理命名熔断器（可能被多个任务共享）
        for pool_name, breaker in _named_breakers.items():
            with _pools_lock:
                tasks = [
                    purpose for purpose, bound_pool_name in _purpose_to_pool.items()
                    if bound_pool_name == pool_name
                ]
            result[pool_name] = {
                'breaker': breaker,
                'pool_name': pool_name,
                'tasks': tasks
            }

        # 2. 处理独立熔断器（没有绑定到命名 Pool 的任务）
        # 收集所有命名熔断器的实例，用于排重
        named_breaker_instances = set(id(b) for b in _named_breakers.values())

        with _pools_lock:
            for purpose, breaker in _breakers.items():
                # 跳过已经在命名熔断器中的实例
                if id(breaker) in named_breaker_instances:
                    continue

                is_bound = purpose in _purpose_to_pool
                if not is_bound:
                    standalone_key = f'standalone_{purpose}'
                    result[standalone_key] = {
                        'breaker': breaker,
                        'pool_name': None,
                        'tasks': [purpose]
                    }

        return result


def clear_all_breaker_registries() -> None:
    """
    清空所有熔断器注册表（用于测试或重新初始化）。
    """
    with _breakers_lock:
        _breakers.clear()
        _named_breakers.clear()
        logger.info('🧹 已清空所有熔断器注册表')
