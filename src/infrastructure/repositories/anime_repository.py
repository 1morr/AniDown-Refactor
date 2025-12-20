"""
Anime repository module.

Contains the AnimeRepository class implementing IAnimeRepository interface.
"""

import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from src.core.domain.entities import AnimeInfo as AnimeInfoEntity
from src.core.domain.value_objects import (
    AnimeTitle,
    Category,
    MediaType,
    SeasonInfo,
    SubtitleGroup,
)
from src.core.exceptions import DatabaseError
from src.core.interfaces.repositories import IAnimeRepository
from src.infrastructure.database.models import AnimeInfo, AnimePattern
from src.infrastructure.database.session import db_manager

logger = logging.getLogger(__name__)


class AnimeRepository(IAnimeRepository):
    """动漫信息仓库"""

    def _normalize_quotes(self, text: str) -> str:
        """标准化引号字符"""
        if not text:
            return text
        text = text.replace('\uff02', '"').replace('\u201c', '"').replace('\u201d', '"')
        text = text.replace('\u2018', "'").replace('\u2019', "'").replace('\uff07', "'")
        return text

    def _to_entity(self, row: AnimeInfo) -> AnimeInfoEntity:
        """将数据库行转换为实体"""
        return AnimeInfoEntity(
            id=row.id,
            title=AnimeTitle(
                original=row.original_title or '',
                short=row.short_title or '',
                full=row.long_title
            ),
            subtitle_group=SubtitleGroup(name=row.subtitle_group or '') if row.subtitle_group else None,
            season=SeasonInfo(
                number=row.season or 1,
                category=Category(row.category) if row.category else Category.TV
            ),
            category=Category(row.category) if row.category else Category.TV,
            media_type=MediaType(row.media_type) if row.media_type else MediaType.ANIME,
            tvdb_id=row.tvdb_id,
            created_at=row.created_at,
            updated_at=row.updated_at
        )

    def _to_dict(self, row: AnimeInfo) -> Dict[str, Any]:
        """将数据库行转换为字典"""
        return {
            'id': row.id,
            'original_title': row.original_title,
            'short_title': row.short_title,
            'long_title': row.long_title,
            'subtitle_group': row.subtitle_group,
            'season': row.season,
            'category': row.category,
            'media_type': row.media_type,
            'tvdb_id': row.tvdb_id,
            'created_at': row.created_at,
            'updated_at': row.updated_at
        }

    # ==================== IAnimeRepository Interface ====================

    def get_by_id(self, anime_id: int) -> Optional[AnimeInfoEntity]:
        """根据ID查找动漫信息"""
        with db_manager.session() as session:
            anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
            if anime:
                return self._to_entity(anime)
            return None

    def get_by_title(self, title: str) -> Optional[AnimeInfoEntity]:
        """根据标题查找动漫信息（模糊匹配）"""
        with db_manager.session() as session:
            anime = session.query(AnimeInfo).filter_by(original_title=title).first()
            if anime:
                return self._to_entity(anime)
            return None

    def get_by_core_info(
        self,
        title: str,
        subtitle_group: Optional[str] = None,
        season: Optional[int] = None
    ) -> Optional[AnimeInfoEntity]:
        """根据动漫核心信息查找动漫信息"""
        clean_title = self._clean_title_for_matching(title)

        with db_manager.session() as session:
            # 1. 精确匹配
            exact_match = session.query(AnimeInfo).filter(
                or_(
                    AnimeInfo.original_title == title,
                    AnimeInfo.short_title == clean_title,
                    AnimeInfo.long_title == title
                )
            ).first()

            if exact_match:
                return self._to_entity(exact_match)

            # 2. 模糊匹配
            all_anime = session.query(AnimeInfo).all()
            best_match = None
            best_score = 0.0

            for anime in all_anime:
                scores = []

                if anime.original_title:
                    scores.append(self._calculate_similarity(
                        clean_title, self._clean_title_for_matching(anime.original_title)))
                if anime.short_title:
                    scores.append(self._calculate_similarity(
                        clean_title, self._clean_title_for_matching(anime.short_title)))
                if anime.long_title:
                    scores.append(self._calculate_similarity(
                        clean_title, self._clean_title_for_matching(anime.long_title)))

                if scores:
                    max_score = max(scores)
                    if max_score > best_score and max_score > 0.8:
                        best_score = max_score
                        best_match = anime

            if best_match:
                return self._to_entity(best_match)

            return None

    def get_all(self, limit: int = 100, offset: int = 0) -> List[AnimeInfoEntity]:
        """获取所有动漫（分页）"""
        with db_manager.session() as session:
            anime_list = session.query(AnimeInfo).order_by(
                AnimeInfo.created_at.desc()
            ).offset(offset).limit(limit).all()
            return [self._to_entity(anime) for anime in anime_list]

    def save(self, anime: AnimeInfoEntity) -> int:
        """保存动漫信息"""
        original_title = anime.title.original if anime.title else ''
        short_title = anime.title.short if anime.title else None
        long_title = anime.title.full if anime.title else None
        subtitle_group = anime.subtitle_group.name if anime.subtitle_group else None
        season = anime.season_number
        category = anime.category.value if anime.category else 'tv'
        media_type = anime.media_type.value if anime.media_type else 'anime'

        original_title = self._normalize_quotes(original_title) if original_title else None
        short_title = self._normalize_quotes(short_title) if short_title else None
        long_title = self._normalize_quotes(long_title) if long_title else None

        with db_manager.session() as session:
            db_anime = AnimeInfo(
                original_title=original_title,
                short_title=short_title,
                long_title=long_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                media_type=media_type,
                tvdb_id=anime.tvdb_id
            )
            session.add(db_anime)
            session.flush()
            return db_anime.id

    def update(self, anime: AnimeInfoEntity) -> bool:
        """更新动漫信息"""
        if not anime.id:
            return False

        with db_manager.session() as session:
            db_anime = session.query(AnimeInfo).filter_by(id=anime.id).first()
            if not db_anime:
                return False

            if anime.title:
                db_anime.original_title = self._normalize_quotes(anime.title.original)
                db_anime.short_title = self._normalize_quotes(anime.title.short) if anime.title.short else None
                db_anime.long_title = self._normalize_quotes(anime.title.full) if anime.title.full else None

            if anime.subtitle_group:
                db_anime.subtitle_group = anime.subtitle_group.name

            if anime.season:
                db_anime.season = anime.season.number

            if anime.category:
                db_anime.category = anime.category.value

            if anime.media_type:
                db_anime.media_type = anime.media_type.value

            if anime.tvdb_id is not None:
                db_anime.tvdb_id = anime.tvdb_id

            db_anime.updated_at = datetime.now(timezone.utc)
            return True

    def delete(self, anime_id: int) -> bool:
        """删除动漫信息"""
        with db_manager.session() as session:
            result = session.query(AnimeInfo).filter_by(id=anime_id).delete()
            return result > 0

    # ==================== Legacy Methods ====================

    def insert_anime_info(
        self,
        original_title: str,
        short_title: str = None,
        long_title: str = None,
        subtitle_group: str = None,
        season: int = 1,
        category: str = 'tv',
        media_type: str = 'anime'
    ) -> int:
        """插入动漫信息（遗留方法）"""
        original_title = self._normalize_quotes(original_title) if original_title else None
        short_title = self._normalize_quotes(short_title) if short_title else None
        long_title = self._normalize_quotes(long_title) if long_title else None

        with db_manager.session() as session:
            anime = AnimeInfo(
                original_title=original_title,
                short_title=short_title,
                long_title=long_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                media_type=media_type
            )
            session.add(anime)
            session.flush()
            return anime.id

    def get_anime_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """根据标题查找动漫信息（遗留方法，返回字典）"""
        with db_manager.session() as session:
            anime = session.query(AnimeInfo).filter_by(original_title=title).first()
            if anime:
                return self._to_dict(anime)
            return None

    def get_anime_by_id(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """根据ID查找动漫信息（遗留方法，返回字典）"""
        with db_manager.session() as session:
            anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
            if anime:
                return self._to_dict(anime)
            return None

    def get_anime_by_core_info(self, title: str) -> Optional[Dict[str, Any]]:
        """根据动漫核心信息查找动漫信息（遗留方法，返回字典）"""
        entity = self.get_by_core_info(title)
        if entity:
            return {
                'id': entity.id,
                'original_title': entity.title.original if entity.title else '',
                'short_title': entity.title.short if entity.title else '',
                'long_title': entity.title.full if entity.title else None,
                'subtitle_group': entity.subtitle_group.name if entity.subtitle_group else None,
                'season': entity.season.number if entity.season else 1,
                'category': entity.category.value if entity.category else 'tv',
                'media_type': entity.media_type.value if entity.media_type else 'anime',
                'tvdb_id': entity.tvdb_id
            }
        return None

    def _clean_title_for_matching(self, title: str) -> str:
        """清理标题用于匹配"""
        if not title:
            return ''

        # 移除常见的标记
        title = re.sub(r'\[.*?\]', '', title)  # 移除方括号内容
        title = re.sub(r'\(.*?\)', '', title)  # 移除圆括号内容
        title = re.sub(r'【.*?】', '', title)  # 移除中文方括号内容
        title = re.sub(r'第\d+季', '', title)  # 移除季数标记
        title = re.sub(r'Season\s*\d+', '', title, flags=re.IGNORECASE)
        title = re.sub(r'S\d+', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s+', ' ', title)  # 合并多个空格

        return title.strip()

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """计算两个字符串的相似度"""
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def update_tvdb_id(self, anime_id: int, tvdb_id: int) -> bool:
        """更新TVDB ID"""
        with db_manager.session() as session:
            anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
            if anime:
                anime.tvdb_id = tvdb_id
                anime.updated_at = datetime.now(timezone.utc)
                return True
            return False

    def insert_patterns(self, anime_id: int, patterns: Dict[str, str]) -> int:
        """插入或更新正则模式"""
        with db_manager.session() as session:
            existing = session.query(AnimePattern).filter_by(anime_id=anime_id).first()

            if existing:
                for key, value in patterns.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.now(timezone.utc)
                return existing.id
            else:
                pattern = AnimePattern(anime_id=anime_id, **patterns)
                session.add(pattern)
                session.flush()
                return pattern.id

    def get_patterns(self, anime_id: int) -> Optional[Dict[str, str]]:
        """获取正则模式"""
        with db_manager.session() as session:
            pattern = session.query(AnimePattern).filter_by(anime_id=anime_id).first()
            if pattern:
                return {
                    'title_group_regex': pattern.title_group_regex,
                    'full_title_regex': pattern.full_title_regex,
                    'short_title_regex': pattern.short_title_regex,
                    'episode_regex': pattern.episode_regex,
                    'quality_regex': pattern.quality_regex,
                    'special_tags_regex': pattern.special_tags_regex,
                    'audio_source_regex': pattern.audio_source_regex,
                    'source_regex': pattern.source_regex,
                    'video_codec_regex': pattern.video_codec_regex,
                    'subtitle_type_regex': pattern.subtitle_type_regex,
                    'video_format_regex': pattern.video_format_regex
                }
            return None

    def count_all(self) -> int:
        """统计所有动漫数量"""
        with db_manager.session() as session:
            return session.query(AnimeInfo).count()

    def count_recent(self, hours: int = 24) -> int:
        """统计最近新增动漫数量"""
        from datetime import timedelta
        with db_manager.session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            return session.query(AnimeInfo).filter(AnimeInfo.created_at >= cutoff).count()

    def get_recent_anime(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近新增动漫"""
        with db_manager.session() as session:
            anime_list = session.query(AnimeInfo).order_by(
                AnimeInfo.created_at.desc()
            ).limit(limit).all()
            return [self._to_dict(anime) for anime in anime_list]

    def get_patterns_by_anime_id(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """获取动漫的正则模式对象"""
        with db_manager.session() as session:
            pattern = session.query(AnimePattern).filter_by(anime_id=anime_id).first()
            if pattern:
                return {
                    'id': pattern.id,
                    'anime_id': pattern.anime_id,
                    'title_group_regex': pattern.title_group_regex,
                    'full_title_regex': pattern.full_title_regex,
                    'short_title_regex': pattern.short_title_regex,
                    'episode_regex': pattern.episode_regex,
                    'quality_regex': pattern.quality_regex,
                    'special_tags_regex': pattern.special_tags_regex,
                    'audio_source_regex': pattern.audio_source_regex,
                    'source_regex': pattern.source_regex,
                    'video_codec_regex': pattern.video_codec_regex,
                    'subtitle_type_regex': pattern.subtitle_type_regex,
                    'video_format_regex': pattern.video_format_regex,
                    'created_at': pattern.created_at,
                    'updated_at': pattern.updated_at
                }
            return None
