"""
Discord 通知模块。

提供 Discord Webhook 集成，包括：
- Webhook 客户端（HTTP 通信）
- Embed 构建器（消息格式化）
- 统一的 Discord 通知器（整合所有通知类型）
"""

from src.infrastructure.notification.discord.discord_notifier import DiscordNotifier
from src.infrastructure.notification.discord.embed_builder import EmbedBuilder
from src.infrastructure.notification.discord.webhook_client import DiscordWebhookClient

__all__ = [
    'DiscordWebhookClient',
    'EmbedBuilder',
    'DiscordNotifier',
]
