"""
Manual upload handling service.

Handles torrent file and magnet link uploads.
"""

import base64
import logging
import os
import tempfile
import time
from datetime import UTC, datetime
from typing import Any

from src.core.domain.entities import AnimeInfo, DownloadRecord
from src.core.domain.value_objects import (
    AnimeTitle,
    Category,
    DownloadMethod,
    DownloadStatus,
    MediaType,
    SeasonInfo,
    SubtitleGroup,
    TorrentHash,
)
from src.core.interfaces.adapters import IDownloadClient
from src.core.interfaces.repositories import (
    IAnimeRepository,
    IDownloadRepository,
    IHardlinkRepository,
)
from src.services.download.download_notifier import DownloadNotifier
from src.services.file.path_builder import PathBuilder

logger = logging.getLogger(__name__)


class UploadHandler:
    """
    Manual upload handling service.

    Handles processing of manually uploaded torrent files and magnet links.
    """

    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        history_repo: IHardlinkRepository,
        download_client: IDownloadClient,
        path_builder: PathBuilder,
        notifier: DownloadNotifier
    ):
        """
        Initialize the upload handler.

        Args:
            anime_repo: Repository for anime information.
            download_repo: Repository for download records.
            history_repo: Repository for history records.
            download_client: Download client (qBittorrent).
            path_builder: Path construction service.
            notifier: Download notifier service.
        """
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._history_repo = history_repo
        self._download_client = download_client
        self._path_builder = path_builder
        self._notifier = notifier

    def process_upload(self, data: dict[str, Any]) -> tuple[bool, str]:
        """
        Process manual upload (torrent file or magnet link).

        Args:
            data: Upload data containing:
                - upload_type: 'torrent' or 'magnet'
                - anime_title: Anime title
                - subtitle_group: Subtitle group name
                - season: Season number
                - category: Content category
                - is_multi_season: Whether multiple seasons
                - media_type: Media type
                - requires_tvdb: Whether to use TVDB for renaming
                - tvdb_id: Manually specified TVDB ID (optional)
                - torrent_file: Base64 encoded torrent file (if upload_type='torrent')
                - magnet_link: Magnet link (if upload_type='magnet')

        Returns:
            Tuple of (success: bool, error_message: str).
            On success, error_message is empty string.
            On failure, error_message contains the error description.
        """
        try:
            upload_type = data.get('upload_type', 'torrent')
            anime_title = data.get('anime_title', '').strip()
            subtitle_group = data.get('subtitle_group', '').strip()
            season = data.get('season', 1)
            category = data.get('category', 'tv')
            is_multi_season = data.get('is_multi_season', False)
            media_type = data.get('media_type', 'anime')
            requires_tvdb = data.get('requires_tvdb', False)
            tvdb_id = data.get('tvdb_id', None)

            logger.info(f'🔄 开始处理手动上传: {anime_title} (类型: {upload_type})')

            # Save anime info with tvdb_id if provided
            anime_id = self._save_anime_info(
                original_title=f'手动上传 - {anime_title}',
                short_title=anime_title,
                long_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                media_type=media_type,
                tvdb_id=tvdb_id
            )

            # Generate save path
            save_path = self._path_builder.build_download_path(
                title=anime_title,
                season=season,
                category=category,
                media_type=media_type
            )

            # Process based on upload type
            hash_id = None

            if upload_type == 'torrent':
                hash_id = self._process_torrent_upload(data, save_path)
            else:  # magnet
                hash_id = self._process_magnet_upload(data, save_path)

            if not hash_id:
                raise ValueError('无法获取hash')

            # Record download status
            self._save_download_record(
                hash_id=hash_id,
                original_filename=f'手动上传 - {anime_title}',
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                download_directory=save_path,
                anime_id=anime_id,
                download_method=f'manual_{upload_type}',
                is_multi_season=is_multi_season,
                requires_tvdb=requires_tvdb
            )

            # Save torrent files information
            self._save_torrent_files_on_add(hash_id, anime_id)

            # Record history (only on success)
            self._history_repo.insert_manual_upload_history(
                upload_type=upload_type,
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                torrent_hash=hash_id,
                upload_status='success'
            )

            # Send notification (same format as RSS, to RSS channel)
            self._notifier.notify_download_task(
                project_name=anime_title,
                hash_id=hash_id,
                anime_title=f'手动上传 - {anime_title}',
                subtitle_group=subtitle_group,
                download_path=save_path,
                season=season
            )

            return (True, '')

        except Exception as e:
            error_message = str(e)
            logger.error(f'手动上传失败: {error_message}')
            # Record failure history
            self._history_repo.insert_manual_upload_history(
                upload_type=data.get('upload_type', 'unknown'),
                anime_title=data.get('anime_title', 'unknown'),
                subtitle_group=data.get('subtitle_group', ''),
                season=data.get('season', 1),
                category=data.get('category', 'tv'),
                torrent_hash=None,
                upload_status='failed',
                error_message=error_message
            )
            self._notifier.notify_error(f'手动上传失败: {error_message}')
            return (False, error_message)

    def _process_torrent_upload(
        self,
        data: dict[str, Any],
        save_path: str
    ) -> str:
        """Process torrent file upload."""
        from src.infrastructure.downloader.qbit_adapter import get_torrent_hash_from_file

        torrent_file = data.get('torrent_file')
        if not torrent_file:
            raise ValueError('缺少torrent文件内容')

        # Decode Base64 and save to temp file
        torrent_content = base64.b64decode(torrent_file)
        with tempfile.NamedTemporaryFile(suffix='.torrent', delete=False) as temp_file:
            temp_file.write(torrent_content)
            temp_file_path = temp_file.name

        try:
            hash_id = get_torrent_hash_from_file(temp_file_path)
            if not hash_id:
                raise ValueError('无法从torrent文件提取hash')

            result = self._download_client.add_torrent_file(temp_file_path, save_path)
            if not result:
                raise ValueError('添加种子到qBittorrent失败（可能无法连接/登录qBittorrent）')
            return hash_id
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def _process_magnet_upload(
        self,
        data: dict[str, Any],
        save_path: str
    ) -> str:
        """Process magnet link upload."""
        from src.infrastructure.downloader.qbit_adapter import get_torrent_hash_from_magnet

        magnet_link = data.get('magnet_link', '').strip()
        if not magnet_link:
            raise ValueError('缺少磁力链接')

        hash_id = get_torrent_hash_from_magnet(magnet_link)
        if not hash_id:
            raise ValueError('无法从磁力链接提取hash')

        result = self._download_client.add_magnet(magnet_link, save_path)
        if not result:
            raise ValueError('添加磁力链接到qBittorrent失败（可能无法连接/登录qBittorrent）')
        return hash_id

    def _save_anime_info(
        self,
        original_title: str,
        short_title: str,
        long_title: str | None = None,
        subtitle_group: str = '',
        season: int = 1,
        category: str = 'tv',
        media_type: str = 'anime',
        tvdb_id: int | None = None
    ) -> int:
        """Save anime information and return ID."""
        anime_info = AnimeInfo(
            title=AnimeTitle(
                original=original_title,
                short=short_title,
                full=long_title
            ),
            subtitle_group=SubtitleGroup(name=subtitle_group),
            season=SeasonInfo(
                number=season,
                category=Category.MOVIE if category == 'movie' else Category.TV
            ),
            category=Category.MOVIE if category == 'movie' else Category.TV,
            media_type=MediaType.LIVE_ACTION if media_type == 'live_action' else MediaType.ANIME,
            tvdb_id=tvdb_id,
            created_at=datetime.now(UTC)
        )
        return self._anime_repo.save(anime_info)

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
