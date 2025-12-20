"""
Rename service module.

Provides coordinated file renaming functionality for media library organization.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from src.core.config import config
from src.core.interfaces.adapters import IFileRenamer, RenameResult
from src.services.rename.file_classifier import (
    ClassificationResult,
    ClassifiedFile,
    FileClassifier,
)
from src.services.rename.filename_formatter import FilenameFormatter

if TYPE_CHECKING:
    from src.core.interfaces.repositories import IAnimeRepository
    from src.core.interfaces.adapters import IFileRenamer as IAIFileRenamer

logger = logging.getLogger(__name__)


class RenameService(IFileRenamer):
    """
    Rename service.

    Coordinates file classification, pattern matching, and filename formatting
    to generate rename mappings for media library organization.

    Follows the same logic as the old code:
    - If database has patterns: use regex to extract episode numbers
    - If no patterns or regex fails: call AI to generate rename mapping
    - If consistency naming enabled and not multi-season: use regex-based naming
    - If multi-season or consistency disabled: use AI returned filenames
    """

    def __init__(
        self,
        file_classifier: Optional[FileClassifier] = None,
        filename_formatter: Optional[FilenameFormatter] = None,
        anime_repo: Optional['IAnimeRepository'] = None,
        ai_file_renamer: Optional['IAIFileRenamer'] = None
    ):
        """
        Initialize the rename service.

        Args:
            file_classifier: File classifier instance.
            filename_formatter: Filename formatter instance.
            anime_repo: Anime repository for pattern storage.
            ai_file_renamer: AI file renamer for processing.
        """
        self._classifier = file_classifier or FileClassifier()
        self._formatter = filename_formatter or FilenameFormatter()
        self._anime_repo = anime_repo
        self._ai_file_renamer = ai_file_renamer

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
        tvdb_data: Optional[Dict[str, Any]] = None,
        folder_structure: Optional[str] = None,
        torrent_hash: Optional[str] = None
    ) -> Optional[RenameResult]:
        """
        Generate rename mapping for classified video files.

        Follows the same logic as the old code:
        1. If multi-season: force AI processing, skip regex
        2. If database has patterns: try regex extraction for all files
        3. If regex succeeds for all: use regex-based naming (with consistency option)
        4. If no patterns or regex fails: call AI to generate rename mapping
        5. Save AI-generated patterns to database (non-multi-season only)

        Args:
            video_files: List of classified video files.
            anime_id: Anime ID for lookup.
            anime_title: Anime title for naming.
            subtitle_group: Subtitle group name.
            season: Season number.
            category: Content category ('tv' or 'movie').
            is_multi_season: Whether torrent contains multiple seasons.
            tvdb_data: Optional TVDB metadata.
            folder_structure: Optional folder structure for AI.
            torrent_hash: Optional torrent hash for logging.

        Returns:
            RenameResult with mappings, or None if failed.
        """
        if not video_files:
            return None

        # Step 1: Check if multi-season - force AI processing
        if is_multi_season:
            logger.info('🔄 检测到多季内容，跳过正则表达式，直接使用AI处理')
            return self._process_with_ai(
                video_files=video_files,
                anime_id=anime_id,
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                is_multi_season=True,
                tvdb_data=tvdb_data,
                folder_structure=folder_structure,
                torrent_hash=torrent_hash
            )

        # Step 2: Check database for existing patterns
        db_patterns = None
        if anime_id and self._anime_repo:
            db_patterns = self._anime_repo.get_patterns(anime_id)
            if db_patterns:
                logger.debug(f'找到数据库中的正则表达式，尝试提取集数')

        # Step 3: Try regex extraction if patterns exist
        if db_patterns:
            extracted_episodes = {}
            can_extract_all = True

            for video in video_files:
                episode = self._extract_episode_from_db_patterns(video.name, db_patterns)
                if episode is not None:
                    extracted_episodes[video.name] = episode
                else:
                    can_extract_all = False
                    logger.warning(f'⚠️ 无法使用正则提取集数: {video.name}')
                    break

            if can_extract_all:
                # All files matched with regex - use database patterns
                logger.info(f'📋 使用数据库正则表达式成功匹配所有文件')
                return self._build_names_from_db_patterns(
                    video_files=video_files,
                    extracted_episodes=extracted_episodes,
                    anime_title=anime_title,
                    subtitle_group=subtitle_group,
                    season=season,
                    category=category,
                    db_patterns=db_patterns
                )
            else:
                logger.warning('数据库正则无法提取所有集数，需要使用AI重新生成正则')

        else:
            logger.info('数据库中没有正则表达式，需要使用AI生成正则')

        # Step 4: Use AI for processing
        return self._process_with_ai(
            video_files=video_files,
            anime_id=anime_id,
            anime_title=anime_title,
            subtitle_group=subtitle_group,
            season=season,
            category=category,
            is_multi_season=False,
            tvdb_data=tvdb_data,
            folder_structure=folder_structure,
            torrent_hash=torrent_hash
        )

    def _extract_episode_from_db_patterns(
        self,
        filename: str,
        patterns: Dict[str, str]
    ) -> Optional[int]:
        """
        Extract episode number using database patterns.

        Args:
            filename: File name to extract from.
            patterns: Pattern dictionary from database.

        Returns:
            Episode number or None if extraction failed.
        """
        if not patterns or not patterns.get('episode_regex'):
            return None

        episode_regex = patterns.get('episode_regex')
        if episode_regex == '无' or not episode_regex:
            return None

        try:
            match = re.search(episode_regex, filename)
            if match:
                episode_str = match.group(1) if match.groups() else match.group(0)
                return int(episode_str)
        except Exception as e:
            logger.error(f'使用正则提取集数失败: {e}')

        return None

    def _build_names_from_db_patterns(
        self,
        video_files: List[ClassifiedFile],
        extracted_episodes: Dict[str, int],
        anime_title: str,
        subtitle_group: str,
        season: int,
        category: str,
        db_patterns: Dict[str, str]
    ) -> RenameResult:
        """
        Build rename mapping using database patterns.

        Args:
            video_files: List of video files.
            extracted_episodes: Extracted episode mapping.
            anime_title: Anime title.
            subtitle_group: Subtitle group name.
            season: Season number.
            category: Content category.
            db_patterns: Patterns from database.

        Returns:
            RenameResult with mappings.
        """
        main_files: Dict[str, str] = {}
        skipped_files: List[str] = []
        seasons_info: Dict[str, Any] = {}

        for video in video_files:
            episode = extracted_episodes.get(video.name)

            # Extract subtitle type and special tag
            subtitle_type = self._extract_from_regex(
                video.name, db_patterns.get('subtitle_type_regex')
            )
            special_tag = self._extract_from_regex(
                video.name, db_patterns.get('special_tags_regex')
            )

            # Generate new filename
            new_name = self._format_filename_with_tags(
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                episode=episode,
                category=category,
                subtitle_type=subtitle_type,
                special_tag=special_tag,
                extension=video.extension
            )

            main_files[video.name] = new_name
            logger.info(f'✓ 文件名生成: {video.name} -> {new_name}')

            # Track season info
            if episode:
                season_key = f'S{season:02d}'
                if season_key not in seasons_info:
                    seasons_info[season_key] = {'episodes': []}
                seasons_info[season_key]['episodes'].append(episode)

        return RenameResult(
            main_files=main_files,
            skipped_files=skipped_files,
            seasons_info=seasons_info,
            patterns=db_patterns,
            method=f'数据库正则表达式（{"剧场版" if category == "movie" else "TV"}）'
        )

    def _process_with_ai(
        self,
        video_files: List[ClassifiedFile],
        anime_id: Optional[int],
        anime_title: str,
        subtitle_group: str,
        season: int,
        category: str,
        is_multi_season: bool,
        tvdb_data: Optional[Dict[str, Any]],
        folder_structure: Optional[str],
        torrent_hash: Optional[str]
    ) -> Optional[RenameResult]:
        """
        Process files using AI renamer.

        Args:
            video_files: List of video files.
            anime_id: Anime ID.
            anime_title: Anime title.
            subtitle_group: Subtitle group name.
            season: Season number.
            category: Content category.
            is_multi_season: Whether multi-season.
            tvdb_data: TVDB data.
            folder_structure: Folder structure.
            torrent_hash: Torrent hash.

        Returns:
            RenameResult or None if failed.
        """
        if not self._ai_file_renamer:
            logger.error('❌ AI文件重命名器未配置，无法处理')
            return None

        # Prepare AI input - use relative_path
        ai_input_files = [v.relative_path or v.name for v in video_files]
        logger.debug(f'🤖 发送给AI的文件: {ai_input_files}')
        logger.debug(f'🎯 数据库中的动漫名称: {anime_title}')

        try:
            # Call AI
            ai_result = self._ai_file_renamer.generate_rename_mapping(
                files=ai_input_files,
                category=category,
                anime_title=anime_title,
                folder_structure=folder_structure,
                tvdb_data=tvdb_data
            )

            if not ai_result or not ai_result.has_files:
                logger.error('❌ AI处理失败或未返回重命名映射')
                return None

            logger.debug(f'🤖 AI返回的main_files keys: {list(ai_result.main_files.keys())}')
            logger.debug(f'🤖 AI返回的skipped_files: {ai_result.skipped_files}')

            # Log seasons info
            if ai_result.seasons_info:
                logger.info('📺 AI识别的季度信息:')
                for season_num, info in sorted(ai_result.seasons_info.items()):
                    if isinstance(info, dict):
                        season_type = info.get('type', 'unknown')
                        season_count = info.get('count', 0)
                        season_desc = info.get('description', '')
                        type_emoji = {'tv': '📺', 'movie': '🎬', 'special': '⭐'}.get(
                            season_type, '❓'
                        )
                        logger.info(
                            f'  {type_emoji} Season {season_num}: {season_desc} '
                            f'({season_count}集, {season_type})'
                        )

            # Save patterns to database (non-multi-season only)
            if not is_multi_season and anime_id and self._anime_repo:
                patterns_to_save = self._extract_patterns_from_ai_result(ai_result.patterns)
                if patterns_to_save:
                    self._anime_repo.insert_patterns(anime_id, patterns_to_save)
                    logger.info(
                        f'✅ 已保存基于实际文件名生成的正则表达式到数据库（anime_id={anime_id}）'
                    )
            elif is_multi_season:
                logger.debug('🔄 多季内容不保存正则表达式，每次都将使用AI处理')

            # Determine naming method based on consistency setting
            use_consistent_naming = self._should_use_consistent_naming(category, is_multi_season)

            # Check if we can use consistent naming
            patterns_valid = (
                ai_result.patterns and
                ai_result.patterns.get('episode_regex') and
                ai_result.patterns.get('episode_regex') != '无'
            )

            if use_consistent_naming and patterns_valid and not is_multi_season:
                # Reload patterns from database
                db_patterns = self._anime_repo.get_patterns(anime_id) if anime_id and self._anime_repo else None
                if db_patterns:
                    logger.info(f'📋 使用一致性命名（{"剧场版" if category == "movie" else "TV"}）')
                    return self._build_consistent_names_from_ai(
                        video_files=video_files,
                        ai_result=ai_result,
                        anime_title=anime_title,
                        subtitle_group=subtitle_group,
                        season=season,
                        category=category,
                        db_patterns=db_patterns
                    )

            # Use AI returned filenames directly
            logger.info(f'📋 使用AI文件名（{"多季内容已禁用一致性命名" if is_multi_season else "TV"}）')
            return self._convert_ai_result_to_rename_result(
                video_files=video_files,
                ai_result=ai_result,
                category=category,
                is_multi_season=is_multi_season
            )

        except Exception as e:
            logger.error(f'❌ AI处理异常: {e}')
            return None

    def _should_use_consistent_naming(self, category: str, is_multi_season: bool) -> bool:
        """
        Determine if consistent naming should be used.

        Args:
            category: Content category.
            is_multi_season: Whether multi-season.

        Returns:
            True if consistent naming should be used.
        """
        if is_multi_season:
            return False

        if category == 'movie':
            return config.use_consistent_naming_movie
        else:
            return config.use_consistent_naming_tv

    def _extract_patterns_from_ai_result(
        self,
        ai_patterns: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, str]]:
        """
        Extract database-compatible patterns from AI result.

        Args:
            ai_patterns: Patterns from AI result.

        Returns:
            Database-compatible pattern dictionary or None.
        """
        if not ai_patterns:
            return None

        # AI field name -> Database field name mapping
        field_mapping = {
            'subtitle_group_regex': 'title_group_regex',
            'full_title_regex': 'full_title_regex',
            'clean_title_regex': 'short_title_regex',
            'episode_regex': 'episode_regex',
            'quality_regex': 'quality_regex',
            'special_tag_regex': 'special_tags_regex',
            'platform_regex': 'audio_source_regex',
            'source_regex': 'source_regex',
            'codec_regex': 'video_codec_regex',
            'subtitle_type_regex': 'subtitle_type_regex',
            'format_regex': 'video_format_regex'
        }

        patterns = {}
        for ai_field, db_field in field_mapping.items():
            value = ai_patterns.get(ai_field)
            if value and value != '无':
                patterns[db_field] = value

        return patterns if patterns else None

    def _extract_from_regex(
        self,
        filename: str,
        regex_pattern: Optional[str]
    ) -> Optional[str]:
        """
        Extract value using regex pattern.

        Args:
            filename: File name to extract from.
            regex_pattern: Regex pattern.

        Returns:
            Extracted value or None.
        """
        if not regex_pattern or regex_pattern == '无':
            return None

        try:
            filename_without_ext = os.path.splitext(filename)[0]
            match = re.search(regex_pattern, filename_without_ext)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                return value.strip('[]').strip()
        except Exception as e:
            logger.warning(f'⚠️ 正则提取失败: {e}')

        return None

    def _format_filename_with_tags(
        self,
        anime_title: str,
        subtitle_group: str,
        season: int,
        episode: Optional[int],
        category: str,
        subtitle_type: Optional[str],
        special_tag: Optional[str],
        extension: str
    ) -> str:
        """
        Format filename with tags (same format as old code).

        Returns format:
        - TV: Season X/动漫标题 - S0XE0X - 字幕组 [标签].ext
        - Movie: 动漫标题 - 字幕组 [标签].ext

        Args:
            anime_title: Anime title.
            subtitle_group: Subtitle group name.
            season: Season number.
            episode: Episode number.
            category: Content category.
            subtitle_type: Subtitle type tag.
            special_tag: Special tag.
            extension: File extension.

        Returns:
            Formatted filename.
        """
        # Clean illegal characters
        clean_anime_title = self._sanitize_filename(anime_title)
        clean_subtitle_group = self._sanitize_filename(subtitle_group)

        # Build tag list
        tags = []
        if special_tag and special_tag != '无':
            tags.append(self._sanitize_filename(special_tag))
        if subtitle_type and subtitle_type != '无':
            tags.append(self._sanitize_filename(subtitle_type))

        tag_suffix = f" [{'] ['.join(tags)}]{extension}" if tags else extension

        # Generate filename
        if category == 'movie':
            return f'{clean_anime_title} - {clean_subtitle_group}{tag_suffix}'
        else:
            filename = (
                f'{clean_anime_title} - S{season:02d}E{episode:02d} - '
                f'{clean_subtitle_group}{tag_suffix}'
            )
            return f'Season {season}/{filename}'

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename by replacing illegal characters.

        Args:
            filename: Original filename.

        Returns:
            Sanitized filename.
        """
        # Windows filesystem illegal characters - replace with fullwidth equivalents
        illegal_chars = {
            '<': '＜', '>': '＞', ':': '：', '"': "'", '"': "'", '"': "'",
            '|': '｜', '?': '？', '*': '＊', '/': '／', '\\': '＼'
        }

        result = filename
        for char, replacement in illegal_chars.items():
            result = result.replace(char, replacement)

        # Remove leading/trailing spaces and dots
        result = result.strip(' .')

        return result if result else 'Unknown'

    def _build_consistent_names_from_ai(
        self,
        video_files: List[ClassifiedFile],
        ai_result: RenameResult,
        anime_title: str,
        subtitle_group: str,
        season: int,
        category: str,
        db_patterns: Dict[str, str]
    ) -> RenameResult:
        """
        Build consistent names using AI result and database patterns.

        Args:
            video_files: List of video files.
            ai_result: AI rename result.
            anime_title: Anime title.
            subtitle_group: Subtitle group.
            season: Season number.
            category: Content category.
            db_patterns: Database patterns.

        Returns:
            RenameResult with consistent naming.
        """
        main_files: Dict[str, str] = {}
        skipped_files = list(ai_result.skipped_files)
        seasons_info = dict(ai_result.seasons_info)

        for video in video_files:
            if video.relative_path in skipped_files or video.name in skipped_files:
                logger.info(f'⏭️ 跳过非正片文件: {video.name}')
                continue

            episode = self._extract_episode_from_db_patterns(video.name, db_patterns)
            if episode is None and category != 'movie':
                logger.warning(f'⚠️ 无法提取集数，跳过: {video.name}')
                continue

            # Extract subtitle type and special tag
            subtitle_type = self._extract_from_regex(
                video.name, db_patterns.get('subtitle_type_regex')
            )
            special_tag = self._extract_from_regex(
                video.name, db_patterns.get('special_tags_regex')
            )

            # Generate new filename
            new_name = self._format_filename_with_tags(
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                episode=episode,
                category=category,
                subtitle_type=subtitle_type,
                special_tag=special_tag,
                extension=video.extension
            )

            main_files[video.name] = new_name
            logger.info(f'✓ 一致性命名: {video.name} -> {new_name}')

        return RenameResult(
            main_files=main_files,
            skipped_files=skipped_files,
            seasons_info=seasons_info,
            patterns=db_patterns,
            method=f'一致性命名（{"剧场版" if category == "movie" else "TV"}）'
        )

    def _convert_ai_result_to_rename_result(
        self,
        video_files: List[ClassifiedFile],
        ai_result: RenameResult,
        category: str,
        is_multi_season: bool
    ) -> RenameResult:
        """
        Convert AI result to final rename result.

        Handles path mapping between relative_path and name.

        Args:
            video_files: List of video files.
            ai_result: AI rename result.
            category: Content category.
            is_multi_season: Whether multi-season.

        Returns:
            Final RenameResult.
        """
        main_files: Dict[str, str] = {}

        # Build relative_path to name mapping
        path_to_name = {v.relative_path: v.name for v in video_files if v.relative_path}
        logger.debug(f'📋 path_to_name映射: {path_to_name}')

        for original_path, new_name in ai_result.main_files.items():
            original_basename = os.path.basename(original_path)

            # Try to match file
            if original_path in path_to_name:
                key_to_use = path_to_name[original_path]
                logger.debug(f'  ✓ 使用relative_path映射: {original_path} -> {key_to_use}')
            elif original_basename in [v.name for v in video_files]:
                key_to_use = original_basename
                logger.debug(f'  ✓ 使用basename匹配: {original_basename}')
            else:
                # Try normalized path
                normalized_path = original_path.replace('\\', '/')
                if normalized_path in path_to_name:
                    key_to_use = path_to_name[normalized_path]
                    logger.debug(f'  ✓ 使用规范化路径映射: {normalized_path} -> {key_to_use}')
                else:
                    logger.warning(f'  ⚠️ 无法匹配文件: {original_path}')
                    continue

            # Handle Season prefix in new_name
            # Check for "Season X/" prefix pattern, not just any "/"
            season_match = re.match(r'^(Season \d+)/', new_name)
            if season_match:
                season_prefix = season_match.group(1)
                filename_only = new_name[len(season_prefix) + 1:]  # Skip "Season X/"
                clean_filename = self._sanitize_filename(filename_only)
                clean_new_name = f'{season_prefix}/{clean_filename}'
                logger.info(f'  ✓ AI重命名（带Season目录）: {key_to_use} -> {clean_new_name}')
            else:
                clean_new_name = self._sanitize_filename(new_name)
                logger.info(f'  ✓ AI重命名: {key_to_use} -> {clean_new_name}')

            main_files[key_to_use] = clean_new_name

        # Determine method string
        if is_multi_season:
            method = 'AI文件名（多季内容，已禁用一致性命名）'
        else:
            method = f'AI文件名（{"剧场版" if category == "movie" else "TV"}）'

        return RenameResult(
            main_files=main_files,
            skipped_files=ai_result.skipped_files,
            seasons_info=ai_result.seasons_info,
            patterns=ai_result.patterns,
            method=method
        )

    def _generate_mappings(
        self,
        classified: ClassificationResult,
        category: str,
        anime_title: Optional[str],
        tvdb_data: Optional[Dict[str, Any]]
    ) -> Optional[RenameResult]:
        """
        Generate rename mappings for classified files using AI.

        Args:
            classified: Classification result.
            category: Content category.
            anime_title: Anime title.
            tvdb_data: TVDB metadata.

        Returns:
            RenameResult with all mappings, or None if failed.
        """
        if not classified.video_files:
            return None

        if not self._ai_file_renamer:
            logger.error('❌ AI文件重命名器未配置，无法处理')
            return None

        # Use AI for processing
        ai_input_files = [v.relative_path or v.name for v in classified.video_files]

        try:
            ai_result = self._ai_file_renamer.generate_rename_mapping(
                files=ai_input_files,
                category=category,
                anime_title=anime_title,
                folder_structure=None,
                tvdb_data=tvdb_data
            )

            if not ai_result or not ai_result.has_files:
                logger.error('❌ AI处理失败或未返回重命名映射')
                return None

            return ai_result

        except Exception as e:
            logger.error(f'❌ AI处理异常: {e}')
            return None

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
