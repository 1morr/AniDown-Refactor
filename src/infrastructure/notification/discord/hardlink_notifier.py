"""
Discord 硬链接通知实现模块。

实现 IHardlinkNotifier 接口。
"""

import logging
from typing import Optional

from src.core.interfaces.notifications import IHardlinkNotifier, HardlinkNotification

from .embed_builder import EmbedBuilder
from .webhook_client import DiscordWebhookClient

logger = logging.getLogger(__name__)


class DiscordHardlinkNotifier(IHardlinkNotifier):
    """
    Discord 硬链接通知实现。

    实现 IHardlinkNotifier 接口，通过 Discord Webhook 发送硬链接相关通知。

    Example:
        >>> notifier = DiscordHardlinkNotifier(webhook_client)
        >>> notifier.notify_hardlink_created(HardlinkNotification(
        ...     anime_title='葬送的芙莉莲',
        ...     season=1,
        ...     video_count=24,
        ...     subtitle_count=24,
        ...     target_dir='/media/anime/葬送的芙莉莲/Season 01',
        ...     rename_method='AI'
        ... ))
    """

    def __init__(
        self,
        webhook_client: DiscordWebhookClient,
        embed_builder: Optional[EmbedBuilder] = None
    ):
        """
        初始化硬链接通知器。

        Args:
            webhook_client: Discord Webhook 客户端
            embed_builder: Embed 构建器（可选）
        """
        self._client = webhook_client
        self._embed_builder = embed_builder or EmbedBuilder()

    def notify_hardlink_created(self, notification: HardlinkNotification) -> None:
        """
        通知硬链接创建成功。

        Args:
            notification: 硬链接通知数据
        """
        embed = self._embed_builder.build_hardlink_created_embed(
            anime_title=notification.anime_title,
            season=notification.season,
            video_count=notification.video_count,
            subtitle_count=notification.subtitle_count,
            target_dir=notification.target_dir,
            rename_method=notification.rename_method
        )

        response = self._client.send(embeds=[embed], channel_type='hardlink')

        if not response.success:
            logger.warning(
                f'⚠️ 硬链接创建通知发送失败: {response.error_message}'
            )

    def notify_hardlink_failed(
        self,
        notification: HardlinkNotification,
        error_message: str,
        source_path: Optional[str] = None,
        target_path: Optional[str] = None
    ) -> None:
        """
        通知硬链接创建失败。

        Args:
            notification: 硬链接通知数据
            error_message: 错误消息
            source_path: 源路径（可选）
            target_path: 目标路径（可选）
        """
        embed = self._embed_builder.build_hardlink_failed_embed(
            anime_title=notification.anime_title,
            error_message=error_message,
            source_path=source_path,
            target_path=target_path
        )

        response = self._client.send(embeds=[embed], channel_type='hardlink')

        if not response.success:
            logger.warning(
                f'⚠️ 硬链接失败通知发送失败: {response.error_message}'
            )
