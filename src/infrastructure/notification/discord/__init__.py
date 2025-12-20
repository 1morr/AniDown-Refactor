"""
Discord 通知模块。

提供 Discord Webhook 集成，包括：
- Webhook 客户端（HTTP 通信）
- Embed 构建器（消息格式化）
- 各类通知实现（RSS、下载、硬链接、错误）
"""

from src.infrastructure.notification.discord.download_notifier import (
    DiscordDownloadNotifier,
)
from src.infrastructure.notification.discord.embed_builder import EmbedBuilder
from src.infrastructure.notification.discord.error_notifier import DiscordErrorNotifier
from src.infrastructure.notification.discord.hardlink_notifier import (
    DiscordHardlinkNotifier,
)
from src.infrastructure.notification.discord.rss_notifier import DiscordRSSNotifier
from src.infrastructure.notification.discord.webhook_client import DiscordWebhookClient

__all__ = [
    'DiscordWebhookClient',
    'EmbedBuilder',
    'DiscordRSSNotifier',
    'DiscordDownloadNotifier',
    'DiscordHardlinkNotifier',
    'DiscordErrorNotifier',
]
