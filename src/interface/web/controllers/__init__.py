"""
控制器模块。

包含所有 Flask Blueprint 控制器。
"""

from .ai_queue_status import ai_queue_bp
from .ai_test import ai_test_bp
from .anime import anime_bp
from .config import config_bp
from .dashboard import dashboard_bp
from .database import database_bp
from .downloads import downloads_bp
from .manual_upload import manual_upload_bp
from .rss import rss_bp
from .system_status import system_status_bp

__all__ = [
    'ai_queue_bp',
    'ai_test_bp',
    'anime_bp',
    'config_bp',
    'dashboard_bp',
    'database_bp',
    'downloads_bp',
    'manual_upload_bp',
    'rss_bp',
    'system_status_bp',
]
