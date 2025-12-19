"""
Discord RSS 通知实现模块。

实现 IRSSNotifier 接口。
"""

import logging
from typing import Any, Dict, List, Optional

from src.core.interfaces.notifications import IRSSNotifier, RSSNotification

from .embed_builder import EmbedBuilder
from .webhook_client import DiscordWebhookClient

logger = logging.getLogger(__name__)


class DiscordRSSNotifier(IRSSNotifier):
    """
    Discord RSS 通知实现。

    实现 IRSSNotifier 接口，通过 Discord Webhook 发送 RSS 相关通知。

    Example:
        >>> notifier = DiscordRSSNotifier(webhook_client)
        >>> notifier.notify_processing_start(RSSNotification(
        ...     trigger_type='定时触发',
        ...     rss_url='https://example.com/rss'
        ... ))
    """

    def __init__(
        self,
        webhook_client: DiscordWebhookClient,
        embed_builder: Optional[EmbedBuilder] = None
    ):
        """
        初始化 RSS 通知器。

        Args:
            webhook_client: Discord Webhook 客户端
            embed_builder: Embed 构建器（可选）
        """
        self._client = webhook_client
        self._embed_builder = embed_builder or EmbedBuilder()

    def notify_processing_start(self, notification: RSSNotification) -> None:
        """
        通知 RSS 处理开始。

        Args:
            notification: RSS 通知数据
        """
        embed = self._embed_builder.build_rss_start_embed(
            trigger_type=notification.trigger_type,
            rss_url=notification.rss_url,
            title=notification.title
        )

        response = self._client.send(embeds=[embed], channel_type='rss')

        if not response.success:
            logger.warning(
                f'⚠️ RSS 开始通知发送失败: {response.error_message}'
            )

    def notify_processing_complete(
        self,
        success_count: int,
        total_count: int,
        failed_items: List[Dict[str, Any]]
    ) -> None:
        """
        通知 RSS 处理完成。

        Args:
            success_count: 成功数量
            total_count: 总数量
            failed_items: 失败项目列表
        """
        embed = self._embed_builder.build_rss_complete_embed(
            success_count=success_count,
            total_count=total_count,
            failed_items=failed_items
        )

        response = self._client.send(embeds=[embed], channel_type='rss')

        if not response.success:
            logger.warning(
                f'⚠️ RSS 完成通知发送失败: {response.error_message}'
            )
