"""
Database infrastructure module.

Provides database session management and ORM models.
"""

from src.infrastructure.database.models import (
    AIKeyDailyCount,
    AIKeyUsageLog,
    AnimeInfo,
    AnimePattern,
    Base,
    DownloadHistory,
    DownloadStatus,
    Hardlink,
    HardlinkAttempt,
    ManualUploadHistory,
    RssProcessingDetail,
    RssProcessingHistory,
    SqlQueryHistory,
    TorrentFile,
)
from src.infrastructure.database.session import (
    DatabaseSessionManager,
    db_manager,
)

__all__ = [
    # Models
    'Base',
    'AnimeInfo',
    'AnimePattern',
    'DownloadStatus',
    'TorrentFile',
    'Hardlink',
    'HardlinkAttempt',
    'RssProcessingHistory',
    'RssProcessingDetail',
    'ManualUploadHistory',
    'DownloadHistory',
    'SqlQueryHistory',
    'AIKeyUsageLog',
    'AIKeyDailyCount',
    # Session
    'DatabaseSessionManager',
    'db_manager',
]
