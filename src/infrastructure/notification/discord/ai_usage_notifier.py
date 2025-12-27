"""
Discord AI 使用通知实现模块。

实现 IAIUsageNotifier 接口。
"""

import logging

from src.core.interfaces.notifications import AIUsageNotification, IAIUsageNotifier

from .embed_builder import EmbedBuilder
from .webhook_client import DiscordWebhookClient

logger = logging.getLogger(__name__)


class DiscordAIUsageNotifier(IAIUsageNotifier):
    """
    Discord AI 使用通知实现。

    实现 IAIUsageNotifier 接口，通过 Discord Webhook 发送 AI 使用相关通知。

    Example:
        >>> notifier = DiscordAIUsageNotifier(webhook_client)
        >>> notifier.notify_ai_usage(AIUsageNotification(
        ...     reason='数据库中没有正则表达式',
        ...     project_name='葬送的芙莉莲',
        ...     context='webhook',
        ...     operation='file_renaming'
        ... ))
    """

    def __init__(
        self,
        webhook_client: DiscordWebhookClient,
        embed_builder: EmbedBuilder | None = None
    ):
        """
        初始化 AI 使用通知器。

        Args:
            webhook_client: Discord Webhook 客户端
            embed_builder: Embed 构建器（可选）
        """
        self._client = webhook_client
        self._embed_builder = embed_builder or EmbedBuilder()

    def notify_ai_usage(self, notification: AIUsageNotification) -> None:
        """
        通知 AI 正在被使用。

        根据上下文发送到对应的 Discord 频道：
        - 'rss' 上下文 → 'rss' 频道
        - 'webhook' 上下文 → 'hardlink' 频道

        Args:
            notification: AI 使用通知数据
        """
        embed = self._embed_builder.build_ai_usage_embed(
            reason=notification.reason,
            project_name=notification.project_name,
            context=notification.context,
            operation=notification.operation
        )

        # 根据上下文确定发送频道
        channel_type = 'rss' if notification.context == 'rss' else 'hardlink'

        response = self._client.send(embeds=[embed], channel_type=channel_type)

        if not response.success:
            logger.warning(
                f'⚠️ AI 使用通知发送失败: {response.error_message}'
            )
