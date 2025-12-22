"""
Discord Embed 构建器模块。

提供 Discord Embed 消息的构建功能。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EmbedBuilder:
    """
    Discord Embed 构建器。

    提供各种通知类型的 Embed 构建方法。

    Discord Embed 结构：
    - title: 标题
    - description: 描述
    - color: 颜色（十进制整数）
    - fields: 字段列表
    - footer: 页脚
    - timestamp: 时间戳

    Example:
        >>> builder = EmbedBuilder()
        >>> embed = builder.build_rss_start_embed(
        ...     trigger_type='定时触发',
        ...     rss_url='https://example.com/rss'
        ... )
    """

    # 颜色常量（Discord 颜色为十进制整数）
    COLOR_SUCCESS = 0x00FF00  # 绿色
    COLOR_INFO = 0x3498DB     # 蓝色
    COLOR_WARNING = 0xFFA500  # 橙色
    COLOR_ERROR = 0xFF0000    # 红色
    COLOR_PROCESSING = 0x9B59B6  # 紫色

    def __init__(self, app_name: str = 'AniDown'):
        """
        初始化构建器。

        Args:
            app_name: 应用名称（显示在页脚）
        """
        self._app_name = app_name

    def _base_embed(
        self,
        title: str,
        description: Optional[str] = None,
        color: int = COLOR_INFO
    ) -> Dict[str, Any]:
        """
        创建基础 Embed 结构。

        Args:
            title: 标题
            description: 描述
            color: 颜色

        Returns:
            Embed 字典
        """
        embed: Dict[str, Any] = {
            'title': title,
            'color': color,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'footer': {
                'text': self._app_name
            }
        }

        if description:
            embed['description'] = description

        return embed

    def _add_fields(
        self,
        embed: Dict[str, Any],
        fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        添加字段到 Embed。

        Args:
            embed: Embed 字典
            fields: 字段列表 [{name, value, inline}]

        Returns:
            更新后的 Embed 字典
        """
        embed['fields'] = fields
        return embed

    # === RSS 通知 ===

    def build_rss_start_embed(
        self,
        trigger_type: str,
        rss_url: str,
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        构建 RSS 处理开始通知 Embed。

        Args:
            trigger_type: 触发类型（定时触发、手动触发等）
            rss_url: RSS URL
            title: 可选标题

        Returns:
            Embed 字典
        """
        embed = self._base_embed(
            title='🚀 RSS 处理开始',
            color=self.COLOR_PROCESSING
        )

        fields = [
            {'name': '⏰ 触发方式', 'value': trigger_type, 'inline': True}
        ]

        if title:
            fields.append({'name': '📝 标题', 'value': title, 'inline': True})

        # 截断过长的 URL
        display_url = rss_url if len(rss_url) <= 50 else rss_url[:47] + '...'
        fields.append({'name': '🔗 RSS URL', 'value': display_url, 'inline': False})

        return self._add_fields(embed, fields)

    def build_rss_complete_embed(
        self,
        success_count: int,
        total_count: int,
        failed_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        构建 RSS 处理完成通知 Embed。

        Args:
            success_count: 成功数量
            total_count: 总数量
            failed_items: 失败项目列表

        Returns:
            Embed 字典
        """
        if success_count == total_count:
            color = self.COLOR_SUCCESS
            title = '✅ RSS 处理完成'
        elif success_count > 0:
            color = self.COLOR_WARNING
            title = '⚠️ RSS 处理部分完成'
        else:
            color = self.COLOR_ERROR
            title = '❌ RSS 处理失败'

        embed = self._base_embed(title=title, color=color)

        fields = [
            {
                'name': '📊 处理结果',
                'value': f'成功: {success_count}/{total_count}',
                'inline': True
            }
        ]

        if failed_items:
            # 最多显示 5 个失败项
            failed_text = '\n'.join(
                f"• {item.get('title', '未知')[:30]}..."
                for item in failed_items[:5]
            )
            if len(failed_items) > 5:
                failed_text += f'\n... 还有 {len(failed_items) - 5} 个'

            fields.append({
                'name': '❌ 失败项目',
                'value': failed_text or '无',
                'inline': False
            })

        return self._add_fields(embed, fields)

    # === 下载通知 ===

    def build_download_start_embed(
        self,
        anime_title: str,
        season: int,
        episode: Optional[int],
        subtitle_group: str,
        hash_id: str
    ) -> Dict[str, Any]:
        """
        构建下载开始通知 Embed。

        Args:
            anime_title: 动漫标题
            season: 季度
            episode: 集数
            subtitle_group: 字幕组
            hash_id: 种子哈希

        Returns:
            Embed 字典
        """
        # 构建集数显示
        ep_text = f'S{season:02d}'
        if episode is not None:
            ep_text += f'E{episode:02d}'

        embed = self._base_embed(
            title='📥 开始下载',
            description=f'**{anime_title}** {ep_text}',
            color=self.COLOR_INFO
        )

        fields = [
            {'name': '👥 字幕组', 'value': subtitle_group or '未知', 'inline': True},
            {'name': '📺 季度', 'value': f'第 {season} 季' if season > 0 else '电影/OVA', 'inline': True},
            {'name': ':hash: Hash', 'value': f'`{hash_id[:8]}...`', 'inline': True}
        ]

        return self._add_fields(embed, fields)

    def build_download_complete_embed(
        self,
        anime_title: str,
        season: int,
        episode: Optional[int],
        subtitle_group: str,
        hash_id: str
    ) -> Dict[str, Any]:
        """
        构建下载完成通知 Embed。

        Args:
            anime_title: 动漫标题
            season: 季度
            episode: 集数
            subtitle_group: 字幕组
            hash_id: 种子哈希

        Returns:
            Embed 字典
        """
        ep_text = f'S{season:02d}'
        if episode is not None:
            ep_text += f'E{episode:02d}'

        embed = self._base_embed(
            title='✅ 下载完成',
            description=f'**{anime_title}** {ep_text}',
            color=self.COLOR_SUCCESS
        )

        fields = [
            {'name': '👥 字幕组', 'value': subtitle_group or '未知', 'inline': True},
            {'name': ':hash: Hash', 'value': f'`{hash_id[:8]}...`', 'inline': True}
        ]

        return self._add_fields(embed, fields)

    def build_download_failed_embed(
        self,
        anime_title: str,
        error_message: str,
        hash_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        构建下载失败通知 Embed。

        Args:
            anime_title: 动漫标题
            error_message: 错误消息
            hash_id: 种子哈希（可选）

        Returns:
            Embed 字典
        """
        embed = self._base_embed(
            title='❌ 下载失败',
            description=f'**{anime_title}**',
            color=self.COLOR_ERROR
        )

        fields = [
            {'name': '⚠️ 错误', 'value': error_message[:500], 'inline': False}
        ]

        if hash_id:
            fields.append({
                'name': ':hash: Hash',
                'value': f'`{hash_id[:8]}...`',
                'inline': True
            })

        return self._add_fields(embed, fields)

    # === 硬链接通知 ===

    def build_hardlink_created_embed(
        self,
        anime_title: str,
        season: int,
        video_count: int,
        subtitle_count: int,
        target_dir: str,
        rename_method: str
    ) -> Dict[str, Any]:
        """
        构建硬链接创建通知 Embed。

        Args:
            anime_title: 动漫标题
            season: 季度
            video_count: 视频文件数量
            subtitle_count: 字幕文件数量
            target_dir: 目标目录
            rename_method: 重命名方式

        Returns:
            Embed 字典
        """
        embed = self._base_embed(
            title='🔗 硬链接创建完成',
            description=f'**{anime_title}** 第 {season} 季' if season > 0 else f'**{anime_title}**',
            color=self.COLOR_SUCCESS
        )

        # 截断目录路径
        display_dir = target_dir if len(target_dir) <= 40 else '...' + target_dir[-37:]

        fields = [
            {'name': '🎬 视频文件', 'value': f'{video_count} 个', 'inline': True},
            {'name': '💬 字幕文件', 'value': f'{subtitle_count} 个', 'inline': True},
            {'name': '✏️ 重命名方式', 'value': rename_method, 'inline': True},
            {'name': '📁 目标目录', 'value': f'`{display_dir}`', 'inline': False}
        ]

        return self._add_fields(embed, fields)

    def build_hardlink_failed_embed(
        self,
        anime_title: str,
        error_message: str,
        source_path: Optional[str] = None,
        target_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        构建硬链接失败通知 Embed。

        Args:
            anime_title: 动漫标题
            error_message: 错误消息
            source_path: 源路径（可选）
            target_path: 目标路径（可选）

        Returns:
            Embed 字典
        """
        embed = self._base_embed(
            title='❌ 硬链接创建失败',
            description=f'**{anime_title}**',
            color=self.COLOR_ERROR
        )

        fields = [
            {'name': '⚠️ 错误', 'value': error_message[:500], 'inline': False}
        ]

        if source_path:
            display_source = source_path if len(source_path) <= 50 else '...' + source_path[-47:]
            fields.append({
                'name': '📤 源路径',
                'value': f'`{display_source}`',
                'inline': False
            })

        if target_path:
            display_target = target_path if len(target_path) <= 50 else '...' + target_path[-47:]
            fields.append({
                'name': '📥 目标路径',
                'value': f'`{display_target}`',
                'inline': False
            })

        return self._add_fields(embed, fields)

    # === 错误通知 ===

    def build_error_embed(
        self,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构建错误通知 Embed。

        Args:
            error_type: 错误类型
            error_message: 错误消息
            context: 上下文信息（可选）

        Returns:
            Embed 字典
        """
        embed = self._base_embed(
            title=f'❌ {error_type}',
            description=error_message[:2000],
            color=self.COLOR_ERROR
        )

        if context:
            fields = []
            for key, value in list(context.items())[:5]:
                fields.append({
                    'name': f'📌 {key}',
                    'value': str(value)[:100],
                    'inline': True
                })
            if fields:
                return self._add_fields(embed, fields)

        return embed

    def build_warning_embed(
        self,
        warning_type: str,
        warning_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构建警告通知 Embed。

        Args:
            warning_type: 警告类型
            warning_message: 警告消息
            context: 上下文信息（可选）

        Returns:
            Embed 字典
        """
        embed = self._base_embed(
            title=f'⚠️ {warning_type}',
            description=warning_message[:2000],
            color=self.COLOR_WARNING
        )

        if context:
            fields = []
            for key, value in list(context.items())[:5]:
                fields.append({
                    'name': f'📌 {key}',
                    'value': str(value)[:100],
                    'inline': True
                })
            if fields:
                return self._add_fields(embed, fields)

        return embed

    # === 辅助方法 ===

    def _truncate_path(self, path: str, max_len: int = 45) -> str:
        """
        截断路径以便显示。

        Args:
            path: 路径字符串
            max_len: 最大长度

        Returns:
            截断后的路径
        """
        if len(path) <= max_len:
            return path
        return '...' + path[-(max_len - 3):]

    def _truncate_url(self, url: str, max_len: int = 50) -> str:
        """
        截断 URL 以便显示。

        Args:
            url: URL 字符串
            max_len: 最大长度

        Returns:
            截断后的 URL
        """
        if len(url) <= max_len:
            return url
        return url[:max_len - 3] + '...'

    def _status_emoji(self, status: str) -> str:
        """
        获取状态对应的 emoji。

        Args:
            status: 状态字符串

        Returns:
            对应的 emoji
        """
        return {
            'completed': '✅',
            'partial': '⚠️',
            'interrupted': '⏸️',
            'failed': '❌'
        }.get(status, '📋')

    # === AI 使用通知 ===

    def build_ai_usage_embed(
        self,
        reason: str,
        project_name: str,
        context: str,
        operation: str
    ) -> Dict[str, Any]:
        """
        构建 AI 使用通知 Embed。

        Args:
            reason: 使用 AI 的原因
            project_name: 项目/动漫名称
            context: 上下文（'rss' 或 'webhook'）
            operation: 操作类型（'title_parsing' 或 'file_renaming'）

        Returns:
            Embed 字典
        """
        operation_display = {
            'title_parsing': '标题解析',
            'file_renaming': '文件重命名'
        }.get(operation, operation)

        embed = self._base_embed(
            title='🤖 使用 AI 处理',
            color=self.COLOR_PROCESSING
        )

        fields = [
            {'name': '📁 项目', 'value': project_name[:50] or '未知', 'inline': True},
            {'name': '⚙️ 操作', 'value': operation_display, 'inline': True},
            {'name': '💡 原因', 'value': reason[:100], 'inline': False}
        ]

        return self._add_fields(embed, fields)

    # === RSS 任务通知 ===

    def build_rss_task_embed(
        self,
        project_name: str,
        hash_id: str,
        anime_title: str,
        subtitle_group: str,
        download_path: str,
        season: int = 1,
        episode: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        构建 RSS 下载任务通知 Embed（即时发送）。

        Args:
            project_name: 项目名称（清洁的动漫标题）
            hash_id: 种子哈希
            anime_title: 原始动漫标题
            subtitle_group: 字幕组
            download_path: 下载路径
            season: 季度
            episode: 集数（可选）

        Returns:
            Embed 字典
        """
        # 构建集数显示
        ep_text = f'S{season:02d}'
        if episode is not None:
            ep_text += f'E{episode:02d}'

        embed = self._base_embed(
            title='📥 下载任务已添加',
            description=f'**{project_name}**',
            color=self.COLOR_INFO
        )

        # 截断长标题
        display_title = anime_title if len(anime_title) <= 50 else anime_title[:47] + '...'

        fields = [
            {'name': '🎬 动漫标题', 'value': display_title, 'inline': False},
            {'name': '👥 字幕组', 'value': subtitle_group or '未知', 'inline': True},
            {'name': '📺 季/集', 'value': ep_text, 'inline': True},
            {'name': ':hash: Hash', 'value': f'`{hash_id[:8]}...`' if hash_id else '未知', 'inline': True},
            {'name': '📁 下载路径', 'value': f'`{download_path}`', 'inline': False}
        ]

        return self._add_fields(embed, fields)

    # === RSS 完成通知（增强版）===

    def build_rss_complete_embed_enhanced(
        self,
        success_count: int,
        total_count: int,
        attempt_count: int,
        status: str,
        failed_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        构建增强版 RSS 处理完成通知 Embed。

        Args:
            success_count: 成功数量
            total_count: 总数量
            attempt_count: 尝试数量（成功 + 失败）
            status: 状态（'completed', 'partial', 'failed', 'interrupted'）
            failed_items: 失败项目列表

        Returns:
            Embed 字典
        """
        # 根据状态确定颜色和标题
        # 特殊情况：如果没有需要尝试的项目（全部被过滤或已存在），视为成功
        if status == 'completed' and attempt_count == 0:
            color = self.COLOR_SUCCESS
            title = '✅ RSS 处理完成 (无新项目)'
        elif success_count == attempt_count and attempt_count > 0:
            # 所有尝试的项目都成功了
            color = self.COLOR_SUCCESS
            title = '✅ RSS 处理完成'
        elif status == 'interrupted':
            color = self.COLOR_WARNING
            title = '⏸️ RSS 处理已中断'
        elif success_count > 0:
            # 部分成功
            color = self.COLOR_WARNING
            title = '⚠️ RSS 处理部分完成'
        else:
            color = self.COLOR_ERROR
            title = '❌ RSS 处理失败'

        embed = self._base_embed(title=title, color=color)

        # 计算成功率
        success_rate = (success_count / attempt_count * 100) if attempt_count > 0 else 0

        fields = [
            {'name': '📊 状态', 'value': status.capitalize(), 'inline': True},
            {'name': '📈 成功率', 'value': f'{success_rate:.1f}%', 'inline': True},
            {
                'name': '📋 统计',
                'value': f'成功: {success_count} / 尝试: {attempt_count} / 总数: {total_count}',
                'inline': False
            }
        ]

        if failed_items:
            # 最多显示 5 个失败项
            failed_text = '\n'.join(
                f"• {item.get('title', '未知')[:30]}..."
                for item in failed_items[:5]
            )
            if len(failed_items) > 5:
                failed_text += f'\n... 还有 {len(failed_items) - 5} 个'

            fields.append({
                'name': '❌ 失败项目',
                'value': failed_text or '无',
                'inline': False
            })

        return self._add_fields(embed, fields)

    # === RSS 中断通知 ===

    def build_rss_interrupted_embed(
        self,
        trigger_type: str,
        rss_url: str,
        processed_count: int,
        total_count: int,
        reason: str
    ) -> Dict[str, Any]:
        """
        构建 RSS 处理中断通知 Embed。

        Args:
            trigger_type: 触发类型
            rss_url: RSS URL
            processed_count: 已处理数量
            total_count: 总数量
            reason: 中断原因

        Returns:
            Embed 字典
        """
        embed = self._base_embed(
            title='⏸️ RSS 处理已中断',
            color=self.COLOR_WARNING
        )

        fields = [
            {'name': '⏰ 触发方式', 'value': trigger_type, 'inline': True},
            {'name': '📊 进度', 'value': f'{processed_count}/{total_count}', 'inline': True},
            {'name': '⏹️ 中断原因', 'value': reason[:100], 'inline': False},
            {'name': '🔗 RSS URL', 'value': self._truncate_url(rss_url), 'inline': False}
        ]

        return self._add_fields(embed, fields)

    # === Webhook 接收通知 ===

    def build_webhook_received_embed(
        self,
        torrent_id: str,
        save_path: str,
        content_path: str,
        torrent_name: str
    ) -> Dict[str, Any]:
        """
        构建 Webhook 接收通知 Embed。

        Args:
            torrent_id: 种子哈希
            save_path: 保存路径
            content_path: 内容路径
            torrent_name: 种子名称

        Returns:
            Embed 字典
        """
        # 截断长名称
        display_name = torrent_name if len(torrent_name) <= 60 else torrent_name[:57] + '...'

        embed = self._base_embed(
            title='📨 收到 Webhook',
            description=f'**{display_name}**' if display_name else None,
            color=self.COLOR_INFO
        )

        # 处理空路径的情况（显示完整路径）
        save_path_display = f'`{save_path}`' if save_path else '未知'
        content_path_display = f'`{content_path}`' if content_path else '未知'

        fields = [
            {'name': ':hash: Hash', 'value': f'`{torrent_id[:8]}...`' if torrent_id else '未知', 'inline': True},
            {'name': '💾 保存路径', 'value': save_path_display, 'inline': False},
            {'name': '📂 内容路径', 'value': content_path_display, 'inline': False}
        ]

        return self._add_fields(embed, fields)

    # === 硬链接详细通知 ===

    def build_hardlink_detailed_embed(
        self,
        torrent_id: str,
        torrent_name: str,
        anime_title: str,
        subtitle_group: str,
        tvdb_used: bool,
        hardlink_path: str,
        rename_method: str,
        video_count: int,
        subtitle_count: int,
        rename_examples: List[str]
    ) -> Dict[str, Any]:
        """
        构建详细硬链接成功通知 Embed。

        Args:
            torrent_id: 种子哈希
            torrent_name: 种子名称
            anime_title: 动漫标题
            subtitle_group: 字幕组
            tvdb_used: 是否使用 TVDB
            hardlink_path: 硬链接路径
            rename_method: 重命名方式
            video_count: 视频文件数量
            subtitle_count: 字幕文件数量
            rename_examples: 重命名示例列表（最多 3 个）

        Returns:
            Embed 字典
        """
        embed = self._base_embed(
            title='🔗 硬链接创建成功',
            description=f'**{anime_title}**',
            color=self.COLOR_SUCCESS
        )

        total_hardlinks = video_count + subtitle_count

        fields = [
            {'name': ':hash: Hash', 'value': f'`{torrent_id[:8]}...`' if torrent_id else '未知', 'inline': True},
            {'name': '👥 字幕组', 'value': subtitle_group or '未知', 'inline': True},
            {'name': '📺 使用 TVDB', 'value': '是' if tvdb_used else '否', 'inline': True},
            {'name': '✏️ 重命名方式', 'value': rename_method[:30] if rename_method else '未知', 'inline': True},
            {'name': '🎬 视频文件', 'value': str(video_count), 'inline': True},
            {'name': '💬 字幕文件', 'value': str(subtitle_count), 'inline': True},
            {'name': '🔢 总硬链接数', 'value': str(total_hardlinks), 'inline': True},
            {'name': '📁 硬链接路径', 'value': f'`{hardlink_path}`' if hardlink_path else '未知', 'inline': False}
        ]

        # 添加最多 3 个重命名示例（显示完整的 原文件名 → 新文件名 格式）
        if rename_examples:
            examples_text = '\n'.join(f'`{ex}`' for ex in rename_examples[:3])
            fields.append({
                'name': '✨ 重命名结果',
                'value': examples_text,
                'inline': False
            })

        return self._add_fields(embed, fields)
