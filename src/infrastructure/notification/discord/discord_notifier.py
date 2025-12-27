"""
统一的 Discord 通知器模块。

整合所有 Discord 通知功能到一个类中，实现所有通知接口。
"""

import logging
from typing import Any

from src.core.interfaces.notifications import (
    AIUsageNotification,
    DownloadNotification,
    ErrorNotification,
    HardlinkNotification,
    IAIUsageNotifier,
    IDownloadNotifier,
    IErrorNotifier,
    IHardlinkNotifier,
    IRSSNotifier,
    IWebhookNotifier,
    RSSInterruptedNotification,
    RSSNotification,
    RSSTaskNotification,
    WebhookReceivedNotification,
)

from .embed_builder import EmbedBuilder
from .webhook_client import DiscordWebhookClient

logger = logging.getLogger(__name__)


class DiscordNotifier(
    IRSSNotifier,
    IDownloadNotifier,
    IHardlinkNotifier,
    IErrorNotifier,
    IAIUsageNotifier,
    IWebhookNotifier
):
    """
    统一的 Discord 通知器。

    整合了所有通知类型（RSS、下载、硬链接、错误、AI使用、Webhook接收）
    到一个类中，减少代码重复，简化依赖注入。

    实现接口:
    - IRSSNotifier: RSS 处理通知
    - IDownloadNotifier: 下载事件通知
    - IHardlinkNotifier: 硬链接创建通知
    - IErrorNotifier: 错误和警告通知
    - IAIUsageNotifier: AI 使用通知
    - IWebhookNotifier: Webhook 接收通知

    Example:
        >>> notifier = DiscordNotifier(webhook_client)
        >>> notifier.notify_processing_start(RSSNotification(...))
        >>> notifier.notify_download_start(DownloadNotification(...))
        >>> notifier.notify_hardlink_created(HardlinkNotification(...))
    """

    def __init__(
        self,
        webhook_client: DiscordWebhookClient,
        embed_builder: EmbedBuilder | None = None,
        default_error_channel: str = 'rss'
    ):
        """
        初始化统一通知器。

        Args:
            webhook_client: Discord Webhook 客户端
            embed_builder: Embed 构建器（可选，默认创建新实例）
            default_error_channel: 默认错误通知频道 ('rss' 或 'hardlink')
        """
        self._client = webhook_client
        self._embed_builder = embed_builder or EmbedBuilder()
        self._default_error_channel = default_error_channel

    # ========== IRSSNotifier 实现 ==========

    def notify_processing_start(self, notification: RSSNotification) -> None:
        """
        通知 RSS 处理开始。

        Args:
            notification: RSS 通知数据
        """
        logger.info(f'🔔 [Notifier] 构建 RSS 开始通知: {notification.rss_url[:50]}...')
        embed = self._embed_builder.build_rss_start_embed(
            trigger_type=notification.trigger_type,
            rss_url=notification.rss_url,
            title=notification.title
        )

        response = self._client.send(embeds=[embed], channel_type='rss')

        if response.success:
            logger.info('✅ [Notifier] RSS 开始通知发送成功')
        else:
            logger.warning(f'⚠️ RSS 开始通知发送失败: {response.error_message}')

    def notify_processing_complete(
        self,
        success_count: int,
        total_count: int,
        failed_items: list[dict[str, Any]],
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
        if attempt_count == 0:
            attempt_count = success_count + len(failed_items)

        logger.info(f'🔔 [Notifier] 构建 RSS 完成通知: 成功={success_count}, 总数={total_count}')
        embed = self._embed_builder.build_rss_complete_embed_enhanced(
            success_count=success_count,
            total_count=total_count,
            attempt_count=attempt_count,
            status=status,
            failed_items=failed_items
        )

        response = self._client.send(embeds=[embed], channel_type='rss')

        if response.success:
            logger.info('✅ [Notifier] RSS 完成通知发送成功')
        else:
            logger.warning(f'⚠️ RSS 完成通知发送失败: {response.error_message}')

    def notify_download_task(self, notification: RSSTaskNotification) -> None:
        """
        通知单个下载任务已添加。

        Args:
            notification: RSS 任务通知数据
        """
        embed = self._embed_builder.build_rss_task_embed(
            project_name=notification.project_name,
            hash_id=notification.hash_id,
            anime_title=notification.anime_title,
            subtitle_group=notification.subtitle_group,
            download_path=notification.download_path,
            season=notification.season,
            episode=notification.episode
        )

        response = self._client.send(embeds=[embed], channel_type='rss')

        if not response.success:
            logger.warning(f'⚠️ RSS 任务通知发送失败: {response.error_message}')

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
            logger.warning(f'⚠️ RSS 中断通知发送失败: {response.error_message}')

    # ========== IDownloadNotifier 实现 ==========

    def notify_download_start(self, notification: DownloadNotification) -> None:
        """
        通知下载开始。

        Args:
            notification: 下载通知数据
        """
        embed = self._embed_builder.build_download_start_embed(
            anime_title=notification.anime_title,
            season=notification.season,
            episode=notification.episode,
            subtitle_group=notification.subtitle_group,
            hash_id=notification.hash_id
        )

        response = self._client.send(embeds=[embed], channel_type='download')

        if not response.success:
            logger.warning(f'⚠️ 下载开始通知发送失败: {response.error_message}')

    def notify_download_complete(self, notification: DownloadNotification) -> None:
        """
        通知下载完成。

        Args:
            notification: 下载通知数据
        """
        embed = self._embed_builder.build_download_complete_embed(
            anime_title=notification.anime_title,
            season=notification.season,
            episode=notification.episode,
            subtitle_group=notification.subtitle_group,
            hash_id=notification.hash_id
        )

        response = self._client.send(embeds=[embed], channel_type='download')

        if not response.success:
            logger.warning(f'⚠️ 下载完成通知发送失败: {response.error_message}')

    def notify_download_failed(
        self,
        notification: DownloadNotification,
        error_message: str
    ) -> None:
        """
        通知下载失败。

        Args:
            notification: 下载通知数据
            error_message: 错误消息
        """
        embed = self._embed_builder.build_download_failed_embed(
            anime_title=notification.anime_title,
            error_message=error_message,
            hash_id=notification.hash_id
        )

        response = self._client.send(embeds=[embed], channel_type='download')

        if not response.success:
            logger.warning(f'⚠️ 下载失败通知发送失败: {response.error_message}')

    # ========== IHardlinkNotifier 实现 ==========

    def notify_hardlink_created(self, notification: HardlinkNotification) -> None:
        """
        通知硬链接创建成功。

        Args:
            notification: 硬链接通知数据
        """
        embed = self._embed_builder.build_hardlink_detailed_embed(
            torrent_id=notification.torrent_id,
            torrent_name=notification.torrent_name,
            anime_title=notification.anime_title,
            subtitle_group=notification.subtitle_group,
            tvdb_used=notification.tvdb_used,
            hardlink_path=notification.hardlink_path or notification.target_dir,
            rename_method=notification.rename_method,
            video_count=notification.video_count,
            subtitle_count=notification.subtitle_count,
            rename_examples=notification.rename_examples
        )

        response = self._client.send(embeds=[embed], channel_type='hardlink')

        if not response.success:
            logger.warning(f'⚠️ 硬链接创建通知发送失败: {response.error_message}')

    def notify_hardlink_failed(
        self,
        notification: HardlinkNotification,
        error_message: str,
        source_path: str | None = None,
        target_path: str | None = None
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
            logger.warning(f'⚠️ 硬链接失败通知发送失败: {response.error_message}')

    # ========== IErrorNotifier 实现 ==========

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

        channel_type = self._determine_error_channel(notification.context)
        response = self._client.send(embeds=[embed], channel_type=channel_type)

        if not response.success:
            logger.warning(f'⚠️ 错误通知发送失败: {response.error_message}')
        else:
            logger.debug(f'✅ 错误通知已发送: {notification.error_type}')

    def notify_warning(
        self,
        message: str,
        context: dict[str, Any] | None = None
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

        channel_type = self._determine_error_channel(context)
        response = self._client.send(embeds=[embed], channel_type=channel_type)

        if not response.success:
            logger.warning(f'⚠️ 警告通知发送失败: {response.error_message}')
        else:
            logger.debug(f'✅ 警告通知已发送: {message[:50]}...')

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
            channel_type=self._default_error_channel
        )

        if not response.success:
            logger.warning(f'⚠️ 简单错误通知发送失败: {response.error_message}')

    def send_detailed_error(
        self,
        error_type: str,
        error_message: str,
        context: dict[str, Any] | None = None,
        channel_type: str | None = None
    ) -> None:
        """
        发送详细的错误通知。

        兼容原始 send_error_detail 方法。

        Args:
            error_type: 错误类型
            error_message: 错误消息
            context: 上下文信息（可选）
            channel_type: 频道类型（可选）
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

        target_channel = channel_type or self._default_error_channel
        response = self._client.send(embeds=[embed], channel_type=target_channel)

        if not response.success:
            logger.warning(f'⚠️ 详细错误通知发送失败: {response.error_message}')

    # ========== IAIUsageNotifier 实现 ==========

    def notify_ai_usage(self, notification: AIUsageNotification) -> None:
        """
        通知 AI 正在被使用。

        根据上下文发送到对应的 Discord 频道。

        Args:
            notification: AI 使用通知数据
        """
        embed = self._embed_builder.build_ai_usage_embed(
            reason=notification.reason,
            project_name=notification.project_name,
            context=notification.context,
            operation=notification.operation
        )

        channel_type = 'rss' if notification.context == 'rss' else 'hardlink'
        response = self._client.send(embeds=[embed], channel_type=channel_type)

        if not response.success:
            logger.warning(f'⚠️ AI 使用通知发送失败: {response.error_message}')

    # ========== IWebhookNotifier 实现 ==========

    def notify_webhook_received(
        self,
        notification: WebhookReceivedNotification
    ) -> None:
        """
        通知收到了 Webhook。

        Args:
            notification: Webhook 接收通知数据
        """
        embed = self._embed_builder.build_webhook_received_embed(
            torrent_id=notification.torrent_id,
            save_path=notification.save_path,
            content_path=notification.content_path,
            torrent_name=notification.torrent_name
        )

        response = self._client.send(embeds=[embed], channel_type='hardlink')

        if not response.success:
            logger.warning(f'⚠️ Webhook 接收通知发送失败: {response.error_message}')

    # ========== 私有辅助方法 ==========

    def _determine_error_channel(
        self,
        context: dict[str, Any] | None
    ) -> str:
        """
        根据上下文确定发送频道。

        Args:
            context: 上下文信息

        Returns:
            频道类型 ('rss' 或 'hardlink')
        """
        if not context:
            return self._default_error_channel

        hardlink_indicators = ['target_dir', 'source_path', 'hardlink']
        for key in hardlink_indicators:
            if key in context:
                return 'hardlink'

        return self._default_error_channel
