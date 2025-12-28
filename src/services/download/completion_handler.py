"""
Torrent completion handling service.

Handles the processing of completed torrent downloads including
renaming and hardlink creation.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from src.core.config import config
from src.core.domain.entities import DownloadRecord
from src.core.domain.value_objects import MediaType
from src.core.interfaces.adapters import IDownloadClient
from src.core.interfaces.repositories import (
    IAnimeRepository,
    IDownloadRepository,
)
from src.services.download.download_notifier import DownloadNotifier
from src.services.file.path_builder import PathBuilder
from src.services.file.file_service import FileService
from src.services.metadata.metadata_service import MetadataService
from src.services.rename.rename_service import RenameService

logger = logging.getLogger(__name__)


class CompletionHandler:
    """
    Torrent completion handling service.

    Handles the post-download processing:
    - File classification
    - Rename mapping generation
    - Hardlink creation
    - Notification sending
    """

    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        download_client: IDownloadClient,
        rename_service: RenameService,
        file_service: FileService,
        path_builder: PathBuilder,
        metadata_service: MetadataService,
        notifier: DownloadNotifier
    ):
        """
        Initialize the completion handler.

        Args:
            anime_repo: Repository for anime information.
            download_repo: Repository for download records.
            download_client: Download client (qBittorrent).
            rename_service: Rename coordination service.
            file_service: File service for hardlink creation.
            path_builder: Path construction service.
            metadata_service: TVDB metadata service.
            notifier: Download notifier service.
        """
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._download_client = download_client
        self._rename_service = rename_service
        self._file_service = file_service
        self._path_builder = path_builder
        self._metadata_service = metadata_service
        self._notifier = notifier

    def handle_completed(
        self,
        hash_id: str,
        webhook_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Handle torrent download completion event.

        Args:
            hash_id: Torrent hash.
            webhook_data: Optional webhook event data.

        Returns:
            Result dictionary with processing details.
        """
        try:
            logger.info('🎉 种子下载完成')
            logger.info(f'  Hash: {hash_id[:8]}...')

            # Send webhook received notification
            if webhook_data:
                torrent_name = webhook_data.get('name', '')
                save_path = webhook_data.get('save_path', '')
                content_path = webhook_data.get('content_path', '')
                self._notifier.notify_webhook_received(
                    torrent_id=hash_id,
                    save_path=save_path,
                    content_path=content_path or save_path,
                    torrent_name=torrent_name
                )

            # Update download status
            completion_time = datetime.now(UTC)
            self._download_repo.update_status(hash_id, 'completed', completion_time)

            # Get download info
            download_info = self._download_repo.get_by_hash(hash_id)
            if not download_info:
                logger.warning(f'未找到下载记录: {hash_id}')
                return {'success': True, 'message': 'Download record not found'}

            logger.info(f'  动漫: {download_info.anime_title or download_info.original_filename}')

            # Get torrent files
            logger.debug('📋 正在获取种子文件列表...')
            torrent_files = self._download_client.get_torrent_files(hash_id)
            hardlink_count = 0

            if torrent_files:
                logger.info(f'  文件数量: {len(torrent_files)}')

                # Create hardlinks
                logger.info('🔗 开始创建硬链接...')
                hardlink_count = self._create_hardlinks(
                    hash_id, download_info, torrent_files
                )

            logger.info(f'✅ 种子处理完成: 成功创建 {hardlink_count} 个硬链接')
            return {
                'success': True,
                'message': 'Torrent completion processed',
                'hardlinks_created': hardlink_count
            }

        except Exception as e:
            logger.error(f'处理种子完成事件失败: {e}')
            # Send error notification to Discord
            self._notifier.notify_error(f'处理种子完成事件失败: {e}')
            # Re-raise exception so caller can get detailed error info
            raise

    def _create_hardlinks(
        self,
        hash_id: str,
        download_info: DownloadRecord,
        torrent_files: list[dict[str, Any]]
    ) -> int:
        """
        Create hardlinks for completed torrent files.

        Args:
            hash_id: Torrent hash.
            download_info: Download record.
            torrent_files: List of torrent files.

        Returns:
            Number of hardlinks created.
        """
        hardlink_count = 0

        try:
            anime_id = download_info.anime_id
            anime_title = download_info.anime_title
            subtitle_group = download_info.subtitle_group
            season = download_info.season
            is_multi_season = download_info.is_multi_season

            # Get media_type from database
            media_type = 'anime'
            if anime_id:
                anime_info = self._anime_repo.get_by_id(anime_id)
                if anime_info:
                    media_type = (
                        'live_action' if anime_info.media_type == MediaType.LIVE_ACTION
                        else 'anime'
                    )

            # Determine category
            category = 'movie' if season == 0 else 'tv'

            # Determine target directory (anime title directory, no Season subdirectory)
            target_dir = self._path_builder.build_library_path(
                title=anime_title,
                media_type=media_type,
                category=category,
                season=None
            )

            # Classify files
            download_directory = (
                download_info.download_directory or
                config.qbittorrent.base_download_path
            )
            video_files, subtitle_files = self._rename_service.classify_files(
                torrent_files, download_directory
            )

            logger.info(f'视频文件: {len(video_files)} 个, 字幕文件: {len(subtitle_files)} 个')

            if not video_files:
                logger.warning('未找到视频文件')
                return 0

            # Get TVDB data and folder structure for manual uploads
            tvdb_data = None
            folder_structure = None
            download_method = download_info.download_method
            requires_tvdb = download_info.requires_tvdb

            if download_method and download_method.value.startswith('manual_'):
                # Get folder structure
                try:
                    folder_structure = self._download_client.get_torrent_folder_structure(
                        hash_id
                    ) if hasattr(self._download_client, 'get_torrent_folder_structure') else None
                    if folder_structure:
                        logger.info(f'📁 获取到Torrent目录结构:\n{folder_structure}')
                except Exception as e:
                    logger.warning(f'⚠️ 获取文件夹结构失败: {e}')

                # Get TVDB data - use requires_tvdb flag from download record
                if requires_tvdb:
                    try:
                        # Get anime_info to check for existing tvdb_id
                        anime_info_record = self._anime_repo.get_by_id(anime_id) if anime_id else None
                        existing_tvdb_id = anime_info_record.tvdb_id if anime_info_record else None

                        if existing_tvdb_id:
                            # Use existing TVDB ID from anime_info
                            logger.info(f'🔍 使用已保存的TVDB ID: {existing_tvdb_id}')
                            tvdb_data = self._metadata_service.get_tvdb_data_by_id(existing_tvdb_id)
                        else:
                            # Auto search by anime title
                            logger.info(f'🔍 自动搜索TVDB数据: {anime_title}')
                            tvdb_data = self._metadata_service.get_tvdb_data_for_anime(anime_title)

                        if tvdb_data:
                            logger.info('✅ 成功获取TVDB数据')
                            # Save TVDB ID to anime_info table if not already saved
                            tvdb_id_from_data = tvdb_data.get('tvdb_id')
                            if tvdb_id_from_data and anime_id and not existing_tvdb_id:
                                self._anime_repo.update_tvdb_id(anime_id, tvdb_id_from_data)
                        else:
                            logger.info('⚠️ 未获取到TVDB数据，将使用AI处理')
                    except Exception as e:
                        logger.warning(f'⚠️ 获取TVDB数据失败: {e}，将使用AI处理')

            # Generate rename mapping
            rename_result = self._rename_service.generate_mapping(
                video_files=video_files,
                anime_id=anime_id,
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                is_multi_season=is_multi_season,
                tvdb_data=tvdb_data,
                folder_structure=folder_structure,
                torrent_hash=hash_id
            )

            if not rename_result or not rename_result.has_files:
                logger.warning('无法生成重命名映射')
                return 0

            logger.info(f'🎯 重命名方案: {rename_result.method}')

            # AI usage notification is sent via RenameService callback, no need to repeat here

            # Collect rename examples (max 3)
            rename_examples = []
            for i, (old_name, new_name) in enumerate(rename_result.main_files.items()):
                if i >= 3:
                    break
                rename_examples.append(f'{old_name} → {new_name}')

            # Create hardlinks for video files
            for video in video_files:
                original_name = video.name
                source_path = video.full_path

                # Check if skipped
                if video.relative_path in rename_result.skipped_files:
                    logger.info(f'⏭️ 跳过非正片文件: {original_name}')
                    continue

                # Check if source exists
                if not os.path.exists(source_path):
                    logger.error(f'✗ 源文件不存在: {source_path}')
                    continue

                # Get new name
                new_name = rename_result.main_files.get(original_name)
                if not new_name:
                    logger.error(f'✗ 未找到重命名映射: {original_name}')
                    continue

                # Create hardlink
                success = self._file_service.create(
                    source_path=source_path,
                    target_dir=target_dir,
                    new_name=new_name,
                    anime_id=anime_id,
                    torrent_hash=hash_id
                )

                if success:
                    hardlink_count += 1
                    logger.info(f'✓ 硬链接创建成功: {new_name}')
                else:
                    logger.warning(f'✗ 硬链接创建失败: {original_name}')

            # Process subtitle files
            if subtitle_files:
                subtitle_mapping = self._rename_service.generate_subtitle_mapping(
                    video_files, subtitle_files, rename_result.main_files
                )

                for sub_file in subtitle_files:
                    if sub_file.name in subtitle_mapping:
                        new_name = subtitle_mapping[sub_file.name]
                        success = self._file_service.create(
                            source_path=sub_file.full_path,
                            target_dir=target_dir,
                            new_name=new_name,
                            anime_id=anime_id,
                            torrent_hash=hash_id
                        )
                        if success:
                            logger.info(f'✓ 字幕硬链接创建成功: {new_name}')

            # Send notification
            if hardlink_count > 0:
                self._notifier.notify_hardlink_created(
                    anime_title=anime_title,
                    season=season,
                    video_count=hardlink_count,
                    subtitle_count=len(subtitle_files),
                    target_dir=target_dir,
                    rename_method=rename_result.method,
                    torrent_id=hash_id,
                    torrent_name=download_info.original_filename,
                    subtitle_group=subtitle_group,
                    tvdb_used=self._rename_service.last_tvdb_used,
                    hardlink_path=target_dir,
                    rename_examples=rename_examples
                )

            # Send failure notification when all hardlinks failed
            elif hardlink_count == 0 and video_files:
                first_video = video_files[0] if video_files else None
                source_path = first_video.full_path if first_video else None
                self._notifier.notify_hardlink_failed(
                    anime_title=anime_title,
                    season=season,
                    target_dir=target_dir,
                    rename_method=rename_result.method if rename_result else 'unknown',
                    torrent_id=hash_id,
                    torrent_name=download_info.original_filename,
                    subtitle_group=subtitle_group,
                    error_message=f'所有硬链接创建失败 (共 {len(video_files)} 个视频文件)，源文件不存在或路径错误',
                    source_path=source_path
                )

        except Exception as e:
            logger.error(f'处理硬链接失败: {e}')

        return hardlink_count
