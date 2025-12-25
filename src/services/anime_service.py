"""
Anime management service module.

Provides CRUD operations, file management, and batch operations for anime.
"""

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy import func, or_

from src.core.config import config
from src.core.utils.timezone_utils import get_utc_now
from src.infrastructure.database.session import db_manager
from src.infrastructure.database.models import (
    AnimeInfo,
    AnimePattern,
    DownloadHistory,
    DownloadStatus,
    Hardlink,
    TorrentFile,
)
from src.core.interfaces import IAnimeRepository, IDownloadRepository, IDownloadClient

if TYPE_CHECKING:
    from src.services.rename.rename_service import RenameService

logger = logging.getLogger(__name__)


class AnimeService:
    """
    Anime management service.

    Provides operations for managing anime records, files, and patterns.
    """

    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        download_client: IDownloadClient
    ):
        """
        Initialize the anime service.

        Args:
            anime_repo: Anime repository for database operations.
            download_repo: Download repository for download records.
            download_client: Download client for torrent operations.
        """
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._download_client = download_client

    def get_anime_list_paginated(
        self,
        page: int = 1,
        per_page: int = 20,
        search: str = '',
        sort_column: str = 'created_at',
        sort_order: str = 'desc',
        media_type_filter: str = '',
        category_filter: str = '',
        tvdb_filter: str = '',
        group_by: str = '',
        viewing_group: str = ''
    ) -> Dict[str, Any]:
        """
        Get paginated anime list with filtering and sorting.

        Args:
            page: Page number (1-indexed).
            per_page: Items per page.
            search: Search term for title/group.
            sort_column: Column to sort by.
            sort_order: Sort direction ('asc' or 'desc').
            media_type_filter: Filter by media type.
            category_filter: Filter by category.
            tvdb_filter: Filter by TVDB status ('linked' or 'unlinked').
            group_by: Group results by field.
            viewing_group: View specific group.

        Returns:
            Dictionary with anime list and pagination info.
        """
        try:
            with db_manager.session() as session:
                # Base query
                query = session.query(AnimeInfo)

                # Apply search filter
                if search:
                    search_term = f'%{search}%'
                    query = query.filter(
                        or_(
                            AnimeInfo.short_title.like(search_term),
                            AnimeInfo.original_title.like(search_term),
                            AnimeInfo.long_title.like(search_term),
                            AnimeInfo.subtitle_group.like(search_term)
                        )
                    )

                # Apply media type filter
                if media_type_filter:
                    query = query.filter(AnimeInfo.media_type == media_type_filter)

                # Apply category filter
                if category_filter:
                    query = query.filter(AnimeInfo.category == category_filter)

                # Apply TVDB filter
                if tvdb_filter == 'linked':
                    query = query.filter(AnimeInfo.tvdb_id.isnot(None))
                elif tvdb_filter == 'unlinked':
                    query = query.filter(AnimeInfo.tvdb_id.is_(None))

                # Handle grouping
                if group_by and not viewing_group:
                    return self._get_anime_grouped(session, query, group_by)

                # Filter by specific group
                if viewing_group:
                    query = self._apply_group_filter(
                        query, group_by, viewing_group
                    )

                # Get total count
                total_count = query.count()

                # Apply sorting
                order_column = getattr(AnimeInfo, sort_column, AnimeInfo.created_at)
                if sort_order == 'desc':
                    query = query.order_by(order_column.desc())
                else:
                    query = query.order_by(order_column.asc())

                # Apply pagination
                offset = (page - 1) * per_page
                anime_list = query.offset(offset).limit(per_page).all()

                # Build result list with file statistics
                result_list = self._build_anime_list_result(session, anime_list)

                return {
                    'anime_list': result_list,
                    'total_count': total_count,
                    'current_page': page,
                    'per_page': per_page,
                    'total_pages': (total_count + per_page - 1) // per_page
                }

        except Exception as e:
            logger.error(f'获取动漫列表失败: {e}')
            return {'error': str(e)}

    def _apply_group_filter(
        self,
        query,
        group_by: str,
        viewing_group: str
    ):
        """Apply group filter to query."""
        if group_by == 'subtitle_group':
            if viewing_group == '(未分类)':
                return query.filter(
                    (AnimeInfo.subtitle_group.is_(None)) |
                    (AnimeInfo.subtitle_group == '')
                )
            return query.filter(AnimeInfo.subtitle_group == viewing_group)
        elif group_by == 'media_type':
            return query.filter(AnimeInfo.media_type == viewing_group)
        elif group_by == 'season':
            return query.filter(AnimeInfo.season == int(viewing_group))
        return query

    def _get_anime_grouped(
        self,
        session,
        base_query,
        group_by: str
    ) -> Dict[str, Any]:
        """Get grouped statistics for anime."""
        groups = []

        if group_by == 'subtitle_group':
            group_results = session.query(
                AnimeInfo.subtitle_group,
                func.count(AnimeInfo.id).label('count')
            ).group_by(AnimeInfo.subtitle_group).all()

            for subtitle_group, count in group_results:
                groups.append({
                    'group_name': subtitle_group or '(未分类)',
                    'total_count': count
                })

        elif group_by == 'media_type':
            group_results = session.query(
                AnimeInfo.media_type,
                func.count(AnimeInfo.id).label('count')
            ).group_by(AnimeInfo.media_type).all()

            type_names = {'anime': '动漫', 'live_action': '真人'}
            for media_type, count in group_results:
                groups.append({
                    'group_name': media_type,
                    'display_name': type_names.get(media_type, media_type),
                    'total_count': count
                })

        elif group_by == 'season':
            group_results = session.query(
                AnimeInfo.season,
                func.count(AnimeInfo.id).label('count')
            ).group_by(AnimeInfo.season).order_by(AnimeInfo.season).all()

            for season, count in group_results:
                groups.append({
                    'group_name': str(season),
                    'display_name': f'Season {season}',
                    'total_count': count
                })

        return {
            'groups': groups,
            'total_count': sum(g['total_count'] for g in groups)
        }

    def _build_anime_list_result(
        self,
        session,
        anime_list: List[AnimeInfo]
    ) -> List[Dict[str, Any]]:
        """Build result list with file statistics."""
        result_list = []

        for anime in anime_list:
            # Get file count
            file_count = session.query(DownloadStatus).filter(
                DownloadStatus.anime_id == anime.id
            ).count()

            # Get hardlink count
            hardlink_count = session.query(Hardlink).filter(
                Hardlink.anime_id == anime.id
            ).count()

            result_list.append({
                'id': anime.id,
                'original_title': anime.original_title,
                'short_title': anime.short_title,
                'long_title': anime.long_title,
                'subtitle_group': anime.subtitle_group,
                'season': anime.season,
                'category': anime.category,
                'media_type': anime.media_type,
                'tvdb_id': anime.tvdb_id,
                'created_at': anime.created_at,
                'updated_at': anime.updated_at,
                'file_count': file_count,
                'hardlink_count': hardlink_count
            })

        return result_list

    def get_anime_details(self, anime_id: int) -> Dict[str, Any]:
        """
        Get detailed anime information including file lists.

        Args:
            anime_id: Anime ID.

        Returns:
            Dictionary with anime details, files, and patterns.
        """
        try:
            with db_manager.session() as session:
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'error': '动漫不存在'}

                # Get downloads
                downloads = session.query(DownloadStatus).filter_by(
                    anime_id=anime_id
                ).all()

                # Get hardlinks
                hardlinks = session.query(Hardlink).filter_by(
                    anime_id=anime_id
                ).all()

                # Get patterns
                patterns = session.query(AnimePattern).filter_by(
                    anime_id=anime_id
                ).first()

                # Calculate total size
                total_original_size = sum(h.file_size or 0 for h in hardlinks)

                # Build file lists
                original_files = [
                    {
                        'id': d.id,
                        'hash_id': d.hash_id,
                        'filename': d.original_filename,
                        'directory': d.download_directory,
                        'status': d.status,
                        'download_time': d.download_time,
                        'completion_time': d.completion_time
                    }
                    for d in downloads
                ]

                hardlink_files = [
                    {
                        'id': h.id,
                        'original_path': h.original_file_path,
                        'hardlink_path': h.hardlink_path,
                        'file_size': h.file_size,
                        'created_at': h.created_at
                    }
                    for h in hardlinks
                ]

                # Build patterns data
                patterns_data = None
                if patterns:
                    patterns_data = {
                        'id': patterns.id,
                        'title_group_regex': patterns.title_group_regex,
                        'full_title_regex': patterns.full_title_regex,
                        'short_title_regex': patterns.short_title_regex,
                        'episode_regex': patterns.episode_regex,
                        'quality_regex': patterns.quality_regex
                    }

                return {
                    'success': True,
                    'anime': {
                        'id': anime.id,
                        'original_title': anime.original_title,
                        'short_title': anime.short_title,
                        'long_title': anime.long_title,
                        'subtitle_group': anime.subtitle_group,
                        'season': anime.season,
                        'category': anime.category,
                        'media_type': anime.media_type,
                        'tvdb_id': anime.tvdb_id,
                        'created_at': anime.created_at,
                        'updated_at': anime.updated_at
                    },
                    'original_files': original_files,
                    'hardlink_files': hardlink_files,
                    'total_size': total_original_size,
                    'patterns': patterns_data
                }

        except Exception as e:
            logger.error(f'获取动漫详情失败: {e}')
            return {'error': str(e)}

    def get_anime_folders(self, anime_id: int) -> Dict[str, Any]:
        """
        Get anime folder paths for delete preview.

        Args:
            anime_id: Anime ID.

        Returns:
            Dictionary with folder paths and torrent hashes.
        """
        try:
            with db_manager.session() as session:
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'error': '动漫不存在'}

                anime_title = anime.short_title or anime.original_title
                media_type = anime.media_type or 'anime'
                category = anime.category or 'tv'

                # Get folder paths
                original_folder = self._get_original_folder_path(
                    anime_title, media_type, category
                )
                hardlink_folder = self._get_hardlink_folder_path(
                    anime_title, media_type, category
                )

                # Get related torrent hashes
                downloads = session.query(DownloadStatus).filter_by(
                    anime_id=anime_id
                ).all()
                torrent_hashes = [d.hash_id for d in downloads]

                return {
                    'success': True,
                    'anime_title': anime_title,
                    'original_folder': original_folder,
                    'hardlink_folder': hardlink_folder,
                    'torrent_hashes': torrent_hashes,
                    'download_count': len(downloads)
                }

        except Exception as e:
            logger.error(f'获取动漫文件夹路径失败: {e}')
            return {'error': str(e)}

    def _sanitize_title(self, name: str) -> str:
        """
        Sanitize anime title for use in file/directory names.

        Replaces illegal filesystem characters with fullwidth equivalents,
        matching the behavior used when creating download paths.

        Args:
            name: Original title string.

        Returns:
            Sanitized title safe for filesystem use.
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

    def _get_original_folder_path(
        self,
        anime_title: str,
        media_type: str,
        category: str
    ) -> str:
        """Get original file folder path."""
        base_path = config.qbittorrent.base_download_path.rstrip('/\\')
        sanitized_title = self._sanitize_title(anime_title)

        # Select folder based on media type
        if media_type == 'live_action':
            media_folder = config.qbittorrent.live_action_folder_name
        else:
            media_folder = config.qbittorrent.anime_folder_name

        # Select folder based on category
        if category == 'movie':
            type_folder = config.qbittorrent.movie_folder_name
        else:
            type_folder = config.qbittorrent.tv_folder_name

        return os.path.join(base_path, media_folder, type_folder, sanitized_title)

    def _get_hardlink_folder_path(
        self,
        anime_title: str,
        media_type: str,
        category: str
    ) -> str:
        """Get hardlink folder path."""
        sanitized_title = self._sanitize_title(anime_title)

        if media_type == 'live_action':
            if category == 'movie':
                target_base = config.live_action_movie_target_path
            else:
                target_base = config.live_action_tv_target_path
        else:
            if category == 'movie':
                target_base = (
                    config.movie_link_target_path or config.link_target_path
                )
            else:
                target_base = config.link_target_path

        return os.path.join(target_base.rstrip('/\\'), sanitized_title)

    def delete_anime_files(
        self,
        anime_id: int,
        delete_original: bool = False,
        delete_hardlinks: bool = False,
        delete_from_database: bool = False
    ) -> Dict[str, Any]:
        """
        Delete anime related files.

        Args:
            anime_id: Anime ID.
            delete_original: Whether to delete original folder.
            delete_hardlinks: Whether to delete hardlink folder.
            delete_from_database: Whether to delete database records.

        Returns:
            Dictionary with deletion results.
        """
        result = {
            'success': True,
            'original_deleted': False,
            'hardlinks_deleted': False,
            'database_deleted': False,
            'torrents_removed': 0,
            'downloads_moved_to_history': 0,
            'errors': []
        }

        try:
            with db_manager.session() as session:
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'success': False, 'error': '动漫不存在'}

                anime_title = anime.short_title or anime.original_title
                media_type = anime.media_type or 'anime'
                category = anime.category or 'tv'

                # Get folder paths
                original_folder = self._get_original_folder_path(
                    anime_title, media_type, category
                )
                hardlink_folder = self._get_hardlink_folder_path(
                    anime_title, media_type, category
                )

                # Get related downloads
                downloads = session.query(DownloadStatus).filter_by(
                    anime_id=anime_id
                ).all()

                # 1. Delete original folder
                if delete_original:
                    result = self._delete_original_files(
                        session, downloads, original_folder,
                        delete_from_database, result
                    )

                # 2. Delete hardlink folder
                if delete_hardlinks:
                    result = self._delete_hardlink_files(
                        session, anime_id, hardlink_folder, result
                    )

                # 3. Delete database records
                if delete_from_database:
                    self._delete_database_records(session, anime_id)
                    result['database_deleted'] = True
                    logger.info(f'从数据库删除动漫记录成功: {anime_id}')

                session.commit()

            # Check for errors
            if result['errors']:
                result['success'] = len(result['errors']) == 0

            return result

        except Exception as e:
            logger.error(f'删除动漫文件失败: {e}')
            return {'success': False, 'error': str(e)}

    def _delete_original_files(
        self,
        session,
        downloads: List[DownloadStatus],
        original_folder: str,
        delete_from_database: bool,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delete original files and torrents."""
        # Delete torrents from qBittorrent
        for download in downloads:
            try:
                if self._download_client.delete_torrent(
                    download.hash_id, delete_files=True
                ):
                    result['torrents_removed'] += 1
                    logger.info(f'从qBittorrent删除torrent: {download.hash_id}')
                else:
                    logger.warning(
                        f'从qBittorrent删除torrent失败: {download.hash_id}'
                    )
            except Exception as e:
                logger.error(f'删除torrent异常: {e}')
                result['errors'].append(f'删除torrent失败: {download.hash_id}')

        # Delete folder
        if os.path.exists(original_folder):
            try:
                shutil.rmtree(original_folder)
                result['original_deleted'] = True
                logger.info(f'删除原文件夹成功: {original_folder}')
            except Exception as e:
                logger.error(f'删除原文件夹失败: {e}')
                result['errors'].append(f'删除原文件夹失败: {str(e)}')
        else:
            logger.warning(f'原文件夹不存在: {original_folder}')
            result['original_deleted'] = True

        # Move downloads to history (if not deleting database)
        if not delete_from_database:
            for download in downloads:
                try:
                    if self._download_repo.move_to_history(download.hash_id):
                        result['downloads_moved_to_history'] += 1
                except Exception as e:
                    logger.error(f'移动下载记录到历史失败: {e}')

        return result

    def _delete_hardlink_files(
        self,
        session,
        anime_id: int,
        hardlink_folder: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delete hardlink files."""
        if os.path.exists(hardlink_folder):
            try:
                shutil.rmtree(hardlink_folder)
                result['hardlinks_deleted'] = True
                logger.info(f'删除硬链接文件夹成功: {hardlink_folder}')
            except Exception as e:
                logger.error(f'删除硬链接文件夹失败: {e}')
                result['errors'].append(f'删除硬链接文件夹失败: {str(e)}')
        else:
            logger.warning(f'硬链接文件夹不存在: {hardlink_folder}')
            result['hardlinks_deleted'] = True

        # Delete hardlink database records
        session.query(Hardlink).filter_by(anime_id=anime_id).delete()

        return result

    def _delete_database_records(self, session, anime_id: int) -> None:
        """Delete all database records for an anime."""
        session.query(AnimePattern).filter_by(anime_id=anime_id).delete()
        session.query(TorrentFile).filter_by(anime_id=anime_id).delete()
        session.query(Hardlink).filter_by(anime_id=anime_id).delete()
        session.query(DownloadStatus).filter_by(anime_id=anime_id).delete()
        session.query(DownloadHistory).filter_by(anime_id=anime_id).delete()
        session.query(AnimeInfo).filter_by(id=anime_id).delete()

    def update_anime_info(
        self,
        anime_id: int,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update anime information.

        Args:
            anime_id: Anime ID.
            data: Dictionary of fields to update.

        Returns:
            Dictionary with update result.
        """
        try:
            with db_manager.session() as session:
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'success': False, 'error': '动漫不存在'}

                # Update allowed fields
                allowed_fields = [
                    'short_title', 'long_title', 'subtitle_group',
                    'season', 'category', 'media_type', 'tvdb_id'
                ]

                for field in allowed_fields:
                    if field in data:
                        setattr(anime, field, data[field])

                anime.updated_at = get_utc_now()
                session.commit()

                return {
                    'success': True,
                    'message': '动漫信息更新成功'
                }

        except Exception as e:
            logger.error(f'更新动漫信息失败: {e}')
            return {'success': False, 'error': str(e)}

    def count_all(self) -> int:
        """Count all anime records."""
        return self._anime_repo.count_all()

    def count_by_media_type(self) -> Dict[str, int]:
        """Count anime by media type."""
        try:
            with db_manager.session() as session:
                results = session.query(
                    AnimeInfo.media_type,
                    func.count(AnimeInfo.id)
                ).group_by(AnimeInfo.media_type).all()

                return {media_type: count for media_type, count in results}
        except Exception as e:
            logger.error(f'统计媒体类型失败: {e}')
            return {}

    # =========================================================================
    # Anime Detail Page Methods
    # =========================================================================

    def get_anime_detail_with_files(self, anime_id: int) -> Dict[str, Any]:
        """
        Get comprehensive anime details including source files and hardlinks.

        Args:
            anime_id: Anime ID.

        Returns:
            Dictionary with anime info, patterns, source files, and hardlinks.
        """
        try:
            with db_manager.session() as session:
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'error': '动漫不存在'}

                # Get downloads for qBit file fetching
                downloads = session.query(DownloadStatus).filter_by(
                    anime_id=anime_id
                ).all()

                # Get hardlinks
                hardlinks = session.query(Hardlink).filter_by(
                    anime_id=anime_id
                ).all()

                # Get patterns
                patterns = session.query(AnimePattern).filter_by(
                    anime_id=anime_id
                ).first()

                # Build patterns dict
                patterns_data = {}
                if patterns:
                    patterns_data = {
                        'episode_regex': patterns.episode_regex,
                        'quality_regex': patterns.quality_regex,
                        'special_tags_regex': patterns.special_tags_regex,
                        'subtitle_type_regex': patterns.subtitle_type_regex,
                        'title_group_regex': patterns.title_group_regex,
                        'video_codec_regex': patterns.video_codec_regex,
                        'source_regex': patterns.source_regex,
                    }

                # Get source files from qBittorrent
                source_files = []
                for download in downloads:
                    try:
                        torrent_files = self._download_client.get_torrent_files(
                            download.hash_id
                        )
                        for f in torrent_files:
                            file_name = f.get('name', '')
                            # Extract just the filename if it's a path
                            if '/' in file_name or '\\' in file_name:
                                display_name = os.path.basename(file_name)
                            else:
                                display_name = file_name

                            metadata = self.extract_file_metadata(
                                display_name, patterns_data
                            )
                            source_files.append({
                                'name': display_name,
                                'full_path': os.path.join(
                                    download.download_directory or '', file_name
                                ),
                                'size': f.get('size', 0),
                                'torrent_hash': download.hash_id,
                                'metadata': metadata
                            })
                    except Exception as e:
                        logger.warning(
                            f'获取torrent文件失败 {download.hash_id}: {e}'
                        )

                # Build hardlink list with metadata
                hardlink_files = []
                for h in hardlinks:
                    hardlink_name = os.path.basename(h.hardlink_path)
                    metadata = self.extract_file_metadata(
                        hardlink_name, patterns_data
                    )
                    hardlink_files.append({
                        'id': h.id,
                        'original_path': h.original_file_path,
                        'hardlink_path': h.hardlink_path,
                        'file_size': h.file_size,
                        'torrent_hash': h.torrent_hash,
                        'created_at': h.created_at,
                        'metadata': metadata
                    })

                return {
                    'success': True,
                    'anime': {
                        'id': anime.id,
                        'original_title': anime.original_title,
                        'short_title': anime.short_title,
                        'long_title': anime.long_title,
                        'subtitle_group': anime.subtitle_group,
                        'season': anime.season,
                        'category': anime.category,
                        'media_type': anime.media_type,
                        'tvdb_id': anime.tvdb_id,
                        'created_at': anime.created_at,
                        'updated_at': anime.updated_at
                    },
                    'patterns': patterns_data,
                    'source_files': source_files,
                    'hardlinks': hardlink_files,
                    'download_count': len(downloads),
                    'hardlink_count': len(hardlinks)
                }

        except Exception as e:
            logger.error(f'获取动漫详情失败: {e}')
            return {'error': str(e)}

    def extract_file_metadata(
        self,
        filename: str,
        patterns: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Extract metadata from filename using regex patterns.

        Args:
            filename: File name to extract from.
            patterns: Dictionary of regex patterns.

        Returns:
            Dictionary with extracted metadata.
        """
        result = {}

        pattern_fields = [
            ('episode_regex', 'episode'),
            ('quality_regex', 'quality'),
            ('subtitle_type_regex', 'subtitle_type'),
            ('special_tags_regex', 'special_tag'),
            ('video_codec_regex', 'video_codec'),
            ('source_regex', 'source'),
            ('title_group_regex', 'subtitle_group'),
        ]

        for pattern_key, result_key in pattern_fields:
            pattern = patterns.get(pattern_key)
            if pattern and pattern != '无':
                try:
                    match = re.search(pattern, filename)
                    if match:
                        value = match.group(1) if match.groups() else match.group(0)
                        result[result_key] = value.strip('[]').strip()
                except re.error:
                    pass

        return result

    def rename_files(
        self,
        anime_id: int,
        mappings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Rename files on filesystem and update database.

        Args:
            anime_id: Anime ID.
            mappings: List of {path, new_name, type} dicts.

        Returns:
            Result dictionary with success status.
        """
        results = {
            'success': True,
            'renamed': [],
            'failed': [],
            'errors': []
        }

        try:
            with db_manager.session() as session:
                for mapping in mappings:
                    old_path = mapping.get('path', '')
                    new_name = mapping.get('new_name', '')
                    file_type = mapping.get('type', 'hardlink')

                    if not old_path or not new_name:
                        results['failed'].append({
                            'path': old_path,
                            'error': '路径或新名称为空'
                        })
                        continue

                    try:
                        old_dir = os.path.dirname(old_path)
                        new_path = os.path.join(old_dir, new_name)

                        # Check if source exists
                        if not os.path.exists(old_path):
                            results['failed'].append({
                                'path': old_path,
                                'error': '文件不存在'
                            })
                            continue

                        # Rename file
                        os.rename(old_path, new_path)

                        # Update database if hardlink
                        if file_type == 'hardlink':
                            session.query(Hardlink).filter(
                                Hardlink.anime_id == anime_id,
                                Hardlink.hardlink_path == old_path
                            ).update({'hardlink_path': new_path})

                        results['renamed'].append({
                            'old_path': old_path,
                            'new_path': new_path
                        })
                        logger.info(f'✅ 重命名成功: {old_path} -> {new_path}')

                    except Exception as e:
                        results['failed'].append({
                            'path': old_path,
                            'error': str(e)
                        })
                        logger.error(f'❌ 重命名失败 {old_path}: {e}')

                session.commit()

        except Exception as e:
            logger.error(f'重命名文件失败: {e}')
            results['success'] = False
            results['errors'].append(str(e))

        return results

    def delete_selected_files(
        self,
        anime_id: int,
        file_ids: List[int],
        delete_hardlinks: bool = True,
        delete_source: bool = False
    ) -> Dict[str, Any]:
        """
        Delete selected files with user options.

        Args:
            anime_id: Anime ID.
            file_ids: List of hardlink IDs to delete.
            delete_hardlinks: Whether to delete hardlink files.
            delete_source: Whether to also delete source files.

        Returns:
            Result dictionary.
        """
        results = {
            'success': True,
            'hardlinks_deleted': 0,
            'source_deleted': 0,
            'errors': []
        }

        try:
            with db_manager.session() as session:
                hardlinks = session.query(Hardlink).filter(
                    Hardlink.id.in_(file_ids),
                    Hardlink.anime_id == anime_id
                ).all()

                for hardlink in hardlinks:
                    # Delete hardlink file
                    if delete_hardlinks and os.path.exists(hardlink.hardlink_path):
                        try:
                            os.remove(hardlink.hardlink_path)
                            results['hardlinks_deleted'] += 1
                            logger.info(f'🗑️ 删除硬链接: {hardlink.hardlink_path}')
                        except Exception as e:
                            results['errors'].append(
                                f'删除硬链接失败 {hardlink.hardlink_path}: {e}'
                            )

                    # Delete source file if requested
                    if delete_source and os.path.exists(hardlink.original_file_path):
                        try:
                            os.remove(hardlink.original_file_path)
                            results['source_deleted'] += 1
                            logger.info(f'🗑️ 删除源文件: {hardlink.original_file_path}')
                        except Exception as e:
                            results['errors'].append(
                                f'删除源文件失败 {hardlink.original_file_path}: {e}'
                            )

                    # Delete database record
                    session.delete(hardlink)

                session.commit()

        except Exception as e:
            logger.error(f'删除文件失败: {e}')
            results['success'] = False
            results['errors'].append(str(e))

        return results

    def move_hardlink_files(
        self,
        anime_id: int,
        file_ids: List[int],
        destination_folder: str
    ) -> Dict[str, Any]:
        """
        Move hardlink files to a new subfolder.

        Args:
            anime_id: Anime ID.
            file_ids: List of hardlink IDs to move.
            destination_folder: Target folder name (e.g., 'Season 2').

        Returns:
            Result dictionary.
        """
        results = {
            'success': True,
            'moved': [],
            'failed': [],
            'errors': []
        }

        try:
            with db_manager.session() as session:
                hardlinks = session.query(Hardlink).filter(
                    Hardlink.id.in_(file_ids),
                    Hardlink.anime_id == anime_id
                ).all()

                for hardlink in hardlinks:
                    try:
                        old_path = hardlink.hardlink_path
                        parent_dir = os.path.dirname(old_path)

                        # Go up one level if in a Season folder
                        if os.path.basename(parent_dir).startswith('Season'):
                            parent_dir = os.path.dirname(parent_dir)

                        # Create new destination
                        new_dir = os.path.join(parent_dir, destination_folder)
                        os.makedirs(new_dir, exist_ok=True)

                        new_path = os.path.join(
                            new_dir, os.path.basename(old_path)
                        )

                        if not os.path.exists(old_path):
                            results['failed'].append({
                                'path': old_path,
                                'error': '文件不存在'
                            })
                            continue

                        # Move file
                        shutil.move(old_path, new_path)

                        # Update database
                        hardlink.hardlink_path = new_path

                        results['moved'].append({
                            'old_path': old_path,
                            'new_path': new_path
                        })
                        logger.info(f'📦 移动文件: {old_path} -> {new_path}')

                    except Exception as e:
                        results['failed'].append({
                            'path': hardlink.hardlink_path,
                            'error': str(e)
                        })
                        logger.error(f'❌ 移动失败: {e}')

                session.commit()

        except Exception as e:
            logger.error(f'移动文件失败: {e}')
            results['success'] = False
            results['errors'].append(str(e))

        return results

    def send_files_to_ai_rename(
        self,
        anime_id: int,
        source_files: List[str],
        rename_service: 'RenameService'
    ) -> Dict[str, Any]:
        """
        Send source files to AI for rename suggestions.

        Args:
            anime_id: Anime ID.
            source_files: List of source file paths.
            rename_service: RenameService instance.

        Returns:
            Dictionary with proposed mappings.
        """
        try:
            with db_manager.session() as session:
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'error': '动漫不存在'}

                anime_title = anime.short_title or anime.original_title
                subtitle_group = anime.subtitle_group or ''
                season = anime.season or 1
                category = anime.category or 'tv'

                # Build classified files for rename service
                from src.services.rename.file_classifier import ClassifiedFile

                video_files = []
                for file_path in source_files:
                    filename = os.path.basename(file_path)
                    ext = os.path.splitext(filename)[1].lower()
                    video_files.append(ClassifiedFile(
                        name=filename,
                        relative_path=file_path,
                        full_path=file_path,
                        size=0,
                        extension=ext
                    ))

                # Call AI rename
                result = rename_service.generate_mapping(
                    video_files=video_files,
                    anime_id=anime_id,
                    anime_title=anime_title,
                    subtitle_group=subtitle_group,
                    season=season,
                    category=category,
                    is_multi_season=False,
                    tvdb_data=None,
                    folder_structure=None,
                    torrent_hash=None
                )

                if not result:
                    return {'error': 'AI处理失败'}

                # Build mapping list
                mappings = []
                for original, new_name in result.main_files.items():
                    mappings.append({
                        'source': original,
                        'proposed_path': new_name
                    })

                return {
                    'success': True,
                    'mappings': mappings,
                    'method': result.method
                }

        except Exception as e:
            logger.error(f'AI重命名失败: {e}')
            return {'error': str(e)}

    def apply_ai_rename_results(
        self,
        anime_id: int,
        mappings: List[Dict[str, Any]],
        replace_all: bool = False
    ) -> Dict[str, Any]:
        """
        Apply AI rename results by creating new hardlinks.

        Args:
            anime_id: Anime ID.
            mappings: List of {source_file, new_hardlink_path, replace_hardlink_id}.
            replace_all: Whether to replace all existing hardlinks.

        Returns:
            Result dictionary.
        """
        results = {
            'success': True,
            'created': [],
            'replaced': [],
            'failed': [],
            'errors': []
        }

        try:
            with db_manager.session() as session:
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'error': '动漫不存在'}

                # Get hardlink base path
                anime_title = anime.short_title or anime.original_title
                media_type = anime.media_type or 'anime'
                category = anime.category or 'tv'
                base_path = self._get_hardlink_folder_path(
                    anime_title, media_type, category
                )

                for mapping in mappings:
                    source_file = mapping.get('source_file', '')
                    new_path_suffix = mapping.get('new_hardlink_path', '')
                    replace_id = mapping.get('replace_hardlink_id')

                    if not source_file or not new_path_suffix:
                        continue

                    try:
                        # Build full new path
                        new_hardlink_path = os.path.join(base_path, new_path_suffix)

                        # Create directory if needed
                        new_dir = os.path.dirname(new_hardlink_path)
                        os.makedirs(new_dir, exist_ok=True)

                        # Check if source exists
                        if not os.path.exists(source_file):
                            results['failed'].append({
                                'source': source_file,
                                'error': '源文件不存在'
                            })
                            continue

                        # Remove old hardlink if replacing
                        if replace_id or replace_all:
                            old_hardlinks = session.query(Hardlink).filter(
                                Hardlink.anime_id == anime_id,
                                Hardlink.original_file_path == source_file
                            ).all()

                            for old_hl in old_hardlinks:
                                if replace_id and old_hl.id != replace_id:
                                    continue
                                if os.path.exists(old_hl.hardlink_path):
                                    os.remove(old_hl.hardlink_path)
                                session.delete(old_hl)
                                results['replaced'].append(old_hl.hardlink_path)

                        # Create new hardlink
                        if os.path.exists(new_hardlink_path):
                            os.remove(new_hardlink_path)

                        os.link(source_file, new_hardlink_path)

                        # Get file size
                        file_size = os.path.getsize(source_file)

                        # Find torrent hash
                        torrent_hash = None
                        download = session.query(DownloadStatus).filter(
                            DownloadStatus.anime_id == anime_id
                        ).first()
                        if download:
                            torrent_hash = download.hash_id

                        # Create database record
                        new_hardlink = Hardlink(
                            anime_id=anime_id,
                            torrent_hash=torrent_hash,
                            original_file_path=source_file,
                            hardlink_path=new_hardlink_path,
                            file_size=file_size
                        )
                        session.add(new_hardlink)

                        results['created'].append({
                            'source': source_file,
                            'hardlink': new_hardlink_path
                        })
                        logger.info(f'✅ 创建硬链接: {source_file} -> {new_hardlink_path}')

                    except Exception as e:
                        results['failed'].append({
                            'source': source_file,
                            'error': str(e)
                        })
                        logger.error(f'❌ 创建硬链接失败: {e}')

                session.commit()

        except Exception as e:
            logger.error(f'应用AI结果失败: {e}')
            results['success'] = False
            results['errors'].append(str(e))

        return results


# Global anime service instance
_anime_service: Optional[AnimeService] = None


def get_anime_service() -> AnimeService:
    """
    Get the global anime service instance.

    Creates the instance on first call.

    Returns:
        AnimeService instance.
    """
    global _anime_service
    if _anime_service is None:
        from src.infrastructure.repositories import AnimeRepository, DownloadRepository
        from src.infrastructure.downloader import QBitAdapter
        _anime_service = AnimeService(
            AnimeRepository(),
            DownloadRepository(),
            QBitAdapter()
        )
    return _anime_service
