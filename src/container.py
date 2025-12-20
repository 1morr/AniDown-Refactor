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


class Container(containers.DeclarativeContainer):
    """依赖注入容器"""

    wiring_config = containers.WiringConfiguration(modules=[
        # Webhook handlers - will be added when migrated
        # 'src.interface.webhook.handler'
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

    # Note: Additional adapters and services will be added as they are migrated:
    # - ai_client (OpenAIAdapter)
    # - discord_client (DiscordAdapter)
    # - tvdb_client (TVDBAdapter)
    # - rss_service (RSSService)
    # - filter_service (FilterService)
    # - file_service (FileService)
    # - download_manager (DownloadManager)
    # - anime_service (AnimeService)


# 全局容器实例
container = Container()
