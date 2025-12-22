"""
Repositories module.

Provides data access layer implementations.
"""

from src.infrastructure.repositories.anime_repository import AnimeRepository
from src.infrastructure.repositories.download_repository import DownloadRepository
from src.infrastructure.repositories.history_repository import HistoryRepository
from src.infrastructure.repositories.ai_key_repository import AIKeyRepository, ai_key_repository
from src.infrastructure.repositories.subtitle_repository import SubtitleRepository, subtitle_repository

__all__ = [
    'AnimeRepository',
    'DownloadRepository',
    'HistoryRepository',
    'AIKeyRepository',
    'ai_key_repository',
    'SubtitleRepository',
    'subtitle_repository',
]
