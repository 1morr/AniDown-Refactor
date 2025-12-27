"""
Anime detail service module.

Provides operations for anime detail page including torrent file management
and AI processing.
"""

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from src.core.interfaces import IAnimeRepository, IDownloadRepository, IDownloadClient
from src.infrastructure.database.session import db_manager
from src.infrastructure.database.models import (
    AnimeInfo,
    DownloadStatus as DownloadStatusModel,
    Hardlink,
)
from src.services.file.path_builder import PathBuilder

logger = logging.getLogger(__name__)


class AnimeDetailService:
    """
    Anime detail service.

    Provides operations for managing anime detail page data and operations.
    """

    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        download_client: IDownloadClient,
        path_builder: PathBuilder
    ):
        """
        Initialize the anime detail service.

        Args:
            anime_repo: Anime repository for database operations.
            download_repo: Download repository for download records.
            download_client: Download client for torrent operations.
            path_builder: Path builder for filesystem path construction.
        """
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._download_client = download_client
        self._path_builder = path_builder

    def get_anime_with_torrents(self, anime_id: int) -> Dict[str, Any]:
        """
        Get anime information with all related torrents and their files.

        Args:
            anime_id: Anime ID.

        Returns:
            Dictionary with anime info, torrents with files, and statistics.
        """
        try:
            with db_manager.session() as session:
                # Get anime info
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'success': False, 'error': '动漫不存在'}

                # Get all downloads for this anime
                downloads = session.query(DownloadStatusModel).filter_by(
                    anime_id=anime_id
                ).order_by(DownloadStatusModel.download_time.desc()).all()

                # Get all hardlinks for this anime
                hardlinks = session.query(Hardlink).filter_by(
                    anime_id=anime_id
                ).all()

                # Build hardlink map by torrent hash
                hardlink_map = self._build_hardlink_map(hardlinks)

                # Build anime info
                anime_info = {
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
                }

                # Build target path using PathBuilder
                target_path = self._path_builder.build_target_directory(
                    anime_title=anime_info.get('short_title') or anime_info.get('original_title'),
                    media_type=anime_info.get('media_type', 'anime'),
                    category=anime_info.get('category', 'tv')
                )

                # Build torrents list with files
                torrents = []
                stats = {
                    'total_files': 0,
                    'video_count': 0,
                    'subtitle_count': 0,
                    'other_count': 0,
                    'linked_count': 0,
                    'unlinked_count': 0,
                    'total_size': 0
                }

                for download in downloads:
                    torrent_data = self._get_torrent_with_files(
                        download,
                        hardlink_map.get(download.hash_id, {}),
                        stats
                    )
                    torrents.append(torrent_data)

                return {
                    'success': True,
                    'anime': anime_info,
                    'torrents': torrents,
                    'target_path': target_path,
                    'stats': stats
                }

        except Exception as e:
            logger.error(f'获取动漫详情失败: {e}')
            return {'success': False, 'error': str(e)}

    def _build_hardlink_map(
        self,
        hardlinks: List[Hardlink]
    ) -> Dict[str, Dict[str, Dict]]:
        """
        Build hardlink map organized by torrent hash and file path.

        Args:
            hardlinks: List of hardlink records.

        Returns:
            Dictionary mapping torrent_hash -> original_path -> hardlink_info.
        """
        hardlink_map = {}

        for h in hardlinks:
            torrent_hash = h.torrent_hash
            if torrent_hash not in hardlink_map:
                hardlink_map[torrent_hash] = {}

            original_path = h.original_file_path

            # Store with multiple path formats for matching
            info = {
                'id': h.id,
                'hardlink_path': h.hardlink_path,
                'file_size': h.file_size
            }

            hardlink_map[torrent_hash][original_path] = info

            # Also store normalized path
            normalized = original_path.replace('\\', '/')
            hardlink_map[torrent_hash][normalized] = info

            # Store filename only
            filename = original_path.split('/')[-1].split('\\')[-1]
            if filename not in hardlink_map[torrent_hash]:
                hardlink_map[torrent_hash][filename] = info

        return hardlink_map

    def _get_torrent_with_files(
        self,
        download: DownloadStatusModel,
        hardlink_map: Dict[str, Dict],
        stats: Dict[str, int]
    ) -> Dict[str, Any]:
        """
        Get torrent info with files from qBittorrent.

        Args:
            download: Download record.
            hardlink_map: Hardlink info mapping for this torrent.
            stats: Statistics dictionary to update.

        Returns:
            Dictionary with torrent info and files.
        """
        torrent_data = {
            'hash_id': download.hash_id,
            'original_filename': download.original_filename,
            'status': download.status,
            'download_directory': download.download_directory,
            'download_time': download.download_time,
            'completion_time': download.completion_time,
            'files': [],
            'file_count': 0,
            'linked_count': 0,
            'in_client': True
        }

        # Try to get files from qBittorrent
        try:
            torrent_files = self._download_client.get_torrent_files(download.hash_id)
            torrent_info = self._download_client.get_torrent_info(download.hash_id)

            if not torrent_files:
                torrent_data['in_client'] = False
                torrent_data['files'] = self._get_files_from_hardlinks(hardlink_map, stats)
                return torrent_data

            save_path = torrent_info.get('save_path', '') if torrent_info else ''
            torrent_name = torrent_info.get('name', '') if torrent_info else ''

            # Process files
            for file_info in torrent_files:
                file_data = self._process_file(
                    file_info,
                    hardlink_map,
                    download.download_directory or save_path,
                    torrent_name,
                    stats
                )
                torrent_data['files'].append(file_data)

            torrent_data['file_count'] = len(torrent_data['files'])
            torrent_data['linked_count'] = sum(
                1 for f in torrent_data['files'] if f['has_hardlink']
            )

        except Exception as e:
            logger.warning(f'获取torrent文件失败 {download.hash_id[:8]}: {e}')
            torrent_data['in_client'] = False
            torrent_data['files'] = self._get_files_from_hardlinks(hardlink_map, stats)

        return torrent_data

    def _get_files_from_hardlinks(
        self,
        hardlink_map: Dict[str, Dict],
        stats: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """
        Get file list from hardlink records when torrent is not in client.

        Args:
            hardlink_map: Hardlink info mapping.
            stats: Statistics dictionary to update.

        Returns:
            List of file data dictionaries.
        """
        files = []
        seen_ids = set()

        for path, info in hardlink_map.items():
            if info['id'] in seen_ids:
                continue
            seen_ids.add(info['id'])

            # Determine file type from path
            file_type = self._get_file_type(path)

            files.append({
                'name': path.split('/')[-1].split('\\')[-1],
                'relative_path': path,
                'size': info.get('file_size', 0),
                'type': file_type,
                'has_hardlink': True,
                'hardlink_info': {
                    'id': info['id'],
                    'hardlink_path': info['hardlink_path']
                }
            })

            # Update stats
            stats['total_files'] += 1
            stats['linked_count'] += 1
            stats['total_size'] += info.get('file_size', 0)
            if file_type == 'video':
                stats['video_count'] += 1
            elif file_type == 'subtitle':
                stats['subtitle_count'] += 1
            else:
                stats['other_count'] += 1

        return files

    def _process_file(
        self,
        file_info: Dict[str, Any],
        hardlink_map: Dict[str, Dict],
        download_dir: str,
        torrent_name: str,
        stats: Dict[str, int]
    ) -> Dict[str, Any]:
        """
        Process a single file from torrent.

        Args:
            file_info: File info from qBittorrent.
            hardlink_map: Hardlink info mapping.
            download_dir: Download directory.
            torrent_name: Torrent name.
            stats: Statistics dictionary to update.

        Returns:
            File data dictionary.
        """
        file_name = file_info.get('name', '')
        file_size = file_info.get('size', 0)
        file_type = self._get_file_type(file_name)

        # Find hardlink info using multiple path formats
        hardlink_info = self._find_hardlink_info(
            file_name, hardlink_map, download_dir, torrent_name
        )

        file_data = {
            'name': file_name.split('/')[-1].split('\\')[-1],
            'relative_path': file_name,
            'size': file_size,
            'type': file_type,
            'has_hardlink': hardlink_info is not None,
            'hardlink_info': hardlink_info
        }

        # Update stats
        stats['total_files'] += 1
        stats['total_size'] += file_size
        if hardlink_info:
            stats['linked_count'] += 1
        else:
            stats['unlinked_count'] += 1
        if file_type == 'video':
            stats['video_count'] += 1
        elif file_type == 'subtitle':
            stats['subtitle_count'] += 1
        else:
            stats['other_count'] += 1

        return file_data

    def _find_hardlink_info(
        self,
        file_name: str,
        hardlink_map: Dict[str, Dict],
        download_dir: str,
        torrent_name: str
    ) -> Optional[Dict]:
        """
        Find hardlink info using multiple path matching strategies.

        Args:
            file_name: File name/path from qBittorrent.
            hardlink_map: Hardlink info mapping.
            download_dir: Download directory.
            torrent_name: Torrent name.

        Returns:
            Hardlink info dict or None.
        """
        if not hardlink_map:
            return None

        # Try multiple path formats
        paths_to_try = [
            file_name,
            file_name.replace('\\', '/'),
            f'{download_dir}/{file_name}'.replace('//', '/').replace('\\', '/'),
            file_name.split('/')[-1].split('\\')[-1],
            f'{torrent_name}/{file_name}'.replace('//', '/').replace('\\', '/')
        ]

        for path in paths_to_try:
            if path in hardlink_map:
                return hardlink_map[path]

        return None

    def _get_file_type(self, filename: str) -> str:
        """
        Determine file type based on extension.

        Args:
            filename: File name.

        Returns:
            File type: 'video', 'subtitle', or 'other'.
        """
        video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')
        subtitle_extensions = ('.srt', '.ass', '.ssa', '.vtt', '.sub')

        lower_name = filename.lower()
        if lower_name.endswith(video_extensions):
            return 'video'
        elif lower_name.endswith(subtitle_extensions):
            return 'subtitle'
        return 'other'

    def check_existing_hardlinks(
        self,
        anime_id: int,
        files: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Check if selected files have existing hardlinks.

        Args:
            anime_id: Anime ID.
            files: List of files with hash_id and relative_path.

        Returns:
            Dictionary with existing and new files info.
        """
        try:
            with db_manager.session() as session:
                hardlinks = session.query(Hardlink).filter_by(
                    anime_id=anime_id
                ).all()

                # Build map of existing hardlinks
                hardlink_map = self._build_hardlink_map(hardlinks)

                existing_files = []
                new_files = []

                for file_data in files:
                    hash_id = file_data.get('hash_id')
                    relative_path = file_data.get('relative_path')
                    filename = relative_path.split('/')[-1].split('\\')[-1]

                    torrent_map = hardlink_map.get(hash_id, {})

                    # Try to find existing hardlink
                    hardlink_info = None
                    for path in [relative_path, relative_path.replace('\\', '/'), filename]:
                        if path in torrent_map:
                            hardlink_info = torrent_map[path]
                            break

                    if hardlink_info:
                        existing_files.append({
                            'original_name': filename,
                            'relative_path': relative_path,
                            'hash_id': hash_id,
                            'current_hardlink': hardlink_info['hardlink_path'],
                            'hardlink_id': hardlink_info['id']
                        })
                    else:
                        new_files.append({
                            'original_name': filename,
                            'relative_path': relative_path,
                            'hash_id': hash_id
                        })

                return {
                    'success': True,
                    'has_existing': len(existing_files) > 0,
                    'existing_files': existing_files,
                    'new_files': new_files
                }

        except Exception as e:
            logger.error(f'检查已存在硬链接失败: {e}')
            return {'success': False, 'error': str(e)}

    def start_ai_processing(
        self,
        anime_id: int,
        files: List[Dict[str, str]],
        replace_existing: bool = False
    ) -> Dict[str, Any]:
        """
        Start AI processing for selected files.

        Creates a task ID for tracking progress.

        Args:
            anime_id: Anime ID.
            files: List of files with hash_id and relative_path.
            replace_existing: Whether to replace existing hardlinks.

        Returns:
            Dictionary with task_id for progress tracking.
        """
        task_id = str(uuid.uuid4())

        # Store task info for tracking
        # In a real implementation, this would be stored in Redis or a database
        # For now, we'll process synchronously in the endpoint

        return {
            'success': True,
            'task_id': task_id,
            'message': '处理已开始'
        }

    def get_ai_rename_preview(
        self,
        anime_id: int,
        files: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Get AI rename suggestions for selected files.

        Calls AI directly (no regex fallback) to get rename suggestions,
        then returns comparison with existing hardlinks.

        Args:
            anime_id: Anime ID.
            files: List of files with hash_id and relative_path.

        Returns:
            Dictionary with AI suggestions and existing hardlink comparison.
        """
        try:
            from src.container import container

            with db_manager.session() as session:
                # Get anime info
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'success': False, 'error': '动漫不存在'}

                anime_title = anime.short_title or anime.original_title
                category = anime.category or 'tv'
                season = anime.season or 1
                media_type = anime.media_type or 'anime'

                # Get existing hardlinks
                hardlinks = session.query(Hardlink).filter_by(anime_id=anime_id).all()
                hardlink_map = self._build_hardlink_map(hardlinks)

                # Group files by torrent hash
                from collections import defaultdict
                files_by_hash = defaultdict(list)
                for f in files:
                    files_by_hash[f.get('hash_id')].append(f)

                # Collect all file names for AI processing
                all_filenames = []
                file_info_map = {}  # Map filename to full file info

                for hash_id, file_list in files_by_hash.items():
                    for f in file_list:
                        relative_path = f.get('relative_path', '')
                        filename = relative_path.split('/')[-1].split('\\')[-1]
                        all_filenames.append(filename)
                        file_info_map[filename] = {
                            'hash_id': hash_id,
                            'relative_path': relative_path,
                            'filename': filename
                        }

                if not all_filenames:
                    return {'success': False, 'error': '没有文件需要处理'}

                # Get AI file renamer directly (bypassing RenameService regex logic)
                ai_file_renamer = container.file_renamer()

                logger.info(f'🤖 调用AI获取重命名建议: {len(all_filenames)} 个文件')

                # Call AI for rename suggestions
                rename_result = ai_file_renamer.generate_rename_mapping(
                    files=all_filenames,
                    category=category,
                    anime_title=anime_title,
                    folder_structure=None,
                    tvdb_data=None
                )

                if not rename_result or not rename_result.main_files:
                    return {
                        'success': False,
                        'error': 'AI未能生成重命名建议'
                    }

                # Build target path first (needed for relative path extraction)
                target_path = self._path_builder.build_target_directory(
                    anime_title=anime_title,
                    media_type=media_type,
                    category=category
                )

                # Build preview results
                preview_items = []

                for original_name, new_name in rename_result.main_files.items():
                    file_info = file_info_map.get(original_name)
                    if not file_info:
                        continue

                    hash_id = file_info['hash_id']
                    relative_path = file_info['relative_path']

                    # Check for existing hardlink
                    torrent_map = hardlink_map.get(hash_id, {})
                    existing_hardlink = None
                    hardlink_id = None

                    for path in [relative_path, relative_path.replace('\\', '/'), original_name]:
                        if path in torrent_map:
                            existing_hardlink = torrent_map[path]['hardlink_path']
                            hardlink_id = torrent_map[path]['id']
                            break

                    # Extract relative path from target_path base (including Season folder)
                    existing_relative_name = None
                    if existing_hardlink:
                        # Normalize paths for comparison
                        normalized_hardlink = existing_hardlink.replace('\\', '/')
                        normalized_target = target_path.replace('\\', '/')

                        # Extract relative path from target directory
                        if normalized_hardlink.startswith(normalized_target):
                            existing_relative_name = normalized_hardlink[len(normalized_target):].lstrip('/')
                        else:
                            # Fallback to just filename if paths don't match
                            existing_relative_name = existing_hardlink.split('/')[-1].split('\\')[-1]

                    preview_items.append({
                        'original_name': original_name,
                        'ai_suggested_name': new_name,
                        'existing_hardlink_path': existing_hardlink,
                        'existing_hardlink_name': existing_relative_name,
                        'hardlink_id': hardlink_id,
                        'hash_id': hash_id,
                        'relative_path': relative_path,
                        'has_existing': existing_hardlink is not None,
                        'is_different': existing_relative_name != new_name if existing_relative_name else True,
                        'selected': True  # Default to selected
                    })

                return {
                    'success': True,
                    'anime_title': anime_title,
                    'target_path': target_path,
                    'preview_items': preview_items,
                    'total_count': len(preview_items),
                    'existing_count': sum(1 for p in preview_items if p['has_existing']),
                    'new_count': sum(1 for p in preview_items if not p['has_existing'])
                }

        except Exception as e:
            logger.error(f'获取AI重命名预览失败: {e}')
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def apply_ai_renames(
        self,
        anime_id: int,
        items: List[Dict[str, Any]],
        target_path: str
    ) -> Dict[str, Any]:
        """
        Apply AI rename suggestions to create/replace hardlinks.

        Args:
            anime_id: Anime ID.
            items: List of items to apply with ai_suggested_name, hash_id,
                   relative_path, and optionally hardlink_id to replace.
            target_path: Target directory for hardlinks.

        Returns:
            Dictionary with results.
        """
        try:
            with db_manager.session() as session:
                anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
                if not anime:
                    return {'success': False, 'error': '动漫不存在'}

                created = []
                replaced = []
                failed = []

                # Ensure target directory exists
                os.makedirs(target_path, mode=0o775, exist_ok=True)

                for item in items:
                    hash_id = item.get('hash_id')
                    relative_path = item.get('relative_path')
                    new_name = item.get('ai_suggested_name')
                    hardlink_id = item.get('hardlink_id')

                    if not hash_id or not relative_path or not new_name:
                        failed.append({
                            'name': relative_path,
                            'error': '缺少必要参数'
                        })
                        continue

                    # Get download record for source path
                    download = session.query(DownloadStatusModel).filter_by(
                        hash_id=hash_id
                    ).first()

                    if not download:
                        failed.append({
                            'name': relative_path,
                            'error': '下载记录不存在'
                        })
                        continue

                    # Build source path and normalize
                    source_path = os.path.normpath(
                        os.path.join(download.download_directory, relative_path)
                    )
                    if not os.path.exists(source_path):
                        failed.append({
                            'name': relative_path,
                            'error': '源文件不存在'
                        })
                        continue

                    # Build target path - handle Season subfolder in new_name
                    if '/' in new_name:
                        # new_name contains subfolder like "Season 1/filename.mkv"
                        subfolder, filename = new_name.rsplit('/', 1)
                        target_dir = os.path.join(target_path, subfolder)
                        os.makedirs(target_dir, mode=0o775, exist_ok=True)
                        target_file_path = os.path.normpath(
                            os.path.join(target_dir, filename)
                        )
                    else:
                        target_file_path = os.path.normpath(
                            os.path.join(target_path, new_name)
                        )

                    try:
                        # Delete existing hardlink if replacing (by ID)
                        is_replacement = False
                        if hardlink_id:
                            old_hardlink = session.query(Hardlink).filter_by(
                                id=hardlink_id
                            ).first()
                            if old_hardlink:
                                old_path = old_hardlink.hardlink_path
                                if os.path.exists(old_path):
                                    os.remove(old_path)
                                session.delete(old_hardlink)
                                session.flush()  # Flush delete before insert
                                is_replacement = True

                        # Also check for existing record by source path (in case not found by ID)
                        existing_by_source = session.query(Hardlink).filter_by(
                            original_file_path=source_path
                        ).first()
                        if existing_by_source:
                            old_path = existing_by_source.hardlink_path
                            if os.path.exists(old_path):
                                os.remove(old_path)
                            session.delete(existing_by_source)
                            session.flush()
                            is_replacement = True

                        # Remove target file if exists
                        if os.path.exists(target_file_path):
                            os.remove(target_file_path)

                        # Create hardlink
                        os.link(source_path, target_file_path)
                        file_size = os.path.getsize(source_path)

                        # Save to database
                        new_hardlink = Hardlink(
                            anime_id=anime_id,
                            original_file_path=source_path,
                            hardlink_path=target_file_path,
                            file_size=file_size,
                            torrent_hash=hash_id
                        )
                        session.add(new_hardlink)

                        if is_replacement:
                            replaced.append({
                                'original': relative_path,
                                'new_name': new_name,
                                'hardlink': target_file_path
                            })
                        else:
                            created.append({
                                'original': relative_path,
                                'new_name': new_name,
                                'hardlink': target_file_path
                            })

                    except OSError as e:
                        logger.error(f'创建硬链接失败: {e}')
                        failed.append({
                            'name': relative_path,
                            'error': str(e)
                        })

                session.commit()

                return {
                    'success': True,
                    'created': created,
                    'replaced': replaced,
                    'failed': failed,
                    'total_created': len(created),
                    'total_replaced': len(replaced),
                    'total_failed': len(failed)
                }

        except Exception as e:
            logger.error(f'应用AI重命名失败: {e}')
            return {'success': False, 'error': str(e)}

    def delete_hardlinks_for_files(
        self,
        hardlink_ids: List[int]
    ) -> Dict[str, Any]:
        """
        Delete hardlinks by IDs.

        Args:
            hardlink_ids: List of hardlink record IDs to delete.

        Returns:
            Dictionary with deletion result.
        """
        try:
            with db_manager.session() as session:
                deleted_count = 0

                for hardlink_id in hardlink_ids:
                    hardlink = session.query(Hardlink).filter_by(id=hardlink_id).first()
                    if hardlink:
                        # Delete physical file
                        if os.path.exists(hardlink.hardlink_path):
                            try:
                                os.remove(hardlink.hardlink_path)
                            except Exception as e:
                                logger.warning(f'删除硬链接文件失败: {e}')

                        # Delete database record
                        session.delete(hardlink)
                        deleted_count += 1

                session.commit()

                return {
                    'success': True,
                    'deleted_count': deleted_count
                }

        except Exception as e:
            logger.error(f'删除硬链接失败: {e}')
            return {'success': False, 'error': str(e)}


# Global service instance
_anime_detail_service: Optional[AnimeDetailService] = None


def get_anime_detail_service() -> AnimeDetailService:
    """
    Get the global anime detail service instance.

    Returns:
        AnimeDetailService instance.
    """
    global _anime_detail_service
    if _anime_detail_service is None:
        from src.infrastructure.repositories import AnimeRepository, DownloadRepository
        from src.infrastructure.downloader import QBitAdapter
        from src.core.config import config as app_config
        _anime_detail_service = AnimeDetailService(
            AnimeRepository(),
            DownloadRepository(),
            QBitAdapter(),
            PathBuilder(
                download_root=app_config.qbittorrent.base_download_path,
                library_root=app_config.link_target_path
            )
        )
    return _anime_detail_service
