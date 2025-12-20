"""
Rename service module.

Provides coordinated file renaming functionality for media library organization.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from src.core.interfaces.adapters import IFileRenamer, RenameResult
from src.services.rename.file_classifier import (
    ClassificationResult,
    ClassifiedFile,
    FileClassifier,
)
from src.services.rename.filename_formatter import FilenameFormatter
from src.services.rename.pattern_matcher import EpisodeMatch, PatternMatcher

logger = logging.getLogger(__name__)


class RenameService(IFileRenamer):
    """
    Rename service.

    Coordinates file classification, pattern matching, and filename formatting
    to generate rename mappings for media library organization.
    """

    def __init__(
        self,
        file_classifier: Optional[FileClassifier] = None,
        pattern_matcher: Optional[PatternMatcher] = None,
        filename_formatter: Optional[FilenameFormatter] = None
    ):
        """
        Initialize the rename service.

        Args:
            file_classifier: File classifier instance.
            pattern_matcher: Pattern matcher instance.
            filename_formatter: Filename formatter instance.
        """
        self._classifier = file_classifier or FileClassifier()
        self._matcher = pattern_matcher or PatternMatcher()
        self._formatter = filename_formatter or FilenameFormatter()

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

        Implements IFileRenamer interface.

        Args:
            files: List of file names to process.
            category: Content category ('tv' or 'movie').
            anime_title: Optional anime title for naming.
            folder_structure: Optional folder structure information.
            tvdb_data: Optional TVDB metadata for episode naming.

        Returns:
            RenameResult if successful, None otherwise.
        """
        if not files:
            return None

        # Convert file names to file info dictionaries
        file_infos = [{'name': f} for f in files]

        # Classify files
        classified = self._classifier.classify_files(file_infos)

        if not classified.has_videos:
            logger.warning('⚠️ No video files found for renaming')
            return None

        # Generate mappings
        return self._generate_mappings(
            classified=classified,
            category=category,
            anime_title=anime_title,
            tvdb_data=tvdb_data
        )

    def classify_files(
        self,
        torrent_files: List[Dict[str, Any]],
        download_directory: str
    ) -> Tuple[List[ClassifiedFile], List[ClassifiedFile]]:
        """
        Classify torrent files into video and subtitle files.

        Args:
            torrent_files: List of torrent file information dictionaries.
            download_directory: Base download directory.

        Returns:
            Tuple of (video_files, subtitle_files).
        """
        # Normalize file info
        file_infos = []
        for f in torrent_files:
            name = f.get('name', '')
            # Handle nested paths (some torrent clients use relative paths)
            if '/' in name or '\\' in name:
                name = os.path.basename(name)

            file_infos.append({
                'name': name,
                'relative_path': f.get('relative_path', f.get('name', '')),
                'full_path': os.path.join(
                    download_directory,
                    f.get('name', '')
                ),
                'size': f.get('size', 0)
            })

        classified = self._classifier.classify_files(file_infos, download_directory)

        return classified.video_files, classified.subtitle_files

    def generate_mapping(
        self,
        video_files: List[ClassifiedFile],
        anime_id: Optional[int],
        anime_title: str,
        subtitle_group: str,
        season: int,
        category: str,
        is_multi_season: bool = False,
        tvdb_data: Optional[Dict[str, Any]] = None
    ) -> Optional[RenameResult]:
        """
        Generate rename mapping for classified video files.

        Args:
            video_files: List of classified video files.
            anime_id: Anime ID for lookup.
            anime_title: Anime title for naming.
            subtitle_group: Subtitle group name.
            season: Season number.
            category: Content category ('tv' or 'movie').
            is_multi_season: Whether torrent contains multiple seasons.
            tvdb_data: Optional TVDB metadata.

        Returns:
            RenameResult with mappings, or None if failed.
        """
        if not video_files:
            return None

        main_files: Dict[str, str] = {}
        skipped_files: List[str] = []
        seasons_info: Dict[str, Any] = {}
        patterns: Dict[str, str] = {}

        for video in video_files:
            # Try pattern matching first
            episode_match = self._matcher.extract_episode(video.name)

            if episode_match:
                # Use pattern-based renaming
                if is_multi_season and episode_match.season:
                    effective_season = episode_match.season
                else:
                    effective_season = season

                new_name = self._formatter.format_tv_episode(
                    title=anime_title,
                    episode_match=EpisodeMatch(
                        episode=episode_match.episode,
                        season=effective_season,
                        version=episode_match.version,
                        special=episode_match.special
                    ),
                    extension=video.extension
                )

                main_files[video.name] = new_name

                # Track season info
                season_key = f'S{effective_season:02d}'
                if season_key not in seasons_info:
                    seasons_info[season_key] = {'episodes': []}
                seasons_info[season_key]['episodes'].append(episode_match.episode)

                patterns[video.name] = episode_match.match_text

            elif category == 'movie':
                # Movie naming (no episode number needed)
                new_name = self._formatter.format_movie(
                    title=anime_title,
                    extension=video.extension
                )
                main_files[video.name] = new_name

            else:
                # Could not extract episode info, skip
                logger.warning(f'⚠️ Could not extract episode from: {video.name}')
                skipped_files.append(video.relative_path or video.name)

        return RenameResult(
            main_files=main_files,
            skipped_files=skipped_files,
            seasons_info=seasons_info,
            patterns=patterns,
            method='pattern'
        )

    def _generate_mappings(
        self,
        classified: ClassificationResult,
        category: str,
        anime_title: Optional[str],
        tvdb_data: Optional[Dict[str, Any]]
    ) -> RenameResult:
        """
        Generate rename mappings for classified files.

        Args:
            classified: Classification result.
            category: Content category.
            anime_title: Anime title.
            tvdb_data: TVDB metadata.

        Returns:
            RenameResult with all mappings.
        """
        main_files: Dict[str, str] = {}
        skipped_files: List[str] = []
        seasons_info: Dict[str, Any] = {}
        patterns: Dict[str, str] = {}

        for video in classified.video_files:
            # Extract episode info
            episode_match = self._matcher.extract_episode(video.name)

            if category == 'movie':
                # Movie naming
                title = anime_title or self._formatter.extract_base_name(video.name)
                new_name = self._formatter.format_movie(
                    title=title,
                    extension=video.extension
                )
                main_files[video.name] = new_name

            elif episode_match:
                # TV episode naming
                title = anime_title or self._formatter.extract_base_name(video.name)
                new_name = self._formatter.format_tv_episode(
                    title=title,
                    episode_match=episode_match,
                    extension=video.extension
                )
                main_files[video.name] = new_name

                # Track season info
                season_key = f'S{episode_match.season:02d}'
                if season_key not in seasons_info:
                    seasons_info[season_key] = {'episodes': []}
                seasons_info[season_key]['episodes'].append(episode_match.episode)

                patterns[video.name] = episode_match.match_text

            else:
                # Could not determine episode
                skipped_files.append(video.relative_path or video.name)
                logger.debug(f'Skipping file (no episode info): {video.name}')

        return RenameResult(
            main_files=main_files,
            skipped_files=skipped_files,
            seasons_info=seasons_info,
            patterns=patterns,
            method='pattern'
        )

    def generate_subtitle_mapping(
        self,
        video_files: List[ClassifiedFile],
        subtitle_files: List[ClassifiedFile],
        video_rename_mapping: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Generate rename mapping for subtitle files based on video mapping.

        Args:
            video_files: List of video files.
            subtitle_files: List of subtitle files.
            video_rename_mapping: Video file rename mapping.

        Returns:
            Subtitle rename mapping (original -> new name).
        """
        subtitle_mapping: Dict[str, str] = {}

        for video in video_files:
            if video.name not in video_rename_mapping:
                continue

            new_video_name = video_rename_mapping[video.name]

            # Find matching subtitle
            matched_sub = self._classifier.get_main_subtitle(video, subtitle_files)
            if matched_sub:
                # Generate subtitle name based on video name
                new_sub_name = self._formatter.format_subtitle(
                    video_filename=new_video_name,
                    subtitle_extension=matched_sub.extension
                )
                subtitle_mapping[matched_sub.name] = new_sub_name

        return subtitle_mapping

    def validate_mapping(self, mapping: Dict[str, str]) -> bool:
        """
        Validate a rename mapping for potential issues.

        Args:
            mapping: Original -> new name mapping.

        Returns:
            True if mapping is valid, False otherwise.
        """
        if not mapping:
            return False

        # Check for duplicate new names
        new_names = list(mapping.values())
        if len(new_names) != len(set(new_names)):
            logger.error('❌ Rename mapping has duplicate target names')
            return False

        # Check for empty names
        for old_name, new_name in mapping.items():
            if not new_name or not new_name.strip():
                logger.error(f'❌ Empty new name for: {old_name}')
                return False

        return True
