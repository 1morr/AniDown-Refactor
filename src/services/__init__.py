"""
Services layer module.

Contains business logic services that orchestrate domain operations.
Services coordinate between adapters, repositories, and domain entities.
"""

from src.services.download.rss_processor import RSSItem, RSSProcessor
from src.services.download.torrent_completion_handler import TorrentCompletionHandler
from src.services.file.hardlink_service import HardlinkService
from src.services.file.path_builder import PathBuilder
from src.services.queue.queue_worker import QueueEvent, QueueWorker
from src.services.queue.rss_queue import RSSQueueWorker
from src.services.queue.webhook_queue import WebhookQueueWorker
from src.services.rename.file_classifier import FileClassifier
from src.services.rename.filename_formatter import FilenameFormatter
from src.services.rename.pattern_matcher import PatternMatcher
from src.services.rename.rename_service import RenameService

__all__ = [
    # Download services
    'RSSProcessor',
    'RSSItem',
    'TorrentCompletionHandler',
    # File services
    'PathBuilder',
    'HardlinkService',
    # Rename services
    'RenameService',
    'FileClassifier',
    'PatternMatcher',
    'FilenameFormatter',
    # Queue services
    'QueueWorker',
    'QueueEvent',
    'WebhookQueueWorker',
    'RSSQueueWorker',
]
