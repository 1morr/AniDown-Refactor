"""
Domain layer module.

Contains value objects and entities that represent the core business concepts.
"""

from src.core.domain.entities import (
    AnimeInfo,
    DownloadRecord,
    HardlinkRecord,
    RenameMapping,
)
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
    # Entities
    'AnimeInfo',
    'DownloadRecord',
    'RenameMapping',
    'HardlinkRecord',
]
