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
            {'name': '触发方式', 'value': trigger_type, 'inline': True}
        ]

        if title:
            fields.append({'name': '标题', 'value': title, 'inline': True})

        # 截断过长的 URL
        display_url = rss_url if len(rss_url) <= 50 else rss_url[:47] + '...'
        fields.append({'name': 'RSS URL', 'value': display_url, 'inline': False})

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
                'name': '处理结果',
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
                'name': '失败项目',
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
            {'name': '字幕组', 'value': subtitle_group or '未知', 'inline': True},
            {'name': '季度', 'value': f'第 {season} 季' if season > 0 else '电影/OVA', 'inline': True},
            {'name': '哈希', 'value': f'`{hash_id[:8]}...`', 'inline': True}
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
            {'name': '字幕组', 'value': subtitle_group or '未知', 'inline': True},
            {'name': '哈希', 'value': f'`{hash_id[:8]}...`', 'inline': True}
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
            {'name': '错误', 'value': error_message[:500], 'inline': False}
        ]

        if hash_id:
            fields.append({
                'name': '哈希',
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
            {'name': '视频文件', 'value': f'{video_count} 个', 'inline': True},
            {'name': '字幕文件', 'value': f'{subtitle_count} 个', 'inline': True},
            {'name': '重命名方式', 'value': rename_method, 'inline': True},
            {'name': '目标目录', 'value': f'`{display_dir}`', 'inline': False}
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
            {'name': '错误', 'value': error_message[:500], 'inline': False}
        ]

        if source_path:
            display_source = source_path if len(source_path) <= 50 else '...' + source_path[-47:]
            fields.append({
                'name': '源路径',
                'value': f'`{display_source}`',
                'inline': False
            })

        if target_path:
            display_target = target_path if len(target_path) <= 50 else '...' + target_path[-47:]
            fields.append({
                'name': '目标路径',
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
                    'name': key,
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
                    'name': key,
                    'value': str(value)[:100],
                    'inline': True
                })
            if fields:
                return self._add_fields(embed, fields)

        return embed
