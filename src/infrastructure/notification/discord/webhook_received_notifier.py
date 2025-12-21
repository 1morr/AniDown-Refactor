"""
Discord Webhook 接收通知实现模块。

实现 IWebhookNotifier 接口。
"""

import logging
from typing import Optional

from src.core.interfaces.notifications import IWebhookNotifier, WebhookReceivedNotification

from .embed_builder import EmbedBuilder
from .webhook_client import DiscordWebhookClient

logger = logging.getLogger(__name__)


class DiscordWebhookReceivedNotifier(IWebhookNotifier):
    """
    Discord Webhook 接收通知实现。

    实现 IWebhookNotifier 接口，通过 Discord Webhook 发送 Webhook 接收相关通知。

    Example:
        >>> notifier = DiscordWebhookReceivedNotifier(webhook_client)
        >>> notifier.notify_webhook_received(WebhookReceivedNotification(
        ...     torrent_id='abc123def456',
        ...     save_path='/downloads/anime',
        ...     content_path='/downloads/anime/[ANi] Anime Title',
        ...     torrent_name='[ANi] Anime Title - 01 [1080P].mkv'
        ... ))
    """

    def __init__(
        self,
        webhook_client: DiscordWebhookClient,
        embed_builder: Optional[EmbedBuilder] = None
    ):
        """
        初始化 Webhook 接收通知器。

        Args:
            webhook_client: Discord Webhook 客户端
            embed_builder: Embed 构建器（可选）
        """
        self._client = webhook_client
        self._embed_builder = embed_builder or EmbedBuilder()

    def notify_webhook_received(
        self,
        notification: WebhookReceivedNotification
    ) -> None:
        """
        通知收到了 Webhook。

        发送到 'hardlink' 频道。

        Args:
            notification: Webhook 接收通知数据
        """
        embed = self._embed_builder.build_webhook_received_embed(
            torrent_id=notification.torrent_id,
            save_path=notification.save_path,
            content_path=notification.content_path,
            torrent_name=notification.torrent_name
        )

        response = self._client.send(embeds=[embed], channel_type='hardlink')

        if not response.success:
            logger.warning(
                f'⚠️ Webhook 接收通知发送失败: {response.error_message}'
            )
