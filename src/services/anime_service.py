"""
Anime management service module.

Provides CRUD operations, file management, and batch operations for anime.
"""

import logging
import os
import re
import shutil
from typing import Any, Dict, List, Optional

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

        # Select folder based on media type (matches path_builder.py structure)
        # Structure: /downloads/Anime/Title or /downloads/LiveAction/Title
        if media_type == 'live_action':
            media_folder = config.qbittorrent.live_action_folder_name
        else:
            media_folder = config.qbittorrent.anime_folder_name

        return os.path.join(base_path, media_folder, sanitized_title)

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
