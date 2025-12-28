"""
Anime repository module.

Contains the AnimeRepository class implementing IAnimeRepository interface.
"""

import logging
import re
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from src.core.domain.entities import AnimeInfo as AnimeInfoEntity
from src.core.domain.value_objects import (
    AnimeTitle,
    Category,
    MediaType,
    SeasonInfo,
    SubtitleGroup,
)
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

    def _detect_season_from_title(self, title: str) -> int:
        """从标题中检测季数

        支持格式:
        - 第X季 / 第二季 (中文)
        - Season X / S2
        - 动漫名称 2 (标题后数字)
        - II, III, IV (罗马数字)
        - 2nd Season, 3rd Season

        Args:
            title: RSS 标题

        Returns:
            检测到的季数，默认返回 1
        """
        detected_season = 1  # 默认为第一季

        # 中文数字转阿拉伯数字的映射
        chinese_to_number = {
            '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
            '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
            '十': 10, '百': 100
        }

        def chinese_number_to_arabic(chinese_num: str) -> int:
            if not chinese_num:
                return 1

            result = 0
            temp = 0

            for char in chinese_num:
                if char == '十':
                    if temp == 0:
                        temp = 1  # 处理 "十" 开头的情况
                    result += temp * 10
                    temp = 0
                elif char == '百':
                    if temp == 0:
                        temp = 1  # 处理 "百" 开头的情况
                    result += temp * 100
                    temp = 0
                elif char in chinese_to_number:
                    temp = chinese_to_number[char]

            result += temp
            return result or 1

        # 检测模式1: "第X季" 格式（中文数字或阿拉伯数字）
        chinese_season_pattern = r'第([一二三四五六七八九十百]+|[0-9]+)季'
        chinese_season_match = re.search(chinese_season_pattern, title)

        if chinese_season_match:
            season_str = chinese_season_match.group(1)
            if re.search(r'[0-9]+', season_str):
                detected_season = int(season_str)
            else:
                detected_season = chinese_number_to_arabic(season_str)

        # 检测模式2: "动漫名称 2" 格式（动漫名称后空格加数字）
        title_number_pattern = (
            r'(?:[\u4e00-\u9fa5]+\s+|[a-zA-Z]+\s+)([2-9]|[1-9][0-9])'
            r'(?:\s*(?:$|[\[\]\/\-\|])|(?:\s+(?:Season|season|期|季)))'
        )
        title_number_match = re.search(title_number_pattern, title)

        # 排除已知的误判模式（数字后跟着单词的情况）
        exclude_pattern = r'\b[0-9]+\s+[a-z]+\b'
        has_excluded_pattern = re.search(exclude_pattern, title, re.IGNORECASE)

        # 排除范围格式（如 "17-26"、"1~12" 等），这些通常是话数范围而不是季数
        range_pattern = r'\b\d+[-~]\d+\b'
        has_range_pattern = re.search(range_pattern, title)

        if (not chinese_season_match and title_number_match
                and not has_excluded_pattern and not has_range_pattern):
            # 额外检查：确保这不是动画名称的一部分
            number_index = title.find(title_number_match.group(1))
            after_number = title[number_index + len(title_number_match.group(1)):]

            # 如果数字后面紧跟着小写字母（如 "8 gou"）或连字符/波浪号，则跳过
            if (not re.search(r'^\s+[a-z]', after_number)
                    and not re.search(r'^[-~]', after_number)):
                detected_season = int(title_number_match.group(1))

        # 检测模式3: "Season X" 格式（需要前后有空格或边界）
        season_pattern = r'(?:^|\s|[\[\(])Season\s*([0-9]+)(?:\s|[\]\)]|$)'
        season_match = re.search(season_pattern, title, re.IGNORECASE)

        if not chinese_season_match and not title_number_match and season_match:
            detected_season = int(season_match.group(1))

        # 检测模式4: "SX" 格式（需要前后有空格或特定字符）
        s_pattern = r'(?:^|\s|[\[\(])S([0-9]{1,2})(?:\s|[\]\)]|E[0-9]|$)'
        s_match = re.search(s_pattern, title)

        if (not chinese_season_match and not title_number_match
                and not season_match and s_match):
            detected_season = int(s_match.group(1))

        # 检测模式5: 罗马数字格式 "II", "III", "IV" 等
        roman_pattern = r'(?:^|\s|[\[\(])(II+|III+|IV|V|VI+|VII+|VIII+|IX|X+)(?:\s|[\]\)]|$)'
        roman_match = re.search(roman_pattern, title)

        if (not chinese_season_match and not title_number_match
                and not season_match and not s_match and roman_match):
            roman_numerals = {
                'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
                'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10
            }
            detected_season = roman_numerals.get(roman_match.group(1), 1)

        # 检测模式6: "第2期"、"第二期" 格式
        period_pattern = r'第([一二三四五六七八九十百]+|[0-9]+)期'
        period_match = re.search(period_pattern, title)

        if not chinese_season_match and not title_number_match and period_match:
            period_str = period_match.group(1)
            if re.search(r'[0-9]+', period_str):
                detected_season = int(period_str)
            else:
                detected_season = chinese_number_to_arabic(period_str)

        # 检测模式7: "2nd Season", "3rd Season" 等
        ordinal_pattern = r'([0-9]+)(?:st|nd|rd|th)\s+Season'
        ordinal_match = re.search(ordinal_pattern, title, re.IGNORECASE)

        if (not chinese_season_match and not title_number_match
                and not season_match and ordinal_match):
            detected_season = int(ordinal_match.group(1))

        return detected_season

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

    def _to_dict(self, row: AnimeInfo) -> dict[str, Any]:
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

    def get_by_id(self, anime_id: int) -> AnimeInfoEntity | None:
        """根据ID查找动漫信息"""
        with db_manager.session() as session:
            anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
            if anime:
                return self._to_entity(anime)
            return None


    def get_by_core_info(
        self,
        title: str,
        subtitle_group: str | None = None,
        season: int | None = None
    ) -> AnimeInfoEntity | None:
        """根据动漫核心信息查找（季数+短标题+字幕组三要素匹配）

        匹配逻辑:
        1. 从 RSS 标题检测季数
        2. 按季数过滤候选动漫
        3. 检查标题是否包含数据库中的 short_title 或 long_title
        4. 检查标题是否包含字幕组名称

        Args:
            title: RSS 标题
            subtitle_group: 字幕组名称（可选，优先使用）
            season: 季数（可选，若不提供则从标题检测）

        Returns:
            匹配的动漫实体，未找到返回 None
        """
        # 1. 从 RSS 标题检测季数
        detected_season = season if season is not None else self._detect_season_from_title(title)

        # 2. 标准化引号（使用已有的 _normalize_quotes 方法）
        clean_title = self._normalize_quotes(title).lower()

        with db_manager.session() as session:
            # 3. 先按季数过滤
            candidates = session.query(AnimeInfo).filter_by(season=detected_season).all()

            if not candidates:
                logger.debug(f'📭 未找到季数 {detected_season} 的候选动漫')
                return None

            # 4. 检查标题和字幕组双重匹配
            for anime in candidates:
                # 标题匹配检查
                short_title = self._normalize_quotes(anime.short_title or '').lower()
                long_title = self._normalize_quotes(anime.long_title or '').lower()

                title_match = (
                    (short_title and short_title in clean_title) or
                    (long_title and long_title in clean_title)
                )

                if not title_match:
                    continue

                # 字幕组匹配检查
                anime_subtitle_group = (anime.subtitle_group or '').lower()
                subtitle_group_match = (
                    anime_subtitle_group and anime_subtitle_group in clean_title
                )

                # 三要素全部匹配
                if title_match and subtitle_group_match:
                    logger.info(
                        f'✅ 匹配成功: {anime.short_title} S{anime.season} '
                        f'[{anime.subtitle_group}]'
                    )
                    return self._to_entity(anime)

            logger.debug(f'📭 未找到匹配: 标题="{title[:50]}..." 季数={detected_season}')
            return None

    def find_exact_match(
        self,
        short_title: str,
        subtitle_group: str,
        season: int
    ) -> AnimeInfoEntity | None:
        """根据短标题、字幕组、季数精确匹配动漫

        用于 AI 处理后检查是否已存在相同动漫，防止重复创建。

        Args:
            short_title: 短标题（精确匹配，不区分大小写）
            subtitle_group: 字幕组（精确匹配，不区分大小写）
            season: 季数（精确匹配）

        Returns:
            匹配的动漫实体，未找到返回 None
        """
        if not short_title or not subtitle_group:
            return None

        # 标准化引号
        clean_short_title = self._normalize_quotes(short_title).lower()
        clean_subtitle_group = self._normalize_quotes(subtitle_group).lower()

        with db_manager.session() as session:
            # 获取相同季数的所有动漫
            candidates = session.query(AnimeInfo).filter_by(season=season).all()

            for anime in candidates:
                db_short_title = self._normalize_quotes(anime.short_title or '').lower()
                db_subtitle_group = self._normalize_quotes(anime.subtitle_group or '').lower()

                # 精确匹配（不区分大小写）
                if db_short_title == clean_short_title and db_subtitle_group == clean_subtitle_group:
                    logger.info(
                        f'🔍 找到精确匹配: {anime.short_title} S{anime.season} '
                        f'[{anime.subtitle_group}] (ID={anime.id})'
                    )
                    return self._to_entity(anime)

            return None

    def get_all(self, limit: int = 100, offset: int = 0) -> list[AnimeInfoEntity]:
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

            db_anime.updated_at = datetime.now(UTC)
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

    def get_anime_by_title(self, title: str) -> dict[str, Any] | None:
        """根据标题查找动漫信息（遗留方法，返回字典）"""
        with db_manager.session() as session:
            anime = session.query(AnimeInfo).filter_by(original_title=title).first()
            if anime:
                return self._to_dict(anime)
            return None

    def get_anime_by_id(self, anime_id: int) -> dict[str, Any] | None:
        """根据ID查找动漫信息（遗留方法，返回字典）"""
        with db_manager.session() as session:
            anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
            if anime:
                return self._to_dict(anime)
            return None

    def get_anime_by_core_info(self, title: str) -> dict[str, Any] | None:
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
                anime.updated_at = datetime.now(UTC)
                return True
            return False

    def insert_patterns(self, anime_id: int, patterns: dict[str, str]) -> int:
        """插入或更新正则模式"""
        with db_manager.session() as session:
            existing = session.query(AnimePattern).filter_by(anime_id=anime_id).first()

            if existing:
                for key, value in patterns.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.now(UTC)
                return existing.id
            else:
                pattern = AnimePattern(anime_id=anime_id, **patterns)
                session.add(pattern)
                session.flush()
                return pattern.id

    def get_patterns(self, anime_id: int) -> dict[str, str] | None:
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
            cutoff = datetime.now(UTC) - timedelta(hours=hours)
            return session.query(AnimeInfo).filter(AnimeInfo.created_at >= cutoff).count()

    def get_recent_anime(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取最近新增动漫"""
        with db_manager.session() as session:
            anime_list = session.query(AnimeInfo).order_by(
                AnimeInfo.created_at.desc()
            ).limit(limit).all()
            return [self._to_dict(anime) for anime in anime_list]

    def get_patterns_by_anime_id(self, anime_id: int) -> dict[str, Any] | None:
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
