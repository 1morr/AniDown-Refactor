"""
Notification data classes module.

Contains data classes for notification services.
"""

from dataclasses import dataclass, field
from typing import Any


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
    title: str | None = None
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
    episode: int | None
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
        torrent_id: Torrent hash identifier.
        torrent_name: Original torrent name.
        subtitle_group: Subtitle group name.
        tvdb_used: Whether TVDB was used for renaming.
        hardlink_path: Full hardlink target path.
        rename_examples: List of rename examples (up to 3).
    """
    anime_title: str
    season: int
    video_count: int
    subtitle_count: int
    target_dir: str
    rename_method: str
    torrent_id: str = ''
    torrent_name: str = ''
    subtitle_group: str = ''
    tvdb_used: bool = False
    hardlink_path: str = ''
    rename_examples: list[str] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        """Return total number of files processed."""
        return self.video_count + self.subtitle_count

    @property
    def total_hardlinks(self) -> int:
        """Return total number of hardlinks created."""
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
    context: dict[str, Any] = field(default_factory=dict)
    severity: str = 'error'

    @property
    def is_critical(self) -> bool:
        """Check if this is a critical error."""
        return self.severity == 'critical'


@dataclass
class AIUsageNotification:
    """
    AI usage notification data.

    Attributes:
        reason: Why AI was used (e.g., 'No database patterns', 'Multi-season content').
        project_name: Anime title/project name.
        context: Processing context ('rss' or 'webhook').
        operation: Operation type ('title_parsing' or 'file_renaming').
    """
    reason: str
    project_name: str
    context: str
    operation: str


@dataclass
class RSSTaskNotification:
    """
    Individual RSS download task notification data.

    Sent immediately when a download task is added.

    Attributes:
        project_name: Clean anime title.
        hash_id: Torrent hash identifier.
        anime_title: Original parsed title.
        subtitle_group: Subtitle group name.
        download_path: Download save path.
        season: Season number.
        episode: Episode number (if applicable).
    """
    project_name: str
    hash_id: str
    anime_title: str
    subtitle_group: str
    download_path: str
    season: int = 1
    episode: int | None = None


@dataclass
class RSSInterruptedNotification:
    """
    RSS processing interrupted notification data.

    Attributes:
        trigger_type: Type of trigger (e.g., 'scheduled', 'manual').
        rss_url: URL of the RSS feed being processed.
        processed_count: Number of items processed before interruption.
        total_count: Total number of items in the feed.
        reason: Reason for interruption.
    """
    trigger_type: str
    rss_url: str
    processed_count: int
    total_count: int
    reason: str


@dataclass
class WebhookReceivedNotification:
    """
    Webhook received notification data.

    Attributes:
        torrent_id: Torrent hash identifier.
        save_path: Save path from webhook.
        content_path: Content path from webhook.
        torrent_name: Torrent name.
    """
    torrent_id: str
    save_path: str
    content_path: str
    torrent_name: str
