"""
Discord Webhook 客户端模块。

提供 Discord Webhook 的 HTTP 通信功能。
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class WebhookResponse:
    """
    Webhook 响应数据类。

    Attributes:
        success: 请求是否成功
        status_code: HTTP 状态码
        error_message: 错误消息（失败时）
    """
    success: bool
    status_code: Optional[int] = None
    error_message: Optional[str] = None


class DiscordWebhookClient:
    """
    Discord Webhook 客户端。

    只负责 HTTP 通信，不包含消息格式化逻辑。
    遵循单一职责原则 (SRP)。

    Example:
        >>> client = DiscordWebhookClient()
        >>> client.configure({
        ...     'rss': 'https://discord.com/api/webhooks/xxx/yyy',
        ...     'download': 'https://discord.com/api/webhooks/xxx/zzz'
        ... })
        >>> response = client.send(
        ...     embeds=[{'title': 'Test', 'description': 'Hello'}],
        ...     channel_type='rss'
        ... )
    """

    def __init__(self, timeout: int = 10):
        """
        初始化客户端。

        Args:
            timeout: 请求超时时间（秒），默认 10 秒
        """
        self._timeout = timeout
        self._webhooks: Dict[str, str] = {}
        self._enabled = True

    def configure(
        self,
        webhooks: Dict[str, str],
        enabled: bool = True
    ) -> None:
        """
        配置 Webhook URLs。

        Args:
            webhooks: {channel_type: webhook_url} 映射
            enabled: 是否启用通知
        """
        self._webhooks = webhooks
        self._enabled = enabled
        logger.info(
            f'🔔 配置 Discord Webhook: {len(webhooks)} 个频道, '
            f'启用: {enabled}'
        )

    def send(
        self,
        embeds: List[Dict[str, Any]],
        channel_type: str = 'default',
        content: Optional[str] = None,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> WebhookResponse:
        """
        发送消息到 Discord。

        Args:
            embeds: Embed 列表
            channel_type: 频道类型（对应配置的 key）
            content: 普通文本内容（可选）
            username: 自定义用户名（可选）
            avatar_url: 自定义头像 URL（可选）

        Returns:
            WebhookResponse: 响应结果
        """
        if not self._enabled:
            logger.debug('🔕 Discord 通知已禁用，跳过发送')
            return WebhookResponse(success=True)

        webhook_url = self._webhooks.get(channel_type)
        if not webhook_url:
            # 尝试使用默认频道
            webhook_url = self._webhooks.get('default')

        if not webhook_url:
            logger.warning(
                f'⚠️ 未配置 Discord Webhook: {channel_type}'
            )
            return WebhookResponse(
                success=False,
                error_message=f'Webhook not configured for: {channel_type}'
            )

        payload: Dict[str, Any] = {}

        if content:
            payload['content'] = content

        if embeds:
            payload['embeds'] = embeds

        if username:
            payload['username'] = username

        if avatar_url:
            payload['avatar_url'] = avatar_url

        try:
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=self._timeout
            )

            if response.status_code in (200, 204):
                logger.debug(f'✅ Discord 消息发送成功: {channel_type}')
                return WebhookResponse(
                    success=True,
                    status_code=response.status_code
                )
            else:
                error_msg = response.text[:200] if response.text else f'HTTP {response.status_code}'
                logger.warning(
                    f'⚠️ Discord 消息发送失败: {response.status_code}, '
                    f'{error_msg}'
                )
                return WebhookResponse(
                    success=False,
                    status_code=response.status_code,
                    error_message=error_msg
                )

        except requests.Timeout:
            logger.error(f'❌ Discord Webhook 超时: {self._timeout}s')
            return WebhookResponse(
                success=False,
                error_message=f'Request timeout after {self._timeout}s'
            )

        except requests.RequestException as e:
            logger.error(f'❌ Discord Webhook 请求失败: {e}')
            return WebhookResponse(
                success=False,
                error_message=str(e)
            )

        except Exception as e:
            logger.exception(f'❌ Discord Webhook 未预期错误: {e}')
            return WebhookResponse(
                success=False,
                error_message=str(e)
            )

    def is_enabled(self) -> bool:
        """检查通知是否启用。"""
        return self._enabled

    def is_configured(self, channel_type: str) -> bool:
        """检查指定频道是否已配置。"""
        return channel_type in self._webhooks or 'default' in self._webhooks
