"""
Download manager module.

Facade that coordinates all download-related operations by delegating
to specialized sub-services for RSS processing, manual uploads,
torrent completion handling, and status management.
"""

import logging
from typing import Any

from src.services.download.completion_handler import CompletionHandler
from src.services.download.download_notifier import DownloadNotifier
from src.services.download.rss_processor import RSSProcessor, RSSProcessResult
from src.services.download.status_service import StatusService
from src.services.download.upload_handler import UploadHandler

logger = logging.getLogger(__name__)

# Re-export RSSProcessResult for backward compatibility
__all__ = ['DownloadManager', 'RSSProcessResult']


class DownloadManager:
    """
    Download manager - facade for download-related operations.

    This class provides a unified interface for all download operations
    while delegating the actual work to specialized sub-services:
    - RSSProcessor: RSS feed processing
    - UploadHandler: Manual uploads (torrent/magnet)
    - CompletionHandler: Torrent completion handling
    - StatusService: Status checking and management

    The facade pattern simplifies the interface for clients while
    allowing each sub-service to focus on a single responsibility.
    """

    def __init__(
        self,
        rss_processor: RSSProcessor,
        upload_handler: UploadHandler,
        completion_handler: CompletionHandler,
        status_service: StatusService,
        notifier: DownloadNotifier
    ):
        """
        Initialize the download manager facade.

        Args:
            rss_processor: Service for RSS feed processing.
            upload_handler: Service for manual uploads.
            completion_handler: Service for torrent completion handling.
            status_service: Service for status management.
            notifier: Unified notification service.
        """
        self._rss_processor = rss_processor
        self._upload_handler = upload_handler
        self._completion_handler = completion_handler
        self._status_service = status_service
        self._notifier = notifier

    # ==================== RSS Processing ====================

    def process_rss_feeds(
        self,
        rss_feeds: list,
        trigger_type: str = '定时触发',
        blocked_keywords: str | None = None,
        blocked_regex: str | None = None
    ) -> RSSProcessResult:
        """
        Process RSS feeds.

        Args:
            rss_feeds: List of RSS feeds (RSSFeed objects, dicts, or URL strings).
            trigger_type: How the processing was triggered.
            blocked_keywords: Global blocked keywords (deprecated, for backward compat).
            blocked_regex: Global regex patterns (deprecated, for backward compat).

        Returns:
            RSSProcessResult with processing statistics.
        """
        return self._rss_processor.process_feeds(
            rss_feeds, trigger_type, blocked_keywords, blocked_regex
        )

    def process_single_rss_item(
        self,
        item: dict[str, Any],
        trigger_type: str = 'queue'
    ) -> bool:
        """
        Process a single RSS item (called from queue).

        Args:
            item: RSS item dictionary with title, torrent_url, hash, media_type etc.
            trigger_type: Trigger type.

        Returns:
            True if processing was successful, False otherwise.

        Raises:
            Exception: When processing fails, contains error details.
        """
        return self._rss_processor.process_single_rss_item(item, trigger_type)

    def process_manual_anime_rss(
        self,
        rss_url: str,
        short_title: str,
        subtitle_group: str,
        season: int,
        category: str,
        trigger_type: str,
        blocked_keywords: str | None = None,
        blocked_regex: str | None = None,
        media_type: str = 'anime'
    ) -> RSSProcessResult:
        """
        Process manually added anime RSS.

        Args:
            rss_url: RSS feed URL.
            short_title: Anime short title.
            subtitle_group: Subtitle group name.
            season: Season number.
            category: Content category ('tv' or 'movie').
            trigger_type: How the processing was triggered.
            blocked_keywords: Blocked keywords.
            blocked_regex: Blocked regex patterns.
            media_type: Media type ('anime' or 'live_action').

        Returns:
            RSSProcessResult with processing statistics.
        """
        return self._rss_processor.process_manual_anime_rss(
            rss_url, short_title, subtitle_group, season, category,
            trigger_type, blocked_keywords, blocked_regex, media_type
        )

    # ==================== Manual Upload ====================

    def process_manual_upload(self, data: dict[str, Any]) -> tuple[bool, str]:
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
        return self._upload_handler.process_upload(data)

    # ==================== Torrent Completion ====================

    def handle_torrent_completed(
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
        return self._completion_handler.handle_completed(hash_id, webhook_data)

    # ==================== Status Management ====================

    def check_torrent_status(self, hash_id: str) -> dict[str, Any]:
        """
        Check status of a single torrent.

        Args:
            hash_id: Torrent hash.

        Returns:
            Status information dictionary.
        """
        return self._status_service.check_torrent_status(hash_id)

    def check_all_torrents(self) -> dict[str, Any]:
        """
        Check status of all incomplete torrents.

        Returns:
            Statistics dictionary.
        """
        return self._status_service.check_all_torrents()

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
        return self._status_service.delete_download(hash_id, delete_file, delete_hardlink)

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
        return self._status_service.redownload_from_history(hash_id, download_directory)

    def get_downloads_paginated(
        self,
        page: int,
        per_page: int,
        **filters
    ) -> dict[str, Any]:
        """Get paginated download records."""
        return self._status_service.get_downloads_paginated(page, per_page, **filters)

    def get_downloads_grouped(
        self,
        group_by: str,
        **filters
    ) -> dict[str, Any]:
        """Get grouped download statistics."""
        return self._status_service.get_downloads_grouped(group_by, **filters)

    # ==================== Notification Helpers ====================

    def notify_error(self, message: str, error_type: str = '错误') -> None:
        """
        Send error notification.

        Args:
            message: Error message.
            error_type: Type of error.
        """
        self._notifier.notify_error(message, error_type)
