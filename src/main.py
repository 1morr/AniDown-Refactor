"""
AniDown Application Entry Point.

This module serves as the main entry point for the AniDown application.
It initializes the core infrastructure, starts the web server, webhook handler,
and RSS scheduler.
"""

import argparse
import base64
import logging
import os
import sys
import time
import schedule
from datetime import datetime, timedelta, timezone
from threading import Thread
from typing import Optional

# 設置日誌路徑
log_path = os.getenv('LOG_PATH', 'logs')
os.makedirs(log_path, exist_ok=True)

# 生成帶日期的日誌文件名
today = datetime.now().strftime('%Y-%m-%d')
log_file = os.path.join(log_path, f'anidown_{today}.log')

# 配置日志 - 修復 Windows 控制台 UTF-8 編碼問題
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setStream(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        stream_handler
    ]
)
logger = logging.getLogger(__name__)


def init_database():
    """初始化数据库"""
    from src.infrastructure.database.session import db_manager

    logger.info('💾 正在初始化数据库...')
    db_manager.init_db()
    logger.info('✅ 数据库初始化完成')


def init_key_pools():
    """初始化 API Key Pool 和熔断器"""
    from src.core.config import config
    from src.container import container
    from src.infrastructure.ai.key_pool import KeySpec, register_pool
    from src.infrastructure.ai.circuit_breaker import register_breaker

    # 初始化 title_parse key pool
    title_parse_pool = container.title_parse_pool()
    title_parse_breaker = container.title_parse_breaker()
    title_parse_config = config.openai.title_parse

    keys = []
    # 优先使用 api_key_pool
    if title_parse_config.api_key_pool:
        for idx, key_entry in enumerate(title_parse_config.api_key_pool):
            if key_entry.enabled and key_entry.api_key:
                keys.append(KeySpec(
                    key_id=f'tp_key_{idx}',
                    name=key_entry.name or f'Key {idx + 1}',
                    api_key=key_entry.api_key,
                    base_url=title_parse_config.base_url,
                    model=title_parse_config.model,
                    rpm_limit=key_entry.rpm,
                    rpd_limit=key_entry.rpd,
                    enabled=True
                ))
    # 回退到单个 api_key
    elif title_parse_config.api_key:
        keys.append(KeySpec(
            key_id='tp_key_0',
            name='Primary Key',
            api_key=title_parse_config.api_key,
            base_url=title_parse_config.base_url,
            model=title_parse_config.model,
            rpm_limit=0,
            rpd_limit=0,
            enabled=True
        ))

    if keys:
        title_parse_pool.configure(keys)
        register_pool(title_parse_pool)
        register_breaker(title_parse_breaker)
        logger.info(f'🔑 Title Parse Key Pool 已配置: {len(keys)} 个 Key')
    else:
        logger.warning('⚠️ Title Parse 未配置 API Key')

    # 初始化 multi_file_rename key pool
    rename_pool = container.rename_pool()
    rename_breaker = container.rename_breaker()
    rename_config = config.openai.multi_file_rename

    rename_keys = []
    if rename_config.api_key_pool:
        for idx, key_entry in enumerate(rename_config.api_key_pool):
            if key_entry.enabled and key_entry.api_key:
                rename_keys.append(KeySpec(
                    key_id=f'rn_key_{idx}',
                    name=key_entry.name or f'Key {idx + 1}',
                    api_key=key_entry.api_key,
                    base_url=rename_config.base_url,
                    model=rename_config.model,
                    rpm_limit=key_entry.rpm,
                    rpd_limit=key_entry.rpd,
                    enabled=True
                ))
    elif rename_config.api_key:
        rename_keys.append(KeySpec(
            key_id='rn_key_0',
            name='Primary Key',
            api_key=rename_config.api_key,
            base_url=rename_config.base_url,
            model=rename_config.model,
            rpm_limit=0,
            rpd_limit=0,
            enabled=True
        ))

    if rename_keys:
        rename_pool.configure(rename_keys)
        register_pool(rename_pool)
        register_breaker(rename_breaker)
        logger.info(f'🔑 Rename Key Pool 已配置: {len(rename_keys)} 个 Key')
    else:
        logger.warning('⚠️ Multi-File Rename 未配置 API Key')


def init_discord_webhook():
    """初始化 Discord Webhook 客户端"""
    from src.core.config import config
    from src.container import container

    discord_client = container.discord_webhook()

    # 构建 webhook URL 映射
    webhooks = {}
    if config.discord.rss_webhook_url:
        webhooks['rss'] = config.discord.rss_webhook_url
    if config.discord.hardlink_webhook_url:
        webhooks['hardlink'] = config.discord.hardlink_webhook_url
        # 下载完成通知也使用 hardlink webhook
        webhooks['download'] = config.discord.hardlink_webhook_url

    # 配置 webhook 客户端
    discord_client.configure(
        webhooks=webhooks,
        enabled=config.discord.enabled
    )

    if config.discord.enabled and webhooks:
        logger.info(f'🔔 Discord 通知已启用: {list(webhooks.keys())}')
    elif not config.discord.enabled:
        logger.info('🔕 Discord 通知已禁用')
    else:
        logger.warning('⚠️ Discord 已启用但未配置 Webhook URL')


def test_config():
    """测试配置模块"""
    from src.core.config import config

    logger.info('📋 测试配置模块...')
    logger.info(f'  qBittorrent URL: {config.qbittorrent.url}')
    logger.info(f'  RSS 检查间隔: {config.rss.check_interval}秒')
    logger.info(f'  Webhook 端口: {config.webhook.port}')
    logger.info(f'  WebUI 端口: {config.webui.port}')
    logger.info('✅ 配置模块测试通过')


def test_repositories():
    """测试仓储模块"""
    from src.infrastructure.repositories.anime_repository import AnimeRepository
    from src.infrastructure.repositories.download_repository import DownloadRepository
    from src.infrastructure.repositories.history_repository import HistoryRepository

    logger.info('🗄️ 测试仓储模块...')

    anime_repo = AnimeRepository()
    download_repo = DownloadRepository()
    history_repo = HistoryRepository()

    anime_count = anime_repo.count_all()
    download_count = download_repo.count_all()
    hardlink_count = history_repo.count_hardlinks()

    logger.info(f'  动漫数量: {anime_count}')
    logger.info(f'  下载数量: {download_count}')
    logger.info(f'  硬链接数量: {hardlink_count}')
    logger.info('✅ 仓储模块测试通过')


def test_qbit_adapter():
    """测试 qBittorrent 适配器"""
    from src.infrastructure.downloader.qbit_adapter import QBitAdapter

    logger.info('📥 测试 qBittorrent 适配器...')

    qb = QBitAdapter()
    if qb.is_connected():
        logger.info('✅ qBittorrent 连接成功')

        # 获取种子列表
        torrents = qb.get_all_torrents()
        if torrents is not None:
            logger.info(f'  活动种子数: {len(torrents)}')
    else:
        logger.warning('⚠️ qBittorrent 连接失败 (可能未配置或服务未启动)')


def test_container():
    """测试依赖注入容器"""
    from src.container import container

    logger.info('📦 测试依赖注入容器...')

    # 测试获取各个组件
    anime_repo = container.anime_repo()
    download_repo = container.download_repo()
    history_repo = container.history_repo()
    qb_client = container.qb_client()

    logger.info('  ✓ AnimeRepository')
    logger.info('  ✓ DownloadRepository')
    logger.info('  ✓ HistoryRepository')
    logger.info('  ✓ QBitAdapter')

    # 测试新增的服务
    try:
        title_parser = container.title_parser()
        logger.info('  ✓ AITitleParser')
    except Exception as e:
        logger.warning(f'  ⚠ AITitleParser (可能未配置API Key): {e}')

    try:
        download_manager = container.download_manager()
        logger.info('  ✓ DownloadManager')
    except Exception as e:
        logger.warning(f'  ⚠ DownloadManager: {e}')

    logger.info('✅ 依赖注入容器测试通过')


def run_all_tests():
    """运行所有测试"""
    logger.info('🚀 AniDown 验证测试开始...')
    logger.info(f'📁 配置文件路径: {os.getenv("CONFIG_PATH", "config.json")}')
    logger.info(f'📝 日志文件路径: {log_file}')
    logger.info('')

    try:
        test_config()
        logger.info('')

        init_database()
        logger.info('')

        test_repositories()
        logger.info('')

        test_qbit_adapter()
        logger.info('')

        test_container()
        logger.info('')

        logger.info('=' * 50)
        logger.info('🎉 所有验证通过！')
        logger.info('=' * 50)
        return True

    except Exception as e:
        logger.error(f'❌ 验证失败: {e}', exc_info=True)
        return False


def init_queue_workers(download_manager):
    """
    初始化队列工作者并注册处理器。

    Args:
        download_manager: DownloadManager 实例
    """
    from src.services.queue.webhook_queue import get_webhook_queue, WebhookQueueWorker
    from src.services.queue.rss_queue import get_rss_queue, RSSQueueWorker

    # 初始化 Webhook 队列
    webhook_queue = get_webhook_queue()

    def handle_torrent_completed(payload):
        """处理种子完成事件"""
        try:
            logger.info(f'🔔 处理种子完成事件: {payload.hash_id[:8]}...')
            download_manager.handle_torrent_completed(payload.hash_id)
        except Exception as e:
            logger.error(f'❌ 处理种子完成事件失败: {e}', exc_info=True)

    def handle_torrent_added(payload):
        """处理种子添加事件"""
        try:
            logger.info(f'📥 种子已添加: {payload.name}')
            download_manager.handle_torrent_added(payload.hash_id)
        except Exception as e:
            logger.error(f'❌ 处理种子添加事件失败: {e}', exc_info=True)

    def handle_torrent_error(payload):
        """处理种子错误事件"""
        try:
            logger.warning(f'⚠️ 种子错误: {payload.name}')
            download_manager.handle_torrent_error(
                payload.hash_id,
                payload.extra_data.get('error', '未知错误')
            )
        except Exception as e:
            logger.error(f'❌ 处理种子错误事件失败: {e}', exc_info=True)

    def handle_torrent_paused(payload):
        """处理种子暂停事件"""
        try:
            logger.info(f'⏸️ 种子已暂停: {payload.name}')
            download_manager.handle_torrent_paused(payload.hash_id)
        except Exception as e:
            logger.error(f'❌ 处理种子暂停事件失败: {e}', exc_info=True)

    # 注册 Webhook 处理器
    webhook_queue.register_handler(
        WebhookQueueWorker.EVENT_TORRENT_COMPLETED,
        handle_torrent_completed
    )
    # 兼容 qBittorrent 的 torrent_finished 事件
    webhook_queue.register_handler(
        'torrent_finished',
        handle_torrent_completed
    )
    webhook_queue.register_handler(
        WebhookQueueWorker.EVENT_TORRENT_ADDED,
        handle_torrent_added
    )
    webhook_queue.register_handler(
        WebhookQueueWorker.EVENT_TORRENT_ERROR,
        handle_torrent_error
    )
    webhook_queue.register_handler(
        WebhookQueueWorker.EVENT_TORRENT_PAUSED,
        handle_torrent_paused
    )

    # 启动 Webhook 队列
    webhook_queue.start()
    logger.info('✅ Webhook 队列 worker 已启动')

    # 初始化 RSS 队列
    rss_queue = get_rss_queue()

    def handle_rss_event(payload):
        """处理 RSS Feed 事件 - 解析 Feed 并将项目加入队列"""
        try:
            from src.core.config import RSSFeed
            from src.container import container

            # 从 extra_data 获取完整的 feed 配置
            feed_data = payload.extra_data.get('feed_data', {})

            # 优先使用 feed_data，如果没有则从 extra_data 根层级获取
            blocked_keywords = feed_data.get('blocked_keywords', '') or payload.extra_data.get('blocked_keywords', '')
            blocked_regex = feed_data.get('blocked_regex', '') or payload.extra_data.get('blocked_regex', '')
            media_type = feed_data.get('media_type', '') or payload.extra_data.get('media_type', 'anime')

            logger.info(f'📡 解析 RSS Feed: {payload.rss_url[:50]}...')

            # 从容器获取服务
            rss_service = container.rss_service()
            history_repo = container.history_repo()
            download_repo = container.download_repo()

            # 创建历史记录
            history_id = history_repo.insert_rss_history(
                rss_url=payload.rss_url,
                triggered_by=payload.trigger_type
            )

            # 解析 RSS Feed
            items = rss_service.parse_feed(payload.rss_url)

            if not items:
                logger.info(f'📭 RSS Feed 没有新项目: {payload.rss_url[:50]}...')
                history_repo.update_rss_history_stats(
                    history_id,
                    items_found=0,
                    items_attempted=0,
                    items_processed=0,
                    status='completed'
                )
                return

            logger.info(f'📥 发现 {len(items)} 个项目，正在过滤和加入队列...')

            # 过滤器配置
            filter_config = {
                'blocked_keywords': blocked_keywords,
                'blocked_regex': blocked_regex,
            }

            # 将每个项目加入队列
            enqueued_count = 0
            filtered_count = 0
            exists_count = 0
            filter_service = container.filter_service()

            for item in items:
                # 检查是否已存在
                if item.hash:
                    existing = download_repo.get_by_hash(item.hash)
                    if existing:
                        history_repo.insert_rss_detail(
                            history_id, item.title, 'exists', '已存在于数据库'
                        )
                        exists_count += 1
                        continue

                # 检查过滤器
                if blocked_keywords or blocked_regex:
                    if filter_service.should_filter(item.title, blocked_keywords, blocked_regex):
                        logger.info(f'⏭️ 过滤跳过: {item.title[:50]}...')
                        history_repo.insert_rss_detail(
                            history_id, item.title, 'filtered', '匹配过滤规则'
                        )
                        filtered_count += 1
                        continue

                # 加入队列
                rss_queue.enqueue_single_item(
                    item_title=item.title,
                    torrent_url=item.torrent_url or item.link,
                    hash_id=item.hash or '',
                    rss_url=payload.rss_url,
                    media_type=media_type,
                    extra_data={
                        'trigger_type': payload.trigger_type,
                        'description': item.description,
                        'pub_date': item.pub_date,
                        'history_id': history_id,
                        **filter_config
                    }
                )
                enqueued_count += 1

            # 更新历史记录统计
            history_repo.update_rss_history_stats(
                history_id,
                items_found=len(items),
                items_attempted=enqueued_count,
                status='processing' if enqueued_count > 0 else 'completed'
            )

            logger.info(
                f'✅ RSS处理完成: 总数={len(items)}, '
                f'已存在={exists_count}, 过滤={filtered_count}, '
                f'加入队列={enqueued_count}'
            )

        except Exception as e:
            logger.error(f'❌ 处理 RSS Feed 事件失败: {e}', exc_info=True)

    def handle_single_item(payload):
        """处理单个 RSS 项目"""
        try:
            from src.container import container

            logger.info(f'🔄 处理项目: {payload.item_title[:50]}...')

            # 获取 history_id（如果有）
            history_id = payload.extra_data.get('history_id')
            history_repo = container.history_repo() if history_id else None

            # 检查是否已存在
            download_repo = container.download_repo()

            if payload.hash_id:
                existing = download_repo.get_by_hash(payload.hash_id)
                if existing:
                    logger.info(f'⏭️ 项目已存在: {payload.item_title[:50]}...')
                    if history_repo and history_id:
                        history_repo.insert_rss_detail(
                            history_id, payload.item_title, 'exists', '已存在于数据库'
                        )
                    return

            # 调用 DownloadManager 处理单个项目
            item_data = {
                'title': payload.item_title,
                'torrent_url': payload.torrent_url,
                'hash': payload.hash_id,
                'link': payload.torrent_url,
                'media_type': payload.media_type,
                'description': payload.extra_data.get('description', ''),
                'pub_date': payload.extra_data.get('pub_date'),
            }

            success = download_manager.process_single_rss_item(
                item_data,
                payload.extra_data.get('trigger_type', 'queue')
            )

            # 记录处理结果
            if history_repo and history_id:
                if success:
                    history_repo.insert_rss_detail(
                        history_id, payload.item_title, 'success'
                    )
                    # 更新处理计数
                    history_repo.increment_rss_history_processed(history_id)
                else:
                    history_repo.insert_rss_detail(
                        history_id, payload.item_title, 'failed', '处理失败'
                    )

            if success:
                logger.info(f'✅ 项目处理成功: {payload.item_title[:50]}...')
            else:
                logger.warning(f'⚠️ 项目处理失败: {payload.item_title[:50]}...')

        except Exception as e:
            logger.error(f'❌ 处理单个项目失败: {e}', exc_info=True)
            # 记录失败
            try:
                if history_id:
                    from src.container import container
                    history_repo = container.history_repo()
                    history_repo.insert_rss_detail(
                        history_id, payload.item_title, 'failed', str(e)
                    )
            except Exception:
                pass

    # 注册 RSS 处理器
    rss_queue.register_handler(
        RSSQueueWorker.EVENT_SCHEDULED_CHECK,
        handle_rss_event
    )
    rss_queue.register_handler(
        RSSQueueWorker.EVENT_MANUAL_CHECK,
        handle_rss_event
    )
    rss_queue.register_handler(
        RSSQueueWorker.EVENT_SINGLE_FEED,
        handle_rss_event
    )
    rss_queue.register_handler(
        RSSQueueWorker.EVENT_FIXED_SUBSCRIPTION,
        handle_rss_event
    )
    rss_queue.register_handler(
        RSSQueueWorker.EVENT_SINGLE_ITEM,
        handle_single_item
    )

    # 启动 RSS 队列
    rss_queue.start()
    logger.info('✅ RSS 队列 worker 已启动')

    return webhook_queue, rss_queue


def run_schedule(download_manager):
    """
    运行定时任务。

    Args:
        download_manager: DownloadManager 实例
    """
    from src.core.config import config
    from src.interface.web.controllers.system_status import system_status_manager
    from src.services.queue.rss_queue import get_rss_queue, RSSQueueWorker, RSSPayload

    logger.info('🔔 启动定时任务调度器...')
    logger.info(f'📋 RSS检查间隔: {config.rss.check_interval} 秒')

    rss_feeds = config.rss.get_feeds()
    logger.info(f'📡 已配置 {len(rss_feeds)} 个RSS订阅源')

    # 标记 RSS 调度器为运行中
    system_status_manager.set_rss_scheduler_status(True)

    # 获取 RSS 队列 worker
    rss_queue = get_rss_queue()

    def enqueue_rss_feeds(triggered_by: str):
        """将所有配置的 RSS feeds 加入队列"""
        feeds = config.rss.get_feeds()
        if not feeds:
            logger.info('📭 没有配置RSS链接')
            return

        for feed in feeds:
            feed_data = {
                'url': feed.url,
                'blocked_keywords': feed.blocked_keywords,
                'blocked_regex': feed.blocked_regex,
                'media_type': feed.media_type,
            }
            payload = RSSPayload(
                rss_url=feed.url,
                trigger_type=triggered_by,
                extra_data={'feed_data': feed_data}
            )
            rss_queue.enqueue_event(
                event_type=RSSQueueWorker.EVENT_SINGLE_FEED,
                payload=payload
            )
        logger.info(f'📥 已将 {len(feeds)} 个RSS链接加入处理队列')

    # 立即执行一次
    logger.info('⚡ 立即执行首次RSS检查...')
    enqueue_rss_feeds('启动时触发')

    # 设置定时任务
    def scheduled_task():
        enqueue_rss_feeds('定时触发')
        next_run = datetime.now() + timedelta(seconds=config.rss.check_interval)
        logger.info(f"⏰ 下次RSS检查时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

    schedule.every(config.rss.check_interval).seconds.do(scheduled_task)

    while True:
        schedule.run_pending()
        time.sleep(1)


def handle_rss_command(args, download_manager):
    """
    处理RSS命令。

    Args:
        args: 命令行参数
        download_manager: DownloadManager 实例
    """
    from src.core.config import RSSFeed

    logger.info(f'🔄 处理RSS链接: {args.url}')
    feed = RSSFeed(url=args.url)
    download_manager.process_rss_feeds([feed], '命令行触发')


def handle_magnet_command(args, download_manager):
    """
    处理磁力链接命令。

    Args:
        args: 命令行参数
        download_manager: DownloadManager 实例
    """
    logger.info(f'🔄 处理磁力链接: {args.hash}')
    magnet_link = f'magnet:?xt=urn:btih:{args.hash}'
    data = {
        'upload_type': 'magnet',
        'magnet_link': magnet_link,
        'anime_title': args.title,
        'subtitle_group': args.group,
        'season': args.season,
        'category': args.category
    }
    success = download_manager.process_manual_upload(data)
    if success:
        logger.info('✅ 磁力链接处理成功')
    else:
        logger.error('❌ 磁力链接处理失败')


def handle_torrent_command(args, download_manager):
    """
    处理Torrent文件命令。

    Args:
        args: 命令行参数
        download_manager: DownloadManager 实例
    """
    logger.info(f'🔄 处理Torrent文件: {args.file}')

    try:
        with open(args.file, 'rb') as f:
            torrent_content = base64.b64encode(f.read()).decode('utf-8')

        data = {
            'upload_type': 'torrent',
            'torrent_file': torrent_content,
            'anime_title': args.title,
            'subtitle_group': args.group,
            'season': args.season,
            'category': args.category
        }
        success = download_manager.process_manual_upload(data)
        if success:
            logger.info('✅ Torrent文件处理成功')
        else:
            logger.error('❌ Torrent文件处理失败')
    except Exception as e:
        logger.error(f'❌ 读取Torrent文件失败: {e}')


def start_webhook_server(host: str, port: int):
    """
    启动 Webhook 服务器。

    Args:
        host: 监听地址
        port: 监听端口
    """
    from flask import Flask
    from src.interface.webhook.handler import create_webhook_blueprint

    app = Flask(__name__)
    app.register_blueprint(create_webhook_blueprint())

    # 使用 Werkzeug 静默模式
    import logging as werkzeug_logging
    werkzeug_logging.getLogger('werkzeug').setLevel(werkzeug_logging.WARNING)

    app.run(host=host, port=port, debug=False, use_reloader=False)


def main():
    """主程序入口"""
    from src.core.config import config
    from src.container import container
    from src.services.ai_debug_service import ai_debug_service

    parser = argparse.ArgumentParser(description='AniDown - 动漫下载管理器')
    parser.add_argument('--debug', action='store_true', help='启用debug模式')
    parser.add_argument('--test', action='store_true', help='运行验证测试')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # RSS命令
    rss_parser = subparsers.add_parser('rss', help='处理RSS链接')
    rss_parser.add_argument('url', help='RSS链接')

    # 磁力链接命令
    magnet_parser = subparsers.add_parser('magnet', help='处理磁力链接')
    magnet_parser.add_argument('hash', help='磁力链接hash')
    magnet_parser.add_argument('title', help='动漫名称')
    magnet_parser.add_argument('group', help='字幕组')
    magnet_parser.add_argument('--season', type=int, default=1, help='季数')
    magnet_parser.add_argument('--category', default='tv', choices=['tv', 'movie'])

    # Torrent文件命令
    torrent_parser = subparsers.add_parser('torrent', help='处理Torrent文件')
    torrent_parser.add_argument('file', help='Torrent文件路径')
    torrent_parser.add_argument('title', help='动漫名称')
    torrent_parser.add_argument('group', help='字幕组')
    torrent_parser.add_argument('--season', type=int, default=1, help='季数')
    torrent_parser.add_argument('--category', default='tv', choices=['tv', 'movie'])

    args = parser.parse_args()

    # 启用debug模式
    if args.debug:
        ai_debug_service.enable()
        logger.info('🐛 DEBUG模式已启用')
        logging.getLogger().setLevel(logging.DEBUG)

    # 验证测试模式
    if args.test:
        success = run_all_tests()
        sys.exit(0 if success else 1)

    logger.info('🚀 AniDown 启动中...')
    logger.info(f'📁 配置文件路径: {os.getenv("CONFIG_PATH", "config.json")}')

    # 初始化数据库
    init_database()

    # 初始化 Discord Webhook
    init_discord_webhook()

    # 初始化 API Key Pool
    init_key_pools()

    # 获取 DownloadManager 实例
    download_manager = container.download_manager()

    # 处理命令行参数
    if args.command == 'rss':
        handle_rss_command(args, download_manager)
        return
    elif args.command == 'magnet':
        handle_magnet_command(args, download_manager)
        return
    elif args.command == 'torrent':
        handle_torrent_command(args, download_manager)
        return

    # 默认启动服务器模式
    logger.info('🎬 启动服务器模式...')

    # 导入状态管理器
    from src.interface.web.controllers.system_status import system_status_manager

    # 初始化队列工作者
    webhook_queue, rss_queue = init_queue_workers(download_manager)

    # 启动 Webhook 服务器 (后台线程)
    if config.webhook.enabled:
        logger.info(f'🔗 正在启动 Webhook 服务器...')
        logger.info(f'📍 Webhook 地址: http://{config.webhook.host}:{config.webhook.port}')
        webhook_thread = Thread(
            target=start_webhook_server,
            kwargs={'host': config.webhook.host, 'port': config.webhook.port},
            daemon=True
        )
        webhook_thread.start()
        system_status_manager.set_webhook_status(True)
        logger.info('✅ Webhook 服务器已在后台启动')
    else:
        logger.info('⏭️ Webhook 服务器已禁用')

    # 启动 Web UI 服务器 (后台线程)
    if config.webui.enabled:
        logger.info(f'🌐 正在启动 Web UI 服务器...')

        def run_webui():
            from src.interface.web.app import create_app

            # 使用 Werkzeug 静默模式
            import logging as werkzeug_logging
            werkzeug_logging.getLogger('werkzeug').setLevel(werkzeug_logging.WARNING)

            app = create_app(container)
            system_status_manager.set_webui_status(True)
            app.run(
                host=config.webui.host,
                port=config.webui.port,
                debug=False,
                use_reloader=False
            )

        webui_thread = Thread(target=run_webui, daemon=True)
        webui_thread.start()
        logger.info(f'✅ Web UI 服务器已启动: http://{config.webui.host}:{config.webui.port}')
    else:
        logger.info('⏭️ Web UI 服务器已禁用')

    # 启动定时任务 (主线程)
    try:
        run_schedule(download_manager)
    except KeyboardInterrupt:
        logger.info('🛑 接收到停止信号，正在退出...')
        system_status_manager.set_rss_scheduler_status(False)
        system_status_manager.set_webui_status(False)
        system_status_manager.set_webhook_status(False)

        # 停止队列工作者
        webhook_queue.stop()
        rss_queue.stop()
        logger.info('✅ 已优雅关闭')
    except Exception as e:
        logger.error(f'❌ 发生未预期错误: {e}', exc_info=True)
        system_status_manager.set_rss_scheduler_status(False)


if __name__ == '__main__':
    main()
