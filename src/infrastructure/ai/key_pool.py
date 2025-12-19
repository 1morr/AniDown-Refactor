"""
API Key 池管理器模块。

提供 API Key 的管理和轮询功能，包括：
- Round-robin 轮询策略
- RPM/RPD 限制检查
- 三级冷却机制（30s → 60s → 180s → 300s）
- 线程安全操作
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KeyState(Enum):
    """
    Key 状态枚举。

    Attributes:
        AVAILABLE: 可用
        COOLING: 短冷却（单次错误）
        LONG_COOLING: 长冷却（多次连续错误）
    """
    AVAILABLE = 'available'
    COOLING = 'cooling'
    LONG_COOLING = 'long_cooling'


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
        last_success_time: 最近成功时间戳
        last_response_time_ms: 最近响应时间（毫秒）
        cooldown_until: 冷却结束时间戳
    """
    rpm_count: int = 0
    rpm_window_start: float = 0
    rpd_count: int = 0
    rpd_date: str = ''
    error_count: int = 0
    last_error: Optional[str] = None
    last_success_time: Optional[float] = None
    last_response_time_ms: Optional[int] = None
    cooldown_until: float = 0


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
    - 短冷却 (SHORT_COOLDOWN): 30 秒，单次错误触发
    - 长冷却 (LONG_COOLDOWN_LEVELS): [60, 180, 300] 秒，连续错误递增

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
    SHORT_COOLDOWN = 30
    LONG_COOLDOWN_LEVELS = [60, 180, 300]
    MAX_CONSECUTIVE_ERRORS = 3

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

    @property
    def purpose(self) -> str:
        """获取 Key Pool 用途标识。"""
        return self._purpose

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

    def reserve(self) -> Optional[KeyReservation]:
        """
        预留一个可用的 Key。

        使用 Round-robin 策略从可用 Key 中选择一个。

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
                logger.warning(f'⚠️ [{self._purpose}] 没有可用的 API Key')
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
                if response_time_ms is not None:
                    usage.last_response_time_ms = response_time_ms
                logger.debug(
                    f'✅ [{self._purpose}] Key {key_id} 请求成功'
                )

    def report_error(
        self,
        key_id: str,
        error_message: str,
        is_rate_limit: bool = False,
        retry_after: Optional[float] = None
    ) -> None:
        """
        报告请求错误。

        根据错误类型和连续错误次数计算冷却时间。

        Args:
            key_id: Key 唯一标识
            error_message: 错误消息
            is_rate_limit: 是否为限流错误（HTTP 429）
            retry_after: 限流时的重试等待时间（秒）
        """
        with self._lock:
            if key_id not in self._usage:
                return

            usage = self._usage[key_id]
            usage.error_count += 1
            usage.last_error = error_message[:200]

            # 计算冷却时间
            if is_rate_limit and retry_after:
                cooldown = retry_after
            elif usage.error_count >= self.MAX_CONSECUTIVE_ERRORS:
                # 多次连续错误，使用长冷却
                level_index = min(
                    usage.error_count - self.MAX_CONSECUTIVE_ERRORS,
                    len(self.LONG_COOLDOWN_LEVELS) - 1
                )
                cooldown = self.LONG_COOLDOWN_LEVELS[level_index]
            else:
                cooldown = self.SHORT_COOLDOWN

            usage.cooldown_until = time.time() + cooldown

            key_name = self._keys.get(key_id, KeySpec(
                key_id=key_id, name=key_id, api_key='', base_url='', model=''
            )).name

            logger.warning(
                f'⚠️ [{self._purpose}] Key {key_name} 进入冷却 {cooldown}s '
                f'(连续错误: {usage.error_count})'
            )

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
                key_name = self._keys.get(key_id, KeySpec(
                    key_id=key_id, name=key_id, api_key='', base_url='', model=''
                )).name
                logger.info(f'🔄 [{self._purpose}] Key {key_name} 冷却已重置')
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
                if cooldown_remaining > 0:
                    if usage.error_count >= self.MAX_CONSECUTIVE_ERRORS:
                        state = KeyState.LONG_COOLING
                    else:
                        state = KeyState.COOLING
                else:
                    state = KeyState.AVAILABLE

                keys_status.append({
                    'key_id': key_id,
                    'name': spec.name,
                    'state': state.value,
                    'rpm_count': usage.rpm_count,
                    'rpm_limit': spec.rpm_limit,
                    'rpd_count': usage.rpd_count,
                    'rpd_limit': spec.rpd_limit,
                    'error_count': usage.error_count,
                    'last_error': usage.last_error,
                    'last_response_time_ms': usage.last_response_time_ms,
                    'cooldown_remaining_seconds': round(cooldown_remaining, 1),
                    'cooldown_until_utc': (
                        datetime.fromtimestamp(
                            usage.cooldown_until,
                            tz=timezone.utc
                        ).isoformat()
                        if cooldown_remaining > 0 else None
                    )
                })

            # 检查是否所有 Key 都在长冷却中
            all_in_long_cooling = all(
                k['state'] == KeyState.LONG_COOLING.value
                for k in keys_status
            ) if keys_status else False

            available_count = sum(
                1 for k in keys_status
                if k['state'] == KeyState.AVAILABLE.value
            )

            return {
                'purpose': self._purpose,
                'keys': keys_status,
                'total_count': len(keys_status),
                'available_count': available_count,
                'all_in_long_cooling': all_in_long_cooling
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
