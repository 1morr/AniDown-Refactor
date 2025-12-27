"""
Discord 下载通知实现模块。

实现 IDownloadNotifier 接口。
"""

import logging

from src.core.interfaces.notifications import DownloadNotification, IDownloadNotifier

from .embed_builder import EmbedBuilder
from .webhook_client import DiscordWebhookClient

logger = logging.getLogger(__name__)


class DiscordDownloadNotifier(IDownloadNotifier):
    """
    Discord 下载通知实现。

    实现 IDownloadNotifier 接口，通过 Discord Webhook 发送下载相关通知。

    Example:
        >>> notifier = DiscordDownloadNotifier(webhook_client)
        >>> notifier.notify_download_start(DownloadNotification(
        ...     anime_title='葬送的芙莉莲',
        ...     season=1,
        ...     episode=24,
        ...     subtitle_group='喵萌奶茶屋',
        ...     hash_id='abc123...'
        ... ))
    """

    def __init__(
        self,
        webhook_client: DiscordWebhookClient,
        embed_builder: EmbedBuilder | None = None
    ):
        """
        初始化下载通知器。

        Args:
            webhook_client: Discord Webhook 客户端
            embed_builder: Embed 构建器（可选）
        """
        self._client = webhook_client
        self._embed_builder = embed_builder or EmbedBuilder()

    def notify_download_start(self, notification: DownloadNotification) -> None:
        """
        通知下载开始。

        Args:
            notification: 下载通知数据
        """
        embed = self._embed_builder.build_download_start_embed(
            anime_title=notification.anime_title,
            season=notification.season,
            episode=notification.episode,
            subtitle_group=notification.subtitle_group,
            hash_id=notification.hash_id
        )

        response = self._client.send(embeds=[embed], channel_type='download')

        if not response.success:
            logger.warning(
                f'⚠️ 下载开始通知发送失败: {response.error_message}'
            )

    def notify_download_complete(self, notification: DownloadNotification) -> None:
        """
        通知下载完成。

        Args:
            notification: 下载通知数据
        """
        embed = self._embed_builder.build_download_complete_embed(
            anime_title=notification.anime_title,
            season=notification.season,
            episode=notification.episode,
            subtitle_group=notification.subtitle_group,
            hash_id=notification.hash_id
        )

        response = self._client.send(embeds=[embed], channel_type='download')

        if not response.success:
            logger.warning(
                f'⚠️ 下载完成通知发送失败: {response.error_message}'
            )

    def notify_download_failed(
        self,
        notification: DownloadNotification,
        error_message: str
    ) -> None:
        """
        通知下载失败。

        Args:
            notification: 下载通知数据
            error_message: 错误消息
        """
        embed = self._embed_builder.build_download_failed_embed(
            anime_title=notification.anime_title,
            error_message=error_message,
            hash_id=notification.hash_id
        )

        response = self._client.send(embeds=[embed], channel_type='download')

        if not response.success:
            logger.warning(
                f'⚠️ 下载失败通知发送失败: {response.error_message}'
            )
