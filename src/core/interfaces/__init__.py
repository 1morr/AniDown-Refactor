"""
Interfaces module.

Contains abstract base classes defining the contracts for repositories
and adapters, plus notification data classes.
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
    AIUsageNotification,
    DownloadNotification,
    ErrorNotification,
    HardlinkNotification,
    RSSInterruptedNotification,
    RSSNotification,
    RSSTaskNotification,
    WebhookReceivedNotification,
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
    'AIUsageNotification',
    'RSSTaskNotification',
    'RSSInterruptedNotification',
    'WebhookReceivedNotification',
]
