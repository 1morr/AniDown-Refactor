"""
Download repository module.

Contains the DownloadRepository class implementing IDownloadRepository interface.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func, or_

from src.core.domain.entities import DownloadRecord
from src.core.domain.value_objects import DownloadMethod, DownloadStatus as DLStatus, TorrentHash
from src.core.exceptions import DatabaseError
from src.core.interfaces.repositories import IDownloadRepository
from src.infrastructure.database.models import (
    AnimeInfo,
    DownloadHistory,
    DownloadStatus,
    Hardlink,
    TorrentFile,
)
from src.infrastructure.database.session import db_manager

logger = logging.getLogger(__name__)


class DownloadRepository(IDownloadRepository):
    """下载状态仓库"""

    def _to_entity(self, row: DownloadStatus) -> DownloadRecord:
        """将数据库行转换为实体"""
        try:
            torrent_hash = TorrentHash(value=row.hash_id) if row.hash_id else None
        except ValueError:
            torrent_hash = None

        try:
            status = DLStatus(row.status) if row.status else DLStatus.PENDING
        except ValueError:
            status = DLStatus.PENDING

        try:
            method = DownloadMethod(row.download_method) if row.download_method else DownloadMethod.FIXED_RSS
        except ValueError:
            method = DownloadMethod.FIXED_RSS

        return DownloadRecord(
            id=row.id,
            hash=torrent_hash,
            anime_id=row.anime_id,
            original_filename=row.original_filename or '',
            anime_title=row.anime_title or '',
            subtitle_group=row.subtitle_group or '',
            season=row.season or 1,
            download_directory=row.download_directory or '',
            status=status,
            download_method=method,
            is_multi_season=bool(row.is_multi_season),
            download_time=row.download_time,
            completion_time=row.completion_time
        )

    def _to_dict(self, row: DownloadStatus) -> Dict[str, Any]:
        """将数据库行转换为字典"""
        return {
            'id': row.id,
            'anime_id': row.anime_id,
            'hash_id': row.hash_id,
            'original_filename': row.original_filename,
            'anime_title': row.anime_title,
            'subtitle_group': row.subtitle_group,
            'season': row.season,
            'download_directory': row.download_directory,
            'status': row.status,
            'download_time': row.download_time,
            'completion_time': row.completion_time,
            'is_multi_season': row.is_multi_season,
            'download_method': row.download_method,
            'created_at': row.created_at,
            'updated_at': row.updated_at
        }

    # ==================== IDownloadRepository Interface ====================

    def get_by_hash(self, hash_id: str) -> Optional[DownloadRecord]:
        """根据hash获取下载状态"""
        with db_manager.session() as session:
            download = session.query(DownloadStatus).filter_by(hash_id=hash_id).first()
            if download:
                return self._to_entity(download)
            return None

    def get_by_id(self, record_id: int) -> Optional[DownloadRecord]:
        """根据ID获取下载状态"""
        with db_manager.session() as session:
            download = session.query(DownloadStatus).filter_by(id=record_id).first()
            if download:
                return self._to_entity(download)
            return None

    def get_by_anime_id(self, anime_id: int) -> List[DownloadRecord]:
        """获取指定动漫的所有下载记录"""
        with db_manager.session() as session:
            downloads = session.query(DownloadStatus).filter_by(anime_id=anime_id).all()
            return [self._to_entity(dl) for dl in downloads]

    def get_incomplete(self) -> List[DownloadRecord]:
        """获取所有未完成的下载"""
        with db_manager.session() as session:
            downloads = session.query(DownloadStatus).filter(
                DownloadStatus.status.in_(['downloading', 'pending', 'paused', 'missing'])
            ).all()
            return [self._to_entity(dl) for dl in downloads]

    def get_recent(self, limit: int = 50) -> List[DownloadRecord]:
        """获取最近下载记录"""
        with db_manager.session() as session:
            downloads = session.query(DownloadStatus).order_by(
                DownloadStatus.created_at.desc()
            ).limit(limit).all()
            return [self._to_entity(dl) for dl in downloads]

    def save(self, record: DownloadRecord) -> int:
        """保存下载记录"""
        with db_manager.session() as session:
            download = DownloadStatus(
                anime_id=record.anime_id,
                hash_id=record.hash.value if record.hash else '',
                original_filename=record.original_filename,
                anime_title=record.anime_title,
                subtitle_group=record.subtitle_group,
                season=record.season,
                download_directory=record.download_directory,
                status=record.status.value if record.status else 'pending',
                download_time=record.download_time,
                is_multi_season=1 if record.is_multi_season else 0,
                download_method=record.download_method.value if record.download_method else 'fixed_rss'
            )
            session.add(download)
            session.flush()
            return download.id

    def update_status(
        self,
        hash_id: str,
        status: str,
        completion_time: Optional[datetime] = None
    ) -> bool:
        """更新下载状态"""
        with db_manager.session() as session:
            download = session.query(DownloadStatus).filter_by(hash_id=hash_id).first()
            if download:
                download.status = status
                if completion_time:
                    download.completion_time = completion_time
                download.updated_at = datetime.now(timezone.utc)
                return True
            return False

    def move_to_history(self, hash_id: str) -> bool:
        """将下载记录移动到历史表"""
        with db_manager.session() as session:
            download = session.query(DownloadStatus).filter_by(hash_id=hash_id).first()
            if not download:
                return False

            history = DownloadHistory(
                anime_id=download.anime_id,
                hash_id=download.hash_id,
                original_filename=download.original_filename,
                anime_title=download.anime_title,
                subtitle_group=download.subtitle_group,
                season=download.season,
                download_directory=download.download_directory,
                status=download.status,
                download_time=download.download_time,
                completion_time=download.completion_time,
                is_multi_season=download.is_multi_season,
                download_method=download.download_method,
                deleted_at=datetime.now(timezone.utc)
            )
            session.add(history)
            session.delete(download)
            return True

    def delete(self, hash_id: str) -> bool:
        """删除下载状态"""
        with db_manager.session() as session:
            result = session.query(DownloadStatus).filter_by(hash_id=hash_id).delete()
            return result > 0

    def exists(self, hash_id: str) -> bool:
        """检查下载记录是否存在"""
        with db_manager.session() as session:
            count = session.query(DownloadStatus).filter_by(hash_id=hash_id).count()
            return count > 0

    # ==================== Legacy Methods ====================

    def insert_download_status(
        self,
        hash_id: str,
        original_filename: str,
        anime_title: str = None,
        subtitle_group: str = None,
        season: int = 1,
        download_directory: str = None,
        download_time: datetime = None,
        anime_id: int = None,
        is_multi_season: int = 0,
        download_method: str = 'fixed_rss'
    ) -> int:
        """插入下载状态（遗留方法）"""
        with db_manager.session() as session:
            download = DownloadStatus(
                anime_id=anime_id,
                hash_id=hash_id,
                original_filename=original_filename,
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                download_directory=download_directory,
                download_time=download_time,
                is_multi_season=is_multi_season,
                download_method=download_method
            )
            session.add(download)
            session.flush()
            return download.id

    def get_download_status_by_hash(self, hash_id: str) -> Optional[Dict[str, Any]]:
        """根据hash获取下载状态（遗留方法，返回字典）"""
        with db_manager.session() as session:
            download = session.query(DownloadStatus).filter_by(hash_id=hash_id).first()
            if download:
                return self._to_dict(download)
            return None

    def update_download_status(
        self,
        hash_id: str,
        status: str,
        completion_time: datetime = None,
        download_time: datetime = None
    ) -> bool:
        """更新下载状态（遗留方法）"""
        with db_manager.session() as session:
            download = session.query(DownloadStatus).filter_by(hash_id=hash_id).first()
            if download:
                download.status = status
                if completion_time:
                    download.completion_time = completion_time
                if download_time:
                    download.download_time = download_time
                download.updated_at = datetime.now(timezone.utc)
                return True
            return False

    def delete_download_status(self, hash_id: str) -> bool:
        """删除下载状态（遗留方法）"""
        return self.delete(hash_id)

    def insert_torrent_file(
        self,
        torrent_hash: str,
        file_path: str,
        file_size: int = None,
        file_type: str = None,
        anime_id: int = None
    ) -> Optional[int]:
        """插入torrent文件记录"""
        with db_manager.session() as session:
            existing = session.query(TorrentFile).filter_by(
                torrent_hash=torrent_hash,
                file_path=file_path
            ).first()

            if existing:
                return existing.id

            torrent_file = TorrentFile(
                anime_id=anime_id,
                torrent_hash=torrent_hash,
                file_path=file_path,
                file_size=file_size,
                file_type=file_type
            )
            session.add(torrent_file)
            session.flush()
            return torrent_file.id

    def get_torrent_files(self, torrent_hash: str) -> List[TorrentFile]:
        """获取torrent的所有文件记录"""
        with db_manager.session() as session:
            return session.query(TorrentFile).filter_by(
                torrent_hash=torrent_hash
            ).order_by(TorrentFile.file_path).all()

    def count_all(self) -> int:
        """统计所有下载数量"""
        with db_manager.session() as session:
            return session.query(DownloadStatus).count()

    def count_recent(self, hours: int = 24) -> int:
        """统计最近新增下载数量"""
        with db_manager.session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            return session.query(DownloadStatus).filter(
                DownloadStatus.created_at >= cutoff
            ).count()

    def get_recent_downloads(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近下载记录（遗留方法，返回字典）"""
        with db_manager.session() as session:
            downloads = session.query(DownloadStatus).order_by(
                DownloadStatus.created_at.desc()
            ).limit(limit).all()
            return [self._to_dict(dl) for dl in downloads]

    def get_downloads_paginated(self, page: int, per_page: int, **filters) -> Dict[str, Any]:
        """获取分页的下载记录"""
        with db_manager.session() as session:
            query = session.query(DownloadStatus, AnimeInfo.media_type).outerjoin(
                AnimeInfo, DownloadStatus.anime_id == AnimeInfo.id
            )

            query = self._apply_filters(query, filters, session)

            if filters.get('group_by') and filters.get('viewing_group'):
                query = self._apply_group_filter(query, filters['group_by'], filters['viewing_group'])

            sort_column = filters.get('sort_column', 'download_time')
            sort_order = filters.get('sort_order', 'desc')

            if sort_column == 'media_type':
                if sort_order == 'desc':
                    query = query.order_by(AnimeInfo.media_type.desc())
                else:
                    query = query.order_by(AnimeInfo.media_type.asc())
            elif sort_column == 'has_hardlinks':
                hardlink_count_subquery = session.query(
                    Hardlink.torrent_hash,
                    func.count(Hardlink.id).label('link_count')
                ).group_by(Hardlink.torrent_hash).subquery()

                query = query.outerjoin(
                    hardlink_count_subquery,
                    DownloadStatus.hash_id == hardlink_count_subquery.c.torrent_hash
                )

                if sort_order == 'desc':
                    query = query.order_by(
                        func.coalesce(hardlink_count_subquery.c.link_count, 0).desc()
                    )
                else:
                    query = query.order_by(
                        func.coalesce(hardlink_count_subquery.c.link_count, 0).asc()
                    )
            elif hasattr(DownloadStatus, sort_column):
                column = getattr(DownloadStatus, sort_column)
                if sort_order == 'desc':
                    query = query.order_by(column.desc())
                else:
                    query = query.order_by(column.asc())
            else:
                query = query.order_by(DownloadStatus.download_time.desc())

            total_count = query.count()
            total_pages = (total_count + per_page - 1) // per_page
            items = query.offset((page - 1) * per_page).limit(per_page).all()

            hash_ids = [item[0].hash_id for item in items]

            hardlink_counts = {}
            if hash_ids:
                hardlink_query = session.query(
                    Hardlink.torrent_hash,
                    func.count(Hardlink.id).label('count')
                ).filter(
                    Hardlink.torrent_hash.in_(hash_ids)
                ).group_by(Hardlink.torrent_hash).all()

                hardlink_counts = {row.torrent_hash: row.count for row in hardlink_query}

            downloads = []
            for download_status, media_type in items:
                hardlink_count = hardlink_counts.get(download_status.hash_id, 0)
                downloads.append({
                    'id': download_status.id,
                    'anime_id': download_status.anime_id,
                    'hash_id': download_status.hash_id,
                    'original_filename': download_status.original_filename,
                    'anime_title': download_status.anime_title,
                    'subtitle_group': download_status.subtitle_group,
                    'season': download_status.season,
                    'download_directory': download_status.download_directory,
                    'status': download_status.status,
                    'download_time': download_status.download_time,
                    'completion_time': download_status.completion_time,
                    'created_at': download_status.created_at,
                    'updated_at': download_status.updated_at,
                    'hardlink_count': hardlink_count,
                    'has_hardlinks': hardlink_count > 0,
                    'media_type': media_type or 'anime'
                })

            return {
                'downloads': downloads,
                'total_count': total_count,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page
            }

    def get_downloads_grouped(self, group_by: str, **filters) -> Dict[str, Any]:
        """获取分组的下载统计"""
        with db_manager.session() as session:
            if group_by == 'anime_title':
                group_field = DownloadStatus.anime_title
            elif group_by == 'subtitle_group':
                group_field = DownloadStatus.subtitle_group
            elif group_by == 'status':
                group_field = DownloadStatus.status
            else:
                return {'groups': [], 'total_count': 0}

            base_query = session.query(DownloadStatus)
            base_query = self._apply_filters(base_query, filters, session)

            group_stats = base_query.with_entities(
                group_field.label('group_name'),
                func.count(DownloadStatus.id).label('total_count'),
                func.sum(case((DownloadStatus.status == 'completed', 1), else_=0)).label('completed_count')
            ).group_by(group_field).all()

            groups = []
            for stat in group_stats:
                group_name = stat.group_name or '(未分类)'

                group_downloads_query = session.query(DownloadStatus)
                group_downloads_query = self._apply_filters(group_downloads_query, filters, session)

                if stat.group_name is None:
                    group_downloads_query = group_downloads_query.filter(group_field.is_(None))
                else:
                    group_downloads_query = group_downloads_query.filter(group_field == stat.group_name)

                hash_ids = [d.hash_id for d in group_downloads_query.all()]

                hardlink_count = 0
                if hash_ids:
                    hardlink_count = session.query(
                        func.count(func.distinct(Hardlink.id))
                    ).filter(Hardlink.torrent_hash.in_(hash_ids)).scalar() or 0

                groups.append({
                    'group_name': group_name,
                    'total_count': stat.total_count,
                    'completed_count': stat.completed_count or 0,
                    'hardlink_count': hardlink_count
                })

            return {
                'groups': groups,
                'total_count': len(groups)
            }

    def _apply_filters(self, query, filters, session=None):
        """应用通用过滤条件"""
        if filters.get('media_type_filter'):
            query = query.join(AnimeInfo, DownloadStatus.anime_id == AnimeInfo.id)
            query = query.filter(AnimeInfo.media_type == filters['media_type_filter'])

        if filters.get('search'):
            search = f"%{filters['search']}%"
            query = query.filter(or_(
                DownloadStatus.hash_id.like(search),
                DownloadStatus.original_filename.like(search),
                DownloadStatus.anime_title.like(search),
                DownloadStatus.subtitle_group.like(search)
            ))

        if filters.get('status_filter'):
            query = query.filter(DownloadStatus.status == filters['status_filter'])

        if filters.get('season_filter'):
            if filters['season_filter'] == '5+':
                query = query.filter(DownloadStatus.season >= 5)
            else:
                try:
                    query = query.filter(DownloadStatus.season == int(filters['season_filter']))
                except ValueError:
                    pass

        if filters.get('hardlink_filter') and session:
            if filters['hardlink_filter'] == 'yes':
                query = query.filter(DownloadStatus.hash_id.in_(
                    session.query(Hardlink.torrent_hash).distinct()
                ))
            elif filters['hardlink_filter'] == 'no':
                query = query.filter(~DownloadStatus.hash_id.in_(
                    session.query(Hardlink.torrent_hash).distinct()
                ))

        return query

    def _apply_group_filter(self, query, group_by: str, group_name: str):
        """应用分组过滤条件"""
        if group_name == '(未分类)':
            if group_by == 'anime_title':
                query = query.filter(DownloadStatus.anime_title.is_(None))
            elif group_by == 'subtitle_group':
                query = query.filter(DownloadStatus.subtitle_group.is_(None))
        else:
            if group_by == 'anime_title':
                query = query.filter(DownloadStatus.anime_title == group_name)
            elif group_by == 'subtitle_group':
                query = query.filter(DownloadStatus.subtitle_group == group_name)
            elif group_by == 'status':
                query = query.filter(DownloadStatus.status == group_name)

        return query

    def get_incomplete_downloads(self) -> List[Dict[str, Any]]:
        """获取所有未完成的下载（遗留方法，返回字典）"""
        with db_manager.session() as session:
            downloads = session.query(DownloadStatus).filter(
                DownloadStatus.status.in_(['downloading', 'pending', 'paused', 'missing'])
            ).all()
            return [self._to_dict(dl) for dl in downloads]

    def get_all_downloads(self) -> List[Dict[str, Any]]:
        """获取所有下载记录（遗留方法，返回字典）"""
        with db_manager.session() as session:
            downloads = session.query(DownloadStatus).all()
            return [self._to_dict(dl) for dl in downloads]

    def get_completed_downloads_without_hardlinks(self) -> List[Dict[str, Any]]:
        """获取已完成但没有硬链接的下载"""
        with db_manager.session() as session:
            hardlink_hashes = session.query(Hardlink.torrent_hash).distinct().subquery()

            downloads = session.query(DownloadStatus).filter(
                DownloadStatus.status == 'completed',
                ~DownloadStatus.hash_id.in_(session.query(hardlink_hashes.c.torrent_hash))
            ).all()
            return [self._to_dict(dl) for dl in downloads]

    def get_downloads_by_group(self, group_by: str, group_name: str) -> List[Dict[str, Any]]:
        """根据分组获取下载记录"""
        with db_manager.session() as session:
            query = session.query(DownloadStatus)

            if group_by == 'anime_title':
                query = query.filter(DownloadStatus.anime_title == group_name)
            elif group_by == 'subtitle_group':
                query = query.filter(DownloadStatus.subtitle_group == group_name)
            elif group_by == 'season':
                try:
                    season_num = int(group_name.replace('Season ', ''))
                    query = query.filter(DownloadStatus.season == season_num)
                except ValueError:
                    return []
            elif group_by == 'status':
                query = query.filter(DownloadStatus.status == group_name)
            else:
                return []

            downloads = query.all()
            return [self._to_dict(dl) for dl in downloads]
