"""
Subtitle repository module.

Contains the SubtitleRepository class for managing subtitle file records.
"""

import logging
from typing import Any

from src.core.domain.entities import SubtitleRecord
from src.infrastructure.database.models import SubtitleFile
from src.infrastructure.database.session import db_manager

logger = logging.getLogger(__name__)


class SubtitleRepository:
    """字幕文件仓库"""

    def _to_entity(self, row: SubtitleFile) -> SubtitleRecord:
        """将数据库行转换为实体"""
        return SubtitleRecord(
            id=row.id,
            anime_id=row.anime_id,
            video_file_path=row.video_file_path or '',
            subtitle_path=row.subtitle_path or '',
            original_name=row.original_name or '',
            language_tag=row.language_tag or '',
            subtitle_format=row.subtitle_format or '',
            source_archive=row.source_archive or '',
            match_method=row.match_method or 'ai',
            created_at=row.created_at,
            updated_at=row.updated_at
        )

    def _to_dict(self, row: SubtitleFile) -> dict[str, Any]:
        """将数据库行转换为字典"""
        return {
            'id': row.id,
            'anime_id': row.anime_id,
            'video_file_path': row.video_file_path or '',
            'subtitle_path': row.subtitle_path or '',
            'original_name': row.original_name or '',
            'language_tag': row.language_tag or '',
            'subtitle_format': row.subtitle_format or '',
            'source_archive': row.source_archive or '',
            'match_method': row.match_method or 'ai',
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'updated_at': row.updated_at.isoformat() if row.updated_at else None
        }

    def get_by_id(self, subtitle_id: int) -> SubtitleRecord | None:
        """根据ID获取字幕记录"""
        with db_manager.session() as session:
            subtitle = session.query(SubtitleFile).filter_by(id=subtitle_id).first()
            if subtitle:
                return self._to_entity(subtitle)
            return None

    def get_by_anime_id(self, anime_id: int) -> list[SubtitleRecord]:
        """根据anime ID获取字幕列表"""
        with db_manager.session() as session:
            subtitles = session.query(SubtitleFile).filter_by(
                anime_id=anime_id
            ).order_by(SubtitleFile.video_file_path, SubtitleFile.language_tag).all()
            return [self._to_entity(s) for s in subtitles]

    def get_by_anime_id_as_dict(self, anime_id: int) -> list[dict[str, Any]]:
        """根据anime ID获取字幕列表（返回字典）"""
        with db_manager.session() as session:
            subtitles = session.query(SubtitleFile).filter_by(
                anime_id=anime_id
            ).order_by(SubtitleFile.video_file_path, SubtitleFile.language_tag).all()
            return [self._to_dict(s) for s in subtitles]

    def get_by_video_path(self, video_file_path: str) -> list[SubtitleRecord]:
        """根据影片路径获取字幕列表"""
        with db_manager.session() as session:
            subtitles = session.query(SubtitleFile).filter_by(
                video_file_path=video_file_path
            ).order_by(SubtitleFile.language_tag).all()
            return [self._to_entity(s) for s in subtitles]

    def save(self, record: SubtitleRecord) -> int:
        """保存字幕记录"""
        with db_manager.session() as session:
            # 检查是否存在（同一视频和字幕路径）
            existing = session.query(SubtitleFile).filter_by(
                video_file_path=record.video_file_path,
                subtitle_path=record.subtitle_path
            ).first()

            if existing:
                # 更新现有记录
                existing.language_tag = record.language_tag
                existing.subtitle_format = record.subtitle_format
                existing.source_archive = record.source_archive
                existing.match_method = record.match_method
                session.flush()
                return existing.id

            # 创建新记录
            subtitle = SubtitleFile(
                anime_id=record.anime_id,
                video_file_path=record.video_file_path,
                subtitle_path=record.subtitle_path,
                original_name=record.original_name,
                language_tag=record.language_tag,
                subtitle_format=record.subtitle_format,
                source_archive=record.source_archive,
                match_method=record.match_method
            )
            session.add(subtitle)
            session.flush()
            logger.info(f'✅ 保存字幕记录: {record.subtitle_path}')
            return subtitle.id

    def save_batch(self, records: list[SubtitleRecord]) -> list[int]:
        """批量保存字幕记录"""
        saved_ids = []
        with db_manager.session() as session:
            for record in records:
                # 检查是否存在
                existing = session.query(SubtitleFile).filter_by(
                    video_file_path=record.video_file_path,
                    subtitle_path=record.subtitle_path
                ).first()

                if existing:
                    existing.language_tag = record.language_tag
                    existing.subtitle_format = record.subtitle_format
                    existing.source_archive = record.source_archive
                    existing.match_method = record.match_method
                    saved_ids.append(existing.id)
                else:
                    subtitle = SubtitleFile(
                        anime_id=record.anime_id,
                        video_file_path=record.video_file_path,
                        subtitle_path=record.subtitle_path,
                        original_name=record.original_name,
                        language_tag=record.language_tag,
                        subtitle_format=record.subtitle_format,
                        source_archive=record.source_archive,
                        match_method=record.match_method
                    )
                    session.add(subtitle)
                    session.flush()
                    saved_ids.append(subtitle.id)

            logger.info(f'✅ 批量保存 {len(saved_ids)} 条字幕记录')
        return saved_ids

    def delete(self, subtitle_id: int) -> bool:
        """删除字幕记录"""
        with db_manager.session() as session:
            result = session.query(SubtitleFile).filter_by(id=subtitle_id).delete()
            if result > 0:
                logger.info(f'✅ 删除字幕记录: id={subtitle_id}')
            return result > 0

    def delete_by_anime_id(self, anime_id: int) -> int:
        """删除指定动漫的所有字幕记录"""
        with db_manager.session() as session:
            result = session.query(SubtitleFile).filter_by(anime_id=anime_id).delete()
            if result > 0:
                logger.info(f'✅ 删除动漫 {anime_id} 的 {result} 条字幕记录')
            return result

    def delete_by_video_path(self, video_file_path: str) -> int:
        """删除指定影片的所有字幕记录"""
        with db_manager.session() as session:
            result = session.query(SubtitleFile).filter_by(
                video_file_path=video_file_path
            ).delete()
            if result > 0:
                logger.info(f'✅ 删除影片 {video_file_path} 的 {result} 条字幕记录')
            return result

    def count_by_anime_id(self, anime_id: int) -> int:
        """统计指定动漫的字幕数量"""
        with db_manager.session() as session:
            return session.query(SubtitleFile).filter_by(anime_id=anime_id).count()

    def exists(self, video_file_path: str, subtitle_path: str) -> bool:
        """检查字幕记录是否存在"""
        with db_manager.session() as session:
            return session.query(SubtitleFile).filter_by(
                video_file_path=video_file_path,
                subtitle_path=subtitle_path
            ).first() is not None


# 全局实例
subtitle_repository = SubtitleRepository()
