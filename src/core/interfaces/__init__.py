"""
Interfaces module.

Contains abstract base classes defining the contracts for repositories,
adapters, and notification services.
"""

from src.core.interfaces.adapters import (
    IDownloadClient,
    IFileRenamer,
    IMetadataClient,
    IRSSParser,
    ITitleParser,
    RenameResult,
    RSSItem,
    TitleParseResult,
)
from src.core.interfaces.notifications import (
    DownloadNotification,
    ErrorNotification,
    HardlinkNotification,
    IDownloadNotifier,
    IErrorNotifier,
    IHardlinkNotifier,
    IRSSNotifier,
    RSSNotification,
)
from src.core.interfaces.repositories import (
    IAnimeRepository,
    IDownloadRepository,
    IHardlinkRepository,
)

__all__ = [
    # Repository Interfaces
    'IAnimeRepository',
    'IDownloadRepository',
    'IHardlinkRepository',
    # Adapter Data Classes
    'TitleParseResult',
    'RenameResult',
    'RSSItem',
    # Adapter Interfaces
    'ITitleParser',
    'IFileRenamer',
    'IDownloadClient',
    'IRSSParser',
    'IMetadataClient',
    # Notification Data Classes
    'RSSNotification',
    'DownloadNotification',
    'HardlinkNotification',
    'ErrorNotification',
    # Notification Interfaces
    'IRSSNotifier',
    'IDownloadNotifier',
    'IHardlinkNotifier',
    'IErrorNotifier',
]
