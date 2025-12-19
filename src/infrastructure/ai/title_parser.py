"""
AI 标题解析器模块。

实现 ITitleParser 接口，使用 AI 解析动漫标题。
"""

import json
import logging
from typing import Optional

from src.core.exceptions import (
    AICircuitBreakerError,
    AIKeyExhaustedError,
    AIResponseParseError,
)
from src.core.interfaces.adapters import ITitleParser, TitleParseResult

from .api_client import OpenAIClient
from .circuit_breaker import CircuitBreaker
from .key_pool import KeyPool
from .prompts import TITLE_PARSE_SYSTEM_PROMPT
from .schemas import TITLE_PARSE_RESPONSE_FORMAT

logger = logging.getLogger(__name__)


class AITitleParser(ITitleParser):
    """
    AI 标题解析器。

    实现 ITitleParser 接口，使用 OpenAI API 解析动漫标题。
    集成 KeyPool 和 CircuitBreaker 进行限流和熔断保护。

    Example:
        >>> parser = AITitleParser(key_pool, circuit_breaker)
        >>> result = parser.parse('[字幕组] 动漫名称 - 01 [1080p]')
        >>> if result:
        ...     print(result.clean_title)
    """

    def __init__(
        self,
        key_pool: KeyPool,
        circuit_breaker: CircuitBreaker,
        api_client: Optional[OpenAIClient] = None,
        max_retries: int = 3
    ):
        """
        初始化标题解析器。

        Args:
            key_pool: API Key 池
            circuit_breaker: 熔断器
            api_client: API 客户端（可选，默认创建新实例）
            max_retries: 最大重试次数
        """
        self._key_pool = key_pool
        self._circuit_breaker = circuit_breaker
        self._api_client = api_client or OpenAIClient(timeout=30)
        self._max_retries = max_retries

    def parse(self, title: str) -> Optional[TitleParseResult]:
        """
        解析动漫标题。

        Args:
            title: 原始标题字符串

        Returns:
            TitleParseResult: 解析成功时返回结果
            None: 解析失败时返回 None

        Raises:
            AICircuitBreakerError: 熔断器已开启
            AIKeyExhaustedError: 没有可用的 API Key
        """
        # 检查熔断器
        if self._circuit_breaker.is_open():
            remaining = self._circuit_breaker.get_remaining_seconds()
            logger.warning(
                f'🔴 [{self._key_pool.purpose}] 熔断器已开启，'
                f'剩余 {remaining:.0f}s'
            )
            raise AICircuitBreakerError(
                message='熔断器已开启',
                remaining_seconds=remaining
            )

        logger.info(f'🤖 开始解析标题: {title[:50]}...')

        for attempt in range(self._max_retries):
            # 预留 Key
            reservation = self._key_pool.reserve()
            if not reservation:
                logger.error(f'❌ [{self._key_pool.purpose}] 没有可用的 API Key')
                raise AIKeyExhaustedError(
                    message='没有可用的 API Key',
                    code='AI_KEY_EXHAUSTED'
                )

            logger.debug(
                f'🔑 尝试 {attempt + 1}/{self._max_retries}: '
                f'使用 Key {reservation.key_id}'
            )

            # 调用 API
            response = self._api_client.call(
                base_url=reservation.base_url,
                api_key=reservation.api_key,
                model=reservation.model,
                messages=[
                    {'role': 'system', 'content': TITLE_PARSE_SYSTEM_PROMPT},
                    {'role': 'user', 'content': title}
                ],
                response_format=TITLE_PARSE_RESPONSE_FORMAT
            )

            if response.success:
                # 报告成功
                self._key_pool.report_success(
                    reservation.key_id,
                    response_time_ms=response.response_time_ms
                )

                # 解析响应
                result = self._parse_response(response.content, title)
                if result:
                    logger.info(
                        f'✅ 标题解析成功: {result.clean_title} '
                        f'({response.response_time_ms}ms)'
                    )
                    return result
                else:
                    logger.warning(
                        f'⚠️ 响应解析失败，尝试重试'
                    )
                    continue
            else:
                # 报告错误
                is_rate_limit = response.error_code == 429
                retry_after = None
                if is_rate_limit:
                    # 尝试从错误消息中提取 retry-after
                    retry_after = self._extract_retry_after(response.error_message)

                self._key_pool.report_error(
                    reservation.key_id,
                    response.error_message or 'Unknown error',
                    is_rate_limit=is_rate_limit,
                    retry_after=retry_after
                )

                # 检查是否需要触发熔断
                pool_status = self._key_pool.get_status()
                if pool_status['all_in_long_cooling']:
                    self._circuit_breaker.trip(
                        reason='所有 Key 都在长冷却中'
                    )
                    raise AICircuitBreakerError(
                        message='所有 Key 都已冷却，触发熔断',
                        remaining_seconds=self._circuit_breaker.get_remaining_seconds()
                    )

        logger.error(f'❌ 标题解析失败: 重试 {self._max_retries} 次后仍失败')
        return None

    def _parse_response(
        self,
        content: Optional[str],
        original_title: str
    ) -> Optional[TitleParseResult]:
        """
        解析 AI 响应内容。

        Args:
            content: AI 响应内容
            original_title: 原始标题（用于回退）

        Returns:
            TitleParseResult 或 None
        """
        if not content:
            return None

        try:
            # 清理 markdown 代码块
            cleaned = content.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            return TitleParseResult(
                original_title=data.get('original_title', original_title),
                clean_title=data.get('anime_clean_title', ''),
                full_title=data.get('anime_full_title'),
                subtitle_group=data.get('subtitle_group_name', ''),
                season=int(data.get('season', 1)),
                episode=data.get('episode'),
                category=data.get('category', 'tv'),
                quality_info={
                    'quality': data.get('quality', ''),
                    'codec': data.get('codec', ''),
                    'source': data.get('source', '')
                }
            )

        except json.JSONDecodeError as e:
            logger.error(f'❌ JSON 解析失败: {e}')
            logger.debug(f'响应内容: {content[:500]}')
            return None

        except (KeyError, TypeError, ValueError) as e:
            logger.error(f'❌ 数据提取失败: {e}')
            return None

        except Exception as e:
            logger.exception(f'❌ 响应解析未预期错误: {e}')
            return None

    def _extract_retry_after(self, error_message: Optional[str]) -> Optional[float]:
        """
        从错误消息中提取 retry-after 时间。

        Args:
            error_message: 错误消息

        Returns:
            重试等待时间（秒）或 None
        """
        if not error_message:
            return None

        import re

        # 尝试匹配常见的 retry-after 格式
        patterns = [
            r'retry.?after[:\s]+(\d+(?:\.\d+)?)\s*(?:s|seconds?)?',
            r'wait[:\s]+(\d+(?:\.\d+)?)\s*(?:s|seconds?)?',
            r'(\d+(?:\.\d+)?)\s*(?:s|seconds?)\s*(?:before|until)',
        ]

        for pattern in patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return None
