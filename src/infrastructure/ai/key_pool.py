"""
API Key 池管理器模块。

提供 API Key 的管理和轮询功能，包括：
- Round-robin 轮询策略
- RPM/RPD 限制检查
- 三级冷却机制（30s → 60s → 180s）
- 错误类型区分（限流、禁用、临时错误）
- 滑动窗口错误统计
- 线程安全操作
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class KeyState(Enum):
    """
    Key 状态枚举。

    Attributes:
        AVAILABLE: 可用
        COOLING: 短冷却（单次错误）
        LONG_COOLING: 长冷却（多次连续错误）
        DISABLED: 已禁用（需要手动启用）
    """
    AVAILABLE = 'available'
    COOLING = 'cooling'
    LONG_COOLING = 'long_cooling'
    DISABLED = 'disabled'


class ErrorType(Enum):
    """
    API 错误类型枚举。

    用于区分不同类型的错误，以便采取不同的处理策略。
    """
    # 需要禁用 Key 的错误（可能被 ban）
    INVALID_KEY = 'invalid_key'          # 400: 格式错误
    PERMISSION_DENIED = 'permission_denied'  # 403: 权限不足
    NOT_FOUND = 'not_found'              # 404: 资源不存在

    # 限流错误（服务正常，只是超限）
    RATE_LIMITED = 'rate_limited'        # 429: 超过速率限制

    # 服务端错误（临时问题）
    SERVER_ERROR = 'server_error'        # 500: 服务器内部错误
    SERVICE_UNAVAILABLE = 'service_unavailable'  # 503: 服务不可用
    TIMEOUT = 'timeout'                  # 504: 超时

    # 其他未知错误
    UNKNOWN = 'unknown'

    @classmethod
    def from_status_code(cls, status_code: int) -> 'ErrorType':
        """
        根据 HTTP 状态码判断错误类型。

        Args:
            status_code: HTTP 状态码

        Returns:
            对应的 ErrorType
        """
        mapping = {
            400: cls.INVALID_KEY,
            403: cls.PERMISSION_DENIED,
            404: cls.NOT_FOUND,
            429: cls.RATE_LIMITED,
            500: cls.SERVER_ERROR,
            503: cls.SERVICE_UNAVAILABLE,
            504: cls.TIMEOUT,
        }
        return mapping.get(status_code, cls.UNKNOWN)

    def should_disable_key(self) -> bool:
        """判断此错误类型是否应该禁用 Key。"""
        return self in (
            ErrorType.INVALID_KEY,
            ErrorType.PERMISSION_DENIED,
            ErrorType.NOT_FOUND,
        )

    def is_rate_limit(self) -> bool:
        """判断是否为限流错误。"""
        return self == ErrorType.RATE_LIMITED

    def is_server_error(self) -> bool:
        """判断是否为服务端错误。"""
        return self in (
            ErrorType.SERVER_ERROR,
            ErrorType.SERVICE_UNAVAILABLE,
            ErrorType.TIMEOUT,
        )


@dataclass
class KeyUsage:
    """
    Key 使用统计数据类。

    Attributes:
        rpm_count: 每分钟请求数
        rpm_window_start: RPM 窗口开始时间戳
        rpd_count: 每日请求数
        rpd_date: RPD 日期（YYYY-MM-DD）
        error_count: 连续错误次数
        last_error: 最近错误消息
        last_error_type: 最近错误类型
        last_success_time: 最近成功时间戳
        last_response_time_ms: 最近响应时间（毫秒）
        cooldown_until: 冷却结束时间戳
        disabled: 是否被禁用
        disabled_reason: 禁用原因
        disabled_at: 禁用时间
        error_history: 滑动窗口内的错误时间戳
    """
    rpm_count: int = 0
    rpm_window_start: float = 0
    rpd_count: int = 0
    rpd_date: str = ''
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_type: Optional[ErrorType] = None
    last_success_time: Optional[float] = None
    last_response_time_ms: Optional[int] = None
    cooldown_until: float = 0
    disabled: bool = False
    disabled_reason: Optional[str] = None
    disabled_at: Optional[float] = None
    error_history: deque = field(default_factory=lambda: deque(maxlen=20))


@dataclass
class KeySpec:
    """
    Key 配置规格数据类。

    Attributes:
        key_id: Key 唯一标识（如 key1, key2）
        name: Key 显示名称
        api_key: API Key 值
        base_url: API 基础 URL
        model: 默认模型名称
        rpm_limit: 每分钟请求限制（0 表示无限制）
        rpd_limit: 每日请求限制（0 表示无限制）
        enabled: 是否启用
    """
    key_id: str
    name: str
    api_key: str
    base_url: str
    model: str
    rpm_limit: int = 0
    rpd_limit: int = 0
    enabled: bool = True


@dataclass
class KeyReservation:
    """
    Key 预留结果数据类。

    当成功预留一个 Key 时返回此对象，包含调用 API 所需的信息。

    Attributes:
        key_id: Key 唯一标识
        api_key: API Key 值
        base_url: API 基础 URL
        model: 模型名称
    """
    key_id: str
    api_key: str
    base_url: str
    model: str


class KeyPool:
    """
    API Key 池管理器。

    管理多个 API Key，提供 Round-robin 轮询、限流检查、冷却机制等功能。
    线程安全。

    冷却机制：
    - 限流冷却 (RATE_LIMIT_COOLDOWN): 10 秒，429 错误触发
    - 短冷却 (SHORT_COOLDOWN): 30 秒，单次一般错误触发
    - 长冷却 (LONG_COOLDOWN_LEVELS): [60, 120, 180] 秒，连续错误递增

    错误处理：
    - 400/403/404: 禁用 Key（可能被 ban），需手动解除
    - 429: 限流冷却，服务正常
    - 500/503/504: 服务端错误，正常冷却

    RPM 智能等待：
    - 当所有 Key 都达到 RPM 限制时，自动等待最短时间后重试
    - 可配置最大等待时间

    Example:
        >>> pool = KeyPool('title_parse')
        >>> pool.configure([
        ...     KeySpec(
        ...         key_id='key1',
        ...         name='Primary Key',
        ...         api_key='sk-xxx',
        ...         base_url='https://api.openai.com/v1',
        ...         model='gpt-4',
        ...         rpm_limit=60,
        ...         rpd_limit=1000
        ...     )
        ... ])
        >>> reservation = pool.reserve()
        >>> if reservation:
        ...     # 使用 reservation.api_key 调用 API
        ...     pool.report_success(reservation.key_id)
    """

    # 冷却时间常量（秒）
    RATE_LIMIT_COOLDOWN = 10   # 429 限流：短冷却
    SHORT_COOLDOWN = 30        # 一般错误
    LONG_COOLDOWN_LEVELS = [60, 120, 180]  # 连续错误递增
    MAX_CONSECUTIVE_ERRORS = 3

    # 滑动窗口配置
    ERROR_WINDOW_SECONDS = 300  # 5 分钟窗口
    ERROR_THRESHOLD_IN_WINDOW = 5  # 窗口内 5 次错误触发长冷却

    # RPM 智能等待配置
    RPM_MAX_WAIT_SECONDS = 65  # RPM 最大等待时间（略大于 60 秒窗口）
    RPM_WAIT_BUFFER = 1.0     # 等待时额外缓冲时间（秒）

    # RPD 智能等待配置
    RPD_MAX_WAIT_SECONDS = 86400  # RPD 最大等待时间（24小时）
    RPD_WAIT_ENABLED = True       # 是否启用 RPD 等待（默认启用）

    def __init__(self, purpose: str):
        """
        初始化 Key Pool。

        Args:
            purpose: Key Pool 用途标识（如 'title_parse', 'multi_file_rename'）
        """
        self._purpose = purpose
        self._keys: Dict[str, KeySpec] = {}
        self._usage: Dict[str, KeyUsage] = {}
        self._lock = threading.Lock()
        self._rr_index = 0
        self._on_key_disabled: Optional[Callable[[str, str, str], None]] = None

    @property
    def purpose(self) -> str:
        """获取 Key Pool 用途标识。"""
        return self._purpose

    def set_on_key_disabled_callback(
        self,
        callback: Callable[[str, str, str], None]
    ) -> None:
        """
        设置 Key 禁用回调。

        Args:
            callback: 回调函数，参数为 (key_id, key_name, reason)
        """
        self._on_key_disabled = callback

    def configure(self, keys: List[KeySpec]) -> None:
        """
        配置 Key 池。

        Args:
            keys: Key 配置列表

        Note:
            只有 enabled=True 的 Key 会被添加到池中。
            已存在的 Key 使用统计会被保留。
        """
        with self._lock:
            self._keys = {k.key_id: k for k in keys if k.enabled}
            for key_id in self._keys:
                if key_id not in self._usage:
                    self._usage[key_id] = KeyUsage()
            logger.info(
                f'🔑 [{self._purpose}] 配置了 {len(self._keys)} 个 API Key'
            )

    def reserve(
        self,
        wait_for_rpm: bool = True,
        wait_for_rpd: bool = False
    ) -> Optional[KeyReservation]:
        """
        预留一个可用的 Key。

        使用 Round-robin 策略从可用 Key 中选择一个。
        当所有 Key 都达到 RPM/RPD 限制时，可自动等待后重试。

        Args:
            wait_for_rpm: 当所有 Key 达到 RPM 限制时是否等待（默认 True）
            wait_for_rpd: 当所有 Key 达到 RPD 限制时是否等待（默认 False，因为可能很长）

        Returns:
            KeyReservation: 成功时返回预留信息
            None: 没有可用 Key 时返回 None
        """
        result = self._try_reserve()
        if result is not None:
            return result

        # 如果没有可用 Key，检查是否可以等待
        wait_info = self._calculate_wait_time()

        if wait_info:
            reason = wait_info.get('reason')
            wait_seconds = wait_info.get('wait_seconds', 0)

            if reason == 'rpm_limit' and wait_for_rpm:
                if wait_seconds <= self.RPM_MAX_WAIT_SECONDS:
                    logger.info(
                        f'⏳ [{self._purpose}] 所有 Key 达到 RPM 限制，'
                        f'等待 {wait_seconds:.1f}s 后重试...'
                    )
                    time.sleep(wait_seconds)
                    return self._try_reserve()
                else:
                    logger.warning(
                        f'⚠️ [{self._purpose}] RPM 等待时间 {wait_seconds:.1f}s '
                        f'超过最大限制 {self.RPM_MAX_WAIT_SECONDS}s'
                    )

            elif reason == 'rpd_limit' and wait_for_rpd and self.RPD_WAIT_ENABLED:
                if wait_seconds <= self.RPD_MAX_WAIT_SECONDS:
                    hours = wait_seconds / 3600
                    logger.info(
                        f'⏳ [{self._purpose}] 所有 Key 达到 RPD 限制，'
                        f'等待 {hours:.1f}h 后重试（UTC 0点重置）...'
                    )
                    time.sleep(wait_seconds)
                    return self._try_reserve()
                else:
                    logger.warning(
                        f'⚠️ [{self._purpose}] RPD 等待时间超过最大限制'
                    )

        return None

    def _try_reserve(self) -> Optional[KeyReservation]:
        """
        尝试预留一个可用的 Key（内部方法）。

        Returns:
            KeyReservation: 成功时返回预留信息
            None: 没有可用 Key 时返回 None
        """
        with self._lock:
            now = time.time()
            available_keys = []

            for key_id, spec in self._keys.items():
                if not spec.enabled:
                    continue

                usage = self._usage.get(key_id, KeyUsage())

                # 检查是否被禁用
                if usage.disabled:
                    continue

                # 检查冷却
                if usage.cooldown_until > now:
                    continue

                # 检查 RPM
                if spec.rpm_limit > 0:
                    if usage.rpm_window_start + 60 < now:
                        # 重置窗口
                        usage.rpm_count = 0
                        usage.rpm_window_start = now
                    if usage.rpm_count >= spec.rpm_limit:
                        continue

                # 检查 RPD
                if spec.rpd_limit > 0:
                    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                    if usage.rpd_date != today:
                        usage.rpd_count = 0
                        usage.rpd_date = today
                    if usage.rpd_count >= spec.rpd_limit:
                        continue

                available_keys.append(key_id)

            if not available_keys:
                logger.debug(f'⚠️ [{self._purpose}] 当前没有可用的 API Key')
                return None

            # Round-robin 选择
            self._rr_index = self._rr_index % len(available_keys)
            selected_key_id = available_keys[self._rr_index]
            self._rr_index += 1

            spec = self._keys[selected_key_id]
            usage = self._usage[selected_key_id]

            # 更新使用计数
            usage.rpm_count += 1
            usage.rpd_count += 1

            logger.debug(
                f'🔑 [{self._purpose}] 预留 Key: {spec.name} '
                f'(RPM: {usage.rpm_count}/{spec.rpm_limit or "∞"}, '
                f'RPD: {usage.rpd_count}/{spec.rpd_limit or "∞"})'
            )

            return KeyReservation(
                key_id=selected_key_id,
                api_key=spec.api_key,
                base_url=spec.base_url,
                model=spec.model
            )

    def _calculate_wait_time(self) -> Optional[Dict[str, Any]]:
        """
        计算等待时间（RPM 或 RPD）。

        优先返回 RPM 等待（因为更短），如果没有 RPM 问题则检查 RPD。

        Returns:
            包含等待信息的字典，如果无法等待则返回 None
            {
                'wait_seconds': float,  # 需要等待的秒数
                'reason': str,          # 'rpm_limit' 或 'rpd_limit'
                'key_id': str,          # 最快可用的 Key ID
            }
        """
        with self._lock:
            now = time.time()
            rpm_min_wait = float('inf')
            rpm_min_wait_key_id = None
            rpd_wait_seconds = None

            # 统计不可用原因
            rpm_blocked_count = 0
            rpd_blocked_count = 0
            cooling_count = 0
            disabled_count = 0
            total_enabled = 0

            for key_id, spec in self._keys.items():
                if not spec.enabled:
                    continue

                total_enabled += 1
                usage = self._usage.get(key_id, KeyUsage())

                # 检查禁用状态
                if usage.disabled:
                    disabled_count += 1
                    continue

                # 检查冷却
                if usage.cooldown_until > now:
                    cooling_count += 1
                    continue

                # 检查 RPD（先检查）
                if spec.rpd_limit > 0:
                    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                    if usage.rpd_date == today and usage.rpd_count >= spec.rpd_limit:
                        rpd_blocked_count += 1
                        continue

                # 检查 RPM
                if spec.rpm_limit > 0:
                    window_end = usage.rpm_window_start + 60
                    if window_end > now and usage.rpm_count >= spec.rpm_limit:
                        # 计算此 Key 的 RPM 窗口重置等待时间
                        wait_time = window_end - now + self.RPM_WAIT_BUFFER
                        if wait_time < rpm_min_wait:
                            rpm_min_wait = wait_time
                            rpm_min_wait_key_id = key_id
                        rpm_blocked_count += 1
                        continue

            # 优先返回 RPM 等待（因为更短）
            if rpm_blocked_count > 0 and rpm_min_wait_key_id is not None:
                # 如果有 Key 只是被 RPM 限制（不是 RPD）
                if rpm_blocked_count > 0:
                    return {
                        'wait_seconds': rpm_min_wait,
                        'reason': 'rpm_limit',
                        'key_id': rpm_min_wait_key_id,
                        'rpm_blocked': rpm_blocked_count,
                        'rpd_blocked': rpd_blocked_count,
                        'cooling': cooling_count,
                        'disabled': disabled_count,
                    }

            # 如果所有启用的 Key 都被 RPD 限制
            if rpd_blocked_count > 0 and rpd_blocked_count == (
                total_enabled - cooling_count - disabled_count
            ):
                # 计算到 UTC 第二天 0 点的等待时间
                rpd_wait_seconds = self._calculate_seconds_until_utc_midnight()
                return {
                    'wait_seconds': rpd_wait_seconds,
                    'reason': 'rpd_limit',
                    'key_id': None,
                    'rpm_blocked': rpm_blocked_count,
                    'rpd_blocked': rpd_blocked_count,
                    'cooling': cooling_count,
                    'disabled': disabled_count,
                }

            return None

    def _calculate_seconds_until_utc_midnight(self) -> float:
        """
        计算到 UTC 第二天 0 点的秒数。

        Returns:
            距离 UTC 午夜的秒数
        """
        now_utc = datetime.now(timezone.utc)
        tomorrow_utc = now_utc.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        return (tomorrow_utc - now_utc).total_seconds()

    def report_success(
        self,
        key_id: str,
        response_time_ms: Optional[int] = None
    ) -> None:
        """
        报告请求成功。

        成功后重置连续错误计数。

        Args:
            key_id: Key 唯一标识
            response_time_ms: 响应时间（毫秒）
        """
        with self._lock:
            if key_id in self._usage:
                usage = self._usage[key_id]
                usage.error_count = 0
                usage.last_success_time = time.time()
                usage.last_error = None
                usage.last_error_type = None
                if response_time_ms is not None:
                    usage.last_response_time_ms = response_time_ms
                logger.debug(
                    f'✅ [{self._purpose}] Key {key_id} 请求成功'
                )

    def report_error(
        self,
        key_id: str,
        error_message: str,
        status_code: Optional[int] = None,
        error_type: Optional[ErrorType] = None,
        retry_after: Optional[float] = None
    ) -> None:
        """
        报告请求错误。

        根据错误类型采取不同的处理策略：
        - 400/403/404: 禁用 Key
        - 429: 限流冷却
        - 500/503/504: 服务端错误冷却
        - 其他: 一般错误冷却

        Args:
            key_id: Key 唯一标识
            error_message: 错误消息
            status_code: HTTP 状态码
            error_type: 错误类型（优先使用）
            retry_after: 限流时的重试等待时间（秒）
        """
        with self._lock:
            if key_id not in self._usage:
                return

            usage = self._usage[key_id]
            now = time.time()

            # 确定错误类型
            if error_type is None and status_code is not None:
                error_type = ErrorType.from_status_code(status_code)
            elif error_type is None:
                error_type = ErrorType.UNKNOWN

            usage.error_count += 1
            usage.last_error = error_message[:200]
            usage.last_error_type = error_type

            # 记录错误到滑动窗口
            usage.error_history.append(now)

            # 清理过期的错误记录
            window_start = now - self.ERROR_WINDOW_SECONDS
            while usage.error_history and usage.error_history[0] < window_start:
                usage.error_history.popleft()

            key_name = self._keys.get(key_id, KeySpec(
                key_id=key_id, name=key_id, api_key='', base_url='', model=''
            )).name

            # 根据错误类型处理
            if error_type.should_disable_key():
                # 禁用 Key
                self._disable_key(key_id, f'{error_type.value}: {error_message}')
                return

            # 计算冷却时间
            if error_type.is_rate_limit():
                # 限流错误
                cooldown = retry_after if retry_after else self.RATE_LIMIT_COOLDOWN
                logger.info(
                    f'⏱️ [{self._purpose}] Key {key_name} 限流冷却 {cooldown}s'
                )
            elif self._should_long_cooldown(usage):
                # 达到长冷却条件
                level_index = min(
                    usage.error_count - self.MAX_CONSECUTIVE_ERRORS,
                    len(self.LONG_COOLDOWN_LEVELS) - 1
                )
                level_index = max(0, level_index)
                cooldown = self.LONG_COOLDOWN_LEVELS[level_index]
                logger.warning(
                    f'🔴 [{self._purpose}] Key {key_name} 长冷却 {cooldown}s '
                    f'(连续错误: {usage.error_count}, '
                    f'窗口内错误: {len(usage.error_history)})'
                )
            else:
                # 短冷却
                cooldown = self.SHORT_COOLDOWN
                logger.warning(
                    f'🟡 [{self._purpose}] Key {key_name} 短冷却 {cooldown}s '
                    f'(连续错误: {usage.error_count})'
                )

            usage.cooldown_until = now + cooldown

    def _should_long_cooldown(self, usage: KeyUsage) -> bool:
        """
        判断是否应该进入长冷却。

        条件：
        1. 连续错误次数 >= MAX_CONSECUTIVE_ERRORS
        2. 或者滑动窗口内错误次数 >= ERROR_THRESHOLD_IN_WINDOW

        Args:
            usage: Key 使用统计

        Returns:
            是否应该长冷却
        """
        if usage.error_count >= self.MAX_CONSECUTIVE_ERRORS:
            return True
        if len(usage.error_history) >= self.ERROR_THRESHOLD_IN_WINDOW:
            return True
        return False

    def _disable_key(self, key_id: str, reason: str) -> None:
        """
        禁用 Key。

        Args:
            key_id: Key 唯一标识
            reason: 禁用原因
        """
        if key_id not in self._usage:
            return

        usage = self._usage[key_id]
        usage.disabled = True
        usage.disabled_reason = reason
        usage.disabled_at = time.time()

        key_name = self._keys.get(key_id, KeySpec(
            key_id=key_id, name=key_id, api_key='', base_url='', model=''
        )).name

        logger.error(
            f'🚫 [{self._purpose}] Key {key_name} 已禁用: {reason}'
        )

        # 触发回调
        if self._on_key_disabled:
            try:
                self._on_key_disabled(key_id, key_name, reason)
            except Exception as e:
                logger.error(f'Key 禁用回调失败: {e}')

    def enable_key(self, key_id: str) -> bool:
        """
        手动启用已禁用的 Key。

        Args:
            key_id: Key 唯一标识

        Returns:
            bool: 是否成功启用
        """
        with self._lock:
            if key_id not in self._usage:
                return False

            usage = self._usage[key_id]
            if not usage.disabled:
                return False

            usage.disabled = False
            usage.disabled_reason = None
            usage.disabled_at = None
            usage.error_count = 0
            usage.cooldown_until = 0
            usage.error_history.clear()

            key_name = self._keys.get(key_id, KeySpec(
                key_id=key_id, name=key_id, api_key='', base_url='', model=''
            )).name

            logger.info(f'✅ [{self._purpose}] Key {key_name} 已重新启用')
            return True

    def reset_cooldown(self, key_id: str) -> bool:
        """
        手动重置 Key 冷却。

        Args:
            key_id: Key 唯一标识

        Returns:
            bool: 是否成功重置
        """
        with self._lock:
            if key_id in self._usage:
                self._usage[key_id].cooldown_until = 0
                self._usage[key_id].error_count = 0
                self._usage[key_id].error_history.clear()
                key_name = self._keys.get(key_id, KeySpec(
                    key_id=key_id, name=key_id, api_key='', base_url='', model=''
                )).name
                logger.info(f'🔄 [{self._purpose}] Key {key_name} 冷却已重置')
                return True
            return False

    def reset_rpm(self, key_id: str) -> bool:
        """
        手动重置 Key 的 RPM 计数。

        Args:
            key_id: Key 唯一标识

        Returns:
            bool: 是否成功重置
        """
        with self._lock:
            if key_id in self._usage:
                self._usage[key_id].rpm_count = 0
                self._usage[key_id].rpm_window_start = 0
                key_name = self._keys.get(key_id, KeySpec(
                    key_id=key_id, name=key_id, api_key='', base_url='', model=''
                )).name
                logger.info(f'🔄 [{self._purpose}] Key {key_name} RPM 计数已重置')
                return True
            return False

    def reset_rpd(self, key_id: str) -> bool:
        """
        手动重置 Key 的 RPD 计数。

        Args:
            key_id: Key 唯一标识

        Returns:
            bool: 是否成功重置
        """
        with self._lock:
            if key_id in self._usage:
                self._usage[key_id].rpd_count = 0
                self._usage[key_id].rpd_date = ''
                key_name = self._keys.get(key_id, KeySpec(
                    key_id=key_id, name=key_id, api_key='', base_url='', model=''
                )).name
                logger.info(f'🔄 [{self._purpose}] Key {key_name} RPD 计数已重置')
                return True
            return False

    def reset_all_limits(self, key_id: str) -> bool:
        """
        手动重置 Key 的所有限制（冷却、RPM、RPD）。

        Args:
            key_id: Key 唯一标识

        Returns:
            bool: 是否成功重置
        """
        with self._lock:
            if key_id in self._usage:
                usage = self._usage[key_id]
                usage.cooldown_until = 0
                usage.error_count = 0
                usage.error_history.clear()
                usage.rpm_count = 0
                usage.rpm_window_start = 0
                usage.rpd_count = 0
                usage.rpd_date = ''
                key_name = self._keys.get(key_id, KeySpec(
                    key_id=key_id, name=key_id, api_key='', base_url='', model=''
                )).name
                logger.info(f'🔄 [{self._purpose}] Key {key_name} 所有限制已重置')
                return True
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        获取 Key Pool 完整状态。

        Returns:
            包含所有 Key 状态、可用数量等信息的字典
        """
        with self._lock:
            now = time.time()
            keys_status = []

            for key_id, spec in self._keys.items():
                usage = self._usage.get(key_id, KeyUsage())
                cooldown_remaining = max(0, usage.cooldown_until - now)

                # 判断状态
                if usage.disabled:
                    state = KeyState.DISABLED
                elif cooldown_remaining > 0:
                    if usage.error_count >= self.MAX_CONSECUTIVE_ERRORS:
                        state = KeyState.LONG_COOLING
                    else:
                        state = KeyState.COOLING
                else:
                    state = KeyState.AVAILABLE

                # 计算 RPM 窗口剩余时间
                rpm_window_remaining = 0
                rpm_blocked = False
                if spec.rpm_limit > 0 and usage.rpm_count >= spec.rpm_limit:
                    window_end = usage.rpm_window_start + 60
                    if window_end > now:
                        rpm_window_remaining = window_end - now
                        rpm_blocked = True

                # 计算 RPD 是否达到限制
                rpd_blocked = False
                if spec.rpd_limit > 0:
                    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                    if usage.rpd_date == today and usage.rpd_count >= spec.rpd_limit:
                        rpd_blocked = True

                keys_status.append({
                    'key_id': key_id,
                    'name': spec.name,
                    'state': state.value,
                    'rpm_count': usage.rpm_count,
                    'rpm_limit': spec.rpm_limit,
                    'rpm_blocked': rpm_blocked,
                    'rpm_window_remaining_seconds': round(rpm_window_remaining, 1),
                    'rpd_count': usage.rpd_count,
                    'rpd_limit': spec.rpd_limit,
                    'rpd_blocked': rpd_blocked,
                    'error_count': usage.error_count,
                    'errors_in_window': len(usage.error_history),
                    'last_error': usage.last_error,
                    'last_error_type': (
                        usage.last_error_type.value
                        if usage.last_error_type else None
                    ),
                    'last_response_time_ms': usage.last_response_time_ms,
                    'cooldown_remaining_seconds': round(cooldown_remaining, 1),
                    'cooldown_until_utc': (
                        datetime.fromtimestamp(
                            usage.cooldown_until,
                            tz=timezone.utc
                        ).isoformat()
                        if cooldown_remaining > 0 else None
                    ),
                    'disabled': usage.disabled,
                    'disabled_reason': usage.disabled_reason,
                    'disabled_at_utc': (
                        datetime.fromtimestamp(
                            usage.disabled_at,
                            tz=timezone.utc
                        ).isoformat()
                        if usage.disabled_at else None
                    ),
                })

            # 检查是否所有 Key 都不可用（长冷却或禁用）
            all_unavailable = all(
                k['state'] in (KeyState.LONG_COOLING.value, KeyState.DISABLED.value)
                for k in keys_status
            ) if keys_status else False

            available_count = sum(
                1 for k in keys_status
                if k['state'] == KeyState.AVAILABLE.value
            )

            disabled_count = sum(
                1 for k in keys_status
                if k['state'] == KeyState.DISABLED.value
            )

            rpm_blocked_count = sum(
                1 for k in keys_status
                if k['rpm_blocked']
            )

            rpd_blocked_count = sum(
                1 for k in keys_status
                if k['rpd_blocked']
            )

            return {
                'purpose': self._purpose,
                'keys': keys_status,
                'total_count': len(keys_status),
                'available_count': available_count,
                'disabled_count': disabled_count,
                'rpm_blocked_count': rpm_blocked_count,
                'rpd_blocked_count': rpd_blocked_count,
                'all_in_long_cooling': all_unavailable,
            }


# 全局 Key Pool 实例（按用途）
_pools: Dict[str, KeyPool] = {}
_pools_lock = threading.Lock()


def get_pool(purpose: str) -> Optional[KeyPool]:
    """
    获取指定用途的 Key Pool。

    Args:
        purpose: Key Pool 用途标识

    Returns:
        KeyPool 实例或 None
    """
    with _pools_lock:
        return _pools.get(purpose)


def register_pool(pool: KeyPool) -> None:
    """
    注册 Key Pool。

    Args:
        pool: KeyPool 实例
    """
    with _pools_lock:
        _pools[pool.purpose] = pool
        logger.info(f'🔑 注册 Key Pool: {pool.purpose}')


def get_all_pools() -> Dict[str, KeyPool]:
    """
    获取所有已注册的 Key Pool。

    Returns:
        {purpose: KeyPool} 字典
    """
    with _pools_lock:
        return dict(_pools)
