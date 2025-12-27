"""
Filename formatter module.

Provides filename formatting for media library organization.
"""

import logging
import os
import re

from src.services.rename.pattern_matcher import EpisodeMatch

logger = logging.getLogger(__name__)


class FilenameFormatter:
    """
    Filename formatter service.

    Formats filenames according to media library conventions.
    Supports Plex/Jellyfin compatible naming schemes.
    """

    # Default format templates
    TV_FORMAT = '{title} - S{season:02d}E{episode:02d}{version}{extension}'
    MOVIE_FORMAT = '{title}{year}{extension}'
    SPECIAL_FORMAT = '{title} - {special}{episode:02d}{version}{extension}'

    def __init__(
        self,
        tv_format: str | None = None,
        movie_format: str | None = None,
        special_format: str | None = None
    ):
        """
        Initialize the filename formatter.

        Args:
            tv_format: Format template for TV episodes.
            movie_format: Format template for movies.
            special_format: Format template for special episodes.
        """
        self._tv_format = tv_format or self.TV_FORMAT
        self._movie_format = movie_format or self.MOVIE_FORMAT
        self._special_format = special_format or self.SPECIAL_FORMAT

    def format_tv_episode(
        self,
        title: str,
        episode_match: EpisodeMatch,
        extension: str
    ) -> str:
        """
        Format a TV episode filename.

        Args:
            title: Anime title.
            episode_match: Extracted episode information.
            extension: File extension (with dot).

        Returns:
            Formatted filename.

        Example:
            >>> formatter.format_tv_episode('Frieren', EpisodeMatch(5, 1), '.mkv')
            'Frieren - S01E05.mkv'
        """
        if episode_match.special:
            return self._format_special(title, episode_match, extension)

        version_str = ''
        if episode_match.version:
            version_str = f' {episode_match.version}'

        formatted = self._tv_format.format(
            title=self._sanitize_title(title),
            season=episode_match.season,
            episode=episode_match.episode,
            version=version_str,
            extension=extension
        )

        return formatted

    def _format_special(
        self,
        title: str,
        episode_match: EpisodeMatch,
        extension: str
    ) -> str:
        """
        Format a special episode filename.

        Args:
            title: Anime title.
            episode_match: Extracted episode information.
            extension: File extension.

        Returns:
            Formatted filename.
        """
        version_str = ''
        if episode_match.version:
            version_str = f' {episode_match.version}'

        formatted = self._special_format.format(
            title=self._sanitize_title(title),
            special=episode_match.special,
            episode=episode_match.episode,
            version=version_str,
            extension=extension
        )

        return formatted

    def format_movie(
        self,
        title: str,
        extension: str,
        year: int | None = None
    ) -> str:
        """
        Format a movie filename.

        Args:
            title: Movie title.
            extension: File extension (with dot).
            year: Optional release year.

        Returns:
            Formatted filename.

        Example:
            >>> formatter.format_movie('Your Name', '.mkv', 2016)
            'Your Name (2016).mkv'
        """
        year_str = f' ({year})' if year else ''

        formatted = self._movie_format.format(
            title=self._sanitize_title(title),
            year=year_str,
            extension=extension
        )

        return formatted

    def format_with_season(
        self,
        title: str,
        season: int,
        episode: int,
        extension: str,
        version: str | None = None
    ) -> str:
        """
        Format a filename with explicit season and episode numbers.

        Args:
            title: Anime title.
            season: Season number.
            episode: Episode number.
            extension: File extension (with dot).
            version: Optional version string.

        Returns:
            Formatted filename.
        """
        version_str = f' {version}' if version else ''

        formatted = self._tv_format.format(
            title=self._sanitize_title(title),
            season=season,
            episode=episode,
            version=version_str,
            extension=extension
        )

        return formatted

    def format_subtitle(
        self,
        video_filename: str,
        subtitle_extension: str,
        language: str | None = None
    ) -> str:
        """
        Format a subtitle filename to match its video file.

        Args:
            video_filename: The video filename (with or without extension).
            subtitle_extension: Subtitle file extension (with dot).
            language: Optional language code (e.g., 'en', 'zh').

        Returns:
            Formatted subtitle filename.

        Example:
            >>> formatter.format_subtitle('Frieren - S01E05.mkv', '.ass', 'zh')
            'Frieren - S01E05.zh.ass'
        """
        # Remove video extension
        base_name = os.path.splitext(video_filename)[0]

        if language:
            return f'{base_name}.{language}{subtitle_extension}'
        else:
            return f'{base_name}{subtitle_extension}'

    def _sanitize_title(self, title: str) -> str:
        """
        Sanitize a title for use in filenames.

        Args:
            title: Original title.

        Returns:
            Sanitized title safe for filesystem use.
        """
        if not title:
            return ''

        # Remove characters invalid in Windows/Unix filenames
        sanitized = re.sub(r'[<>:"/\\|?*]', '', title)

        # Replace multiple spaces with single space
        sanitized = re.sub(r'\s+', ' ', sanitized)

        # Remove leading/trailing spaces
        sanitized = sanitized.strip()

        # Truncate if too long (preserve reasonable length)
        if len(sanitized) > 150:
            sanitized = sanitized[:150].rsplit(' ', 1)[0]

        return sanitized

    def extract_base_name(self, filename: str) -> str:
        """
        Extract the base name (title portion) from a formatted filename.

        Args:
            filename: Formatted filename.

        Returns:
            Extracted base name.
        """
        # Remove extension
        name = os.path.splitext(filename)[0]

        # Remove season/episode info
        # Pattern: - S01E05, S01E05, etc.
        name = re.sub(r'\s*-?\s*[Ss]\d{1,2}[Ee]\d{1,4}.*$', '', name)

        # Remove trailing version info
        name = re.sub(r'\s*[vV]\d+\s*$', '', name)

        return name.strip()

    def guess_format(self, filename: str) -> str:
        """
        Guess the format type of a filename.

        Args:
            filename: Filename to analyze.

        Returns:
            Format type: 'tv', 'movie', or 'unknown'.
        """
        # Check for season/episode patterns
        if re.search(r'[Ss]\d{1,2}[Ee]\d{1,4}', filename):
            return 'tv'
        if re.search(r'[\[\s\-](\d{2,4})[\]\s\-]', filename):
            return 'tv'

        # Check for movie patterns
        if re.search(r'\(\d{4}\)', filename):
            return 'movie'
        if re.search(r'movie|film|剧场版|劇場版', filename, re.IGNORECASE):
            return 'movie'

        return 'unknown'

    def add_quality_suffix(
        self,
        filename: str,
        quality_info: dict
    ) -> str:
        """
        Add quality information suffix to a filename.

        Args:
            filename: Base filename (with extension).
            quality_info: Dictionary with quality information.

        Returns:
            Filename with quality suffix added.

        Example:
            >>> formatter.add_quality_suffix('Frieren - S01E05.mkv', {'resolution': '1080p', 'codec': 'HEVC'})
            'Frieren - S01E05 [1080p HEVC].mkv'
        """
        if not quality_info:
            return filename

        # Build quality string
        parts = []
        for key in ['resolution', 'source', 'codec', 'audio']:
            if key in quality_info:
                parts.append(quality_info[key])

        if not parts:
            return filename

        quality_str = ' '.join(parts)

        # Insert before extension
        base, ext = os.path.splitext(filename)
        return f'{base} [{quality_str}]{ext}'
