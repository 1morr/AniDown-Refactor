"""
Dashboard controller module.

Contains the dashboard blueprint and routes for the main dashboard page.
"""
import os
import re
import shutil
import threading
from datetime import UTC, datetime

import psutil
from dependency_injector.wiring import Provide, inject
from flask import Blueprint, render_template

from src.container import Container
from src.core.config import config
from src.core.utils.timezone_utils import format_datetime_iso
from src.infrastructure.database.models import Hardlink
from src.infrastructure.database.session import db_manager
from src.infrastructure.downloader.qbit_adapter import QBitAdapter
from src.infrastructure.repositories.anime_repository import AnimeRepository
from src.infrastructure.repositories.download_repository import DownloadRepository
from src.infrastructure.repositories.history_repository import HistoryRepository
from src.interface.web.utils import APIResponse, WebLogger, handle_api_errors

dashboard_bp = Blueprint('dashboard', __name__)
logger = WebLogger(__name__)


@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@inject
def dashboard(
    anime_repo: AnimeRepository = Provide[Container.anime_repo],
    download_repo: DownloadRepository = Provide[Container.download_repo],
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """主仪表板"""
    stats = _get_database_stats(anime_repo, download_repo, history_repo)
    activity = _get_recent_activity(anime_repo, download_repo)

    return render_template('dashboard.html',
                           stats=stats,
                           activity=activity,
                           config=config)


@dashboard_bp.route('/status')
@inject
@handle_api_errors
def status_api(
    anime_repo: AnimeRepository = Provide[Container.anime_repo],
    download_repo: DownloadRepository = Provide[Container.download_repo],
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """API: 获取系统状态"""
    logger.api_request("获取系统状态")

    stats = _get_database_stats(anime_repo, download_repo, history_repo)
    activity = _get_recent_activity(anime_repo, download_repo)

    logger.api_success('/status', "系统状态获取成功")
    return APIResponse.success(
        webui_active=True,
        stats=stats,
        activity=activity,
        timestamp=datetime.now(UTC).isoformat()
    )


@dashboard_bp.route('/api/system/status')
@handle_api_errors
def get_system_status():
    """API: 获取系统服务状态"""
    logger.api_request("获取系统服务状态")

    # 简化版本：返回基础状态
    status = {
        'overall': 'running',
        'services': {
            'webui': 'running',
            'webhook': 'unknown',
            'rss_scheduler': 'unknown'
        }
    }

    logger.api_success('/api/system/status', "系统服务状态获取成功")
    return APIResponse.success(data=status)


@dashboard_bp.route('/api/hardlinks/<hash_id>')
@inject
@handle_api_errors
def get_hardlinks_by_hash(
    hash_id: str,
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """API: 根据hash_id获取硬链接信息"""
    # 验证hash_id
    if not hash_id or len(hash_id) != 40:
        return APIResponse.bad_request("无效的torrent哈希值")

    logger.api_request(f"获取硬链接信息 - hash:{hash_id[:8]}...")

    # 使用with语句确保在会话内完成所有数据访问
    with db_manager.session() as session:
        # 直接在会话内查询并构建数据
        hardlinks = session.query(Hardlink).filter(
            Hardlink.torrent_hash == hash_id
        ).all()

        if not hardlinks:
            logger.api_error_msg('/api/hardlinks', '未找到硬链接信息')
            return APIResponse.bad_request('未找到该下载任务的硬链接信息')

        # 在会话内格式化硬链接数据
        hardlinks_data = []
        for hardlink in hardlinks:
            # 格式化文件大小
            file_size = hardlink.file_size
            if file_size:
                if file_size > 1024 * 1024 * 1024:
                    size_str = f"{file_size / (1024 * 1024 * 1024):.2f} GB"
                elif file_size > 1024 * 1024:
                    size_str = f"{file_size / (1024 * 1024):.2f} MB"
                else:
                    size_str = f"{file_size / 1024:.2f} KB"
            else:
                size_str = "未知"

            hardlinks_data.append({
                'id': hardlink.id,
                'original_path': hardlink.original_file_path,
                'hardlink_path': hardlink.hardlink_path,
                'original_filename': os.path.basename(hardlink.original_file_path),
                'hardlink_filename': os.path.basename(hardlink.hardlink_path),
                'file_size': size_str,
                'created_at': hardlink.created_at.isoformat() if hardlink.created_at else None
            })

        logger.api_success('/api/hardlinks', f"返回 {len(hardlinks_data)} 条硬链接记录")
        return APIResponse.success(data=hardlinks_data, count=len(hardlinks_data))


@dashboard_bp.route('/api/qbittorrent/active-downloads')
@handle_api_errors
def get_active_downloads():
    """API: 获取qBittorrent活跃下载任务"""
    logger.api_request("获取qBittorrent活跃下载")

    qbit = QBitAdapter()
    if not qbit.login():
        logger.api_error_msg('/api/qbittorrent/active-downloads', 'qBittorrent连接失败')
        return APIResponse.internal_error('qBittorrent连接失败')

    # 获取所有种子信息
    info_url = f"{qbit.base_url}/api/v2/torrents/info"
    response = qbit.session.get(info_url, params={'filter': 'downloading'})

    if response.status_code != 200:
        logger.api_error_msg('/api/qbittorrent/active-downloads', 'Failed to fetch torrents')
        return APIResponse.internal_error('Failed to fetch torrents')

    torrents = response.json()
    active_downloads = []

    for torrent in torrents:
        active_downloads.append({
            'id': torrent['hash'],
            'name': torrent['name'],
            'progress': round(torrent['progress'] * 100, 1),
            'speed': _format_speed(torrent['dlspeed']),
            'downloaded': _format_size(torrent['downloaded']),
            'total': _format_size(torrent['size']),
            'eta': torrent['eta'] if torrent['eta'] != 8640000 else '∞'
        })

    logger.api_success('/api/qbittorrent/active-downloads', f"返回 {len(active_downloads)} 个活跃下载")
    return APIResponse.success(downloads=active_downloads)


@dashboard_bp.route('/api/system/resources')
@handle_api_errors
def get_system_resources():
    """API: 获取系统资源使用情况"""
    logger.api_request("获取系统资源使用情况")

    # CPU使用率
    cpu_percent = psutil.cpu_percent(interval=1)

    # 内存使用情况
    memory = psutil.virtual_memory()
    memory_used_gb = memory.used / (1024**3)
    memory_total_gb = memory.total / (1024**3)

    # 磁盘使用情况 (获取根目录或下载目录)
    download_path = getattr(config.qbittorrent, 'download_path', '/')
    if not os.path.exists(download_path):
        download_path = '/'

    disk_usage = shutil.disk_usage(download_path)
    disk_used_gb = (disk_usage.total - disk_usage.free) / (1024**3)
    disk_total_gb = disk_usage.total / (1024**3)
    disk_percent = (disk_used_gb / disk_total_gb) * 100

    logger.api_success(
        '/api/system/resources',
        f"CPU:{cpu_percent:.1f}%, 内存:{memory.percent:.1f}%, 磁盘:{disk_percent:.1f}%"
    )

    return APIResponse.success(
        resources={
            'cpu': round(cpu_percent, 1),
            'memory': {
                'used': round(memory_used_gb, 1),
                'total': round(memory_total_gb, 1),
                'percent': round(memory.percent, 1)
            },
            'disk': {
                'used': round(disk_used_gb, 1),
                'total': round(disk_total_gb, 1),
                'percent': round(disk_percent, 1)
            }
        }
    )


@dashboard_bp.route('/api/rss/refresh', methods=['POST'])
@handle_api_errors
def refresh_rss_api():
    """API: 立即刷新RSS (dashboard快捷方式)"""
    logger.api_request("Dashboard刷新RSS")

    # 获取配置中的所有RSS Feeds
    rss_feeds = config.rss.get_feeds()

    if not rss_feeds:
        logger.api_error_msg('/api/rss/refresh', '没有配置RSS链接')
        return APIResponse.bad_request('没有配置RSS链接')

    # 在后台线程中处理所有RSS
    def process_rss_background():
        try:
            logger.processing_start(f"Dashboard触发刷新RSS配置 ({len(rss_feeds)}个链接)")
            # TODO: 需要 download_manager 完成后才能调用
            # download_manager.process_rss_feeds(rss_feeds, "Dashboard触发")
            logger.processing_success("Dashboard RSS处理完成")
        except Exception as e:
            logger.processing_error("Dashboard RSS处理", e)

    thread = threading.Thread(target=process_rss_background, daemon=True)
    thread.start()

    logger.api_success('/api/rss/refresh', f'已启动处理 {len(rss_feeds)} 个RSS链接')
    return APIResponse.success(message=f'已启动处理 {len(rss_feeds)} 个RSS链接')


def _get_database_stats(anime_repo, download_repo, history_repo):
    """获取数据库统计信息"""
    try:
        anime_count = anime_repo.count_all()
        download_count = download_repo.count_all()
        hardlink_count = history_repo.count_hardlinks()

        recent_anime_count = anime_repo.count_recent(hours=24)
        recent_download_count = download_repo.count_recent(hours=24)

        last_rss_check = history_repo.get_last_rss_check_time()

        return {
            'anime_count': anime_count,
            'download_count': download_count,
            'hardlink_count': hardlink_count,
            'recent_anime_count': recent_anime_count,
            'recent_download_count': recent_download_count,
            'last_rss_check': format_datetime_iso(last_rss_check) if last_rss_check else None
        }
    except Exception as e:
        logger.db_error("获取统计信息", e)
        return {'error': str(e)}


def _get_recent_activity(anime_repo, download_repo):
    """获取最近活动"""
    try:
        recent_anime = anime_repo.get_recent_anime(limit=10)
        recent_downloads = download_repo.get_recent_downloads(limit=10)

        # 格式化动漫记录为模板期望的元组格式 (original_title, short_title, created_at)
        formatted_anime = []
        for anime in recent_anime:
            formatted_anime.append((
                anime['original_title'],
                anime['short_title'],
                format_datetime_iso(anime['created_at'])  # 转换为ISO格式字符串
            ))

        # 格式化下载记录为模板期望的元组格式
        formatted_downloads = []
        for dl in recent_downloads:
            # 提取集数 (需要AnimeRepository提供正则)
            episode = None
            if dl['anime_id']:
                pattern = anime_repo.get_patterns_by_anime_id(dl['anime_id'])
                if pattern and pattern.get('episode_regex'):
                    try:
                        match = re.search(pattern['episode_regex'], dl['original_filename'])
                        if match:
                            episode_str = match.group(1) if match.groups() else match.group(0)
                            try:
                                episode = int(episode_str)
                            except ValueError:
                                pass
                    except re.error:
                        # 忽略无效的正则表达式
                        pass

            # 模板期望的格式：(hash_id, original_filename, status, created_at, anime_title, episode, download_directory)
            formatted_downloads.append((
                dl['hash_id'],
                dl['original_filename'],
                dl['status'],
                format_datetime_iso(dl['created_at']),  # 转换为ISO格式字符串
                dl['anime_title'] if dl['anime_title'] else '未知',
                episode,
                dl['download_directory'] if dl['download_directory'] else ''
            ))

        return {
            'recent_anime': formatted_anime,
            'recent_downloads': formatted_downloads
        }
    except Exception as e:
        logger.db_error("获取最近活动", e)
        return {'error': str(e)}


def _format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.1f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.1f} MB"
    else:
        return f"{size_bytes / 1024:.1f} KB"


def _format_speed(speed_bytes):
    """格式化下载速度"""
    if speed_bytes >= 1024**2:
        return f"{speed_bytes / (1024**2):.1f} MB/s"
    elif speed_bytes >= 1024:
        return f"{speed_bytes / 1024:.1f} KB/s"
    else:
        return f"{speed_bytes:.0f} B/s"
