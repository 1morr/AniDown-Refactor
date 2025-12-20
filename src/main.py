"""
AniDown Application Entry Point.

This module serves as the main entry point for the AniDown application.
It initializes the core infrastructure and can run basic validation tests.
"""

import argparse
import logging
import os
import sys
from datetime import datetime

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
    logger.info('✅ 依赖注入容器测试通过')


def run_all_tests():
    """运行所有测试"""
    logger.info('🚀 AniDown 阶段 A 验证开始...')
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
        logger.info('🎉 阶段 A 所有验证通过！')
        logger.info('=' * 50)
        return True

    except Exception as e:
        logger.error(f'❌ 验证失败: {e}', exc_info=True)
        return False


def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(description='AniDown - 动漫下载管理器')
    parser.add_argument('--test', action='store_true', help='运行阶段 A 验证测试')
    parser.add_argument('--debug', action='store_true', help='启用debug模式')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info('🐛 DEBUG模式已启用')

    if args.test:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    else:
        logger.info('🚀 AniDown 启动中...')
        logger.info('📌 阶段 A 完成 - 核心运行时迁移')
        logger.info('💡 使用 --test 参数运行验证测试')
        logger.info('')

        # 初始化数据库
        init_database()

        logger.info('✅ 核心组件初始化完成')
        logger.info('')
        logger.info('等待后续阶段迁移完成...')


if __name__ == '__main__':
    main()
