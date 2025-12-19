"""
Value objects module.

Contains immutable value objects representing domain concepts without identity.
Value objects are compared by their attributes, not by identity.
"""

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DownloadStatus(Enum):
    """Download status enumeration."""
    PENDING = 'pending'
    DOWNLOADING = 'downloading'
    COMPLETED = 'completed'
    FAILED = 'failed'
    PAUSED = 'paused'
    MISSING = 'missing'


class Category(Enum):
    """Content category enumeration."""
    TV = 'tv'
    MOVIE = 'movie'


class MediaType(Enum):
    """Media type enumeration."""
    ANIME = 'anime'
    LIVE_ACTION = 'live_action'


class DownloadMethod(Enum):
    """Download method enumeration."""
    RSS_AI = 'rss_ai'
    FIXED_RSS = 'fixed_rss'
    MANUAL_RSS = 'manual_rss'
    MANUAL_TORRENT = 'manual_torrent'
    MANUAL_MAGNET = 'manual_magnet'


@dataclass(frozen=True)
class TorrentHash:
    """
    Torrent hash value object.

    Represents a unique identifier for a torrent, typically a 40-character
    hexadecimal string (SHA-1 hash).

    Attributes:
        value: The full hash string (must be at least 32 characters).
    """
    value: str

    def __post_init__(self) -> None:
        """Validate hash value on initialization."""
        if not self.value or len(self.value) < 32:
            raise ValueError(
                f'Invalid torrent hash: must be at least 32 characters, '
                f'got {len(self.value) if self.value else 0}'
            )

    @property
    def short(self) -> str:
        """Return shortened hash (first 8 characters) for display."""
        return self.value[:8]

    def __str__(self) -> str:
        """Return full hash value as string."""
        return self.value


@dataclass(frozen=True)
class SeasonInfo:
    """
    Season information value object.

    Represents information about an anime season.

    Attributes:
        number: Season number (0 for movies, 1+ for TV series).
        episode_count: Total number of episodes in the season.
        category: Content category (TV or Movie).
        description: Optional description of the season.
    """
    number: int
    episode_count: int = 0
    category: Category = Category.TV
    description: str = ''

    def __post_init__(self) -> None:
        """Validate season number on initialization."""
        if self.number < 0:
            raise ValueError(f'Season number cannot be negative: {self.number}')

    @property
    def is_movie(self) -> bool:
        """Check if this season represents a movie (season 0)."""
        return self.number == 0 or self.category == Category.MOVIE

    @property
    def display_number(self) -> str:
        """Return formatted season number for display (e.g., 'S01')."""
        if self.is_movie:
            return 'Movie'
        return f'S{self.number:02d}'


@dataclass(frozen=True)
class AnimeTitle:
    """
    Anime title value object.

    Represents various forms of an anime title.

    Attributes:
        original: Original title from the source (RSS feed, file name, etc.).
        short: Cleaned short title for internal use and file naming.
        full: Full official title (if available).
    """
    original: str
    short: str
    full: Optional[str] = None

    @property
    def display_name(self) -> str:
        """Return the best available name for display purposes."""
        return self.full or self.short or self.original

    @property
    def safe_name(self) -> str:
        """Return filename-safe version of the short title."""
        if not self.short:
            return ''
        # Remove or replace characters that are invalid in file names
        safe = re.sub(r'[<>:"/\\|?*]', '', self.short)
        # Replace multiple spaces with single space
        safe = re.sub(r'\s+', ' ', safe)
        return safe.strip()


@dataclass(frozen=True)
class SubtitleGroup:
    """
    Subtitle group information value object.

    Represents a fansub group that provides subtitles.

    Attributes:
        name: Name of the subtitle group.
    """
    name: str

    @property
    def safe_name(self) -> str:
        """Return filename-safe version of the group name."""
        if not self.name:
            return ''
        # Remove brackets and other special characters
        safe = re.sub(r'[\[\]<>:"/\\|?*]', '', self.name)
        # Replace multiple spaces with single space
        safe = re.sub(r'\s+', ' ', safe)
        return safe.strip()

    @property
    def display_name(self) -> str:
        """Return formatted name for display (with brackets)."""
        if not self.name:
            return ''
        return f'[{self.name}]'


@dataclass(frozen=True)
class FilePath:
    """
    File path value object.

    Represents a file system path with utility properties.

    Attributes:
        path: The full file path.
    """
    path: str

    @property
    def filename(self) -> str:
        """Return the file name (with extension)."""
        return os.path.basename(self.path)

    @property
    def stem(self) -> str:
        """Return the file name without extension."""
        name = self.filename
        if '.' in name:
            return name.rsplit('.', 1)[0]
        return name

    @property
    def extension(self) -> str:
        """Return the file extension (with dot, lowercase)."""
        _, ext = os.path.splitext(self.path)
        return ext.lower()

    @property
    def directory(self) -> str:
        """Return the parent directory path."""
        return os.path.dirname(self.path)

    @property
    def exists(self) -> bool:
        """Check if the file exists."""
        return os.path.exists(self.path)

    @property
    def is_video(self) -> bool:
        """Check if this is a video file."""
        video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm'}
        return self.extension in video_extensions

    @property
    def is_subtitle(self) -> bool:
        """Check if this is a subtitle file."""
        subtitle_extensions = {'.ass', '.srt', '.sub', '.ssa', '.vtt'}
        return self.extension in subtitle_extensions

    def __str__(self) -> str:
        """Return the path as string."""
        return self.path
