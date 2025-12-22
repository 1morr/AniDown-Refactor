"""
Database models module.

Contains SQLAlchemy ORM models for the AniDown application.
"""

from sqlalchemy import (
    Column, Integer, String, Text, Float, ForeignKey,
    TIMESTAMP, UniqueConstraint, Index, func
)
from sqlalchemy.orm import declarative_base, relationship

from src.core.utils.timezone_utils import get_utc_now

Base = declarative_base()


class AnimeInfo(Base):
    """动漫信息表"""

    __tablename__ = 'anime_info'

    id = Column(Integer, primary_key=True, autoincrement=True)
    original_title = Column(Text, nullable=False)
    short_title = Column(Text)
    long_title = Column(Text)
    subtitle_group = Column(Text)
    season = Column(Integer, default=1)
    category = Column(Text, default='tv')  # tv: 剧集, movie: 电影
    media_type = Column(Text, default='anime')  # anime: 动漫, live_action: 真人
    tvdb_id = Column(Integer, default=None, nullable=True)
    created_at = Column(TIMESTAMP, default=get_utc_now)
    updated_at = Column(TIMESTAMP, default=get_utc_now, onupdate=get_utc_now)

    # 关系
    patterns = relationship('AnimePattern', back_populates='anime', cascade='all, delete-orphan')
    downloads = relationship('DownloadStatus', back_populates='anime')
    hardlinks = relationship('Hardlink', back_populates='anime')
    hardlink_attempts = relationship('HardlinkAttempt', back_populates='anime')
    download_history = relationship('DownloadHistory', back_populates='anime')
    subtitles = relationship('SubtitleFile', back_populates='anime', cascade='all, delete-orphan')

    __table_args__ = (
        Index('idx_anime_title', 'original_title'),
    )

    def __repr__(self):
        return f"<AnimeInfo(id={self.id}, title='{self.short_title or self.original_title}', season={self.season})>"


class AnimePattern(Base):
    """动漫正则模式表"""

    __tablename__ = 'anime_patterns'

    id = Column(Integer, primary_key=True, autoincrement=True)
    anime_id = Column(Integer, ForeignKey('anime_info.id'), nullable=False)
    title_group_regex = Column(Text)
    full_title_regex = Column(Text)
    short_title_regex = Column(Text)
    episode_regex = Column(Text)
    quality_regex = Column(Text)
    special_tags_regex = Column(Text)
    audio_source_regex = Column(Text)
    source_regex = Column(Text)
    video_codec_regex = Column(Text)
    subtitle_type_regex = Column(Text)
    video_format_regex = Column(Text)
    created_at = Column(TIMESTAMP, default=get_utc_now)
    updated_at = Column(TIMESTAMP, default=get_utc_now, onupdate=get_utc_now)

    # 关系
    anime = relationship('AnimeInfo', back_populates='patterns')

    def __repr__(self):
        return f'<AnimePattern(id={self.id}, anime_id={self.anime_id})>'


class DownloadStatus(Base):
    """下载状态表"""

    __tablename__ = 'download_status'

    id = Column(Integer, primary_key=True, autoincrement=True)
    anime_id = Column(Integer, ForeignKey('anime_info.id'), nullable=True)
    hash_id = Column(Text, unique=True, nullable=False)
    original_filename = Column(Text, nullable=False)
    anime_title = Column(Text)
    subtitle_group = Column(Text)
    season = Column(Integer)
    download_directory = Column(Text)
    status = Column(Text, default='pending')  # pending, downloading, completed, failed, missing
    download_time = Column(TIMESTAMP)
    completion_time = Column(TIMESTAMP)
    is_multi_season = Column(Integer, default=0)  # 0: 单季, 1: 多季
    download_method = Column(Text, default='fixed_rss')  # fixed_rss, manual_magnet, manual_torrent, rss_ai, rss_manual
    requires_tvdb = Column(Integer, default=0)  # 0: 不使用TVDB, 1: 使用TVDB
    created_at = Column(TIMESTAMP, default=get_utc_now)
    updated_at = Column(TIMESTAMP, default=get_utc_now, onupdate=get_utc_now)

    # 关系
    anime = relationship('AnimeInfo', back_populates='downloads')

    __table_args__ = (
        Index('idx_download_hash', 'hash_id'),
    )

    def __repr__(self):
        return f"<DownloadStatus(id={self.id}, hash='{self.hash_id[:8]}...', status='{self.status}')>"


class TorrentFile(Base):
    """Torrent文件表"""

    __tablename__ = 'torrent_files'

    id = Column(Integer, primary_key=True, autoincrement=True)
    anime_id = Column(Integer, ForeignKey('anime_info.id'), nullable=True)
    torrent_hash = Column(Text, nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    file_type = Column(Text)
    created_at = Column(TIMESTAMP, default=get_utc_now)

    # 关系
    anime = relationship('AnimeInfo')

    __table_args__ = (
        UniqueConstraint('torrent_hash', 'file_path', name='uq_torrent_file'),
        Index('idx_torrent_files_hash', 'torrent_hash'),
        Index('idx_torrent_files_anime', 'anime_id'),
    )

    def __repr__(self):
        return f"<TorrentFile(id={self.id}, hash='{self.torrent_hash[:8]}...', file='{self.file_path}')>"


class Hardlink(Base):
    """硬链接表"""

    __tablename__ = 'hardlinks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    anime_id = Column(Integer, ForeignKey('anime_info.id'), nullable=True)
    torrent_hash = Column(Text)
    original_file_path = Column(Text, nullable=False)
    hardlink_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    created_at = Column(TIMESTAMP, default=get_utc_now)
    updated_at = Column(TIMESTAMP, default=get_utc_now, onupdate=get_utc_now)

    # 关系
    anime = relationship('AnimeInfo', back_populates='hardlinks')

    __table_args__ = (
        UniqueConstraint('original_file_path', 'hardlink_path', name='uq_hardlink'),
        Index('idx_hardlinks_original', 'original_file_path'),
        Index('idx_hardlinks_hardlink', 'hardlink_path'),
        Index('idx_hardlinks_anime', 'anime_id'),
    )

    def __repr__(self):
        return f"<Hardlink(id={self.id}, original='{self.original_file_path}')>"


class HardlinkAttempt(Base):
    """硬链接尝试记录表"""

    __tablename__ = 'hardlink_attempts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    anime_id = Column(Integer, ForeignKey('anime_info.id'), nullable=True)
    torrent_hash = Column(Text)
    original_file_path = Column(Text, nullable=False)
    target_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    file_type = Column(Text)
    success = Column(Integer, default=0)  # 0: 失败, 1: 成功
    failure_reason = Column(Text)
    link_method = Column(Text)
    created_at = Column(TIMESTAMP, default=get_utc_now)

    # 关系
    anime = relationship('AnimeInfo', back_populates='hardlink_attempts')

    __table_args__ = (
        Index('idx_hardlink_attempts_anime', 'anime_id'),
        Index('idx_hardlink_attempts_torrent', 'torrent_hash'),
        Index('idx_hardlink_attempts_success', 'success'),
    )

    def __repr__(self):
        return f'<HardlinkAttempt(id={self.id}, success={self.success})>'


class RssProcessingHistory(Base):
    """RSS处理历史表"""

    __tablename__ = 'rss_processing_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rss_url = Column(Text, nullable=False)
    status = Column(Text, default='processing')
    items_found = Column(Integer, default=0)
    items_attempted = Column(Integer, default=0)
    items_processed = Column(Integer, default=0)
    batch_feeds_processed = Column(Integer, default=0)  # 批处理模式下已处理的feed数量
    error_message = Column(Text)
    triggered_by = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, default=get_utc_now)
    completed_at = Column(TIMESTAMP)

    # 关系
    details = relationship('RssProcessingDetail', back_populates='history', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<RssProcessingHistory(id={self.id}, status='{self.status}')>"


class RssProcessingDetail(Base):
    """RSS处理详情表"""

    __tablename__ = 'rss_processing_details'

    id = Column(Integer, primary_key=True, autoincrement=True)
    history_id = Column(Integer, ForeignKey('rss_processing_history.id'), nullable=False)
    item_title = Column(Text, nullable=False)
    item_status = Column(Text, nullable=False)
    failure_reason = Column(Text)
    created_at = Column(TIMESTAMP, default=func.current_timestamp())

    # 关系
    history = relationship('RssProcessingHistory', back_populates='details')

    __table_args__ = (
        Index('idx_rss_details_history', 'history_id'),
    )

    def __repr__(self):
        return f"<RssProcessingDetail(id={self.id}, history_id={self.history_id}, status='{self.item_status}')>"


class ManualUploadHistory(Base):
    """手动上传历史表"""

    __tablename__ = 'manual_upload_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    upload_type = Column(Text, nullable=False)  # 'torrent' or 'magnet'
    anime_title = Column(Text, nullable=False)
    subtitle_group = Column(Text)
    season = Column(Integer, default=1)
    category = Column(Text, default='tv')
    torrent_hash = Column(Text)
    upload_status = Column(Text, default='success')  # 'success', 'failed'
    error_message = Column(Text)
    created_at = Column(TIMESTAMP, default=func.current_timestamp())

    def __repr__(self):
        return f"<ManualUploadHistory(id={self.id}, type='{self.upload_type}', status='{self.upload_status}')>"


class DownloadHistory(Base):
    """下载历史表（记录所有下载，不会被删除）"""

    __tablename__ = 'download_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    anime_id = Column(Integer, ForeignKey('anime_info.id'), nullable=True)
    hash_id = Column(Text, nullable=False)
    original_filename = Column(Text, nullable=False)
    anime_title = Column(Text)
    subtitle_group = Column(Text)
    season = Column(Integer)
    download_directory = Column(Text)
    status = Column(Text, default='pending')
    download_time = Column(TIMESTAMP)
    completion_time = Column(TIMESTAMP)
    is_multi_season = Column(Integer, default=0)  # 0: 单季, 1: 多季
    download_method = Column(Text, default='fixed_rss')  # 下载方式
    deleted_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, default=func.current_timestamp(), onupdate=func.current_timestamp())

    # 关系
    anime = relationship('AnimeInfo', back_populates='download_history')

    __table_args__ = (
        Index('idx_download_history_hash', 'hash_id'),
        Index('idx_download_history_deleted', 'deleted_at'),
    )

    def __repr__(self):
        return f"<DownloadHistory(id={self.id}, hash='{self.hash_id[:8]}...', status='{self.status}')>"


class SqlQueryHistory(Base):
    """SQL查询历史表"""

    __tablename__ = 'sql_query_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, nullable=False)
    query_type = Column(Text, default='select')  # select, insert, update, delete, other
    execution_time = Column(Float)  # 执行时间（秒）
    rows_affected = Column(Integer)  # 影响的行数
    success = Column(Integer, default=1)  # 0: 失败, 1: 成功
    error_message = Column(Text)
    created_at = Column(TIMESTAMP, default=func.current_timestamp())

    __table_args__ = (
        Index('idx_sql_history_created', 'created_at'),
        Index('idx_sql_history_type', 'query_type'),
    )

    def __repr__(self):
        return f"<SqlQueryHistory(id={self.id}, type='{self.query_type}', success={self.success})>"


class AIKeyUsageLog(Base):
    """AI Key 使用日志表"""

    __tablename__ = 'ai_key_usage_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    purpose = Column(Text, nullable=False)  # title_parse, multi_file_rename
    key_id = Column(Text, nullable=False)   # key 的哈希 ID（不存储原始 key）
    key_name = Column(Text)                 # key 名称（用户自定义）
    model = Column(Text)                    # 使用的 AI 模型名称
    hash_id = Column(Text)                  # 相关 torrent 的 hash（可选）
    anime_title = Column(Text)              # 关联的动漫标题（用于统计哪些项目使用了此 Key）
    context_summary = Column(Text)          # 简短上下文描述（如文件名）
    success = Column(Integer, default=1)    # 0: 失败, 1: 成功
    error_code = Column(Integer)            # HTTP 错误码（如 429, 403, 404 等）
    error_message = Column(Text)            # 错误信息（如果失败）
    response_time_ms = Column(Integer)      # 响应时间（毫秒）
    rpm_at_call = Column(Integer)           # 调用时的 RPM 计数
    rpd_at_call = Column(Integer)           # 调用时的 RPD 计数
    created_at = Column(TIMESTAMP, default=func.current_timestamp())

    __table_args__ = (
        Index('idx_ai_usage_purpose_key', 'purpose', 'key_id'),
        Index('idx_ai_usage_created', 'created_at'),
        Index('idx_ai_usage_hash', 'hash_id'),
        Index('idx_ai_usage_anime_title', 'anime_title'),
    )

    def __repr__(self):
        return f"<AIKeyUsageLog(id={self.id}, purpose='{self.purpose}', key_id='{self.key_id}', success={self.success})>"


class AIKeyDailyCount(Base):
    """AI Key 每日计数表（用于持久化 RPD）"""

    __tablename__ = 'ai_key_daily_count'

    id = Column(Integer, primary_key=True, autoincrement=True)
    purpose = Column(Text, nullable=False)  # title_parse, multi_file_rename
    key_id = Column(Text, nullable=False)   # key 的哈希 ID
    date_utc = Column(Text, nullable=False)  # UTC 日期字符串 (YYYY-MM-DD)
    count = Column(Integer, default=0)      # 当日请求计数
    updated_at = Column(TIMESTAMP, default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('purpose', 'key_id', 'date_utc', name='uq_ai_key_daily'),
        Index('idx_ai_daily_date', 'date_utc'),
    )

    def __repr__(self):
        return f"<AIKeyDailyCount(purpose='{self.purpose}', key_id='{self.key_id}', date='{self.date_utc}', count={self.count})>"


class SubtitleFile(Base):
    """字幕文件表"""

    __tablename__ = 'subtitle_files'

    id = Column(Integer, primary_key=True, autoincrement=True)
    anime_id = Column(Integer, ForeignKey('anime_info.id'), nullable=False)
    video_file_path = Column(Text, nullable=False)    # 关联的影片文件路径
    subtitle_path = Column(Text, nullable=False)      # 字幕文件的完整路径
    original_name = Column(Text, nullable=False)      # 字幕原始文件名
    language_tag = Column(Text)                       # 语言标签: chs, cht, eng, jpn等
    subtitle_format = Column(Text)                    # 字幕格式: ass, srt, sub等
    source_archive = Column(Text)                     # 来源压缩档名
    match_method = Column(Text, default='ai')         # 匹配方式: ai, manual
    created_at = Column(TIMESTAMP, default=get_utc_now)
    updated_at = Column(TIMESTAMP, default=get_utc_now, onupdate=get_utc_now)

    # 关系
    anime = relationship('AnimeInfo', back_populates='subtitles')

    __table_args__ = (
        UniqueConstraint('video_file_path', 'subtitle_path', name='uq_subtitle_video'),
        Index('idx_subtitle_anime', 'anime_id'),
        Index('idx_subtitle_video', 'video_file_path'),
    )

    def __repr__(self):
        return f"<SubtitleFile(id={self.id}, video='{self.video_file_path}', subtitle='{self.subtitle_path}')>"
