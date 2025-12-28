"""
Download status management service.

Handles status checking, deletion, and re-downloading of torrents.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from src.core.domain.entities import DownloadRecord
from src.core.domain.value_objects import (
    DownloadMethod,
    DownloadStatus,
    TorrentHash,
)
from src.core.interfaces.adapters import IDownloadClient
from src.core.interfaces.repositories import (
    IDownloadRepository,
    IHardlinkRepository,
)

logger = logging.getLogger(__name__)


class StatusService:
    """
    Download status management service.

    Handles:
    - Torrent status checking and updates
    - Download deletion (with optional file/hardlink cleanup)
    - Re-downloading from history
    - Paginated/grouped download queries
    """

    def __init__(
        self,
        download_repo: IDownloadRepository,
        history_repo: IHardlinkRepository,
        download_client: IDownloadClient,
        hardlink_service: Any  # HardlinkService (avoid circular import)
    ):
        """
        Initialize the status service.

        Args:
            download_repo: Repository for download records.
            history_repo: Repository for history records.
            download_client: Download client (qBittorrent).
            hardlink_service: Hardlink service for cleanup.
        """
        self._download_repo = download_repo
        self._history_repo = history_repo
        self._download_client = download_client
        self._hardlink_service = hardlink_service

    def check_torrent_status(self, hash_id: str) -> dict[str, Any]:
        """
        Check status of a single torrent.

        Args:
            hash_id: Torrent hash.

        Returns:
            Status information dictionary.
        """
        try:
            # Get current status from database
            current_download = self._download_repo.get_by_hash(hash_id)
            current_status = current_download.status if current_download else None

            torrent_info = self._download_client.get_torrent_info(hash_id)
            if not torrent_info:
                # Torrent not found
                if current_status == DownloadStatus.COMPLETED:
                    return {'success': True, 'status': 'completed', 'message': '種子已完成'}
                elif current_status == DownloadStatus.PENDING:
                    self._download_repo.update_status(hash_id, 'missing', None)
                    return {'success': True, 'status': 'missing', 'message': '未找到種子'}
                else:
                    if current_status:
                        self._download_repo.update_status(hash_id, 'missing', None)
                    return {'success': True, 'status': 'missing', 'message': '未找到種子'}

            status = 'completed' if torrent_info.get('progress', 0) >= 1.0 else 'downloading'
            completion_time = None

            if status == 'completed':
                if torrent_info.get('completion_date', -1) != -1:
                    completion_time = datetime.fromtimestamp(
                        torrent_info['completion_date'],
                        tz=UTC
                    )
                else:
                    completion_time = datetime.now(UTC)

            # Update database
            self._download_repo.update_status(hash_id, status, completion_time)

            return {
                'success': True,
                'status': status,
                'progress': torrent_info.get('progress', 0),
                'completion_time': completion_time
            }
        except Exception as e:
            logger.error(f'检查种子状态失败: {e}')
            return {'success': False, 'error': str(e)}

    def check_all_torrents(self) -> dict[str, Any]:
        """
        Check status of all incomplete torrents.

        Returns:
            Statistics dictionary.
        """
        try:
            incomplete_downloads = self._download_repo.get_incomplete()

            updated_count = 0
            completed_count = 0

            for download in incomplete_downloads:
                hash_value = download.hash_value if download.hash else ''
                if not hash_value:
                    continue

                result = self.check_torrent_status(hash_value)
                if result.get('success'):
                    updated_count += 1
                    if result.get('status') == 'completed':
                        completed_count += 1

            return {
                'success': True,
                'updated_count': updated_count,
                'completed_count': completed_count,
                'total_checked': len(incomplete_downloads)
            }
        except Exception as e:
            logger.error(f'批量检查失败: {e}')
            return {'success': False, 'error': str(e)}

    def delete_download(
        self,
        hash_id: str,
        delete_file: bool,
        delete_hardlink: bool
    ) -> dict[str, Any]:
        """
        Delete a download task.

        Args:
            hash_id: Torrent hash.
            delete_file: Whether to delete original files.
            delete_hardlink: Whether to delete hardlinks.

        Returns:
            Result dictionary.
        """
        result = {
            'success': True,
            'deleted_files': False,
            'deleted_hardlinks': False,
            'moved_to_history': False
        }

        try:
            # Delete hardlinks if requested
            if delete_hardlink:
                deleted_count = self._hardlink_service.delete_by_torrent(
                    hash_id, delete_files=True
                )
                result['deleted_hardlinks'] = deleted_count > 0
                result['hardlinks_deleted_count'] = deleted_count
                logger.info(f'删除了 {deleted_count} 个硬链接')

            # Delete original files if requested
            if delete_file:
                if self._download_client.delete_torrent(hash_id, delete_files=True):
                    result['deleted_files'] = True
                    logger.info(f'从qBittorrent删除了种子和文件: {hash_id}')
                else:
                    logger.warning(f'从qBittorrent删除失败: {hash_id}')

                # Move download record to history
                if self._download_repo.move_to_history(hash_id):
                    result['moved_to_history'] = True
                    logger.info(f'将下载记录移动到历史: {hash_id}')

            return result
        except Exception as e:
            logger.error(f'删除下载失败: {e}')
            return {'success': False, 'error': str(e)}

    def redownload_from_history(
        self,
        hash_id: str,
        download_directory: str
    ) -> bool:
        """
        Re-download from history record.

        Args:
            hash_id: Torrent hash.
            download_directory: Download directory path.

        Returns:
            True if successful.
        """
        try:
            # Check if already downloading
            if self._download_repo.get_by_hash(hash_id):
                raise ValueError('该项目已在下载列表中')

            # Get history record
            history = self._history_repo.get_download_history_by_hash(hash_id)
            if not history:
                logger.warning(f'未找到hash {hash_id} 的历史记录')
                raise ValueError('未找到下载历史记录')

            logger.info(
                f"📥 开始重新下载: {history.get('anime_title') or history.get('original_filename')}"
            )

            # Add magnet link to qBittorrent
            magnet_link = f'magnet:?xt=urn:btih:{hash_id}'
            result = self._download_client.add_magnet(magnet_link, save_path=download_directory)

            if not result:
                raise ValueError('添加磁力链接失败')

            # Restore to download_status table
            self._save_download_record(
                hash_id=hash_id,
                original_filename=history.get('original_filename', ''),
                anime_title=history.get('anime_title', ''),
                subtitle_group=history.get('subtitle_group', ''),
                season=history.get('season', 1),
                download_directory=download_directory,
                anime_id=history.get('anime_id'),
                download_method=history.get('download_method', 'unknown'),
                is_multi_season=history.get('is_multi_season', False)
            )

            # Save torrent files information
            self._save_torrent_files_on_add(hash_id, history.get('anime_id'))

            # Delete from history
            if self._history_repo.delete_download_history_by_hash(hash_id):
                logger.info(f'✅ 已从历史记录中移除: {hash_id}')

            logger.info('✅ 成功从历史记录重新下载，记录已恢复到下载列表')
            return True
        except Exception as e:
            logger.error(f'❌ 重新下载失败: {e}')
            return False

    def get_downloads_paginated(
        self,
        page: int,
        per_page: int,
        **filters
    ) -> dict[str, Any]:
        """
        Get paginated download records.

        Args:
            page: Page number (1-based).
            per_page: Items per page.
            **filters: Additional filter parameters.

        Returns:
            Paginated result dictionary.
        """
        return self._download_repo.get_downloads_paginated(page, per_page, **filters)

    def get_downloads_grouped(
        self,
        group_by: str,
        **filters
    ) -> dict[str, Any]:
        """
        Get grouped download statistics.

        Args:
            group_by: Grouping field.
            **filters: Additional filter parameters.

        Returns:
            Grouped statistics dictionary.
        """
        return self._download_repo.get_downloads_grouped(group_by, **filters)

    # ==================== Private Helper Methods ====================

    def _save_download_record(
        self,
        hash_id: str,
        original_filename: str,
        anime_title: str,
        subtitle_group: str,
        season: int,
        download_directory: str,
        anime_id: int,
        download_method: str,
        is_multi_season: bool = False,
        requires_tvdb: bool = False
    ) -> int:
        """Save download record and return ID."""
        # Determine download method enum
        method_map = {
            'rss_ai': DownloadMethod.RSS_AI,
            'fixed_rss': DownloadMethod.FIXED_RSS,
            'manual_rss': DownloadMethod.MANUAL_RSS,
            'manual_torrent': DownloadMethod.MANUAL_TORRENT,
            'manual_magnet': DownloadMethod.MANUAL_MAGNET,
        }
        method = method_map.get(download_method, DownloadMethod.RSS_AI)

        record = DownloadRecord(
            hash=TorrentHash(hash_id) if hash_id and len(hash_id) >= 32 else None,
            anime_id=anime_id,
            original_filename=original_filename,
            anime_title=anime_title,
            subtitle_group=subtitle_group,
            season=season,
            download_directory=download_directory,
            status=DownloadStatus.PENDING,
            download_method=method,
            is_multi_season=is_multi_season,
            requires_tvdb=requires_tvdb,
            download_time=datetime.now(UTC)
        )
        return self._download_repo.save(record)

    def _save_torrent_file(
        self,
        torrent_hash: str,
        file_path: str,
        file_size: int,
        anime_id: int | None
    ) -> None:
        """Save torrent file information."""
        # Determine file type based on extension
        file_type = 'other'
        file_lower = file_path.lower()

        if file_lower.endswith(('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')):
            file_type = 'video'
        elif file_lower.endswith(('.srt', '.ass', '.ssa', '.vtt', '.sub')):
            file_type = 'subtitle'

        # Save to database via repository
        try:
            self._download_repo.insert_torrent_file(
                torrent_hash=torrent_hash,
                file_path=file_path,
                file_size=file_size,
                file_type=file_type,
                anime_id=anime_id
            )
        except Exception as e:
            logger.warning(f'⚠️ Failed to save torrent file to database: {e}')

    def _save_torrent_files_on_add(
        self,
        hash_id: str,
        anime_id: int | None,
        max_retries: int = 5,
        retry_delay: float = 1.0
    ) -> None:
        """
        Save torrent file information when download starts.

        Waits for qBittorrent to parse the torrent and retrieves file list.
        For magnet links, may need multiple retries to get metadata.

        Args:
            hash_id: Torrent hash.
            anime_id: Anime ID for records.
            max_retries: Maximum retry attempts for getting file list.
            retry_delay: Delay between retries in seconds.
        """
        logger.debug(f'💾 正在保存种子文件信息: {hash_id[:8]}...')

        torrent_files = []
        for attempt in range(max_retries):
            torrent_files = self._download_client.get_torrent_files(hash_id)
            if torrent_files:
                break
            # Wait and retry (torrent may still be loading metadata)
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                logger.debug(f'  重试获取文件列表 ({attempt + 2}/{max_retries})...')

        if not torrent_files:
            logger.warning(f'⚠️ 无法获取种子文件列表: {hash_id[:8]} (可能是磁力链接等待元数据)')
            return

        logger.info(f'📋 获取到 {len(torrent_files)} 个文件，正在保存到数据库...')
        for file_info in torrent_files:
            self._save_torrent_file(
                torrent_hash=hash_id,
                file_path=file_info.get('name', ''),
                file_size=file_info.get('size', 0),
                anime_id=anime_id
            )
        logger.debug(f'✅ 种子文件信息保存完成: {hash_id[:8]}')
