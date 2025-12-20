"""
Dependency Injection Container module.

Contains the Container class for managing application dependencies.
"""

from dependency_injector import containers, providers

from src.core.config import config
from src.infrastructure.database.session import DatabaseSessionManager, db_manager
from src.infrastructure.repositories.anime_repository import AnimeRepository
from src.infrastructure.repositories.download_repository import DownloadRepository
from src.infrastructure.repositories.history_repository import HistoryRepository
from src.infrastructure.downloader.qbit_adapter import QBitAdapter
from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter
from src.services.filter_service import FilterService
from src.services.metadata_service import MetadataService
from src.services.anime_service import AnimeService
from src.services.ai_debug_service import AIDebugService
from src.services.log_rotation_service import LogRotationService


class Container(containers.DeclarativeContainer):
    """依赖注入容器"""

    wiring_config = containers.WiringConfiguration(modules=[
        'src.interface.webhook.handler',
    ])

    # Configuration
    config = providers.Configuration()

    # Database
    db_manager = providers.Singleton(DatabaseSessionManager)

    # Repositories
    anime_repo = providers.Singleton(AnimeRepository)
    download_repo = providers.Singleton(DownloadRepository)
    history_repo = providers.Singleton(HistoryRepository)

    # Adapters
    qb_client = providers.Singleton(QBitAdapter)
    tvdb_client = providers.Singleton(TVDBAdapter)

    # Services - Filter
    filter_service = providers.Singleton(FilterService)

    # Services - Metadata
    metadata_service = providers.Singleton(
        MetadataService,
        metadata_client=tvdb_client
    )

    # Services - Anime
    anime_service = providers.Singleton(
        AnimeService,
        anime_repo=anime_repo,
        download_repo=download_repo,
        download_client=qb_client
    )

    # Services - AI Debug
    ai_debug_service = providers.Singleton(AIDebugService)

    # Services - Log Rotation
    log_rotation_service = providers.Singleton(LogRotationService)

    # Note: Additional services will be added as they are migrated:
    # - ai_client (OpenAIAdapter)
    # - discord_client (DiscordAdapter)
    # - rss_service (RSSService)
    # - file_service (FileService)
    # - download_manager (DownloadManager)


# 全局容器实例
container = Container()
