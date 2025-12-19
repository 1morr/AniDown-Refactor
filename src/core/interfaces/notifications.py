"""
Notification interfaces module.

Contains data classes and abstract base classes for notification services.
Following Interface Segregation Principle with focused, specialized interfaces.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Notification Data Classes

@dataclass
class RSSNotification:
    """
    RSS processing notification data.

    Attributes:
        trigger_type: Type of trigger (e.g., 'scheduled', 'manual').
        rss_url: URL of the RSS feed being processed.
        title: Optional title for the notification.
        item_count: Number of items found in the feed.
    """
    trigger_type: str
    rss_url: str
    title: Optional[str] = None
    item_count: int = 0


@dataclass
class DownloadNotification:
    """
    Download event notification data.

    Attributes:
        anime_title: Title of the anime being downloaded.
        season: Season number.
        episode: Episode number (if applicable).
        subtitle_group: Name of the subtitle group.
        hash_id: Torrent hash identifier.
        progress: Download progress (0.0 to 1.0).
    """
    anime_title: str
    season: int
    episode: Optional[int]
    subtitle_group: str
    hash_id: str
    progress: float = 0.0

    @property
    def season_episode_display(self) -> str:
        """Return formatted season/episode string (e.g., 'S01E05')."""
        if self.episode is not None:
            return f'S{self.season:02d}E{self.episode:02d}'
        return f'S{self.season:02d}'

    @property
    def short_hash(self) -> str:
        """Return shortened hash for display."""
        return self.hash_id[:8] if self.hash_id else ''


@dataclass
class HardlinkNotification:
    """
    Hardlink creation notification data.

    Attributes:
        anime_title: Title of the anime.
        season: Season number.
        video_count: Number of video files linked.
        subtitle_count: Number of subtitle files linked.
        target_dir: Target directory for the hardlinks.
        rename_method: Method used for renaming ('ai', 'pattern', etc.).
    """
    anime_title: str
    season: int
    video_count: int
    subtitle_count: int
    target_dir: str
    rename_method: str

    @property
    def total_files(self) -> int:
        """Return total number of files processed."""
        return self.video_count + self.subtitle_count


@dataclass
class ErrorNotification:
    """
    Error notification data.

    Attributes:
        error_type: Type/category of the error.
        error_message: Human-readable error message.
        context: Additional context information.
        severity: Error severity level.
    """
    error_type: str
    error_message: str
    context: Dict[str, Any] = field(default_factory=dict)
    severity: str = 'error'

    @property
    def is_critical(self) -> bool:
        """Check if this is a critical error."""
        return self.severity == 'critical'


# Notification Interfaces (following Interface Segregation Principle)

class IRSSNotifier(ABC):
    """
    RSS notification interface.

    Specialized interface for RSS processing notifications.
    """

    @abstractmethod
    def notify_processing_start(self, notification: RSSNotification) -> None:
        """
        Notify that RSS processing has started.

        Args:
            notification: RSS notification data.
        """
        pass

    @abstractmethod
    def notify_processing_complete(
        self,
        success_count: int,
        total_count: int,
        failed_items: List[Dict[str, Any]]
    ) -> None:
        """
        Notify that RSS processing has completed.

        Args:
            success_count: Number of successfully processed items.
            total_count: Total number of items processed.
            failed_items: List of failed items with error details.
        """
        pass


class IDownloadNotifier(ABC):
    """
    Download notification interface.

    Specialized interface for download event notifications.
    """

    @abstractmethod
    def notify_download_start(self, notification: DownloadNotification) -> None:
        """
        Notify that a download has started.

        Args:
            notification: Download notification data.
        """
        pass

    @abstractmethod
    def notify_download_complete(self, notification: DownloadNotification) -> None:
        """
        Notify that a download has completed.

        Args:
            notification: Download notification data.
        """
        pass

    @abstractmethod
    def notify_download_failed(
        self,
        notification: DownloadNotification,
        error_message: str
    ) -> None:
        """
        Notify that a download has failed.

        Args:
            notification: Download notification data.
            error_message: Description of the failure.
        """
        pass


class IHardlinkNotifier(ABC):
    """
    Hardlink notification interface.

    Specialized interface for hardlink creation notifications.
    """

    @abstractmethod
    def notify_hardlink_created(self, notification: HardlinkNotification) -> None:
        """
        Notify that hardlinks have been created.

        Args:
            notification: Hardlink notification data.
        """
        pass

    @abstractmethod
    def notify_hardlink_failed(
        self,
        notification: HardlinkNotification,
        error_message: str
    ) -> None:
        """
        Notify that hardlink creation has failed.

        Args:
            notification: Hardlink notification data.
            error_message: Description of the failure.
        """
        pass


class IErrorNotifier(ABC):
    """
    Error notification interface.

    Specialized interface for error notifications.
    """

    @abstractmethod
    def notify_error(self, notification: ErrorNotification) -> None:
        """
        Send an error notification.

        Args:
            notification: Error notification data.
        """
        pass

    @abstractmethod
    def notify_warning(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Send a warning notification.

        Args:
            message: Warning message.
            context: Optional additional context.
        """
        pass
