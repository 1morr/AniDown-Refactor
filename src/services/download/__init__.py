"""
Download services package.

This package contains the refactored download management services,
split from the original monolithic DownloadManager into focused,
single-responsibility classes.
"""

from src.services.download.completion_handler import CompletionHandler
from src.services.download.download_notifier import DownloadNotifier
from src.services.download.rss_processor import RSSProcessor, RSSProcessResult
from src.services.download.status_service import StatusService
from src.services.download.upload_handler import UploadHandler

__all__ = [
    'DownloadNotifier',
    'RSSProcessor',
    'RSSProcessResult',
    'UploadHandler',
    'CompletionHandler',
    'StatusService',
]
