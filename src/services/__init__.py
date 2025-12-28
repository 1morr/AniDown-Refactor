"""
Services layer module.

Contains business logic services that orchestrate domain operations.
Services coordinate between adapters, repositories, and domain entities.

Directory structure:
- anime/       : Anime and subtitle services
- debug/       : AI debugging services
- download/    : Download processing services
- file/        : File and path operations
- metadata/    : External metadata services
- queue/       : Queue processing workers
- rename/      : File renaming services
- rss/         : RSS feed and filtering services
- system/      : System-level services (config, logging)
"""

# Anime services
from src.services.anime.anime_service import AnimeService
from src.services.anime.subtitle_service import SubtitleService

# Debug services
from src.services.debug.ai_debug_service import AIDebugService

# Download services
from src.services.download_manager import DownloadManager, RSSProcessResult

# File services
from src.services.file.file_service import FileService
from src.services.file.path_builder import PathBuilder

# Metadata services
from src.services.metadata.metadata_service import MetadataService

# Queue services
from src.services.queue import rss_queue, webhook_queue
from src.services.queue.queue_worker import QueueEvent, QueueWorker
from src.services.queue.rss_queue import RSSQueueWorker
from src.services.queue.webhook_queue import WebhookQueueWorker

# Rename services
from src.services.rename.file_classifier import FileClassifier
from src.services.rename.filename_formatter import FilenameFormatter
from src.services.rename.rename_service import RenameService

# RSS services
from src.services.rss.filter_service import FilterService
from src.services.rss.rss_service import RSSService

# System services
from src.services.system.config_reloader import ConfigReloader, config_reloader, reload_config
from src.services.system.log_rotation_service import LogRotationService

__all__ = [
    # Anime services
    'AnimeService',
    'SubtitleService',
    # Debug services
    'AIDebugService',
    # Download services
    'DownloadManager',
    'RSSProcessResult',
    # File services
    'PathBuilder',
    'FileService',
    # Metadata services
    'MetadataService',
    # Queue services
    'QueueWorker',
    'QueueEvent',
    'WebhookQueueWorker',
    'RSSQueueWorker',
    'webhook_queue',
    'rss_queue',
    # Rename services
    'RenameService',
    'FileClassifier',
    'FilenameFormatter',
    # RSS services
    'RSSService',
    'FilterService',
    # System services
    'ConfigReloader',
    'config_reloader',
    'reload_config',
    'LogRotationService',
]
