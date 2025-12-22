"""
字幕管理服务模块。

提供字幕上传、AI匹配、管理等功能。
"""

import logging
import os
import shutil
import tempfile
import zipfile
from typing import Any, Dict, List, Optional

from src.core.domain.entities import SubtitleRecord
from src.core.exceptions import AICircuitBreakerError, AIKeyExhaustedError
from src.infrastructure.ai.subtitle_matcher import AISubtitleMatcher, MatchResult
from src.infrastructure.repositories.subtitle_repository import SubtitleRepository
from src.infrastructure.repositories.history_repository import HistoryRepository

logger = logging.getLogger(__name__)

# 支持的字幕扩展名
SUBTITLE_EXTENSIONS = {'.ass', '.srt', '.sub', '.ssa', '.vtt', '.idx', '.sup'}

# 支持的视频扩展名
VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts'}

# 支持的压缩档扩展名
ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z', '.tar', '.gz'}


class SubtitleService:
    """字幕管理服务"""

    def __init__(
        self,
        subtitle_repo: SubtitleRepository,
        history_repo: HistoryRepository,
        subtitle_matcher: AISubtitleMatcher
    ):
        """
        初始化字幕服务。

        Args:
            subtitle_repo: 字幕仓库
            history_repo: 历史记录仓库（用于获取硬链接）
            subtitle_matcher: AI字幕匹配器
        """
        self._subtitle_repo = subtitle_repo
        self._history_repo = history_repo
        self._subtitle_matcher = subtitle_matcher

    def get_subtitles_for_anime(self, anime_id: int) -> Dict[str, Any]:
        """
        获取动漫的字幕列表和影片列表。

        Args:
            anime_id: 动漫ID

        Returns:
            包含字幕列表和影片列表的字典
        """
        # 获取已有字幕记录
        subtitles = self._subtitle_repo.get_by_anime_id_as_dict(anime_id)

        # 获取硬链接文件列表（只要视频文件）
        hardlinks = self._history_repo.get_by_anime_id(anime_id)
        video_files = []
        subtitle_count_map = {}

        # 统计每个视频的字幕数量
        for sub in subtitles:
            video_path = sub.get('video_file_path', '')
            subtitle_count_map[video_path] = subtitle_count_map.get(video_path, 0) + 1

        for hl in hardlinks:
            if self._is_video(hl.hardlink_path):
                video_files.append({
                    'path': hl.hardlink_path,
                    'has_subtitle': hl.hardlink_path in subtitle_count_map,
                    'subtitle_count': subtitle_count_map.get(hl.hardlink_path, 0)
                })

        return {
            'subtitles': subtitles,
            'video_files': video_files,
            'total_subtitles': len(subtitles),
            'total_videos': len(video_files)
        }

    def process_subtitle_archive(
        self,
        anime_id: int,
        archive_content: bytes,
        archive_name: str,
        anime_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理上传的字幕压缩档。

        Args:
            anime_id: 动漫ID
            archive_content: 压缩档内容（二进制）
            archive_name: 压缩档文件名
            anime_title: 动漫标题（用于AI上下文）

        Returns:
            处理结果字典
        """
        logger.info(f'🔄 开始处理字幕压缩档: {archive_name}')

        # 1. 获取硬链接文件夹中的影片列表
        hardlinks = self._history_repo.get_by_anime_id(anime_id)
        video_files = [
            hl.hardlink_path
            for hl in hardlinks
            if self._is_video(hl.hardlink_path)
        ]

        if not video_files:
            logger.warning(f'⚠️ 动漫 {anime_id} 没有找到影片文件')
            return {
                'success': False,
                'error': '没有找到影片文件，请先确保动漫已下载并创建硬链接'
            }

        # 2. 解压压缩档到临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(temp_dir, archive_name)

            # 写入压缩档
            with open(archive_path, 'wb') as f:
                f.write(archive_content)

            # 解压并获取字幕文件列表
            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)

            subtitle_files = self._extract_archive(archive_path, extract_dir)

            if not subtitle_files:
                logger.warning(f'⚠️ 压缩档中没有找到字幕文件')
                return {
                    'success': False,
                    'error': '压缩档中没有找到字幕文件（支持格式：.ass, .srt, .sub, .ssa, .vtt）'
                }

            logger.info(f'📁 发现 {len(subtitle_files)} 个字幕文件')

            # 3. 调用AI匹配
            try:
                match_result = self._subtitle_matcher.match_subtitles(
                    video_files=video_files,
                    subtitle_files=list(subtitle_files.keys()),
                    anime_title=anime_title
                )
            except AICircuitBreakerError as e:
                logger.error(f'❌ AI熔断器已开启: {e}')
                return {
                    'success': False,
                    'error': f'AI服务暂时不可用，请稍后重试 (剩余 {e.remaining_seconds:.0f}s)'
                }
            except AIKeyExhaustedError as e:
                logger.error(f'❌ API Key耗尽: {e}')
                return {
                    'success': False,
                    'error': 'API Key额度已用完，请检查配置'
                }

            if match_result is None:
                logger.error('❌ AI匹配失败')
                return {
                    'success': False,
                    'error': 'AI匹配失败，请重试'
                }

            # 4. 执行重命名和复制
            applied_result = self._apply_matches(
                anime_id=anime_id,
                match_result=match_result,
                subtitle_files=subtitle_files,
                archive_name=archive_name
            )

            return applied_result

    def _extract_archive(
        self,
        archive_path: str,
        extract_to: str
    ) -> Dict[str, str]:
        """
        解压压缩档，返回字幕文件映射。

        Args:
            archive_path: 压缩档路径
            extract_to: 解压目标目录

        Returns:
            字典：{字幕文件名: 完整路径}
        """
        subtitle_files = {}
        ext = os.path.splitext(archive_path)[1].lower()

        try:
            if ext == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(extract_to)
            elif ext == '.rar':
                try:
                    import rarfile
                    with rarfile.RarFile(archive_path, 'r') as rf:
                        rf.extractall(extract_to)
                except ImportError:
                    logger.error('❌ 需要安装 rarfile 库来解压 RAR 文件')
                    return {}
            elif ext == '.7z':
                try:
                    import py7zr
                    with py7zr.SevenZipFile(archive_path, 'r') as sz:
                        sz.extractall(extract_to)
                except ImportError:
                    logger.error('❌ 需要安装 py7zr 库来解压 7z 文件')
                    return {}
            elif ext in {'.tar', '.gz'}:
                import tarfile
                with tarfile.open(archive_path, 'r:*') as tf:
                    tf.extractall(extract_to)
            else:
                logger.error(f'❌ 不支持的压缩格式: {ext}')
                return {}

            # 遍历解压目录，找出字幕文件
            for root, dirs, files in os.walk(extract_to):
                for file in files:
                    if self._is_subtitle(file):
                        full_path = os.path.join(root, file)
                        # 使用文件名作为key（不含路径）
                        subtitle_files[file] = full_path

            logger.info(f'✅ 解压成功，发现 {len(subtitle_files)} 个字幕文件')

        except Exception as e:
            logger.error(f'❌ 解压失败: {e}')

        return subtitle_files

    def _apply_matches(
        self,
        anime_id: int,
        match_result: MatchResult,
        subtitle_files: Dict[str, str],
        archive_name: str
    ) -> Dict[str, Any]:
        """
        应用匹配结果：重命名并复制字幕文件。

        Args:
            anime_id: 动漫ID
            match_result: AI匹配结果
            subtitle_files: 字幕文件映射 {文件名: 完整路径}
            archive_name: 来源压缩档名

        Returns:
            处理结果
        """
        applied_matches = []
        failed_matches = []
        saved_records = []

        for match in match_result.matches:
            try:
                # 获取源字幕文件路径
                source_path = subtitle_files.get(match.subtitle_file)
                if not source_path or not os.path.exists(source_path):
                    logger.warning(f'⚠️ 找不到字幕文件: {match.subtitle_file}')
                    failed_matches.append({
                        'subtitle': match.subtitle_file,
                        'reason': '找不到源文件'
                    })
                    continue

                # 获取目标目录（与影片文件相同）
                video_dir = os.path.dirname(match.video_file)
                target_path = os.path.join(video_dir, match.new_name)

                # 创建目标目录（如果不存在）
                os.makedirs(video_dir, exist_ok=True)

                # 复制字幕文件
                shutil.copy2(source_path, target_path)

                logger.info(f'✅ 复制字幕: {match.subtitle_file} -> {target_path}')

                # 获取字幕格式
                subtitle_format = os.path.splitext(match.subtitle_file)[1].lstrip('.')

                # 保存记录到数据库
                record = SubtitleRecord(
                    anime_id=anime_id,
                    video_file_path=match.video_file,
                    subtitle_path=target_path,
                    original_name=match.subtitle_file,
                    language_tag=match.language_tag,
                    subtitle_format=subtitle_format,
                    source_archive=archive_name,
                    match_method='ai'
                )
                record_id = self._subtitle_repo.save(record)
                saved_records.append(record_id)

                applied_matches.append({
                    'video': os.path.basename(match.video_file),
                    'subtitle': match.subtitle_file,
                    'language_tag': match.language_tag,
                    'new_name': match.new_name
                })

            except Exception as e:
                logger.error(f'❌ 处理字幕失败 {match.subtitle_file}: {e}')
                failed_matches.append({
                    'subtitle': match.subtitle_file,
                    'reason': str(e)
                })

        return {
            'success': True,
            'matched': applied_matches,
            'failed': failed_matches,
            'unmatched_subtitles': match_result.unmatched_subtitles,
            'videos_without_subtitle': match_result.videos_without_subtitle,
            'total_matched': len(applied_matches),
            'total_failed': len(failed_matches)
        }

    def delete_subtitle(self, subtitle_id: int, delete_file: bool = True) -> Dict[str, Any]:
        """
        删除字幕记录。

        Args:
            subtitle_id: 字幕记录ID
            delete_file: 是否同时删除文件

        Returns:
            操作结果
        """
        # 获取记录
        record = self._subtitle_repo.get_by_id(subtitle_id)
        if not record:
            return {'success': False, 'error': '字幕记录不存在'}

        # 删除文件
        if delete_file and record.subtitle_path:
            try:
                if os.path.exists(record.subtitle_path):
                    os.remove(record.subtitle_path)
                    logger.info(f'✅ 删除字幕文件: {record.subtitle_path}')
            except Exception as e:
                logger.error(f'❌ 删除字幕文件失败: {e}')

        # 删除数据库记录
        success = self._subtitle_repo.delete(subtitle_id)

        return {
            'success': success,
            'deleted_file': delete_file,
            'subtitle_path': record.subtitle_path
        }

    def _is_video(self, path: str) -> bool:
        """判断是否为视频文件"""
        ext = os.path.splitext(path)[1].lower()
        return ext in VIDEO_EXTENSIONS

    def _is_subtitle(self, path: str) -> bool:
        """判断是否为字幕文件"""
        ext = os.path.splitext(path)[1].lower()
        return ext in SUBTITLE_EXTENSIONS
