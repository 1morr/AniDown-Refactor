"""
Interfaces module.

Contains abstract base classes defining the contracts for repositories,
adapters, and notification services.
"""

from src.core.interfaces.repositories import (
    IAnimeRepository,
    IDownloadRepository,
    IHardlinkRepository,
)
from src.core.interfaces.adapters import (
    TitleParseResult,
    RenameResult,
    RSSItem,
    ITitleParser,
    IFileRenamer,
    IDownloadClient,
    IRSSParser,
    IMetadataClient,
)
from src.core.interfaces.notifications import (
    RSSNotification,
    DownloadNotification,
    HardlinkNotification,
    ErrorNotification,
    IRSSNotifier,
    IDownloadNotifier,
    IHardlinkNotifier,
    IErrorNotifier,
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
