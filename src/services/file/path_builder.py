"""
Path builder service module.

Provides centralized path construction for downloads and media library organization.
"""

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)


class PathBuilder:
    """
    Path builder service.

    Constructs paths for download directories and media library organization.
    Follows a consistent naming convention for anime content.
    """

    def __init__(
        self,
        download_root: str,
        library_root: str,
        anime_subdir: str = 'Anime',
        live_action_subdir: str = 'LiveAction',
        tv_subdir: str = 'TV',
        movie_subdir: str = 'Movies'
    ):
        """
        Initialize the path builder.

        Args:
            download_root: Root directory for downloads.
            library_root: Root directory for media library.
            anime_subdir: Subdirectory name for anime content.
            live_action_subdir: Subdirectory name for live action content.
            tv_subdir: Subdirectory name for TV series.
            movie_subdir: Subdirectory name for movies.
        """
        # Normalize paths: convert backslashes to forward slashes and remove trailing slash
        self._download_root = self._normalize_path(download_root)
        self._library_root = self._normalize_path(library_root)
        self._anime_subdir = anime_subdir
        self._live_action_subdir = live_action_subdir
        self._tv_subdir = tv_subdir
        self._movie_subdir = movie_subdir

    def _normalize_path(self, path: str) -> str:
        """
        Normalize a path for cross-platform compatibility.

        Converts Windows backslashes to forward slashes and removes trailing slash.
        This ensures consistent path handling when running in Docker (Linux)
        with Windows-style paths from config.

        Args:
            path: Path to normalize.

        Returns:
            Normalized path with forward slashes and no trailing slash.
        """
        if not path:
            return path
        # Convert backslashes to forward slashes
        normalized = path.replace('\\', '/')
        # Remove trailing slash (but keep root slash for absolute paths like '/')
        if len(normalized) > 1 and normalized.endswith('/'):
            normalized = normalized.rstrip('/')
        return normalized

    def _build_path(self, *parts: str) -> str:
        """
        Build a path from parts using forward slashes.

        Args:
            *parts: Path components to join.

        Returns:
            Joined path with forward slashes.
        """
        # Filter out empty parts and join with forward slash
        non_empty = [p for p in parts if p]
        return '/'.join(non_empty)

    @property
    def download_root(self) -> str:
        """Return the download root directory."""
        return self._download_root

    @property
    def library_root(self) -> str:
        """Return the library root directory."""
        return self._library_root

    def build_download_path(
        self,
        title: str,
        season: int,
        category: str,
        media_type: str = 'anime',
        subtitle_group: Optional[str] = None
    ) -> str:
        """
        Build the download path for a new anime.

        Args:
            title: Anime title (cleaned/safe version).
            season: Season number (0 for movies).
            category: Content category ('tv' or 'movie').
            media_type: Media type ('anime' or 'live_action').
            subtitle_group: Optional subtitle group name.

        Returns:
            Full path for download directory.

        Example:
            >>> builder.build_download_path('Frieren', 1, 'tv', 'anime', 'Sakurato')
            '/downloads/Anime/TV/Frieren/Season 1/[Sakurato]'
        """
        # Sanitize title for filesystem
        safe_title = self._sanitize_filename(title)

        # Determine media type subdirectory (Anime or LiveAction)
        media_dir = self._anime_subdir if media_type == 'anime' else self._live_action_subdir

        # Determine category subdirectory (TV or Movies)
        category_dir = self._movie_subdir if (category == 'movie' or season == 0) else self._tv_subdir

        # Build path components using forward slashes
        if category == 'movie' or season == 0:
            # Movies: /downloads/Anime/Movies/Title
            path = self._build_path(self._download_root, media_dir, category_dir, safe_title)
        else:
            # TV: /downloads/Anime/TV/Title/Season X
            season_dir = f'Season {season}'
            path = self._build_path(self._download_root, media_dir, category_dir, safe_title, season_dir)

        # Optionally add subtitle group directory
        if subtitle_group:
            safe_group = self._sanitize_filename(subtitle_group)
            path = self._build_path(path, f'[{safe_group}]')

        logger.debug(f'📁 Built download path: {path}')
        return path

    def build_library_path(
        self,
        title: str,
        media_type: str,
        category: str,
        season: Optional[int] = None
    ) -> str:
        """
        Build the library path for media organization.

        Args:
            title: Anime title (cleaned/safe version).
            media_type: Media type ('anime' or 'live_action').
            category: Content category ('tv' or 'movie').
            season: Optional season number for TV series.

        Returns:
            Full path for library directory.

        Example:
            >>> builder.build_library_path('Frieren', 'anime', 'tv', 1)
            '/library/Anime/Frieren/Season 1'
        """
        # Sanitize title for filesystem
        safe_title = self._sanitize_filename(title)

        # Determine media type subdirectory
        type_dir = self._anime_subdir if media_type == 'anime' else self._live_action_subdir

        # Build path based on category using forward slashes
        if category == 'movie':
            # Movies: /library/Anime/Title
            path = self._build_path(self._library_root, type_dir, safe_title)
        else:
            # TV series: /library/Anime/Title/Season X
            if season is not None and season > 0:
                season_dir = f'Season {season}'
                path = self._build_path(self._library_root, type_dir, safe_title, season_dir)
            else:
                path = self._build_path(self._library_root, type_dir, safe_title)

        logger.debug(f'📁 Built library path: {path}')
        return path

    def build_target_directory(
        self,
        anime_title: str,
        media_type: str,
        category: str,
        season: Optional[int] = None
    ) -> str:
        """
        Build target directory for hardlink creation.

        This is an alias for build_library_path for semantic clarity.

        Args:
            anime_title: Anime title.
            media_type: Media type.
            category: Content category.
            season: Optional season number.

        Returns:
            Target directory path.
        """
        return self.build_library_path(anime_title, media_type, category, season)

    def ensure_directory(self, path: str) -> bool:
        """
        Ensure a directory exists, creating it if necessary.

        Args:
            path: Directory path to ensure.

        Returns:
            True if directory exists or was created successfully.
        """
        try:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                logger.info(f'📁 Created directory: {path}')
            return True
        except OSError as e:
            logger.error(f'❌ Failed to create directory {path}: {e}')
            return False

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a string for use in file/directory names.

        Args:
            name: Original name string.

        Returns:
            Sanitized name safe for filesystem use.
        """
        if not name:
            return ''

        # Replace invalid characters with fullwidth equivalents
        # Invalid chars in Windows/Unix: < > : " / \ | ? *
        illegal_chars = {
            '<': '＜', '>': '＞', ':': '：', '"': '"', '/': '／',
            '\\': '＼', '|': '｜', '?': '？', '*': '＊'
        }

        sanitized = name
        for char, replacement in illegal_chars.items():
            sanitized = sanitized.replace(char, replacement)

        # Replace multiple spaces with single space
        sanitized = re.sub(r'\s+', ' ', sanitized)

        # Remove leading/trailing spaces and dots
        sanitized = sanitized.strip(' .')

        # Truncate to reasonable length (255 chars max on most filesystems)
        if len(sanitized) > 200:
            sanitized = sanitized[:200]

        return sanitized

    def get_relative_path(self, full_path: str, root: str) -> str:
        """
        Get relative path from a root directory.

        Args:
            full_path: Full absolute path.
            root: Root directory to make relative to.

        Returns:
            Relative path from root.
        """
        try:
            return os.path.relpath(full_path, root)
        except ValueError:
            # Different drives on Windows
            return full_path

    def join_path(self, *parts: str) -> str:
        """
        Join path components safely.

        Args:
            *parts: Path components to join.

        Returns:
            Joined path string.
        """
        return os.path.join(*parts)
