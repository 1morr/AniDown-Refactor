"""
Download notification service.

Handles all Discord notifications for download-related events.
"""

import logging

from src.core.interfaces.notifications import (
    AIUsageNotification,
    DownloadNotification,
    ErrorNotification,
    HardlinkNotification,
    RSSNotification,
    RSSTaskNotification,
    WebhookReceivedNotification,
)
from src.infrastructure.notification.discord.discord_notifier import DiscordNotifier

logger = logging.getLogger(__name__)


class DownloadNotifier:
    """
    Unified download notification service.

    Provides a clean interface for all download-related notifications,
    encapsulating the Discord notifier and handling errors gracefully.
    """

    def __init__(self, discord_notifier: DiscordNotifier | None = None):
        """
        Initialize the download notifier.

        Args:
            discord_notifier: Optional Discord notifier instance.
        """
        self._notifier = discord_notifier

    @property
    def notifier(self) -> DiscordNotifier | None:
        """Get the underlying notifier for direct access if needed."""
        return self._notifier

    def notify_ai_usage(
        self,
        reason: str,
        project_name: str,
        context: str = 'webhook',
        operation: str = 'file_renaming'
    ) -> None:
        """
        Send AI usage notification.

        Args:
            reason: Reason for using AI.
            project_name: Anime title being processed.
            context: Context where AI was used ('webhook', 'rss', etc.).
            operation: Operation type ('file_renaming', 'title_parsing', etc.).
        """
        if not self._notifier:
            return

        try:
            self._notifier.notify_ai_usage(
                AIUsageNotification(
                    reason=reason,
                    project_name=project_name,
                    context=context,
                    operation=operation
                )
            )
        except Exception as e:
            logger.warning(f'⚠️ 发送AI使用通知失败: {e}')

    def notify_download_start(
        self,
        anime_title: str,
        season: int,
        episode: int | None,
        subtitle_group: str,
        hash_id: str
    ) -> None:
        """
        Send download start notification.

        Args:
            anime_title: Anime title.
            season: Season number.
            episode: Episode number (optional).
            subtitle_group: Subtitle group name.
            hash_id: Torrent hash ID.
        """
        if not self._notifier:
            return

        try:
            notification = DownloadNotification(
                anime_title=anime_title,
                season=season,
                episode=episode,
                subtitle_group=subtitle_group,
                hash_id=hash_id
            )
            self._notifier.notify_download_start(notification)
        except Exception as e:
            logger.warning(f'⚠️ 发送下载开始通知失败: {e}')

    def notify_download_task(
        self,
        project_name: str,
        hash_id: str,
        anime_title: str,
        subtitle_group: str,
        download_path: str,
        season: int = 1,
        episode: int | None = None
    ) -> None:
        """
        Send download task notification (immediate, per task).

        Args:
            project_name: Original project/torrent name.
            hash_id: Torrent hash ID.
            anime_title: Parsed anime title.
            subtitle_group: Subtitle group name.
            download_path: Download directory path.
            season: Season number.
            episode: Episode number (optional).
        """
        if not self._notifier:
            return

        try:
            self._notifier.notify_download_task(
                RSSTaskNotification(
                    project_name=project_name,
                    hash_id=hash_id or '',
                    anime_title=anime_title,
                    subtitle_group=subtitle_group,
                    download_path=download_path,
                    season=season,
                    episode=episode
                )
            )
        except Exception as e:
            logger.warning(f'⚠️ 发送下载任务通知失败: {e}')

    def notify_rss_start(self, trigger_type: str, rss_url: str) -> None:
        """
        Send RSS processing start notification.

        Args:
            trigger_type: How the processing was triggered.
            rss_url: RSS feed URL.
        """
        if not self._notifier:
            return

        try:
            self._notifier.notify_processing_start(
                RSSNotification(trigger_type=trigger_type, rss_url=rss_url)
            )
        except Exception as e:
            logger.warning(f'⚠️ 发送RSS开始通知失败: {e}')

    def notify_completion(
        self,
        success_count: int,
        total_count: int,
        failed_items: list[dict[str, str]],
        attempt_count: int = 0
    ) -> None:
        """
        Send RSS processing completion notification.

        Args:
            success_count: Number of successful items.
            total_count: Total number of items found.
            failed_items: List of failed items with reasons.
            attempt_count: Number of items attempted.
        """
        logger.info(f'📤 准备发送RSS完成通知: 成功={success_count}, 总数={total_count}')

        if not self._notifier:
            logger.warning('⚠️ RSS通知器未配置，无法发送完成通知')
            return

        try:
            # Calculate attempt count if not provided
            if attempt_count == 0:
                attempt_count = success_count + len(failed_items)

            # Determine status
            if len(failed_items) > 0 and success_count == 0:
                status = 'failed'
            elif len(failed_items) > 0:
                status = 'partial'
            else:
                status = 'completed'

            logger.debug(f'📤 发送完成通知: status={status}, attempt={attempt_count}')
            self._notifier.notify_processing_complete(
                success_count=success_count,
                total_count=total_count,
                failed_items=failed_items,
                attempt_count=attempt_count,
                status=status
            )
            logger.debug('✅ RSS完成通知发送成功')
        except Exception as e:
            logger.warning(f'⚠️ 发送完成通知失败: {e}')

    def notify_webhook_received(
        self,
        torrent_id: str,
        save_path: str,
        content_path: str,
        torrent_name: str
    ) -> None:
        """
        Send webhook received notification.

        Args:
            torrent_id: Torrent hash ID.
            save_path: Save path from webhook.
            content_path: Content path from webhook.
            torrent_name: Torrent name from webhook.
        """
        if not self._notifier:
            return

        try:
            self._notifier.notify_webhook_received(
                WebhookReceivedNotification(
                    torrent_id=torrent_id,
                    save_path=save_path,
                    content_path=content_path or save_path,
                    torrent_name=torrent_name
                )
            )
        except Exception as e:
            logger.warning(f'⚠️ 发送webhook接收通知失败: {e}')

    def notify_hardlink_created(
        self,
        anime_title: str,
        season: int,
        video_count: int,
        subtitle_count: int,
        target_dir: str,
        rename_method: str,
        torrent_id: str,
        torrent_name: str,
        subtitle_group: str,
        tvdb_used: bool,
        hardlink_path: str,
        rename_examples: list[str]
    ) -> None:
        """
        Send hardlink creation success notification.

        Args:
            anime_title: Anime title.
            season: Season number.
            video_count: Number of video hardlinks created.
            subtitle_count: Number of subtitle files.
            target_dir: Target directory for hardlinks.
            rename_method: Method used for renaming.
            torrent_id: Torrent hash ID.
            torrent_name: Original torrent name.
            subtitle_group: Subtitle group name.
            tvdb_used: Whether TVDB was used.
            hardlink_path: Full hardlink path.
            rename_examples: List of rename examples.
        """
        if not self._notifier:
            return

        try:
            notification = HardlinkNotification(
                anime_title=anime_title,
                season=season,
                video_count=video_count,
                subtitle_count=subtitle_count,
                target_dir=target_dir,
                rename_method=rename_method,
                torrent_id=torrent_id,
                torrent_name=torrent_name,
                subtitle_group=subtitle_group,
                tvdb_used=tvdb_used,
                hardlink_path=hardlink_path,
                rename_examples=rename_examples
            )
            self._notifier.notify_hardlink_created(notification)
        except Exception as e:
            logger.error(f'发送硬链接创建通知失败: {e}')

    def notify_hardlink_failed(
        self,
        anime_title: str,
        season: int,
        target_dir: str,
        rename_method: str,
        torrent_id: str,
        torrent_name: str,
        subtitle_group: str,
        error_message: str,
        source_path: str | None = None
    ) -> None:
        """
        Send hardlink creation failure notification.

        Args:
            anime_title: Anime title.
            season: Season number.
            target_dir: Target directory for hardlinks.
            rename_method: Method used for renaming.
            torrent_id: Torrent hash ID.
            torrent_name: Original torrent name.
            subtitle_group: Subtitle group name.
            error_message: Error message describing the failure.
            source_path: Source file path (optional).
        """
        if not self._notifier:
            return

        try:
            notification = HardlinkNotification(
                anime_title=anime_title,
                season=season,
                video_count=0,
                subtitle_count=0,
                target_dir=target_dir,
                rename_method=rename_method,
                torrent_id=torrent_id,
                torrent_name=torrent_name,
                subtitle_group=subtitle_group,
                tvdb_used=False,
                hardlink_path=target_dir,
                rename_examples=[]
            )
            self._notifier.notify_hardlink_failed(
                notification=notification,
                error_message=error_message,
                source_path=source_path
            )
        except Exception as e:
            logger.error(f'发送硬链接失败通知失败: {e}')

    def notify_error(self, message: str, error_type: str = '错误') -> None:
        """
        Send error notification.

        Args:
            message: Error message.
            error_type: Type of error.
        """
        if not self._notifier:
            return

        try:
            self._notifier.notify_error(ErrorNotification(
                error_type=error_type,
                error_message=message
            ))
        except Exception as e:
            logger.warning(f'⚠️ 发送错误通知失败: {e}')
