"""
Services layer module.

Contains business logic services that orchestrate domain operations.
Services coordinate between adapters, repositories, and domain entities.
"""

from src.services.ai_debug_service import AIDebugService
from src.services.anime_service import AnimeService
from src.services.download_manager import DownloadManager, RSSProcessResult
from src.services.file.path_builder import PathBuilder
from src.services.file_service import FileService
from src.services.filter_service import FilterService
from src.services.log_rotation_service import LogRotationService
from src.services.metadata_service import MetadataService
from src.services.queue import rss_queue, webhook_queue
from src.services.queue.queue_worker import QueueEvent, QueueWorker
from src.services.queue.rss_queue import RSSQueueWorker
from src.services.queue.webhook_queue import WebhookQueueWorker
from src.services.rename.file_classifier import FileClassifier
from src.services.rename.filename_formatter import FilenameFormatter
from src.services.rename.rename_service import RenameService
from src.services.rss_service import RSSService

__all__ = [
    # Download services
    'DownloadManager',
    'RSSProcessResult',
    # RSS Service
    'RSSService',
    # File services
    'PathBuilder',
    'FileService',
    # Rename services
    'RenameService',
    'FileClassifier',
    'FilenameFormatter',
    # Queue services
    'QueueWorker',
    'QueueEvent',
    'WebhookQueueWorker',
    'RSSQueueWorker',
    'webhook_queue',
    'rss_queue',
    # Filter service
    'FilterService',
    # Metadata service
    'MetadataService',
    # Anime service
    'AnimeService',
    # AI Debug service
    'AIDebugService',
    # Log rotation service
    'LogRotationService',
]
