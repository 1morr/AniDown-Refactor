"""
Discord RSS 通知实现模块。

实现 IRSSNotifier 接口。
"""

import logging
from typing import Any, Dict, List, Optional

from src.core.interfaces.notifications import (
    IRSSNotifier,
    RSSNotification,
    RSSTaskNotification,
    RSSInterruptedNotification,
)

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
        logger.info(f'🔔 [RSSNotifier] 构建开始通知 Embed: {notification.rss_url[:50]}...')
        embed = self._embed_builder.build_rss_start_embed(
            trigger_type=notification.trigger_type,
            rss_url=notification.rss_url,
            title=notification.title
        )

        logger.info('🔔 [RSSNotifier] 发送开始通知到 rss 频道')
        response = self._client.send(embeds=[embed], channel_type='rss')

        if response.success:
            logger.info('✅ [RSSNotifier] RSS 开始通知发送成功')
        else:
            logger.warning(
                f'⚠️ RSS 开始通知发送失败: {response.error_message}'
            )

    def notify_processing_complete(
        self,
        success_count: int,
        total_count: int,
        failed_items: List[Dict[str, Any]],
        attempt_count: int = 0,
        status: str = 'completed'
    ) -> None:
        """
        通知 RSS 处理完成。

        Args:
            success_count: 成功数量
            total_count: 总数量
            failed_items: 失败项目列表
            attempt_count: 尝试数量（成功 + 失败）
            status: 状态（'completed', 'partial', 'failed', 'interrupted'）
        """
        # 如果未提供 attempt_count，则使用旧的计算方式
        if attempt_count == 0:
            attempt_count = success_count + len(failed_items)

        logger.info(f'🔔 [RSSNotifier] 构建完成通知 Embed: 成功={success_count}, 总数={total_count}')
        embed = self._embed_builder.build_rss_complete_embed_enhanced(
            success_count=success_count,
            total_count=total_count,
            attempt_count=attempt_count,
            status=status,
            failed_items=failed_items
        )

        logger.info('🔔 [RSSNotifier] 发送完成通知到 rss 频道')
        response = self._client.send(embeds=[embed], channel_type='rss')

        if response.success:
            logger.info('✅ [RSSNotifier] RSS 完成通知发送成功')
        else:
            logger.warning(
                f'⚠️ RSS 完成通知发送失败: {response.error_message}'
            )

    def notify_download_task(self, notification: RSSTaskNotification) -> None:
        """
        通知单个下载任务已添加（即时发送）。

        Args:
            notification: RSS 任务通知数据
        """
        embed = self._embed_builder.build_rss_task_embed(
            project_name=notification.project_name,
            hash_id=notification.hash_id,
            anime_title=notification.anime_title,
            subtitle_group=notification.subtitle_group,
            download_path=notification.download_path
        )

        response = self._client.send(embeds=[embed], channel_type='rss')

        if not response.success:
            logger.warning(
                f'⚠️ RSS 任务通知发送失败: {response.error_message}'
            )

    def notify_processing_interrupted(
        self,
        notification: RSSInterruptedNotification
    ) -> None:
        """
        通知 RSS 处理已中断。

        Args:
            notification: RSS 中断通知数据
        """
        embed = self._embed_builder.build_rss_interrupted_embed(
            trigger_type=notification.trigger_type,
            rss_url=notification.rss_url,
            processed_count=notification.processed_count,
            total_count=notification.total_count,
            reason=notification.reason
        )

        response = self._client.send(embeds=[embed], channel_type='rss')

        if not response.success:
            logger.warning(
                f'⚠️ RSS 中断通知发送失败: {response.error_message}'
            )
