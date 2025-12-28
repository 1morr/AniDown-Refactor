"""
AI 文件重命名器模块。

实现 IFileRenamer 接口，使用 AI 生成文件重命名映射。
"""

import json
import logging
from collections import defaultdict
from typing import Any

from src.core.config import config
from src.core.exceptions import (
    AICircuitBreakerError,
    AIKeyExhaustedError,
)
from src.core.interfaces.adapters import IFileRenamer, RenameResult
from src.infrastructure.repositories.ai_key_repository import ai_key_repository
from src.services.ai_debug_service import AIDebugService

from .api_client import OpenAIClient
from .circuit_breaker import CircuitBreaker
from .key_pool import KeyPool
from .prompts import (
    MULTI_FILE_RENAME_STANDARD_PROMPT,
    MULTI_FILE_RENAME_WITH_TVDB_PROMPT,
)
from .schemas import MULTI_FILE_RENAME_RESPONSE_FORMAT

logger = logging.getLogger(__name__)


# 默认批次大小
DEFAULT_BATCH_SIZE = 30


class AIFileRenamer(IFileRenamer):
    """
    AI 文件重命名器。

    实现 IFileRenamer 接口，使用 OpenAI API 生成文件重命名映射。
    支持 TVDB 数据、文件夹结构输入和批量处理。

    Example:
        >>> renamer = AIFileRenamer(key_pool, circuit_breaker)
        >>> result = renamer.generate_rename_mapping(
        ...     files=['[ANi] Title - 01 [1080P].mp4'],
        ...     category='tv',
        ...     anime_title='动漫标题'
        ... )
        >>> if result:
        ...     print(result.main_files)
    """

    # 任务用途标识（用于日志记录，独立于 Pool 名称）
    TASK_PURPOSE = 'multi_file_rename'

    def __init__(
        self,
        key_pool: KeyPool,
        circuit_breaker: CircuitBreaker,
        api_client: OpenAIClient | None = None,
        max_retries: int = 3,
        batch_size: int = DEFAULT_BATCH_SIZE,
        ai_debug_service: AIDebugService | None = None
    ):
        """
        初始化文件重命名器。

        Args:
            key_pool: API Key 池
            circuit_breaker: 熔断器
            api_client: API 客户端（可选，默认创建新实例）
            max_retries: 最大重试次数
            batch_size: 批量处理文件数
            ai_debug_service: AI 调试服务（可选）
        """
        self._key_pool = key_pool
        self._circuit_breaker = circuit_breaker
        self._api_client = api_client or OpenAIClient(timeout=360)
        self._max_retries = max_retries
        self._batch_size = batch_size
        self._ai_debug_service = ai_debug_service

    def generate_rename_mapping(
        self,
        files: list[str],
        category: str,
        anime_title: str | None = None,
        folder_structure: str | None = None,
        tvdb_data: dict[str, Any] | None = None
    ) -> RenameResult | None:
        """
        生成文件重命名映射。

        支持批量处理大文件列表，自动分批调用 AI。

        Args:
            files: 文件名列表
            category: 内容类型 ('tv' 或 'movie')
            anime_title: 动漫标题（用于重命名）
            folder_structure: 文件夹结构信息
            tvdb_data: TVDB 元数据

        Returns:
            RenameResult: 重命名结果
            None: 处理失败

        Raises:
            AICircuitBreakerError: 熔断器已开启
            AIKeyExhaustedError: 没有可用的 API Key
        """
        if not files:
            logger.warning('📭 没有文件需要处理')
            return RenameResult()

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

        logger.info(f'🤖 开始处理 {len(files)} 个文件的重命名')

        # 如果文件数量超过批次大小，分批处理
        if len(files) > self._batch_size:
            return self._process_batches(
                files=files,
                category=category,
                anime_title=anime_title,
                folder_structure=folder_structure,
                tvdb_data=tvdb_data
            )
        else:
            return self._process_single_batch(
                files=files,
                category=category,
                anime_title=anime_title,
                folder_structure=folder_structure,
                tvdb_data=tvdb_data,
                previous_hardlinks=[]
            )

    def _group_files_by_folder(
        self,
        files: list[str]
    ) -> list[tuple[str, list[str]]]:
        """
        按文件夹路径（第二层目录）对文件进行分组。

        将文件按其所属的子文件夹分组，确保同一季度/子文件夹的文件
        被放在一起处理，避免不同季度的文件混在同一批次中。

        Args:
            files: 文件路径列表

        Returns:
            按文件夹分组的列表，每个元素为 (文件夹路径, 文件列表)
        """
        folder_groups: dict[str, list[str]] = defaultdict(list)

        for file_path in files:
            # 解析文件路径，提取第二层目录作为分组键
            # 例如: "[VCB-Studio] selector WIXOSS/[VCB-Studio] selector infected WIXOSS [Ma10p_1080p]/..."
            # 分组键为: "[VCB-Studio] selector WIXOSS/[VCB-Studio] selector infected WIXOSS [Ma10p_1080p]"
            parts = file_path.replace('\\', '/').split('/')

            if len(parts) >= 2:
                # 使用前两层目录作为分组键
                folder_key = '/'.join(parts[:2])
            elif len(parts) == 1:
                # 只有文件名，使用空字符串作为根目录键
                folder_key = ''
            else:
                folder_key = parts[0] if parts else ''

            folder_groups[folder_key].append(file_path)

        # 转换为有序列表，保持文件夹的原始出现顺序
        seen_folders: list[str] = []
        for file_path in files:
            parts = file_path.replace('\\', '/').split('/')
            if len(parts) >= 2:
                folder_key = '/'.join(parts[:2])
            elif len(parts) == 1:
                folder_key = ''
            else:
                folder_key = parts[0] if parts else ''

            if folder_key not in seen_folders:
                seen_folders.append(folder_key)

        result = [(folder, folder_groups[folder]) for folder in seen_folders]

        logger.debug(
            f'📁 文件按文件夹分组: {len(result)} 个文件夹, '
            f'分别有 {[len(g[1]) for g in result]} 个文件'
        )

        return result

    def _process_batches(
        self,
        files: list[str],
        category: str,
        anime_title: str | None,
        folder_structure: str | None,
        tvdb_data: dict[str, Any] | None
    ) -> RenameResult | None:
        """
        分批处理大文件列表。

        先按文件夹分组，再对每个文件夹组内的文件按数量分批。
        确保不同文件夹（如不同季度）的文件不会混在同一批次中。

        Args:
            files: 文件名列表
            category: 内容类型
            anime_title: 动漫标题
            folder_structure: 文件夹结构
            tvdb_data: TVDB 数据

        Returns:
            合并后的 RenameResult 或 None
        """
        merged_result = RenameResult()
        previous_hardlinks: list[str] = []

        # 先按文件夹分组
        folder_groups = self._group_files_by_folder(files)

        # 计算总批次数（用于日志显示）
        total_batches = 0
        for folder_name, folder_files in folder_groups:
            folder_batches = (len(folder_files) + self._batch_size - 1) // self._batch_size
            total_batches += folder_batches

        logger.info(
            f'📊 分批策略: {len(folder_groups)} 个文件夹, '
            f'共 {total_batches} 个批次'
        )

        batch_idx = 0
        for folder_name, folder_files in folder_groups:
            folder_display = folder_name.split('/')[-1] if folder_name else '根目录'
            folder_batch_count = (
                len(folder_files) + self._batch_size - 1
            ) // self._batch_size

            logger.info(
                f'📁 处理文件夹 [{folder_display}]: '
                f'{len(folder_files)} 个文件, {folder_batch_count} 个批次'
            )

            # 对当前文件夹内的文件按数量分批
            for inner_idx in range(folder_batch_count):
                batch_idx += 1
                start = inner_idx * self._batch_size
                end = min(start + self._batch_size, len(folder_files))
                batch_files = folder_files[start:end]

                logger.info(
                    f'🔄 处理批次 {batch_idx}/{total_batches}: '
                    f'{len(batch_files)} 个文件 (来自 {folder_display})'
                )

                batch_result = self._process_single_batch(
                    files=batch_files,
                    category=category,
                    anime_title=anime_title,
                    folder_structure=folder_structure,
                    tvdb_data=tvdb_data,
                    previous_hardlinks=previous_hardlinks
                )

                if batch_result is None:
                    logger.error(f'❌ 批次 {batch_idx} 处理失败')
                    continue

                # 合并结果
                merged_result.main_files.update(batch_result.main_files)
                merged_result.skipped_files.extend(batch_result.skipped_files)

                # 合并季度信息
                for season_key, season_info in batch_result.seasons_info.items():
                    if season_key in merged_result.seasons_info:
                        # 累加集数
                        existing = merged_result.seasons_info[season_key]
                        if isinstance(existing, dict) and isinstance(season_info, dict):
                            existing['count'] = (
                                existing.get('count', 0) + season_info.get('count', 0)
                            )
                    else:
                        merged_result.seasons_info[season_key] = season_info

                # 更新已处理的硬链接列表，用于后续批次冲突检测
                previous_hardlinks.extend(batch_result.main_files.values())

                # 保留最后一批的 patterns
                merged_result.patterns = batch_result.patterns

        if not merged_result.has_files:
            logger.warning('📭 批量处理完成但没有生成任何重命名映射')
            return None

        logger.info(
            f'✅ 批量处理完成: {merged_result.file_count} 个文件映射, '
            f'{merged_result.skipped_count} 个跳过'
        )
        return merged_result

    def _process_single_batch(
        self,
        files: list[str],
        category: str,
        anime_title: str | None,
        folder_structure: str | None,
        tvdb_data: dict[str, Any] | None,
        previous_hardlinks: list[str]
    ) -> RenameResult | None:
        """
        处理单个批次的文件。

        Args:
            files: 文件名列表
            category: 内容类型
            anime_title: 动漫标题
            folder_structure: 文件夹结构
            tvdb_data: TVDB 数据
            previous_hardlinks: 已创建的硬链接列表（用于冲突检测）

        Returns:
            RenameResult 或 None
        """
        # 构建用户消息
        user_message, indexed_files = self._build_user_message(
            files=files,
            category=category,
            anime_title=anime_title,
            folder_structure=folder_structure,
            tvdb_data=tvdb_data,
            previous_hardlinks=previous_hardlinks
        )

        # 选择提示词
        system_prompt = (
            MULTI_FILE_RENAME_WITH_TVDB_PROMPT
            if tvdb_data
            else MULTI_FILE_RENAME_STANDARD_PROMPT
        )

        for attempt in range(self._max_retries):
            # 预留 Key（启用 RPM/RPD 等待）
            reservation = self._key_pool.reserve(
                wait_for_rpm=True,
                wait_for_rpd=True
            )
            if not reservation:
                logger.error(f'❌ [{self._key_pool.purpose}] 没有可用的 API Key')
                raise AIKeyExhaustedError(
                    message='没有可用的 API Key'
                )

            logger.debug(
                f'🔑 尝试 {attempt + 1}/{self._max_retries}: '
                f'使用 Key {reservation.key_id}'
            )

            # 解析 extra_body（从任务配置读取，不是从 pool）
            extra_params = self._parse_extra_body(config.openai.multi_file_rename.extra_body)

            # 获取任务配置的 model（不是从 pool 读取）
            model = config.openai.multi_file_rename.model

            # 调用 API
            response = self._api_client.call(
                base_url=reservation.base_url,
                api_key=reservation.api_key,
                model=model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message}
                ],
                response_format=MULTI_FILE_RENAME_RESPONSE_FORMAT,
                extra_params=extra_params
            )

            if response.success:
                # 报告成功给 Key Pool
                self._key_pool.report_success(
                    reservation.key_id,
                    response_time_ms=response.response_time_ms
                )

                # 报告成功给熔断器（用于半开状态探测）
                self._circuit_breaker.report_success()

                # 获取 Key 信息和当前 RPM/RPD 计数
                pool_status = self._key_pool.get_status()
                key_info = next(
                    (k for k in pool_status.get('keys', []) if k['key_id'] == reservation.key_id),
                    {}
                )

                # 解析响应
                result = self._parse_response(response.content, indexed_files)

                # 记录到数据库
                ai_key_repository.log_usage(
                    purpose=self.TASK_PURPOSE,
                    key_id=reservation.key_id,
                    key_name=key_info.get('name', ''),
                    model=model,
                    anime_title=anime_title or '',
                    context_summary=f'{len(files)} files: {files[0][:50]}...' if files else '',
                    success=True,
                    response_time_ms=response.response_time_ms,
                    rpm_at_call=key_info.get('rpm_count', 0),
                    rpd_at_call=key_info.get('rpd_count', 0),
                )

                # 记录 AI 调试日志
                if self._ai_debug_service and self._ai_debug_service.enabled:
                    self._ai_debug_service.log_ai_interaction(
                        operation='multi_file_rename',
                        input_data={
                            'files': files,
                            'category': category,
                            'anime_title': anime_title,
                            'folder_structure': folder_structure,
                            'tvdb_data': tvdb_data,
                            'previous_hardlinks': previous_hardlinks
                        },
                        output_data=response.content,
                        model=model,
                        response_time_ms=response.response_time_ms,
                        key_id=reservation.key_id,
                        success=True
                    )

                if result:
                    logger.info(
                        f'✅ 文件重命名成功: {result.file_count} 个文件 '
                        f'({response.response_time_ms}ms)'
                    )
                    return result
                else:
                    logger.warning('⚠️ 响应解析失败，尝试重试')
                    continue
            else:
                # 获取 Key 信息和当前 RPM/RPD 计数
                pool_status = self._key_pool.get_status()
                key_info = next(
                    (k for k in pool_status.get('keys', []) if k['key_id'] == reservation.key_id),
                    {}
                )

                # 记录到数据库
                ai_key_repository.log_usage(
                    purpose=self.TASK_PURPOSE,
                    key_id=reservation.key_id,
                    key_name=key_info.get('name', ''),
                    model=model,
                    anime_title=anime_title or '',
                    context_summary=f'{len(files)} files: {files[0][:50]}...' if files else '',
                    success=False,
                    error_code=response.error_code,
                    error_message=response.error_message or 'Unknown error',
                    response_time_ms=response.response_time_ms,
                    rpm_at_call=key_info.get('rpm_count', 0),
                    rpd_at_call=key_info.get('rpd_count', 0),
                )

                # 记录 AI 调试日志（失败）
                if self._ai_debug_service and self._ai_debug_service.enabled:
                    self._ai_debug_service.log_ai_interaction(
                        operation='multi_file_rename',
                        input_data={
                            'files': files,
                            'category': category,
                            'anime_title': anime_title
                        },
                        output_data=None,
                        model=model,
                        response_time_ms=response.response_time_ms,
                        key_id=reservation.key_id,
                        success=False,
                        error_message=response.error_message
                    )

                # 报告错误给 Key Pool（使用状态码区分错误类型）
                retry_after = None
                if response.error_code == 429:
                    retry_after = self._extract_retry_after(response.error_message)

                self._key_pool.report_error(
                    reservation.key_id,
                    response.error_message or 'Unknown error',
                    status_code=response.error_code,
                    retry_after=retry_after
                )

                # 报告失败给熔断器（用于半开状态探测）
                self._circuit_breaker.report_failure(response.error_message)

                # 检查是否需要触发熔断
                if pool_status['all_in_long_cooling']:
                    self._circuit_breaker.trip(
                        reason='所有 Key 都不可用（长冷却或已禁用）'
                    )
                    raise AICircuitBreakerError(
                        message='所有 Key 都不可用，触发熔断',
                        remaining_seconds=self._circuit_breaker.get_remaining_seconds()
                    )

        logger.error(
            f'❌ 文件重命名失败: 重试 {self._max_retries} 次后仍失败'
        )
        return None

    def _build_user_message(
        self,
        files: list[str],
        category: str,
        anime_title: str | None,
        folder_structure: str | None,
        tvdb_data: dict[str, Any] | None,
        previous_hardlinks: list[str]
    ) -> tuple[str, dict[str, str]]:
        """
        构建发送给 AI 的用户消息。

        Args:
            files: 文件列表
            category: 内容类型
            anime_title: 动漫标题
            folder_structure: 文件夹结构
            tvdb_data: TVDB 数据
            previous_hardlinks: 已创建的硬链接

        Returns:
            Tuple[str, Dict[str, str]]: (格式化的用户消息, key到文件路径的映射)
        """
        message_parts = []

        # 基本信息
        message_parts.append(f'**Category**: {category}')

        if anime_title:
            message_parts.append(f'**Anime Title**: {anime_title}')

        # 构建带 key 的文件映射
        indexed_files = {str(i + 1): f for i, f in enumerate(files)}
        files_json = json.dumps({'files': indexed_files}, ensure_ascii=False, indent=2)
        message_parts.append(f'**Files**:\n```json\n{files_json}\n```')

        # 文件夹结构
        if folder_structure:
            message_parts.append(f'**Folder Structure**:\n```\n{folder_structure}\n```')

        # TVDB 数据
        if tvdb_data:
            tvdb_json = json.dumps(tvdb_data, ensure_ascii=False, indent=2)
            message_parts.append(f'**TVDB Data**:\n```json\n{tvdb_json}\n```')

        # 已创建的硬链接（用于批量处理时避免冲突）
        if previous_hardlinks:
            hardlinks_json = json.dumps(
                {'previous_hardlinks': previous_hardlinks},
                ensure_ascii=False,
                indent=2
            )
            message_parts.append(
                f'**Previous Hardlinks**:\n```json\n{hardlinks_json}\n```'
            )

        return '\n\n'.join(message_parts), indexed_files

    def _parse_response(
        self,
        content: str | None,
        indexed_files: dict[str, str]
    ) -> RenameResult | None:
        """
        解析 AI 响应内容。

        Args:
            content: AI 响应内容
            indexed_files: key 到原始文件路径的映射

        Returns:
            RenameResult 或 None
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

            # 将 key 转换回原始文件路径
            main_files_raw = data.get('main_files', {})
            main_files = {}
            for key, new_name in main_files_raw.items():
                original_path = indexed_files.get(key)
                if original_path:
                    main_files[original_path] = new_name
                else:
                    logger.warning(f'⚠️ 未知的文件 key: {key}')

            # 将 skipped_files 的 key 转换回原始文件路径
            skipped_keys = data.get('skipped_files', [])
            skipped_files = []
            for key in skipped_keys:
                original_path = indexed_files.get(key)
                if original_path:
                    skipped_files.append(original_path)
                else:
                    logger.warning(f'⚠️ 未知的跳过文件 key: {key}')

            seasons_info = data.get('seasons_info', {})

            # 构建 patterns 信息
            patterns = {
                'subtitle_group_regex': data.get('subtitle_group_regex', ''),
                'full_title_regex': data.get('full_title_regex', ''),
                'clean_title_regex': data.get('clean_title_regex', ''),
                'episode_regex': data.get('episode_regex', ''),
                'special_tag_regex': data.get('special_tag_regex', ''),
                'quality_regex': data.get('quality_regex', ''),
                'platform_regex': data.get('platform_regex', ''),
                'source_regex': data.get('source_regex', ''),
                'codec_regex': data.get('codec_regex', ''),
                'subtitle_type_regex': data.get('subtitle_type_regex', ''),
                'format_regex': data.get('format_regex', ''),
                'anime_full_title': data.get('anime_full_title', ''),
                'anime_clean_title': data.get('anime_clean_title', ''),
                'subtitle_group_name': data.get('subtitle_group_name', ''),
                'season': data.get('season', 1),
                'category': data.get('category', 'tv'),
                'method': 'ai'
            }

            return RenameResult(
                main_files=main_files,
                skipped_files=skipped_files,
                seasons_info=seasons_info,
                patterns=patterns,
                method='ai'
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

    def _extract_retry_after(self, error_message: str | None) -> float | None:
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

    def _parse_extra_body(self, extra_body: str) -> dict[str, Any] | None:
        """
        解析 extra_body JSON 字符串。

        Args:
            extra_body: JSON 格式的额外参数字符串

        Returns:
            解析后的字典，解析失败或为空则返回 None
        """
        if not extra_body or not extra_body.strip():
            return None

        try:
            parsed = json.loads(extra_body)
            if isinstance(parsed, dict) and parsed:
                logger.debug(f'🔧 使用 extra_body 参数: {list(parsed.keys())}')
                return parsed
            return None
        except json.JSONDecodeError as e:
            logger.warning(f'⚠️ extra_body JSON 解析失败: {e}')
            return None
