"""
AI 字幕匹配器模块。

使用 AI 将字幕文件与影片文件进行智能匹配。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.exceptions import (
    AICircuitBreakerError,
    AIKeyExhaustedError,
)
from src.infrastructure.repositories.ai_key_repository import ai_key_repository
from src.services.ai_debug_service import ai_debug_service

from .api_client import OpenAIClient
from .circuit_breaker import CircuitBreaker
from .key_pool import KeyPool
from .prompts import SUBTITLE_MATCH_PROMPT
from .schemas import SUBTITLE_MATCH_RESPONSE_FORMAT

logger = logging.getLogger(__name__)


@dataclass
class SubtitleMatch:
    """字幕匹配结果项"""
    video_file: str
    subtitle_file: str
    language_tag: str
    new_name: str


@dataclass
class MatchResult:
    """完整匹配结果"""
    matches: List[SubtitleMatch] = field(default_factory=list)
    unmatched_subtitles: List[str] = field(default_factory=list)
    videos_without_subtitle: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'matches': [
                {
                    'video_file': m.video_file,
                    'subtitle_file': m.subtitle_file,
                    'language_tag': m.language_tag,
                    'new_name': m.new_name
                }
                for m in self.matches
            ],
            'unmatched_subtitles': self.unmatched_subtitles,
            'videos_without_subtitle': self.videos_without_subtitle
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MatchResult':
        """从字典创建"""
        matches = [
            SubtitleMatch(
                video_file=m['video_file'],
                subtitle_file=m['subtitle_file'],
                language_tag=m['language_tag'],
                new_name=m['new_name']
            )
            for m in data.get('matches', [])
        ]
        return cls(
            matches=matches,
            unmatched_subtitles=data.get('unmatched_subtitles', []),
            videos_without_subtitle=data.get('videos_without_subtitle', [])
        )


class AISubtitleMatcher:
    """
    AI 字幕匹配器。

    使用 OpenAI API 智能匹配影片文件和字幕文件。

    Example:
        >>> matcher = AISubtitleMatcher(key_pool, circuit_breaker)
        >>> result = matcher.match_subtitles(
        ...     video_files=['Season 1/Anime - S01E01.mkv'],
        ...     subtitle_files=['01.chs.ass', '01.cht.ass']
        ... )
        >>> if result:
        ...     for match in result.matches:
        ...         print(f'{match.subtitle_file} -> {match.new_name}')
    """

    def __init__(
        self,
        key_pool: KeyPool,
        circuit_breaker: CircuitBreaker,
        api_client: Optional[OpenAIClient] = None,
        max_retries: int = 3
    ):
        """
        初始化字幕匹配器。

        Args:
            key_pool: API Key 池
            circuit_breaker: 熔断器
            api_client: API 客户端（可选，默认创建新实例）
            max_retries: 最大重试次数
        """
        self._key_pool = key_pool
        self._circuit_breaker = circuit_breaker
        self._api_client = api_client or OpenAIClient(timeout=180)
        self._max_retries = max_retries

    def match_subtitles(
        self,
        video_files: List[str],
        subtitle_files: List[str],
        anime_title: Optional[str] = None
    ) -> Optional[MatchResult]:
        """
        匹配影片文件和字幕文件。

        Args:
            video_files: 影片文件名列表（包含路径）
            subtitle_files: 字幕文件名列表
            anime_title: 动漫标题（用于上下文）

        Returns:
            MatchResult: 匹配结果
            None: 处理失败

        Raises:
            AICircuitBreakerError: 熔断器已开启
            AIKeyExhaustedError: 没有可用的 API Key
        """
        if not video_files or not subtitle_files:
            logger.warning('📭 没有文件需要匹配')
            return MatchResult()

        # 检查熔断器是否允许请求
        if not self._circuit_breaker.allow_request():
            remaining = self._circuit_breaker.get_remaining_seconds()
            state = self._circuit_breaker.state.value
            logger.warning(
                f'🔴 [{self._key_pool.purpose}] 熔断器状态: {state}，'
                f'剩余 {remaining:.0f}s'
            )
            raise AICircuitBreakerError(
                message=f'熔断器状态: {state}',
                remaining_seconds=remaining
            )

        logger.info(
            f'🤖 开始匹配 {len(subtitle_files)} 个字幕文件到 '
            f'{len(video_files)} 个影片文件'
        )

        return self._call_ai(
            video_files=video_files,
            subtitle_files=subtitle_files,
            anime_title=anime_title
        )

    def _call_ai(
        self,
        video_files: List[str],
        subtitle_files: List[str],
        anime_title: Optional[str] = None
    ) -> Optional[MatchResult]:
        """
        调用 AI API 进行字幕匹配。

        Args:
            video_files: 影片文件列表
            subtitle_files: 字幕文件列表
            anime_title: 动漫标题

        Returns:
            MatchResult: 匹配结果
            None: 处理失败
        """
        import time

        # 构建用户消息
        user_message = self._build_user_message(
            video_files=video_files,
            subtitle_files=subtitle_files,
            anime_title=anime_title
        )

        # 重试循环
        for attempt in range(self._max_retries):
            reservation = None
            try:
                # 获取可用的 API Key
                reservation = self._key_pool.reserve(
                    wait_for_rpm=True,
                    wait_for_rpd=False
                )

                if reservation is None:
                    logger.error(f'❌ [{self._key_pool.purpose}] 没有可用的 API Key')
                    raise AIKeyExhaustedError(
                        message='所有 API Key 都不可用',
                        purpose=self._key_pool.purpose
                    )

                logger.debug(
                    f'🔑 尝试 {attempt + 1}/{self._max_retries}: '
                    f'使用 Key {reservation.key_id}'
                )

                # 解析 extra_body
                extra_params = self._parse_extra_body(reservation.extra_body)

                # 构建消息
                messages = [
                    {'role': 'system', 'content': SUBTITLE_MATCH_PROMPT},
                    {'role': 'user', 'content': user_message}
                ]

                # 调用 AI API
                response = self._api_client.call(
                    base_url=reservation.base_url,
                    api_key=reservation.api_key,
                    model=reservation.model,
                    messages=messages,
                    response_format=SUBTITLE_MATCH_RESPONSE_FORMAT,
                    extra_params=extra_params
                )

                if response.success:
                    # 报告成功给 Key Pool
                    self._key_pool.report_success(
                        reservation.key_id,
                        response_time_ms=response.response_time_ms
                    )

                    # 报告成功给熔断器
                    self._circuit_breaker.report_success()

                    # 获取 Key 信息和当前 RPM/RPD 计数
                    pool_status = self._key_pool.get_status()
                    key_info = next(
                        (k for k in pool_status.get('keys', [])
                         if k['key_id'] == reservation.key_id),
                        {}
                    )

                    # 解析响应
                    result = self._parse_response(response.content)

                    # 记录到数据库
                    ai_key_repository.log_usage(
                        purpose=self._key_pool.purpose,
                        key_id=reservation.key_id,
                        key_name=key_info.get('name', ''),
                        model=reservation.model,
                        anime_title=anime_title,
                        context_summary=f'匹配 {len(subtitle_files)} 个字幕',
                        success=True,
                        response_time_ms=response.response_time_ms,
                        rpm_at_call=key_info.get('rpm_count', 0),
                        rpd_at_call=key_info.get('rpd_count', 0)
                    )

                    # 记录 AI 调试日志
                    if ai_debug_service.enabled:
                        ai_debug_service.log_ai_interaction(
                            operation='subtitle_match',
                            input_data={
                                'video_files': video_files,
                                'subtitle_files': subtitle_files,
                                'anime_title': anime_title,
                                'base_url': reservation.base_url,
                                'extra_params': extra_params,
                            },
                            output_data=response.content,
                            model=reservation.model,
                            response_time_ms=response.response_time_ms,
                            key_id=reservation.key_id,
                            success=True
                        )

                    logger.info(
                        f'✅ 字幕匹配完成: {len(result.matches)} 个匹配，'
                        f'{len(result.unmatched_subtitles)} 个未匹配 '
                        f'({response.response_time_ms}ms)'
                    )
                    return result

                else:
                    # API 返回错误
                    error_message = response.error_message or 'Unknown error'
                    retry_after = None
                    if response.error_code == 429:
                        retry_after = self._extract_retry_after(error_message)

                    self._key_pool.report_error(
                        reservation.key_id,
                        error_message,
                        status_code=response.error_code,
                        retry_after=retry_after
                    )

                    # 报告失败给熔断器
                    self._circuit_breaker.report_failure(error_message)

                    # 获取 Key 信息
                    pool_status = self._key_pool.get_status()
                    key_info = next(
                        (k for k in pool_status.get('keys', [])
                         if k['key_id'] == reservation.key_id),
                        {}
                    )

                    # 记录失败日志
                    ai_key_repository.log_usage(
                        purpose=self._key_pool.purpose,
                        key_id=reservation.key_id,
                        key_name=key_info.get('name', ''),
                        model=reservation.model,
                        anime_title=anime_title,
                        context_summary=f'匹配 {len(subtitle_files)} 个字幕',
                        success=False,
                        error_code=response.error_code,
                        error_message=error_message[:500],
                        response_time_ms=response.response_time_ms,
                        rpm_at_call=key_info.get('rpm_count', 0),
                        rpd_at_call=key_info.get('rpd_count', 0)
                    )

                    # 记录 AI 调试日志（失败）
                    if ai_debug_service.enabled:
                        ai_debug_service.log_ai_interaction(
                            operation='subtitle_match',
                            input_data={
                                'video_files': video_files,
                                'subtitle_files': subtitle_files,
                                'anime_title': anime_title,
                                'base_url': reservation.base_url,
                                'extra_params': extra_params,
                            },
                            output_data=None,
                            model=reservation.model,
                            response_time_ms=response.response_time_ms,
                            key_id=reservation.key_id,
                            success=False,
                            error_message=error_message
                        )

                    # 检查是否需要触发熔断
                    if pool_status['all_in_long_cooling']:
                        self._circuit_breaker.trip(
                            reason='所有 Key 都不可用（长冷却或已禁用）'
                        )
                        raise AICircuitBreakerError(
                            message='所有 Key 都不可用',
                            remaining_seconds=self._circuit_breaker.get_remaining_seconds()
                        )

                    logger.warning(
                        f'⚠️ 字幕匹配失败 (attempt {attempt + 1}): '
                        f'{response.error_code} - {error_message}'
                    )

            except AIKeyExhaustedError:
                raise

            except AICircuitBreakerError:
                raise

            except Exception as e:
                logger.error(f'❌ 字幕匹配异常 (attempt {attempt + 1}): {e}')

                # 如果有 reservation，报告错误
                if reservation:
                    error_message = str(e)
                    status_code = getattr(e, 'status_code', 500)

                    self._key_pool.report_error(
                        reservation.key_id,
                        error_message,
                        status_code=status_code
                    )
                    self._circuit_breaker.report_failure(error_message)

                    # 获取 Key 信息
                    pool_status = self._key_pool.get_status()
                    key_info = next(
                        (k for k in pool_status.get('keys', [])
                         if k['key_id'] == reservation.key_id),
                        {}
                    )

                    # 记录失败日志
                    ai_key_repository.log_usage(
                        purpose=self._key_pool.purpose,
                        key_id=reservation.key_id,
                        key_name=key_info.get('name', ''),
                        model=reservation.model,
                        anime_title=anime_title,
                        context_summary=f'匹配 {len(subtitle_files)} 个字幕',
                        success=False,
                        error_code=status_code,
                        error_message=error_message[:500],
                        rpm_at_call=key_info.get('rpm_count', 0),
                        rpd_at_call=key_info.get('rpd_count', 0)
                    )

            # 重试前等待
            if attempt < self._max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f'⏳ 等待 {wait_time}s 后重试... (attempt {attempt + 2}/{self._max_retries})')
                time.sleep(wait_time)

        logger.error(f'❌ 字幕匹配在 {self._max_retries} 次尝试后失败')
        return None

    def _parse_extra_body(self, extra_body: str) -> Optional[Dict[str, Any]]:
        """解析 extra_body JSON 字符串"""
        if not extra_body:
            return None
        try:
            return json.loads(extra_body)
        except json.JSONDecodeError:
            return None

    def _extract_retry_after(self, error_message: str) -> Optional[float]:
        """从错误消息中提取 retry-after 时间"""
        import re
        # 尝试匹配常见的 retry-after 格式
        patterns = [
            r'retry.?after[:\s]+(\d+(?:\.\d+)?)',
            r'wait[:\s]+(\d+(?:\.\d+)?)\s*s',
            r'(\d+(?:\.\d+)?)\s*seconds?',
        ]
        for pattern in patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def _build_user_message(
        self,
        video_files: List[str],
        subtitle_files: List[str],
        anime_title: Optional[str] = None
    ) -> str:
        """构建发送给 AI 的用户消息"""
        data = {
            'video_files': video_files,
            'subtitle_files': subtitle_files
        }

        if anime_title:
            data['anime_title'] = anime_title

        return json.dumps(data, ensure_ascii=False, indent=2)

    def _parse_response(self, response: str) -> MatchResult:
        """解析 AI 响应"""
        try:
            data = json.loads(response)
            return MatchResult.from_dict(data)
        except json.JSONDecodeError as e:
            logger.error(f'❌ 解析 AI 响应失败: {e}')
            logger.debug(f'原始响应: {response[:500]}...')
            return MatchResult()
