"""
Torrent completion handler module.

Handles post-download processing including file renaming and hardlink creation.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.domain.entities import AnimeInfo, DownloadRecord
from src.core.domain.value_objects import DownloadStatus, TorrentHash
from src.core.exceptions import HardlinkError, TorrentNotFoundError
from src.core.interfaces.adapters import IDownloadClient, IFileRenamer
from src.core.interfaces.notifications import (
    HardlinkNotification,
    IDownloadNotifier,
    IHardlinkNotifier,
)
from src.core.interfaces.repositories import IAnimeRepository, IDownloadRepository
from src.services.file.hardlink_service import HardlinkService
from src.services.rename.file_classifier import ClassifiedFile, FileClassifier

logger = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    """
    Torrent completion processing result.

    Attributes:
        hash_id: Torrent hash.
        success: Whether processing was successful.
        video_count: Number of video files processed.
        subtitle_count: Number of subtitle files processed.
        target_directory: Target library directory.
        errors: List of errors encountered.
    """
    hash_id: str
    success: bool = False
    video_count: int = 0
    subtitle_count: int = 0
    target_directory: str = ''
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class TorrentCompletionHandler:
    """
    Torrent completion handler.

    Processes completed torrents by:
    1. Getting torrent files from download client
    2. Classifying files into videos, subtitles, etc.
    3. Generating rename mappings
    4. Creating hardlinks in the media library
    5. Updating download records
    6. Sending notifications
    """

    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        download_client: IDownloadClient,
        hardlink_service: HardlinkService,
        file_renamer: IFileRenamer,
        download_notifier: Optional[IDownloadNotifier] = None,
        hardlink_notifier: Optional[IHardlinkNotifier] = None
    ):
        """
        Initialize the completion handler.

        Args:
            anime_repo: Repository for anime information.
            download_repo: Repository for download records.
            download_client: Download client for torrent info.
            hardlink_service: Service for creating hardlinks.
            file_renamer: Service for file renaming.
            download_notifier: Optional download event notifier.
            hardlink_notifier: Optional hardlink event notifier.
        """
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._download_client = download_client
        self._hardlink_service = hardlink_service
        self._file_renamer = file_renamer
        self._download_notifier = download_notifier
        self._hardlink_notifier = hardlink_notifier
        self._file_classifier = FileClassifier()

    def handle(self, hash_id: str) -> CompletionResult:
        """
        Handle a completed torrent.

        Main entry point for processing a completed download.

        Args:
            hash_id: Torrent hash identifier.

        Returns:
            CompletionResult with processing details.
        """
        result = CompletionResult(hash_id=hash_id)

        logger.info(f'🔄 Processing completed torrent: {hash_id[:8]}...')

        try:
            # Get download record
            download_record = self._download_repo.get_by_hash(hash_id)
            if not download_record:
                raise TorrentNotFoundError(f'Download record not found: {hash_id[:8]}')

            # Get anime info
            anime_info = None
            if download_record.anime_id:
                anime_info = self._anime_repo.get_by_id(download_record.anime_id)

            # Get torrent files from client
            torrent_files = self._download_client.get_torrent_files(hash_id)
            if not torrent_files:
                raise TorrentNotFoundError(f'No files found for torrent: {hash_id[:8]}')

            # Classify files
            video_files, subtitle_files = self._file_renamer.classify_files(
                torrent_files,
                download_record.download_directory
            )

            if not video_files:
                logger.warning(f'⚠️ No video files found in torrent: {hash_id[:8]}')
                result.errors.append('No video files found')
                return result

            # Generate rename mapping
            rename_result = self._file_renamer.generate_mapping(
                video_files=video_files,
                anime_id=download_record.anime_id,
                anime_title=download_record.anime_title,
                subtitle_group=download_record.subtitle_group,
                season=download_record.season,
                category='movie' if download_record.season == 0 else 'tv',
                is_multi_season=download_record.is_multi_season
            )

            if not rename_result or not rename_result.has_files:
                logger.warning(f'⚠️ Could not generate rename mapping: {hash_id[:8]}')
                result.errors.append('Failed to generate rename mapping')
                return result

            # Build target directory
            target_dir = self._hardlink_service.build_target_directory(
                anime_title=download_record.anime_title,
                media_type='anime',
                category='movie' if download_record.season == 0 else 'tv',
                season=download_record.season
            )
            result.target_directory = target_dir

            # Create hardlinks for video files
            video_count = self._create_hardlinks(
                files=video_files,
                rename_mapping=rename_result.main_files,
                target_dir=target_dir,
                anime_id=download_record.anime_id,
                torrent_hash=hash_id
            )
            result.video_count = video_count

            # Generate and create hardlinks for subtitle files
            if subtitle_files:
                subtitle_mapping = self._file_renamer.generate_subtitle_mapping(
                    video_files=video_files,
                    subtitle_files=subtitle_files,
                    video_rename_mapping=rename_result.main_files
                )
                subtitle_count = self._create_hardlinks(
                    files=subtitle_files,
                    rename_mapping=subtitle_mapping,
                    target_dir=target_dir,
                    anime_id=download_record.anime_id,
                    torrent_hash=hash_id
                )
                result.subtitle_count = subtitle_count

            # Update download record
            self._update_record(download_record)

            # Send notifications
            self._send_notifications(download_record, result, rename_result.method)

            result.success = True
            logger.info(
                f'✅ Completed processing: {hash_id[:8]} - '
                f'{result.video_count} videos, {result.subtitle_count} subtitles'
            )

        except TorrentNotFoundError as e:
            logger.error(f'❌ Torrent not found: {e}')
            result.errors.append(str(e))
        except HardlinkError as e:
            logger.error(f'❌ Hardlink error: {e}')
            result.errors.append(str(e))
        except Exception as e:
            logger.exception(f'❌ Unexpected error processing torrent: {e}')
            result.errors.append(str(e))

        return result

    def _create_hardlinks(
        self,
        files: List[ClassifiedFile],
        rename_mapping: Dict[str, str],
        target_dir: str,
        anime_id: Optional[int],
        torrent_hash: str
    ) -> int:
        """
        Create hardlinks for files.

        Args:
            files: List of classified files.
            rename_mapping: Original -> new name mapping.
            target_dir: Target directory for hardlinks.
            anime_id: Anime ID for records.
            torrent_hash: Torrent hash for records.

        Returns:
            Number of hardlinks created successfully.
        """
        success_count = 0

        for file in files:
            if file.name not in rename_mapping:
                continue

            new_name = rename_mapping[file.name]

            success = self._hardlink_service.create(
                source_path=file.full_path,
                target_dir=target_dir,
                new_name=new_name,
                anime_id=anime_id,
                torrent_hash=torrent_hash
            )

            if success:
                success_count += 1
            else:
                logger.warning(f'⚠️ Failed to create hardlink for: {file.name}')

        return success_count

    def _update_record(self, record: DownloadRecord) -> None:
        """
        Update download record to completed status.

        Args:
            record: Download record to update.
        """
        record.status = DownloadStatus.COMPLETED
        record.completion_time = datetime.now(timezone.utc)
        self._download_repo.update(record)
        logger.debug(f'Updated download record: {record.short_hash}')

    def _send_notifications(
        self,
        record: DownloadRecord,
        result: CompletionResult,
        rename_method: str
    ) -> None:
        """
        Send completion notifications.

        Args:
            record: Download record.
            result: Completion result.
            rename_method: Method used for renaming.
        """
        if self._hardlink_notifier:
            notification = HardlinkNotification(
                anime_title=record.anime_title,
                season=record.season,
                video_count=result.video_count,
                subtitle_count=result.subtitle_count,
                target_dir=result.target_directory,
                rename_method=rename_method
            )
            try:
                self._hardlink_notifier.notify_hardlink_created(notification)
            except Exception as e:
                logger.warning(f'⚠️ Failed to send hardlink notification: {e}')

    def handle_webhook(
        self,
        hash_id: str,
        name: str = '',
        category: str = '',
        save_path: str = ''
    ) -> CompletionResult:
        """
        Handle a webhook completion event.

        Wrapper for handle() with webhook-specific parameter handling.

        Args:
            hash_id: Torrent hash.
            name: Torrent name (may be used for missing records).
            category: Torrent category.
            save_path: Save path.

        Returns:
            CompletionResult.
        """
        logger.info(f'🔔 Webhook received: {hash_id[:8]} - {name[:50] if name else ""}')
        return self.handle(hash_id)

    def retry_failed(self, hash_id: str) -> CompletionResult:
        """
        Retry processing a previously failed torrent.

        Args:
            hash_id: Torrent hash.

        Returns:
            CompletionResult.
        """
        logger.info(f'🔄 Retrying failed torrent: {hash_id[:8]}')

        # Reset status if needed
        record = self._download_repo.get_by_hash(hash_id)
        if record and record.is_failed:
            record.status = DownloadStatus.DOWNLOADING
            self._download_repo.update(record)

        return self.handle(hash_id)
