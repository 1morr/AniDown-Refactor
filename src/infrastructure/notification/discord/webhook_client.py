"""
Discord Webhook 客户端模块。

提供 Discord Webhook 的 HTTP 通信功能。
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

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
    status_code: int | None = None
    error_message: str | None = None


class DiscordWebhookClient:
    """
    Discord Webhook 客户端。

    只负责 HTTP 通信，不包含消息格式化逻辑。
    遵循单一职责原则 (SRP)。

    Features:
        - Rate Limit 自动处理（429 响应时等待 Retry-After 后重试）
        - 指数退避重试机制（网络错误时自动重试）
        - 最大重试次数限制

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

    # Rate Limit 和重试配置
    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 1.0  # 基础重试延迟（秒）
    MAX_RETRY_DELAY = 30.0  # 最大重试延迟（秒）

    def __init__(self, timeout: int = 10):
        """
        初始化客户端。

        Args:
            timeout: 请求超时时间（秒），默认 10 秒
        """
        self._timeout = timeout
        self._webhooks: dict[str, str] = {}
        self._enabled = True

    def configure(
        self,
        webhooks: dict[str, str],
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
        embeds: list[dict[str, Any]],
        channel_type: str = 'default',
        content: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None
    ) -> WebhookResponse:
        """
        发送消息到 Discord（带重试机制）。

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

        payload: dict[str, Any] = {}

        if content:
            payload['content'] = content

        if embeds:
            payload['embeds'] = embeds

        if username:
            payload['username'] = username

        if avatar_url:
            payload['avatar_url'] = avatar_url

        # 带重试的发送
        return self._send_with_retry(webhook_url, payload, channel_type)

    def _send_with_retry(
        self,
        webhook_url: str,
        payload: dict[str, Any],
        channel_type: str
    ) -> WebhookResponse:
        """
        带重试机制的发送实现。

        处理:
        - 429 Rate Limit: 等待 Retry-After 后重试
        - 5xx 服务器错误: 指数退避重试
        - 网络错误: 指数退避重试

        Args:
            webhook_url: Webhook URL
            payload: 请求负载
            channel_type: 频道类型（用于日志）

        Returns:
            WebhookResponse: 响应结果
        """
        last_error: str | None = None
        last_status_code: int | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = requests.post(
                    webhook_url,
                    json=payload,
                    timeout=self._timeout
                )

                # 成功
                if response.status_code in (200, 204):
                    if attempt > 0:
                        logger.info(
                            f'✅ Discord 消息发送成功 (第 {attempt + 1} 次尝试): '
                            f'{channel_type}'
                        )
                    else:
                        logger.debug(f'✅ Discord 消息发送成功: {channel_type}')
                    return WebhookResponse(
                        success=True,
                        status_code=response.status_code
                    )

                # Rate Limit (429)
                if response.status_code == 429:
                    retry_after = self._get_retry_after(response)
                    if attempt < self.MAX_RETRIES:
                        logger.warning(
                            f'⏳ Discord Rate Limit，等待 {retry_after:.1f}s 后重试 '
                            f'(第 {attempt + 1}/{self.MAX_RETRIES + 1} 次)'
                        )
                        time.sleep(retry_after)
                        continue
                    else:
                        logger.error(
                            '❌ Discord Rate Limit，已达最大重试次数'
                        )
                        return WebhookResponse(
                            success=False,
                            status_code=429,
                            error_message='Rate limited, max retries exceeded'
                        )

                # 服务器错误 (5xx) - 可重试
                if response.status_code >= 500:
                    last_status_code = response.status_code
                    last_error = f'Server error: {response.status_code}'
                    if attempt < self.MAX_RETRIES:
                        delay = self._calculate_backoff_delay(attempt)
                        logger.warning(
                            f'⚠️ Discord 服务器错误 {response.status_code}，'
                            f'{delay:.1f}s 后重试 '
                            f'(第 {attempt + 1}/{self.MAX_RETRIES + 1} 次)'
                        )
                        time.sleep(delay)
                        continue

                # 其他错误 - 不重试
                error_msg = (
                    response.text[:200] if response.text
                    else f'HTTP {response.status_code}'
                )
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
                last_error = f'Request timeout after {self._timeout}s'
                if attempt < self.MAX_RETRIES:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        f'⏱️ Discord Webhook 超时，{delay:.1f}s 后重试 '
                        f'(第 {attempt + 1}/{self.MAX_RETRIES + 1} 次)'
                    )
                    time.sleep(delay)
                    continue

            except requests.RequestException as e:
                last_error = str(e)
                if attempt < self.MAX_RETRIES:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        f'🔄 Discord Webhook 请求失败: {e}，{delay:.1f}s 后重试 '
                        f'(第 {attempt + 1}/{self.MAX_RETRIES + 1} 次)'
                    )
                    time.sleep(delay)
                    continue

            except Exception as e:
                logger.exception(f'❌ Discord Webhook 未预期错误: {e}')
                return WebhookResponse(
                    success=False,
                    error_message=str(e)
                )

        # 所有重试都失败
        logger.error(
            f'❌ Discord Webhook 发送失败，已达最大重试次数: {last_error}'
        )
        return WebhookResponse(
            success=False,
            status_code=last_status_code,
            error_message=last_error or 'Max retries exceeded'
        )

    def _get_retry_after(self, response: requests.Response) -> float:
        """
        从响应中获取 Retry-After 延迟时间。

        Args:
            response: HTTP 响应

        Returns:
            等待时间（秒）
        """
        # 尝试从 header 获取
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        # 尝试从 JSON body 获取
        try:
            data = response.json()
            if 'retry_after' in data:
                return float(data['retry_after'])
        except (ValueError, KeyError):
            pass

        # 默认等待时间
        return 5.0

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        计算指数退避延迟时间。

        Args:
            attempt: 当前尝试次数（从 0 开始）

        Returns:
            延迟时间（秒）
        """
        delay = self.BASE_RETRY_DELAY * (2 ** attempt)
        return min(delay, self.MAX_RETRY_DELAY)

    def is_enabled(self) -> bool:
        """检查通知是否启用。"""
        return self._enabled

    def is_configured(self, channel_type: str) -> bool:
        """检查指定频道是否已配置。"""
        return channel_type in self._webhooks or 'default' in self._webhooks
