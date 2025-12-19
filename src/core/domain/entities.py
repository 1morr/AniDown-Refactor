"""
Entities module.

Contains domain entities that have identity and lifecycle.
Entities are compared by their identity, not by their attributes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

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


@dataclass
class AnimeInfo:
    """
    Anime information entity.

    Represents a unique anime series/movie with its metadata.

    Attributes:
        id: Unique identifier in the database.
        title: Anime title information.
        subtitle_group: Subtitle group information.
        season: Season information.
        category: Content category (TV or Movie).
        media_type: Media type (Anime or Live Action).
        tvdb_id: The TVDB identifier for this anime.
        created_at: Timestamp when the record was created.
        updated_at: Timestamp when the record was last updated.
    """
    id: Optional[int] = None
    title: Optional[AnimeTitle] = None
    subtitle_group: Optional[SubtitleGroup] = None
    season: Optional[SeasonInfo] = None
    category: Category = Category.TV
    media_type: MediaType = MediaType.ANIME
    tvdb_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def display_name(self) -> str:
        """Return the display name for this anime."""
        if self.title:
            return self.title.display_name
        return ''

    @property
    def season_number(self) -> int:
        """Return the season number."""
        if self.season:
            return self.season.number
        return 1

    @property
    def subtitle_group_name(self) -> str:
        """Return the subtitle group name."""
        if self.subtitle_group:
            return self.subtitle_group.name
        return ''


@dataclass
class DownloadRecord:
    """
    Download record entity.

    Represents a single download task with its status and metadata.

    Attributes:
        id: Unique identifier in the database.
        hash: Torrent hash value.
        anime_id: Reference to the associated AnimeInfo.
        original_filename: Original file name from the torrent.
        anime_title: Cached anime title for quick access.
        subtitle_group: Cached subtitle group name.
        season: Season number.
        download_directory: Directory where files are downloaded.
        status: Current download status.
        download_method: Method used to initiate the download.
        is_multi_season: Whether this torrent contains multiple seasons.
        download_time: Timestamp when download was initiated.
        completion_time: Timestamp when download completed.
    """
    id: Optional[int] = None
    hash: Optional[TorrentHash] = None
    anime_id: Optional[int] = None
    original_filename: str = ''
    anime_title: str = ''
    subtitle_group: str = ''
    season: int = 1
    download_directory: str = ''
    status: DownloadStatus = DownloadStatus.PENDING
    download_method: DownloadMethod = DownloadMethod.RSS_AI
    is_multi_season: bool = False
    download_time: Optional[datetime] = None
    completion_time: Optional[datetime] = None

    @property
    def hash_value(self) -> str:
        """Return the hash string value."""
        if self.hash:
            return self.hash.value
        return ''

    @property
    def short_hash(self) -> str:
        """Return shortened hash for display."""
        if self.hash:
            return self.hash.short
        return ''

    @property
    def is_completed(self) -> bool:
        """Check if download is completed."""
        return self.status == DownloadStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """Check if download has failed."""
        return self.status == DownloadStatus.FAILED

    @property
    def is_active(self) -> bool:
        """Check if download is active (pending or downloading)."""
        return self.status in (DownloadStatus.PENDING, DownloadStatus.DOWNLOADING)


@dataclass
class RenameMapping:
    """
    Rename mapping entity.

    Represents a file rename operation mapping.

    Attributes:
        original_name: Original file name.
        new_name: New file name after renaming.
        season: Season number for this file.
        episode: Episode number (if applicable).
        is_skipped: Whether this file should be skipped.
        skip_reason: Reason for skipping (if skipped).
    """
    original_name: str
    new_name: str
    season: int
    episode: Optional[int] = None
    is_skipped: bool = False
    skip_reason: str = ''

    @property
    def should_process(self) -> bool:
        """Check if this file should be processed."""
        return not self.is_skipped and bool(self.new_name)


@dataclass
class HardlinkRecord:
    """
    Hardlink record entity.

    Represents a hardlink created in the media library.

    Attributes:
        id: Unique identifier in the database.
        anime_id: Reference to the associated AnimeInfo.
        torrent_hash: Hash of the source torrent.
        original_file_path: Path to the original file.
        hardlink_path: Path to the created hardlink.
        file_size: Size of the file in bytes.
        link_method: Method used (hardlink or copy).
        created_at: Timestamp when the hardlink was created.
    """
    id: Optional[int] = None
    anime_id: Optional[int] = None
    torrent_hash: str = ''
    original_file_path: str = ''
    hardlink_path: str = ''
    file_size: int = 0
    link_method: str = 'hardlink'
    created_at: Optional[datetime] = None

    @property
    def is_hardlink(self) -> bool:
        """Check if this was created as a hardlink."""
        return self.link_method == 'hardlink'

    @property
    def is_copy(self) -> bool:
        """Check if this was created as a file copy."""
        return self.link_method == 'copy'

    @property
    def file_size_mb(self) -> float:
        """Return file size in megabytes."""
        return self.file_size / (1024 * 1024)
