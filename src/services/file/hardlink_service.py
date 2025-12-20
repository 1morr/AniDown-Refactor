"""
Hardlink service module.

Provides hardlink creation functionality for media library organization.
"""

import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.core.domain.entities import HardlinkRecord
from src.core.exceptions import HardlinkError
from src.core.interfaces.repositories import IHardlinkRepository
from src.services.file.path_builder import PathBuilder

logger = logging.getLogger(__name__)


class HardlinkService:
    """
    Hardlink service.

    Creates hardlinks from download directories to media library.
    Falls back to file copy when hardlinks are not possible
    (e.g., cross-filesystem operations).
    """

    def __init__(
        self,
        hardlink_repo: IHardlinkRepository,
        path_builder: PathBuilder
    ):
        """
        Initialize the hardlink service.

        Args:
            hardlink_repo: Repository for storing hardlink records.
            path_builder: Path builder for constructing target paths.
        """
        self._hardlink_repo = hardlink_repo
        self._path_builder = path_builder

    def create(
        self,
        source_path: str,
        target_dir: str,
        new_name: str,
        anime_id: Optional[int] = None,
        torrent_hash: Optional[str] = None
    ) -> bool:
        """
        Create a hardlink from source to target directory.

        Args:
            source_path: Full path to the source file.
            target_dir: Target directory for the hardlink.
            new_name: New filename for the hardlink.
            anime_id: Optional anime ID for record keeping.
            torrent_hash: Optional torrent hash for record keeping.

        Returns:
            True if successful, False otherwise.

        Raises:
            HardlinkError: If hardlink creation fails and fallback is disabled.
        """
        # Validate source exists
        if not os.path.exists(source_path):
            logger.error(f'❌ Source file does not exist: {source_path}')
            return False

        # Ensure target directory exists
        if not self._path_builder.ensure_directory(target_dir):
            logger.error(f'❌ Failed to create target directory: {target_dir}')
            return False

        # Build target path
        target_path = os.path.join(target_dir, new_name)

        # Skip if target already exists
        if os.path.exists(target_path):
            logger.warning(f'⚠️ Target already exists, skipping: {target_path}')
            return True

        # Attempt hardlink creation
        link_method = self._create_link(source_path, target_path)

        if link_method:
            # Get file size for record
            try:
                file_size = os.path.getsize(source_path)
            except OSError:
                file_size = 0

            # Save record
            record = HardlinkRecord(
                anime_id=anime_id,
                torrent_hash=torrent_hash or '',
                original_file_path=source_path,
                hardlink_path=target_path,
                file_size=file_size,
                link_method=link_method,
                created_at=datetime.now(timezone.utc)
            )
            self._hardlink_repo.save(record)

            logger.info(
                f'🔗 Created {link_method}: '
                f'{os.path.basename(source_path)} -> {new_name}'
            )
            return True

        return False

    def _create_link(self, source: str, target: str) -> Optional[str]:
        """
        Create a link from source to target, using hardlink or copy fallback.

        Args:
            source: Source file path.
            target: Target link path.

        Returns:
            Link method used ('hardlink' or 'copy'), or None if failed.
        """
        # Try hardlink first
        try:
            os.link(source, target)
            return 'hardlink'
        except OSError as e:
            logger.debug(f'Hardlink failed ({e}), falling back to copy')

        # Fallback to copy
        try:
            shutil.copy2(source, target)
            return 'copy'
        except (OSError, shutil.Error) as e:
            logger.error(f'❌ Failed to copy file: {e}')
            return None

    def build_target_directory(
        self,
        anime_title: str,
        media_type: str,
        category: str,
        season: Optional[int] = None
    ) -> str:
        """
        Build target directory for hardlink creation.

        Args:
            anime_title: Title of the anime.
            media_type: Media type ('anime' or 'live_action').
            category: Content category ('tv' or 'movie').
            season: Optional season number.

        Returns:
            Target directory path.
        """
        return self._path_builder.build_target_directory(
            anime_title=anime_title,
            media_type=media_type,
            category=category,
            season=season
        )

    def delete_by_torrent(self, torrent_hash: str, delete_files: bool = False) -> int:
        """
        Delete hardlink records for a torrent.

        Args:
            torrent_hash: Torrent hash to delete records for.
            delete_files: Whether to also delete the hardlink files.

        Returns:
            Number of records deleted.
        """
        records = self._hardlink_repo.get_by_torrent_hash(torrent_hash)
        deleted_count = 0

        for record in records:
            try:
                # Delete file if requested
                if delete_files and record.hardlink_path:
                    if os.path.exists(record.hardlink_path):
                        os.remove(record.hardlink_path)
                        logger.debug(f'Deleted file: {record.hardlink_path}')

                # Delete record
                if record.id:
                    self._hardlink_repo.delete(record.id)
                    deleted_count += 1
            except OSError as e:
                logger.warning(f'⚠️ Failed to delete hardlink: {e}')

        if deleted_count > 0:
            logger.info(f'🗑️ Deleted {deleted_count} hardlink records for {torrent_hash[:8]}')

        return deleted_count

    def get_stats(self, torrent_hash: str) -> Dict[str, Any]:
        """
        Get statistics for hardlinks created for a torrent.

        Args:
            torrent_hash: Torrent hash to get stats for.

        Returns:
            Dictionary with hardlink statistics.
        """
        records = self._hardlink_repo.get_by_torrent_hash(torrent_hash)

        total_size = sum(r.file_size for r in records)
        hardlink_count = sum(1 for r in records if r.is_hardlink)
        copy_count = sum(1 for r in records if r.is_copy)

        return {
            'total_files': len(records),
            'hardlinks': hardlink_count,
            'copies': copy_count,
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024) if total_size else 0
        }

    def verify_hardlink(self, record: HardlinkRecord) -> bool:
        """
        Verify that a hardlink still exists and is valid.

        Args:
            record: Hardlink record to verify.

        Returns:
            True if the hardlink exists and is valid.
        """
        if not record.hardlink_path:
            return False

        if not os.path.exists(record.hardlink_path):
            return False

        # For hardlinks, verify inode matches
        if record.is_hardlink and record.original_file_path:
            if os.path.exists(record.original_file_path):
                try:
                    source_stat = os.stat(record.original_file_path)
                    target_stat = os.stat(record.hardlink_path)
                    return source_stat.st_ino == target_stat.st_ino
                except OSError:
                    return False

        return True
