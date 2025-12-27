"""
Dependency Injection Container module.

Contains the Container class for managing application dependencies.
All services are registered following SOLID principles with proper
dependency chains.
"""

from dependency_injector import containers, providers

from src.core.config import config

# AI Components
from src.infrastructure.ai.api_client import OpenAIClient
from src.infrastructure.ai.circuit_breaker import CircuitBreaker
from src.infrastructure.ai.file_renamer import AIFileRenamer
from src.infrastructure.ai.key_pool import KeyPool
from src.infrastructure.ai.subtitle_matcher import AISubtitleMatcher
from src.infrastructure.ai.title_parser import AITitleParser

# Database
from src.infrastructure.database.session import DatabaseSessionManager

# External Adapters
from src.infrastructure.downloader.qbit_adapter import QBitAdapter
from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter

# Discord Notification Components
from src.infrastructure.notification.discord.discord_notifier import DiscordNotifier
from src.infrastructure.notification.discord.webhook_client import DiscordWebhookClient

# Repositories
from src.infrastructure.repositories.anime_repository import AnimeRepository
from src.infrastructure.repositories.download_repository import DownloadRepository
from src.infrastructure.repositories.history_repository import HistoryRepository
from src.infrastructure.repositories.subtitle_repository import SubtitleRepository

# Utility Services
from src.services.ai_debug_service import AIDebugService
from src.services.anime_service import AnimeService
from src.services.download_manager import DownloadManager

# File Services
from src.services.file.path_builder import PathBuilder
from src.services.file_service import FileService

# Core Services
from src.services.filter_service import FilterService
from src.services.log_rotation_service import LogRotationService
from src.services.metadata_service import MetadataService

# Rename Services
from src.services.rename.file_classifier import FileClassifier
from src.services.rename.filename_formatter import FilenameFormatter
from src.services.rename.rename_service import RenameService
from src.services.rss_service import RSSService
from src.services.subtitle_service import SubtitleService


class Container(containers.DeclarativeContainer):
    """
    依赖注入容器。

    管理应用程序所有依赖的生命周期和注入。
    遵循 SOLID 原则，特别是依赖倒置原则 (DIP)。

    服务层次结构:
    1. Database & Repositories (基础数据访问)
    2. External Adapters (外部服务适配器)
    3. AI Components (AI 相关组件)
    4. Notification Components (通知组件)
    5. Core Services (核心业务服务)
    6. Orchestrator (业务协调器)
    """

    wiring_config = containers.WiringConfiguration(modules=[
        'src.interface.webhook.handler',
        'src.interface.web.controllers.ai_queue_status',
        'src.interface.web.controllers.ai_test',
        'src.interface.web.controllers.anime',
        'src.interface.web.controllers.anime_detail',
        'src.interface.web.controllers.config',
        'src.interface.web.controllers.dashboard',
        'src.interface.web.controllers.database',
        'src.interface.web.controllers.downloads',
        'src.interface.web.controllers.manual_upload',
        'src.interface.web.controllers.rss',
        'src.interface.web.controllers.system_status',
    ])

    # ===== Configuration =====
    app_config = providers.Configuration()

    # ===== Database =====
    db_manager = providers.Singleton(DatabaseSessionManager)

    # ===== Repositories =====
    anime_repo = providers.Singleton(AnimeRepository)
    download_repo = providers.Singleton(DownloadRepository)
    history_repo = providers.Singleton(HistoryRepository)
    subtitle_repo = providers.Singleton(SubtitleRepository)

    # ===== External Adapters =====
    qb_client = providers.Singleton(QBitAdapter)
    tvdb_client = providers.Singleton(TVDBAdapter)

    # ===== AI Components =====
    # OpenAI API Clients - 分离标题解析和重命名的客户端（使用不同 timeout）
    title_parse_api_client = providers.Singleton(
        OpenAIClient,
        timeout=config.openai.title_parse.timeout
    )
    rename_api_client = providers.Singleton(
        OpenAIClient,
        timeout=config.openai.multi_file_rename.timeout
    )

    # Title Parse: KeyPool & CircuitBreaker
    title_parse_pool = providers.Singleton(
        KeyPool,
        purpose='title_parse'
    )
    title_parse_breaker = providers.Singleton(
        CircuitBreaker,
        purpose='title_parse'
    )
    title_parser = providers.Singleton(
        AITitleParser,
        key_pool=title_parse_pool,
        circuit_breaker=title_parse_breaker,
        api_client=title_parse_api_client
    )

    # Multi-File Rename: KeyPool & CircuitBreaker
    rename_pool = providers.Singleton(
        KeyPool,
        purpose='multi_file_rename'
    )
    rename_breaker = providers.Singleton(
        CircuitBreaker,
        purpose='multi_file_rename'
    )
    file_renamer = providers.Singleton(
        AIFileRenamer,
        key_pool=rename_pool,
        circuit_breaker=rename_breaker,
        api_client=rename_api_client
    )

    # Subtitle Match: KeyPool & CircuitBreaker
    # 如果subtitle_match未配置，则fallback到multi_file_rename配置
    subtitle_match_api_client = providers.Singleton(
        OpenAIClient,
        timeout=config.openai.subtitle_match.timeout
        if config.openai.subtitle_match.api_key or config.openai.subtitle_match.pool_name
        else config.openai.multi_file_rename.timeout
    )
    subtitle_match_pool = providers.Singleton(
        KeyPool,
        purpose='subtitle_match'
    )
    subtitle_match_breaker = providers.Singleton(
        CircuitBreaker,
        purpose='subtitle_match'
    )
    subtitle_matcher = providers.Singleton(
        AISubtitleMatcher,
        key_pool=subtitle_match_pool,
        circuit_breaker=subtitle_match_breaker,
        api_client=subtitle_match_api_client
    )

    # ===== Notification Components =====
    # 统一的 Discord 通知器（实现所有通知接口）
    discord_webhook = providers.Singleton(DiscordWebhookClient)
    discord_notifier = providers.Singleton(
        DiscordNotifier,
        webhook_client=discord_webhook
    )

    # 为向后兼容，提供别名（指向同一实例）
    rss_notifier = discord_notifier
    download_notifier = discord_notifier
    hardlink_notifier = discord_notifier
    error_notifier = discord_notifier
    ai_usage_notifier = discord_notifier
    webhook_received_notifier = discord_notifier

    # ===== File Services =====
    path_builder = providers.Singleton(
        PathBuilder,
        download_root=config.qbittorrent.base_download_path,
        library_root=config.link_target_path
    )

    # ===== Rename Services =====
    file_classifier = providers.Singleton(FileClassifier)
    filename_formatter = providers.Singleton(FilenameFormatter)

    rename_service = providers.Singleton(
        RenameService,
        file_classifier=file_classifier,
        filename_formatter=filename_formatter,
        anime_repo=anime_repo,
        ai_file_renamer=file_renamer
    )

    # ===== Core Services =====
    filter_service = providers.Singleton(FilterService)

    metadata_service = providers.Singleton(
        MetadataService,
        metadata_client=tvdb_client
    )

    rss_service = providers.Singleton(
        RSSService,
        download_repo=download_repo
    )

    anime_service = providers.Singleton(
        AnimeService,
        anime_repo=anime_repo,
        download_repo=download_repo,
        download_client=qb_client,
        path_builder=path_builder
    )

    file_service = providers.Singleton(
        FileService,
        history_repo=history_repo,
        path_builder=path_builder
    )

    subtitle_service = providers.Singleton(
        SubtitleService,
        subtitle_repo=subtitle_repo,
        history_repo=history_repo,
        subtitle_matcher=subtitle_matcher
    )

    # ===== Core Orchestrator =====
    download_manager = providers.Singleton(
        DownloadManager,
        anime_repo=anime_repo,
        download_repo=download_repo,
        history_repo=history_repo,
        title_parser=title_parser,
        file_renamer=file_renamer,
        download_client=qb_client,
        rss_service=rss_service,
        filter_service=filter_service,
        rename_service=rename_service,
        hardlink_service=file_service,
        path_builder=path_builder,
        metadata_service=metadata_service,
        rss_notifier=rss_notifier,
        download_notifier=download_notifier,
        hardlink_notifier=hardlink_notifier,
        error_notifier=error_notifier,
        ai_usage_notifier=ai_usage_notifier,
        webhook_received_notifier=webhook_received_notifier
    )

    # ===== Utility Services =====
    ai_debug_service = providers.Singleton(AIDebugService)
    log_rotation_service = providers.Singleton(LogRotationService)


# 全局容器实例
container = Container()
