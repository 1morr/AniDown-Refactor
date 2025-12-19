"""
Domain layer module.

Contains value objects and entities that represent the core business concepts.
"""

from src.core.domain.value_objects import (
    DownloadStatus,
    Category,
    MediaType,
    DownloadMethod,
    TorrentHash,
    SeasonInfo,
    AnimeTitle,
    SubtitleGroup,
    FilePath,
)
from src.core.domain.entities import (
    AnimeInfo,
    DownloadRecord,
    RenameMapping,
    HardlinkRecord,
)

__all__ = [
    # Value Objects - Enums
    'DownloadStatus',
    'Category',
    'MediaType',
    'DownloadMethod',
    # Value Objects - Data Classes
    'TorrentHash',
    'SeasonInfo',
    'AnimeTitle',
    'SubtitleGroup',
    'FilePath',
    # Entities
    'AnimeInfo',
    'DownloadRecord',
    'RenameMapping',
    'HardlinkRecord',
]
