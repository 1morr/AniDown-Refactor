"""
基础设施层模块。

提供外部服务集成实现，包括：
- AI 服务（OpenAI API 客户端、Key Pool、熔断器）
- 通知服务（Discord Webhook）
- 仓储实现（数据库访问）
"""

from src.infrastructure.ai import (
    AITitleParser,
    APIResponse,
    CircuitBreaker,
    KeyPool,
    KeyReservation,
    KeySpec,
    KeyState,
    KeyUsage,
    OpenAIClient,
)
from src.infrastructure.notification.discord import (
    DiscordNotifier,
    DiscordWebhookClient,
    EmbedBuilder,
)

__all__ = [
    # AI
    'OpenAIClient',
    'APIResponse',
    'KeyPool',
    'KeySpec',
    'KeyReservation',
    'KeyState',
    'KeyUsage',
    'CircuitBreaker',
    'AITitleParser',
    # Discord Notification
    'DiscordWebhookClient',
    'EmbedBuilder',
    'DiscordNotifier',
]
