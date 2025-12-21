"""
History repository module.

Contains the HistoryRepository class implementing IHardlinkRepository and
providing access to various history records.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from src.core.domain.entities import HardlinkRecord
from src.core.interfaces.repositories import IHardlinkRepository
from src.infrastructure.database.models import (
    DownloadHistory,
    DownloadStatus,
    Hardlink,
    HardlinkAttempt,
    ManualUploadHistory,
    RssProcessingDetail,
    RssProcessingHistory,
    TorrentFile,
    AnimeInfo,
)
from src.infrastructure.database.session import db_manager

logger = logging.getLogger(__name__)


class HistoryRepository(IHardlinkRepository):
    """历史记录仓库"""

    def _to_entity(self, row: Hardlink) -> HardlinkRecord:
        """将数据库行转换为实体"""
        return HardlinkRecord(
            id=row.id,
            anime_id=row.anime_id,
            torrent_hash=row.torrent_hash or '',
            original_file_path=row.original_file_path or '',
            hardlink_path=row.hardlink_path or '',
            file_size=row.file_size or 0,
            created_at=row.created_at
        )

    # ==================== IHardlinkRepository Interface ====================

    def get_by_id(self, hardlink_id: int) -> Optional[HardlinkRecord]:
        """根据ID获取硬链接"""
        with db_manager.session() as session:
            hardlink = session.query(Hardlink).filter_by(id=hardlink_id).first()
            if hardlink:
                return self._to_entity(hardlink)
            return None

    def get_by_torrent_hash(self, hash_id: str) -> List[HardlinkRecord]:
        """根据torrent hash获取硬链接"""
        with db_manager.session() as session:
            hardlinks = session.query(Hardlink).filter_by(
                torrent_hash=hash_id
            ).order_by(Hardlink.created_at.desc()).all()
            return [self._to_entity(hl) for hl in hardlinks]

    def get_by_anime_id(self, anime_id: int) -> List[HardlinkRecord]:
        """根据anime ID获取硬链接"""
        with db_manager.session() as session:
            hardlinks = session.query(Hardlink).filter_by(
                anime_id=anime_id
            ).order_by(Hardlink.created_at.desc()).all()
            return [self._to_entity(hl) for hl in hardlinks]

    def save(self, record: HardlinkRecord) -> int:
        """保存硬链接记录"""
        with db_manager.session() as session:
            # 检查是否存在
            existing = session.query(Hardlink).filter_by(
                original_file_path=record.original_file_path,
                hardlink_path=record.hardlink_path
            ).first()

            if existing:
                return existing.id

            hardlink = Hardlink(
                anime_id=record.anime_id,
                torrent_hash=record.torrent_hash,
                original_file_path=record.original_file_path,
                hardlink_path=record.hardlink_path,
                file_size=record.file_size
            )
            session.add(hardlink)
            session.flush()
            return hardlink.id

    def delete(self, hardlink_id: int) -> bool:
        """删除硬链接记录"""
        with db_manager.session() as session:
            result = session.query(Hardlink).filter_by(id=hardlink_id).delete()
            return result > 0

    def delete_by_torrent_hash(self, hash_id: str) -> int:
        """删除指定torrent hash的所有硬链接记录"""
        with db_manager.session() as session:
            result = session.query(Hardlink).filter_by(torrent_hash=hash_id).delete()
            return result

    # ==================== Legacy Methods ====================

    def insert_hardlink(
        self,
        original_file_path: str,
        hardlink_path: str,
        file_size: int = None,
        anime_id: int = None,
        torrent_hash: str = None
    ) -> Optional[int]:
        """插入硬链接记录"""
        with db_manager.session() as session:
            existing = session.query(Hardlink).filter_by(
                original_file_path=original_file_path,
                hardlink_path=hardlink_path
            ).first()

            if existing:
                return existing.id

            hardlink = Hardlink(
                anime_id=anime_id,
                torrent_hash=torrent_hash,
                original_file_path=original_file_path,
                hardlink_path=hardlink_path,
                file_size=file_size
            )
            session.add(hardlink)
            session.flush()
            return hardlink.id

    def insert_hardlink_attempt(
        self,
        original_file_path: str,
        target_path: str,
        success: bool,
        anime_id: int = None,
        torrent_hash: str = None,
        file_size: int = None,
        file_type: str = None,
        failure_reason: str = None,
        link_method: str = None
    ) -> int:
        """插入硬链接尝试记录"""
        with db_manager.session() as session:
            attempt = HardlinkAttempt(
                anime_id=anime_id,
                torrent_hash=torrent_hash,
                original_file_path=original_file_path,
                target_path=target_path,
                file_size=file_size,
                file_type=file_type,
                success=1 if success else 0,
                failure_reason=failure_reason,
                link_method=link_method
            )
            session.add(attempt)
            session.flush()
            return attempt.id

    # ==================== RSS处理历史相关 ====================

    def insert_rss_history(
        self,
        rss_url: str,
        triggered_by: str,
        items_found: int = 0,
        items_attempted: int = 0,
        items_processed: int = 0,
        status: str = 'processing',
        error_message: str = None
    ) -> int:
        """插入RSS处理历史记录"""
        with db_manager.session() as session:
            history = RssProcessingHistory(
                rss_url=rss_url,
                triggered_by=triggered_by,
                items_found=items_found,
                items_attempted=items_attempted,
                items_processed=items_processed,
                status=status,
                error_message=error_message
            )
            session.add(history)
            session.flush()
            return history.id

    def insert_rss_detail(
        self,
        history_id: int,
        item_title: str,
        item_status: str,
        failure_reason: str = None
    ) -> int:
        """插入RSS处理详情记录"""
        with db_manager.session() as session:
            detail = RssProcessingDetail(
                history_id=history_id,
                item_title=item_title,
                item_status=item_status,
                failure_reason=failure_reason
            )
            session.add(detail)
            session.flush()
            return detail.id

    def update_rss_history_stats(
        self,
        history_id: int,
        items_found: int = None,
        items_processed: int = None,
        items_attempted: int = None,
        status: str = None
    ) -> bool:
        """更新RSS处理历史统计信息"""
        with db_manager.session() as session:
            history = session.query(RssProcessingHistory).filter_by(id=history_id).first()
            if history:
                if items_found is not None:
                    history.items_found = items_found
                if items_processed is not None:
                    history.items_processed = items_processed
                if items_attempted is not None:
                    history.items_attempted = items_attempted
                if status:
                    history.status = status
                    if status in ['completed', 'failed']:
                        history.completed_at = datetime.now(timezone.utc)
                return True
            return False

    def update_rss_history_url(self, history_id: int, rss_url: str) -> bool:
        """更新RSS处理历史的URL（用于批处理模式更新实际数量）"""
        with db_manager.session() as session:
            history = session.query(RssProcessingHistory).filter_by(id=history_id).first()
            if history:
                history.rss_url = rss_url
                return True
            return False

    def accumulate_rss_history_stats(
        self,
        history_id: int,
        items_found: int = 0,
        items_attempted: int = 0,
        items_processed: int = 0
    ) -> bool:
        """累加RSS处理历史统计信息（用于批处理模式）"""
        with db_manager.session() as session:
            history = session.query(RssProcessingHistory).filter_by(id=history_id).first()
            if history:
                history.items_found = (history.items_found or 0) + items_found
                history.items_attempted = (history.items_attempted or 0) + items_attempted
                history.items_processed = (history.items_processed or 0) + items_processed
                return True
            return False

    def increment_rss_history_processed(self, history_id: int) -> bool:
        """递增RSS处理历史的已处理计数"""
        with db_manager.session() as session:
            history = session.query(RssProcessingHistory).filter_by(id=history_id).first()
            if history:
                history.items_processed = (history.items_processed or 0) + 1
                # 检查是否所有项目都已处理完成
                if history.items_attempted and history.items_processed >= history.items_attempted:
                    history.status = 'completed'
                    history.completed_at = datetime.now(timezone.utc)
                return True
            return False

    def mark_processing_as_interrupted(self) -> int:
        """
        将所有 processing 状态的历史记录标记为 interrupted。

        用于程序启动时清理上次运行遗留的未完成记录，
        或程序关闭时标记未处理完的记录。

        Returns:
            受影响的记录数
        """
        with db_manager.session() as session:
            result = session.query(RssProcessingHistory).filter_by(
                status='processing'
            ).update({
                'status': 'interrupted',
                'completed_at': datetime.now(timezone.utc)
            })
            logger.info(f'📋 标记了 {result} 条 processing 状态的历史记录为 interrupted')
            return result

    def mark_history_interrupted(self, history_ids: List[int]) -> int:
        """
        将指定的历史记录标记为 interrupted。

        用于队列清除时，标记被清除项目对应的历史记录。

        Args:
            history_ids: 要标记的历史记录 ID 列表

        Returns:
            受影响的记录数
        """
        if not history_ids:
            return 0

        # 去重
        unique_ids = list(set(history_ids))

        with db_manager.session() as session:
            result = session.query(RssProcessingHistory).filter(
                RssProcessingHistory.id.in_(unique_ids),
                RssProcessingHistory.status == 'processing'
            ).update({
                'status': 'interrupted',
                'completed_at': datetime.now(timezone.utc)
            }, synchronize_session=False)
            logger.info(f'📋 标记了 {result} 条历史记录为 interrupted')
            return result

    # ==================== 手动上传历史相关 ====================

    def insert_manual_upload(
        self,
        upload_type: str,
        anime_title: str,
        subtitle_group: str = None,
        season: int = 1,
        category: str = 'tv',
        torrent_hash: str = None,
        upload_status: str = 'success',
        error_message: str = None
    ) -> int:
        """插入手动上传历史记录"""
        with db_manager.session() as session:
            history = ManualUploadHistory(
                upload_type=upload_type,
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                torrent_hash=torrent_hash,
                upload_status=upload_status,
                error_message=error_message
            )
            session.add(history)
            session.flush()
            return history.id

    def insert_manual_upload_history(
        self,
        upload_type: str,
        anime_title: str,
        subtitle_group: str = None,
        season: int = 1,
        category: str = 'tv',
        torrent_hash: str = None,
        upload_status: str = 'success',
        error_message: str = None
    ) -> int:
        """插入手动上传历史记录 (别名)"""
        return self.insert_manual_upload(
            upload_type, anime_title, subtitle_group, season,
            category, torrent_hash, upload_status, error_message
        )

    def count_hardlinks(self) -> int:
        """统计硬链接数量"""
        with db_manager.session() as session:
            return session.query(Hardlink).count()

    def get_last_rss_check_time(self) -> Optional[datetime]:
        """获取上次RSS检查时间"""
        with db_manager.session() as session:
            history = session.query(RssProcessingHistory).order_by(
                RssProcessingHistory.created_at.desc()
            ).first()
            if history:
                return history.created_at
            return None

    def get_download_history_by_hash(self, hash_id: str) -> Optional[Dict[str, Any]]:
        """根据hash获取下载历史记录"""
        with db_manager.session() as session:
            history = session.query(DownloadHistory).filter_by(hash_id=hash_id).first()

            if history:
                return {
                    'id': history.id,
                    'anime_id': history.anime_id,
                    'hash_id': history.hash_id,
                    'original_filename': history.original_filename,
                    'anime_title': history.anime_title,
                    'subtitle_group': history.subtitle_group,
                    'season': history.season,
                    'download_directory': history.download_directory,
                    'status': history.status,
                    'download_time': history.download_time,
                    'completion_time': history.completion_time,
                    'is_multi_season': getattr(history, 'is_multi_season', 0),
                    'download_method': getattr(history, 'download_method', 'unknown'),
                    'deleted_at': history.deleted_at,
                    'created_at': history.created_at,
                    'updated_at': history.updated_at
                }

            return None

    def delete_download_history_by_hash(self, hash_id: str) -> bool:
        """从download_history表中删除记录"""
        with db_manager.session() as session:
            result = session.query(DownloadHistory).filter_by(hash_id=hash_id).delete()
            return result > 0

    def clear_all_download_history(self) -> int:
        """清空所有下载历史记录"""
        with db_manager.session() as session:
            result = session.query(DownloadHistory).delete()
            return result

    def get_hardlinks_by_hash(self, hash_id: str) -> List[Dict[str, Any]]:
        """根据hash获取硬链接（返回字典）"""
        with db_manager.session() as session:
            hardlinks = session.query(Hardlink).filter_by(
                torrent_hash=hash_id
            ).order_by(Hardlink.created_at.desc()).all()

            return [{
                'id': hl.id,
                'anime_id': hl.anime_id,
                'torrent_hash': hl.torrent_hash,
                'original_file_path': hl.original_file_path,
                'hardlink_path': hl.hardlink_path,
                'file_size': hl.file_size,
                'created_at': hl.created_at
            } for hl in hardlinks]

    def get_torrent_files_data_by_hash(self, hash_id: str) -> Dict[str, Any]:
        """根据hash获取torrent文件信息"""
        with db_manager.session() as session:
            download_info = session.query(DownloadStatus).filter_by(hash_id=hash_id).first()
            if not download_info:
                return {'error': '未找到下载记录'}

            torrent_files = session.query(TorrentFile).filter_by(torrent_hash=hash_id).all()

            hardlinks = session.query(Hardlink).filter_by(torrent_hash=hash_id).all()
            hardlink_paths = {h.original_file_path: {
                'id': h.id,
                'hardlink_path': h.hardlink_path
            } for h in hardlinks}

            files_data = []
            total_size = 0

            for torrent_file in torrent_files:
                file_path = torrent_file.file_path
                file_size = torrent_file.file_size or 0
                total_size += file_size

                file_type = torrent_file.file_type or 'other'
                if not file_type or file_type == 'other':
                    if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')):
                        file_type = 'video'
                    elif file_path.lower().endswith(('.srt', '.ass', '.ssa', '.vtt', '.sub')):
                        file_type = 'subtitle'
                    else:
                        file_type = 'other'

                hardlink_info = hardlink_paths.get(file_path)

                files_data.append({
                    'name': file_path.split('/')[-1],
                    'relative_path': file_path,
                    'size': file_size,
                    'type': file_type,
                    'has_hardlink': hardlink_info is not None,
                    'hardlink_info': hardlink_info
                })

            torrent_info = {
                'name': download_info.original_filename,
                'save_path': download_info.download_directory or '',
                'size': total_size,
                'progress': 1.0 if download_info.status == 'completed' else 0.0
            }

            return {
                'success': True,
                'torrent_info': torrent_info,
                'files': files_data
            }

    def get_hardlink_by_id(self, hardlink_id: int) -> Optional[Hardlink]:
        """根据ID获取硬链接（返回ORM对象）"""
        with db_manager.session() as session:
            return session.query(Hardlink).filter_by(id=hardlink_id).first()

    def delete_hardlink_by_id(self, hardlink_id: int) -> bool:
        """删除硬链接记录"""
        return self.delete(hardlink_id)

    def update_hardlink_path(self, hardlink_id: int, new_path: str) -> bool:
        """更新硬链接路径"""
        with db_manager.session() as session:
            hardlink = session.query(Hardlink).filter_by(id=hardlink_id).first()
            if hardlink:
                hardlink.hardlink_path = new_path
                return True
            return False

    def get_all_hardlinks(self) -> List[Dict[str, Any]]:
        """获取所有硬链接"""
        with db_manager.session() as session:
            hardlinks = session.query(Hardlink).order_by(Hardlink.created_at.desc()).all()

            return [{
                'id': hl.id,
                'anime_id': hl.anime_id,
                'torrent_hash': hl.torrent_hash,
                'original_file_path': hl.original_file_path,
                'hardlink_path': hl.hardlink_path,
                'file_size': hl.file_size,
                'created_at': hl.created_at
            } for hl in hardlinks]

    def get_download_history_paginated(
        self,
        page: int,
        per_page: int,
        search: str = '',
        sort_column: str = 'deleted_at',
        sort_order: str = 'desc'
    ) -> Dict[str, Any]:
        """获取分页的下载历史记录"""
        with db_manager.session() as session:
            query = session.query(DownloadHistory, AnimeInfo.media_type).outerjoin(
                AnimeInfo, DownloadHistory.anime_id == AnimeInfo.id
            )

            if search:
                search_pattern = f"%{search}%"
                query = query.filter(or_(
                    DownloadHistory.hash_id.like(search_pattern),
                    DownloadHistory.original_filename.like(search_pattern),
                    DownloadHistory.anime_title.like(search_pattern),
                    DownloadHistory.subtitle_group.like(search_pattern)
                ))

            if sort_column == 'media_type':
                if sort_order == 'desc':
                    query = query.order_by(AnimeInfo.media_type.desc())
                else:
                    query = query.order_by(AnimeInfo.media_type.asc())
            elif hasattr(DownloadHistory, sort_column):
                column = getattr(DownloadHistory, sort_column)
                if sort_order == 'desc':
                    query = query.order_by(column.desc())
                else:
                    query = query.order_by(column.asc())
            else:
                query = query.order_by(DownloadHistory.deleted_at.desc())

            total_count = query.count()
            total_pages = (total_count + per_page - 1) // per_page
            items = query.offset((page - 1) * per_page).limit(per_page).all()

            history = []
            for item, media_type in items:
                history.append({
                    'id': item.id,
                    'anime_id': item.anime_id,
                    'hash_id': item.hash_id,
                    'original_filename': item.original_filename,
                    'anime_title': item.anime_title,
                    'subtitle_group': item.subtitle_group,
                    'season': item.season,
                    'download_directory': item.download_directory,
                    'status': item.status,
                    'download_time': item.download_time,
                    'completion_time': item.completion_time,
                    'deleted_at': item.deleted_at,
                    'created_at': item.created_at,
                    'updated_at': item.updated_at,
                    'media_type': media_type or 'anime'
                })

            return {
                'history': history,
                'total_count': total_count,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page
            }

    def get_rss_processing_history(self, limit: int = 10) -> List[RssProcessingHistory]:
        """获取RSS处理历史"""
        with db_manager.session() as session:
            return session.query(RssProcessingHistory).order_by(
                RssProcessingHistory.created_at.desc()
            ).limit(limit).all()

    def get_rss_processing_history_by_id(self, history_id: int) -> Optional[RssProcessingHistory]:
        """根据ID获取RSS处理历史"""
        with db_manager.session() as session:
            return session.query(RssProcessingHistory).filter_by(id=history_id).first()

    def get_rss_processing_details(self, history_id: int) -> List[RssProcessingDetail]:
        """获取RSS处理详情"""
        with db_manager.session() as session:
            return session.query(RssProcessingDetail).filter_by(history_id=history_id).all()

    def delete_rss_processing_history(self, history_id: int) -> bool:
        """删除RSS处理历史"""
        with db_manager.session() as session:
            session.query(RssProcessingDetail).filter_by(history_id=history_id).delete()
            result = session.query(RssProcessingHistory).filter_by(id=history_id).delete()
            return result > 0

    def get_manual_upload_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取手动上传历史"""
        with db_manager.session() as session:
            records = session.query(ManualUploadHistory).order_by(
                ManualUploadHistory.created_at.desc()
            ).limit(limit).all()
            return [{
                'id': record.id,
                'upload_type': record.upload_type,
                'anime_title': record.anime_title,
                'subtitle_group': record.subtitle_group,
                'season': record.season,
                'category': record.category,
                'torrent_hash': record.torrent_hash,
                'upload_status': record.upload_status,
                'error_message': record.error_message,
                'created_at': record.created_at.isoformat() if record.created_at else None
            } for record in records]

    def get_rss_history_stats(self, history_id: int) -> Optional[Dict[str, Any]]:
        """获取RSS历史统计信息"""
        with db_manager.session() as session:
            record = session.query(RssProcessingHistory).filter_by(id=history_id).first()
            if not record:
                return None
            return {
                'items_found': record.items_found or 0,
                'items_attempted': record.items_attempted or 0,
                'items_processed': record.items_processed or 0,
                'status': record.status or 'unknown'
            }

    def get_rss_detail_stats(self, history_id: int) -> Dict[str, int]:
        """获取RSS详情统计（按状态分组）"""
        with db_manager.session() as session:
            details = session.query(RssProcessingDetail).filter_by(history_id=history_id).all()
            stats = {'success': 0, 'failed': 0, 'exists': 0, 'filtered': 0}
            for detail in details:
                status = detail.item_status or 'unknown'
                if status in stats:
                    stats[status] += 1
            return stats

    def get_rss_details_by_status(
        self, history_id: int, status: str
    ) -> List[Dict[str, Any]]:
        """获取指定状态的RSS详情"""
        with db_manager.session() as session:
            details = session.query(RssProcessingDetail).filter_by(
                history_id=history_id,
                item_status=status
            ).all()
            return [
                {
                    'item_title': d.item_title,
                    'status': d.item_status,
                    'error_message': d.failure_reason
                }
                for d in details
            ]

    def get_hardlink_attempts_stats(self) -> Dict[str, int]:
        """获取硬链接尝试统计"""
        with db_manager.session() as session:
            total = session.query(HardlinkAttempt).count()
            success = session.query(HardlinkAttempt).filter_by(success=1).count()
            failed = session.query(HardlinkAttempt).filter_by(success=0).count()
            return {
                'total': total,
                'success': success,
                'failed': failed
            }

    def get_hardlink_attempts_paginated(
        self,
        page: int,
        per_page: int,
        search: str = '',
        success_filter: bool = None
    ) -> Dict[str, Any]:
        """获取分页的硬链接尝试记录"""
        with db_manager.session() as session:
            query = session.query(HardlinkAttempt)

            if search:
                search_pattern = f"%{search}%"
                query = query.filter(or_(
                    HardlinkAttempt.original_file_path.like(search_pattern),
                    HardlinkAttempt.target_path.like(search_pattern),
                    HardlinkAttempt.torrent_hash.like(search_pattern)
                ))

            if success_filter is not None:
                query = query.filter(HardlinkAttempt.success == (1 if success_filter else 0))

            query = query.order_by(HardlinkAttempt.created_at.desc())

            total_count = query.count()
            total_pages = (total_count + per_page - 1) // per_page
            items = query.offset((page - 1) * per_page).limit(per_page).all()

            return {
                'data': items,
                'total_count': total_count,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page
            }
