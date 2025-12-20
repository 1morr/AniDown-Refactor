"""
Discord 错误通知实现模块。

实现 IErrorNotifier 接口。
"""

import logging
from typing import Any, Dict, Optional

from src.core.interfaces.notifications import IErrorNotifier, ErrorNotification

from .embed_builder import EmbedBuilder
from .webhook_client import DiscordWebhookClient

logger = logging.getLogger(__name__)


class DiscordErrorNotifier(IErrorNotifier):
    """
    Discord 错误通知实现。

    实现 IErrorNotifier 接口，通过 Discord Webhook 发送错误和警告通知。

    Example:
        >>> notifier = DiscordErrorNotifier(webhook_client)
        >>> notifier.notify_error(ErrorNotification(
        ...     error_type='AI处理错误',
        ...     error_message='无法解析标题',
        ...     context={'anime_title': '葬送的芙莉莲'}
        ... ))
    """

    def __init__(
        self,
        webhook_client: DiscordWebhookClient,
        embed_builder: Optional[EmbedBuilder] = None,
        default_channel: str = 'rss'
    ):
        """
        初始化错误通知器。

        Args:
            webhook_client: Discord Webhook 客户端
            embed_builder: Embed 构建器（可选）
            default_channel: 默认发送频道 ('rss' 或 'hardlink')
        """
        self._client = webhook_client
        self._embed_builder = embed_builder or EmbedBuilder()
        self._default_channel = default_channel

    def notify_error(self, notification: ErrorNotification) -> None:
        """
        发送错误通知。

        Args:
            notification: 错误通知数据
        """
        embed = self._embed_builder.build_error_embed(
            error_type=notification.error_type,
            error_message=notification.error_message,
            context=notification.context
        )

        # 根据上下文决定频道
        channel_type = self._determine_channel(notification.context)

        response = self._client.send(embeds=[embed], channel_type=channel_type)

        if not response.success:
            logger.warning(
                f'⚠️ 错误通知发送失败: {response.error_message}'
            )
        else:
            logger.debug(
                f'✅ 错误通知已发送: {notification.error_type}'
            )

    def notify_warning(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        发送警告通知。

        Args:
            message: 警告消息
            context: 可选的上下文信息
        """
        embed = self._embed_builder.build_warning_embed(
            warning_type='系统警告',
            warning_message=message,
            context=context
        )

        # 根据上下文决定频道
        channel_type = self._determine_channel(context)

        response = self._client.send(embeds=[embed], channel_type=channel_type)

        if not response.success:
            logger.warning(
                f'⚠️ 警告通知发送失败: {response.error_message}'
            )
        else:
            logger.debug(
                f'✅ 警告通知已发送: {message[:50]}...'
            )

    def send_simple_error(self, error_message: str) -> None:
        """
        发送简单的错误消息。

        兼容原始 send_error_info 方法。

        Args:
            error_message: 错误消息
        """
        response = self._client.send(
            content=f'❌ 处理出错: {error_message}',
            embeds=[],
            channel_type=self._default_channel
        )

        if not response.success:
            logger.warning(
                f'⚠️ 简单错误通知发送失败: {response.error_message}'
            )

    def send_detailed_error(
        self,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None,
        channel_type: Optional[str] = None
    ) -> None:
        """
        发送详细的错误通知。

        兼容原始 send_error_detail 方法。

        Args:
            error_type: 错误类型
            error_message: 错误消息
            context: 上下文信息（可选）
            channel_type: 频道类型（可选，默认使用 default_channel）
        """
        notification = ErrorNotification(
            error_type=error_type,
            error_message=error_message,
            context=context or {}
        )

        embed = self._embed_builder.build_error_embed(
            error_type=notification.error_type,
            error_message=notification.error_message,
            context=notification.context
        )

        target_channel = channel_type or self._default_channel

        response = self._client.send(embeds=[embed], channel_type=target_channel)

        if not response.success:
            logger.warning(
                f'⚠️ 详细错误通知发送失败: {response.error_message}'
            )

    def _determine_channel(
        self,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """
        根据上下文确定发送频道。

        Args:
            context: 上下文信息

        Returns:
            频道类型 ('rss' 或 'hardlink')
        """
        if not context:
            return self._default_channel

        # 如果上下文包含硬链接相关信息，使用 hardlink 频道
        hardlink_indicators = ['target_dir', 'source_path', 'hardlink']
        for key in hardlink_indicators:
            if key in context:
                return 'hardlink'

        return self._default_channel
