"""
Adapter interfaces module.

Contains abstract base classes defining contracts for external service adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TitleParseResult:
    """
    Title parsing result data class.

    Represents the result of parsing an anime title from RSS feed or file name.

    Attributes:
        original_title: The original unparsed title.
        clean_title: Cleaned short title for internal use.
        full_title: Full official title (if available).
        subtitle_group: Name of the subtitle group.
        season: Season number (0 for movies).
        episode: Episode number (if applicable).
        category: Content category ('tv' or 'movie').
        quality_info: Quality-related information (resolution, codec, etc.).
    """
    original_title: str
    clean_title: str
    full_title: Optional[str] = None
    subtitle_group: str = ''
    season: int = 1
    episode: Optional[int] = None
    category: str = 'tv'
    quality_info: Dict[str, str] = field(default_factory=dict)

    @property
    def is_movie(self) -> bool:
        """Check if this is a movie."""
        return self.category == 'movie' or self.season == 0

    @property
    def display_title(self) -> str:
        """Return the best available title for display."""
        return self.full_title or self.clean_title or self.original_title


@dataclass
class RenameResult:
    """
    Rename operation result data class.

    Represents the result of a file rename mapping operation.

    Attributes:
        main_files: Mapping of original names to new names for main files.
        skipped_files: List of files that were skipped.
        seasons_info: Season-related information.
        patterns: Regular expression patterns used for matching.
        method: The renaming method used.
    """
    main_files: Dict[str, str] = field(default_factory=dict)
    skipped_files: List[str] = field(default_factory=list)
    seasons_info: Dict[str, Any] = field(default_factory=dict)
    patterns: Dict[str, str] = field(default_factory=dict)
    method: str = 'ai'

    @property
    def has_files(self) -> bool:
        """Check if there are any files to rename."""
        return bool(self.main_files)

    @property
    def file_count(self) -> int:
        """Return the number of files to rename."""
        return len(self.main_files)

    @property
    def skipped_count(self) -> int:
        """Return the number of skipped files."""
        return len(self.skipped_files)


class ITitleParser(ABC):
    """
    Title parser interface.

    Defines the contract for parsing anime titles from various sources.
    """

    @abstractmethod
    def parse(self, title: str) -> Optional[TitleParseResult]:
        """
        Parse an anime title.

        Args:
            title: The title string to parse.

        Returns:
            TitleParseResult if parsing was successful, None otherwise.
        """
        pass


class IFileRenamer(ABC):
    """
    File renamer interface.

    Defines the contract for generating file rename mappings.
    """

    @abstractmethod
    def generate_rename_mapping(
        self,
        files: List[str],
        category: str,
        anime_title: Optional[str] = None,
        folder_structure: Optional[str] = None,
        tvdb_data: Optional[Dict[str, Any]] = None
    ) -> Optional[RenameResult]:
        """
        Generate rename mapping for a list of files.

        Args:
            files: List of file names to process.
            category: Content category ('tv' or 'movie').
            anime_title: Optional anime title for naming.
            folder_structure: Optional folder structure information.
            tvdb_data: Optional TVDB metadata for episode naming.

        Returns:
            RenameResult if successful, None otherwise.
        """
        pass


class IDownloadClient(ABC):
    """
    Download client interface.

    Defines the contract for interacting with download clients (e.g., qBittorrent).
    """

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if connected to the download client.

        Returns:
            True if connected, False otherwise.
        """
        pass

    @abstractmethod
    def add_torrent(
        self,
        torrent_url: str,
        save_path: str,
        hash_id: Optional[str] = None
    ) -> bool:
        """
        Add a torrent by URL.

        Args:
            torrent_url: URL to the torrent file or magnet link.
            save_path: Directory to save downloaded files.
            hash_id: Optional expected hash for verification.

        Returns:
            True if torrent was added successfully, False otherwise.
        """
        pass

    @abstractmethod
    def add_torrent_file(
        self,
        file_path: str,
        save_path: str
    ) -> Optional[str]:
        """
        Add a torrent from a local file.

        Args:
            file_path: Path to the .torrent file.
            save_path: Directory to save downloaded files.

        Returns:
            Torrent hash if successful, None otherwise.
        """
        pass

    @abstractmethod
    def add_magnet(
        self,
        magnet_link: str,
        save_path: str
    ) -> Optional[str]:
        """
        Add a torrent from a magnet link.

        Args:
            magnet_link: The magnet URI.
            save_path: Directory to save downloaded files.

        Returns:
            Torrent hash if successful, None otherwise.
        """
        pass

    @abstractmethod
    def get_torrent_info(self, hash_id: str) -> Optional[Dict[str, Any]]:
        """
        Get torrent information.

        Args:
            hash_id: The torrent hash.

        Returns:
            Dictionary with torrent info if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_torrent_files(self, hash_id: str) -> List[Dict[str, Any]]:
        """
        Get list of files in a torrent.

        Args:
            hash_id: The torrent hash.

        Returns:
            List of file information dictionaries.
        """
        pass

    @abstractmethod
    def get_torrent_progress(self, hash_id: str) -> float:
        """
        Get download progress for a torrent.

        Args:
            hash_id: The torrent hash.

        Returns:
            Progress as a float from 0.0 to 1.0.
        """
        pass

    @abstractmethod
    def delete_torrent(self, hash_id: str, delete_files: bool = False) -> bool:
        """
        Delete a torrent.

        Args:
            hash_id: The torrent hash.
            delete_files: Whether to delete downloaded files.

        Returns:
            True if deletion was successful, False otherwise.
        """
        pass

    @abstractmethod
    def pause_torrent(self, hash_id: str) -> bool:
        """
        Pause a torrent.

        Args:
            hash_id: The torrent hash.

        Returns:
            True if pause was successful, False otherwise.
        """
        pass

    @abstractmethod
    def resume_torrent(self, hash_id: str) -> bool:
        """
        Resume a paused torrent.

        Args:
            hash_id: The torrent hash.

        Returns:
            True if resume was successful, False otherwise.
        """
        pass
