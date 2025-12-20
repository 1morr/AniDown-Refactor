"""
Services layer module.

Contains business logic services that orchestrate domain operations.
Services coordinate between adapters, repositories, and domain entities.
"""

from src.services.download.rss_processor import RSSItem, RSSProcessor, RSSProcessResult
from src.services.download.torrent_completion_handler import TorrentCompletionHandler
from src.services.file.hardlink_service import HardlinkService
from src.services.file.path_builder import PathBuilder
from src.services.queue.queue_worker import QueueEvent, QueueWorker
from src.services.queue.rss_queue import RSSQueueWorker
from src.services.queue.webhook_queue import WebhookQueueWorker
from src.services.queue import webhook_queue
from src.services.queue import rss_queue
from src.services.rename.file_classifier import FileClassifier
from src.services.rename.filename_formatter import FilenameFormatter
from src.services.rename.rename_service import RenameService
from src.services.filter_service import FilterService, get_filter_service
from src.services.metadata_service import MetadataService, get_metadata_service
from src.services.anime_service import AnimeService, get_anime_service
from src.services.ai_debug_service import AIDebugService, get_ai_debug_service
from src.services.log_rotation_service import LogRotationService, get_log_rotation_service
from src.services.rss_service import RSSService
from src.services.download_manager import DownloadManager, RSSProcessResult as DMProcessResult

__all__ = [
    # Download services
    'DownloadManager',
    'DMProcessResult',
    'RSSProcessor',
    'RSSItem',
    'RSSProcessResult',
    'TorrentCompletionHandler',
    # RSS Service
    'RSSService',
    # File services
    'PathBuilder',
    'HardlinkService',
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
    'get_filter_service',
    # Metadata service
    'MetadataService',
    'get_metadata_service',
    # Anime service
    'AnimeService',
    'get_anime_service',
    # AI Debug service
    'AIDebugService',
    'get_ai_debug_service',
    # Log rotation service
    'LogRotationService',
    'get_log_rotation_service',
]
