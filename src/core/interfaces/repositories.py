"""
Repository interfaces module.

Contains abstract base classes defining contracts for data access operations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from src.core.domain.entities import AnimeInfo, DownloadRecord, HardlinkRecord


class IAnimeRepository(ABC):
    """
    Anime information repository interface.

    Defines the contract for anime data access operations.
    """

    @abstractmethod
    def get_by_id(self, anime_id: int) -> Optional[AnimeInfo]:
        """
        Get anime by ID.

        Args:
            anime_id: The anime ID.

        Returns:
            AnimeInfo if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_by_title(self, title: str) -> Optional[AnimeInfo]:
        """
        Get anime by title (fuzzy match).

        Args:
            title: The title to search for.

        Returns:
            AnimeInfo if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_by_core_info(
        self,
        title: str,
        subtitle_group: Optional[str] = None,
        season: Optional[int] = None
    ) -> Optional[AnimeInfo]:
        """
        Get anime by core information (exact match).

        Args:
            title: The anime title.
            subtitle_group: Optional subtitle group name.
            season: Optional season number.

        Returns:
            AnimeInfo if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_all(self, limit: int = 100, offset: int = 0) -> List[AnimeInfo]:
        """
        Get all anime with pagination.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            List of AnimeInfo entities.
        """
        pass

    @abstractmethod
    def save(self, anime: AnimeInfo) -> int:
        """
        Save anime information.

        Args:
            anime: The anime entity to save.

        Returns:
            The ID of the saved anime.
        """
        pass

    @abstractmethod
    def update(self, anime: AnimeInfo) -> bool:
        """
        Update anime information.

        Args:
            anime: The anime entity to update.

        Returns:
            True if update was successful, False otherwise.
        """
        pass

    @abstractmethod
    def delete(self, anime_id: int) -> bool:
        """
        Delete anime by ID.

        Args:
            anime_id: The anime ID to delete.

        Returns:
            True if deletion was successful, False otherwise.
        """
        pass


class IDownloadRepository(ABC):
    """
    Download record repository interface.

    Defines the contract for download record data access operations.
    """

    @abstractmethod
    def get_by_hash(self, hash_id: str) -> Optional[DownloadRecord]:
        """
        Get download record by torrent hash.

        Args:
            hash_id: The torrent hash.

        Returns:
            DownloadRecord if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_by_id(self, record_id: int) -> Optional[DownloadRecord]:
        """
        Get download record by ID.

        Args:
            record_id: The record ID.

        Returns:
            DownloadRecord if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_by_anime_id(self, anime_id: int) -> List[DownloadRecord]:
        """
        Get all download records for an anime.

        Args:
            anime_id: The anime ID.

        Returns:
            List of DownloadRecord entities.
        """
        pass

    @abstractmethod
    def get_incomplete(self) -> List[DownloadRecord]:
        """
        Get all incomplete downloads.

        Returns:
            List of DownloadRecord entities with pending or downloading status.
        """
        pass

    @abstractmethod
    def get_recent(self, limit: int = 50) -> List[DownloadRecord]:
        """
        Get recent download records.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of DownloadRecord entities ordered by download time descending.
        """
        pass

    @abstractmethod
    def save(self, record: DownloadRecord) -> int:
        """
        Save download record.

        Args:
            record: The download record to save.

        Returns:
            The ID of the saved record.
        """
        pass

    @abstractmethod
    def update_status(
        self,
        hash_id: str,
        status: str,
        completion_time: Optional[datetime] = None
    ) -> bool:
        """
        Update download status.

        Args:
            hash_id: The torrent hash.
            status: The new status value.
            completion_time: Optional completion timestamp.

        Returns:
            True if update was successful, False otherwise.
        """
        pass

    @abstractmethod
    def move_to_history(self, hash_id: str) -> bool:
        """
        Move download record to history table.

        Args:
            hash_id: The torrent hash.

        Returns:
            True if move was successful, False otherwise.
        """
        pass

    @abstractmethod
    def delete(self, hash_id: str) -> bool:
        """
        Delete download record.

        Args:
            hash_id: The torrent hash.

        Returns:
            True if deletion was successful, False otherwise.
        """
        pass

    @abstractmethod
    def exists(self, hash_id: str) -> bool:
        """
        Check if download record exists.

        Args:
            hash_id: The torrent hash.

        Returns:
            True if record exists, False otherwise.
        """
        pass


class IHardlinkRepository(ABC):
    """
    Hardlink record repository interface.

    Defines the contract for hardlink record data access operations.
    """

    @abstractmethod
    def get_by_id(self, hardlink_id: int) -> Optional[HardlinkRecord]:
        """
        Get hardlink record by ID.

        Args:
            hardlink_id: The hardlink record ID.

        Returns:
            HardlinkRecord if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_by_torrent_hash(self, hash_id: str) -> List[HardlinkRecord]:
        """
        Get all hardlink records for a torrent.

        Args:
            hash_id: The torrent hash.

        Returns:
            List of HardlinkRecord entities.
        """
        pass

    @abstractmethod
    def get_by_anime_id(self, anime_id: int) -> List[HardlinkRecord]:
        """
        Get all hardlink records for an anime.

        Args:
            anime_id: The anime ID.

        Returns:
            List of HardlinkRecord entities.
        """
        pass

    @abstractmethod
    def save(self, record: HardlinkRecord) -> int:
        """
        Save hardlink record.

        Args:
            record: The hardlink record to save.

        Returns:
            The ID of the saved record.
        """
        pass

    @abstractmethod
    def delete(self, hardlink_id: int) -> bool:
        """
        Delete hardlink record.

        Args:
            hardlink_id: The hardlink record ID.

        Returns:
            True if deletion was successful, False otherwise.
        """
        pass

    @abstractmethod
    def delete_by_torrent_hash(self, hash_id: str) -> int:
        """
        Delete all hardlink records for a torrent.

        Args:
            hash_id: The torrent hash.

        Returns:
            Number of records deleted.
        """
        pass
