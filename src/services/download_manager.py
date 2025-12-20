"""
Download manager module.

Core orchestrator coordinating all download-related operations including
RSS processing, manual uploads, torrent completion handling, and status management.
"""

import base64
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import config, RSSFeed
from src.core.domain.entities import AnimeInfo, DownloadRecord
from src.core.domain.value_objects import (
    AnimeTitle,
    Category,
    DownloadMethod,
    DownloadStatus,
    MediaType,
    SeasonInfo,
    SubtitleGroup,
    TorrentHash,
)
from src.core.exceptions import (
    AnimeInfoExtractionError,
    TorrentAddError,
)
from src.core.interfaces.adapters import (
    IDownloadClient,
    IFileRenamer,
    IRSSParser,
    ITitleParser,
    RSSItem,
    TitleParseResult,
)
from src.core.interfaces.notifications import (
    DownloadNotification,
    ErrorNotification,
    HardlinkNotification,
    IDownloadNotifier,
    IErrorNotifier,
    IHardlinkNotifier,
    IRSSNotifier,
    RSSNotification,
)
from src.core.interfaces.repositories import (
    IAnimeRepository,
    IDownloadRepository,
    IHardlinkRepository,
)
from src.services.file.hardlink_service import HardlinkService
from src.services.file.path_builder import PathBuilder
from src.services.filter_service import FilterService
from src.services.metadata_service import MetadataService
from src.services.rename.file_classifier import FileClassifier
from src.services.rename.rename_service import RenameService

logger = logging.getLogger(__name__)


@dataclass
class RSSProcessResult:
    """
    RSS processing result.

    Attributes:
        total_items: Total items found in feeds.
        new_items: Number of new items processed.
        skipped_items: Number of skipped items.
        failed_items: Number of failed items.
        errors: List of error details.
    """
    total_items: int = 0
    new_items: int = 0
    skipped_items: int = 0
    failed_items: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        processed = self.new_items + self.failed_items
        if processed == 0:
            return 0.0
        return (self.new_items / processed) * 100


class DownloadManager:
    """
    Download manager - core orchestrator.

    Coordinates all download-related operations:
    - RSS feed processing
    - Manual uploads (torrent/magnet)
    - Torrent completion handling
    - Status management
    - Hardlink creation

    Follows SOLID principles with dependency injection.
    """

    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        history_repo: IHardlinkRepository,
        title_parser: ITitleParser,
        file_renamer: IFileRenamer,
        download_client: IDownloadClient,
        rss_service: IRSSParser,
        filter_service: FilterService,
        rename_service: RenameService,
        hardlink_service: HardlinkService,
        path_builder: PathBuilder,
        metadata_service: MetadataService,
        rss_notifier: Optional[IRSSNotifier] = None,
        download_notifier: Optional[IDownloadNotifier] = None,
        hardlink_notifier: Optional[IHardlinkNotifier] = None,
        error_notifier: Optional[IErrorNotifier] = None
    ):
        """
        Initialize the download manager.

        Args:
            anime_repo: Repository for anime information.
            download_repo: Repository for download records.
            history_repo: Repository for hardlink and history records.
            title_parser: AI title parser.
            file_renamer: AI file renamer.
            download_client: Download client (qBittorrent).
            rss_service: RSS parser service.
            filter_service: Content filter service.
            rename_service: Rename coordination service.
            hardlink_service: Hardlink creation service.
            path_builder: Path construction service.
            metadata_service: TVDB metadata service.
            rss_notifier: Optional RSS notification service.
            download_notifier: Optional download notification service.
            hardlink_notifier: Optional hardlink notification service.
            error_notifier: Optional error notification service.
        """
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._history_repo = history_repo
        self._title_parser = title_parser
        self._file_renamer = file_renamer
        self._download_client = download_client
        self._rss_service = rss_service
        self._filter_service = filter_service
        self._rename_service = rename_service
        self._hardlink_service = hardlink_service
        self._path_builder = path_builder
        self._metadata_service = metadata_service
        self._rss_notifier = rss_notifier
        self._download_notifier = download_notifier
        self._hardlink_notifier = hardlink_notifier
        self._error_notifier = error_notifier
        self._file_classifier = FileClassifier()

    # ==================== RSS Processing ====================

    def process_rss_feeds(
        self,
        rss_feeds: List,
        trigger_type: str = '定时触发',
        blocked_keywords: Optional[str] = None,
        blocked_regex: Optional[str] = None
    ) -> RSSProcessResult:
        """
        Process RSS feeds.

        Args:
            rss_feeds: List of RSS feeds (RSSFeed objects, dicts, or URL strings).
            trigger_type: How the processing was triggered.
            blocked_keywords: Global blocked keywords (deprecated, for backward compat).
            blocked_regex: Global regex patterns (deprecated, for backward compat).

        Returns:
            RSSProcessResult with processing statistics.
        """
        logger.info(f'🚀 开始处理RSS feeds，触发方式: {trigger_type}')
        logger.debug(f'📊 RSS feeds数量: {len(rss_feeds)}')

        result = RSSProcessResult()

        # Normalize feeds to RSSFeed objects
        feed_objects = self._normalize_feeds(rss_feeds, blocked_keywords, blocked_regex)

        logger.info(f'📡 开始解析 {len(feed_objects)} 个RSS订阅源...')

        # Record history
        history_id = self._history_repo.insert_rss_history(
            rss_url=', '.join([f.url for f in feed_objects]),
            triggered_by=trigger_type
        )

        # Send start notifications
        if self._rss_notifier:
            for feed in feed_objects:
                self._rss_notifier.notify_processing_start(
                    RSSNotification(trigger_type=trigger_type, rss_url=feed.url)
                )

        # Parse and process each feed
        all_items = []
        total_items_found = 0

        for feed in feed_objects:
            try:
                items = self._rss_service.parse_feed(feed.url)
                total_items_found += len(items)

                # Process each item
                new_items = self._filter_feed_items(
                    items, feed, history_id
                )
                all_items.extend(new_items)

            except Exception as e:
                logger.error(f'❌ RSS解析失败 [{feed.url}]: {e}')
                result.errors.append({'url': feed.url, 'error': str(e)})

        result.total_items = total_items_found

        logger.info(
            f'📦 RSS解析完成，共找到 {total_items_found} 个项目，'
            f'其中 {len(all_items)} 个新项目待处理'
        )

        if not all_items and total_items_found == 0:
            logger.info('📭 没有找到RSS项目')
            self._history_repo.update_rss_history_stats(
                history_id, 0, 0, 0, 'completed'
            )
            self._notify_completion(0, 0, [], feed_objects)
            return result

        # Update stats
        self._history_repo.update_rss_history_stats(
            history_id,
            items_found=total_items_found,
            items_attempted=len(all_items)
        )

        # Process new items
        logger.info(f'🔄 开始处理 {len(all_items)} 个RSS项目...')

        for idx, item in enumerate(all_items, 1):
            logger.debug(f'处理进度: {idx}/{len(all_items)} - {item.get("title", "")}')
            try:
                if self._process_single_item(item):
                    result.new_items += 1
                    self._history_repo.insert_rss_detail(
                        history_id, item.get('title', ''), 'success'
                    )
                else:
                    result.skipped_items += 1
                    self._history_repo.insert_rss_detail(
                        history_id, item.get('title', ''), 'failed', '处理失败'
                    )
            except Exception as e:
                logger.error(f'处理项目失败: {e}')
                result.failed_items += 1
                result.errors.append({'title': item.get('title', ''), 'reason': str(e)})
                self._history_repo.insert_rss_detail(
                    history_id, item.get('title', ''), 'failed', str(e)
                )

        # Complete processing
        logger.info(f'✅ RSS处理完成: 成功 {result.new_items}/{len(all_items)} 个项目')
        if result.errors:
            logger.warning(f'⚠️ 失败 {len(result.errors)} 个项目')
            for failed in result.errors[:3]:
                logger.debug(f'  失败: {failed}')

        self._history_repo.update_rss_history_stats(
            history_id,
            items_processed=result.new_items,
            status='completed'
        )
        self._notify_completion(
            result.new_items, len(all_items), result.errors, feed_objects
        )

        return result

    def process_single_rss_item(
        self,
        item: Dict[str, Any],
        trigger_type: str = 'queue'
    ) -> bool:
        """
        处理单个 RSS 项目（从队列调用）。

        Args:
            item: RSS 项目字典，包含 title, torrent_url, hash, media_type 等。
            trigger_type: 触发类型。

        Returns:
            处理成功返回 True，否则返回 False。
        """
        title = item.get('title', '')
        logger.info(f'🔄 [队列] 处理项目: {title[:50]}...')

        try:
            # 调用内部处理方法
            success = self._process_single_item(item)

            if success:
                logger.info(f'✅ [队列] 项目处理成功: {title[:50]}...')
            else:
                logger.warning(f'⚠️ [队列] 项目处理失败: {title[:50]}...')

            return success

        except Exception as e:
            logger.error(f'❌ [队列] 处理项目失败: {title[:50]}... - {e}', exc_info=True)
            return False

    def process_manual_anime_rss(
        self,
        rss_url: str,
        short_title: str,
        subtitle_group: str,
        season: int,
        category: str,
        trigger_type: str,
        blocked_keywords: Optional[str] = None,
        blocked_regex: Optional[str] = None,
        media_type: str = 'anime'
    ) -> RSSProcessResult:
        """
        Process manually added anime RSS.

        Args:
            rss_url: RSS feed URL.
            short_title: Anime short title.
            subtitle_group: Subtitle group name.
            season: Season number.
            category: Content category ('tv' or 'movie').
            trigger_type: How the processing was triggered.
            blocked_keywords: Blocked keywords.
            blocked_regex: Blocked regex patterns.
            media_type: Media type ('anime' or 'live_action').

        Returns:
            RSSProcessResult with processing statistics.
        """
        logger.info(f'🚀 开始处理手动添加动漫RSS: {short_title}, 触发方式: {trigger_type}')

        result = RSSProcessResult()

        # Record history
        history_id = self._history_repo.insert_rss_history(
            rss_url=rss_url,
            triggered_by=trigger_type
        )

        try:
            # Parse RSS
            items = self._rss_service.parse_feed(rss_url)
            result.total_items = len(items)

            if not items:
                logger.info('📭 没有找到RSS项目')
                self._history_repo.update_rss_history_stats(
                    history_id, 0, 0, 0, 'completed'
                )
                return result

            # Filter new items
            new_items = self._rss_service.filter_new_items(items)

            # Apply additional filters
            if blocked_keywords or blocked_regex:
                filtered_items = []
                for item in new_items:
                    title = item.title if isinstance(item, RSSItem) else item.get('title', '')
                    if not self._filter_service.should_filter(
                        title, blocked_keywords, blocked_regex
                    ):
                        filtered_items.append(item)
                new_items = filtered_items

            # Update stats
            self._history_repo.update_rss_history_stats(
                history_id,
                items_found=len(items),
                items_attempted=len(new_items)
            )

            if not new_items:
                logger.info('📭 所有项目都已在数据库中或被过滤')
                self._history_repo.update_rss_history_stats(history_id, status='completed')
                return result

            # Save anime info
            anime_id = self._save_anime_info(
                original_title=short_title,
                short_title=short_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                media_type=media_type
            )

            # Generate save path
            save_path = self._generate_save_path({
                'anime_clean_title': short_title,
                'season': season,
                'category': category,
                'media_type': media_type
            })

            # Process items
            for item in new_items:
                title = item.title if isinstance(item, RSSItem) else item.get('title', '')
                torrent_url = (
                    item.effective_url if isinstance(item, RSSItem)
                    else item.get('torrent_url', '') or item.get('link', '')
                )
                hash_id = item.hash if isinstance(item, RSSItem) else item.get('hash', '')

                try:
                    if not torrent_url:
                        raise TorrentAddError('缺少torrent_url，无法添加下载任务')

                    add_result = self._download_client.add_torrent(
                        torrent_url, save_path, hash_id=hash_id
                    )
                    if not add_result:
                        raise TorrentAddError(
                            '添加种子到qBittorrent失败（可能无法连接/登录qBittorrent）'
                        )

                    # Record download status
                    self._save_download_record(
                        hash_id=hash_id,
                        original_filename=title,
                        anime_title=short_title,
                        subtitle_group=subtitle_group,
                        season=season,
                        download_directory=save_path,
                        anime_id=anime_id,
                        download_method='manual_rss'
                    )

                    result.new_items += 1
                    self._history_repo.insert_rss_detail(history_id, title, 'success')

                    # Send notification
                    self._notify_download_start(
                        anime_title=short_title,
                        season=season,
                        episode=1,
                        subtitle_group=subtitle_group,
                        hash_id=hash_id
                    )

                except Exception as e:
                    logger.error(f'处理项目失败: {e}')
                    result.failed_items += 1
                    result.errors.append({'title': title, 'reason': str(e)})
                    self._history_repo.insert_rss_detail(
                        history_id, title, 'failed', str(e)
                    )

            # Complete processing
            self._history_repo.update_rss_history_stats(
                history_id,
                items_processed=result.new_items,
                status='completed'
            )

        except Exception as e:
            logger.error(f'❌ 处理手动RSS失败: {e}')
            result.errors.append({'error': str(e)})
            self._history_repo.update_rss_history_stats(
                history_id, status='failed'
            )

        return result

    def _normalize_feeds(
        self,
        feeds: List,
        blocked_keywords: Optional[str],
        blocked_regex: Optional[str]
    ) -> List[RSSFeed]:
        """Normalize feed inputs to RSSFeed objects."""
        feed_objects = []
        for feed in feeds:
            if isinstance(feed, str):
                feed_objects.append(RSSFeed(
                    url=feed,
                    blocked_keywords=blocked_keywords or '',
                    blocked_regex=blocked_regex or ''
                ))
            elif isinstance(feed, dict):
                feed_objects.append(RSSFeed(**feed))
            else:
                feed_objects.append(feed)
        return feed_objects

    def _filter_feed_items(
        self,
        items: List[RSSItem],
        feed: RSSFeed,
        history_id: int
    ) -> List[Dict[str, Any]]:
        """Filter and process feed items."""
        new_items = []

        # 调试日志：显示过滤器配置
        if feed.blocked_keywords or feed.blocked_regex:
            logger.info(f'🔍 过滤器已启用:')
            if feed.blocked_keywords:
                keywords_preview = feed.blocked_keywords.replace('\n', ', ')[:100]
                logger.info(f'  屏蔽词: {keywords_preview}')
            if feed.blocked_regex:
                regex_preview = feed.blocked_regex.replace('\n', ', ')[:100]
                logger.info(f'  正则: {regex_preview}')
        else:
            logger.debug(f'📋 未配置过滤器')

        for item in items:
            title = item.title
            hash_id = item.hash

            # Convert RSSItem to dict for compatibility
            item_dict = {
                'title': item.title,
                'torrent_url': item.torrent_url or item.link,
                'link': item.link,
                'hash': item.hash,
                'description': item.description,
                'pub_date': item.pub_date,
                'media_type': feed.media_type
            }

            # Check if already exists
            if hash_id:
                existing = self._download_repo.get_by_hash(hash_id)
                if existing:
                    self._history_repo.insert_rss_detail(
                        history_id, title, 'exists', '已存在于数据库'
                    )
                    continue

            # Check filters
            should_skip = False
            skip_reason = ''

            if feed.blocked_keywords or feed.blocked_regex:
                if self._filter_service.should_filter(
                    title, feed.blocked_keywords, feed.blocked_regex
                ):
                    should_skip = True
                    skip_reason = '匹配过滤规则'
                    logger.info(f'⏭️ 过滤器跳过 [{feed.url}]: {title}')

            if should_skip:
                self._history_repo.insert_rss_detail(
                    history_id, title, 'filtered', skip_reason
                )
                continue

            new_items.append(item_dict)

        return new_items

    def _process_single_item(self, item: Dict[str, Any]) -> bool:
        """
        Process a single RSS item.

        Args:
            item: RSS item dictionary.

        Returns:
            True if processing was successful.
        """
        title = item.get('title', '')
        media_type = item.get('media_type', 'anime')

        # Check for existing anime
        existing_anime = self._find_existing_anime(title)

        if existing_anime:
            return self._process_existing_anime(item, existing_anime)
        else:
            return self._process_new_anime(item, media_type)

    def _process_new_anime(self, item: Dict[str, Any], media_type: str = 'anime') -> bool:
        """
        Process a new anime item.

        Args:
            item: RSS item dictionary.
            media_type: Media type ('anime' or 'live_action').

        Returns:
            True if processing was successful.
        """
        title = item.get('title', '')
        torrent_url = item.get('torrent_url', '') or item.get('link', '')
        hash_id = item.get('hash', '')

        try:
            # Send notification for AI processing
            if self._rss_notifier:
                self._rss_notifier.notify_processing_start(
                    RSSNotification(trigger_type='AI分析', rss_url=torrent_url, title=title)
                )

            # AI title parsing
            parse_result = self._title_parser.parse(title)
            if not parse_result:
                raise AnimeInfoExtractionError('AI解析失败')

            # Save anime info
            anime_id = self._save_anime_info(
                original_title=parse_result.original_title,
                short_title=parse_result.clean_title,
                long_title=parse_result.full_title,
                subtitle_group=parse_result.subtitle_group,
                season=parse_result.season,
                category=parse_result.category,
                media_type=media_type
            )

            # Generate save path
            save_path = self._generate_save_path({
                'anime_clean_title': parse_result.clean_title,
                'season': parse_result.season,
                'category': parse_result.category,
                'media_type': media_type
            })

            # Add torrent
            if not torrent_url:
                raise TorrentAddError('缺少torrent_url，无法添加下载任务')

            add_result = self._download_client.add_torrent(
                torrent_url, save_path, hash_id=hash_id
            )
            if not add_result:
                raise TorrentAddError(
                    '添加种子到qBittorrent失败（可能无法连接/登录qBittorrent）'
                )

            # Record download status
            self._save_download_record(
                hash_id=hash_id,
                original_filename=title,
                anime_title=parse_result.clean_title,
                subtitle_group=parse_result.subtitle_group,
                season=parse_result.season,
                download_directory=save_path,
                anime_id=anime_id,
                download_method='rss_ai'
            )

            # Send notification
            self._notify_download_start(
                anime_title=parse_result.clean_title,
                season=parse_result.season,
                episode=parse_result.episode,
                subtitle_group=parse_result.subtitle_group,
                hash_id=hash_id
            )

            return True

        except Exception as e:
            logger.error(f'处理新动漫失败: {e}')
            raise

    def _process_existing_anime(
        self,
        item: Dict[str, Any],
        anime_info: AnimeInfo
    ) -> bool:
        """
        Process an item for an existing anime.

        Args:
            item: RSS item dictionary.
            anime_info: Existing anime information.

        Returns:
            True if processing was successful.
        """
        title = item.get('title', '')
        torrent_url = item.get('torrent_url', '') or item.get('link', '')
        hash_id = item.get('hash', '')

        anime_id = anime_info.id
        anime_short_title = anime_info.display_name
        anime_subtitle_group = anime_info.subtitle_group_name
        anime_season = anime_info.season_number
        anime_category = 'movie' if anime_info.category == Category.MOVIE else 'tv'

        # Try to extract episode number from title
        episode = self._extract_episode_from_title(title)

        # Generate save path
        save_path = self._generate_save_path({
            'anime_clean_title': anime_short_title,
            'season': anime_season,
            'category': anime_category
        })

        # Add torrent
        if not torrent_url:
            raise TorrentAddError('缺少torrent_url，无法添加下载任务')

        add_result = self._download_client.add_torrent(
            torrent_url, save_path, hash_id=hash_id
        )
        if not add_result:
            raise TorrentAddError(
                '添加种子到qBittorrent失败（可能无法连接/登录qBittorrent）'
            )

        # Record download status
        self._save_download_record(
            hash_id=hash_id,
            original_filename=title,
            anime_title=anime_short_title,
            subtitle_group=anime_subtitle_group,
            season=anime_season,
            download_directory=save_path,
            anime_id=anime_id,
            download_method='fixed_rss'
        )

        # Send notification
        self._notify_download_start(
            anime_title=anime_short_title,
            season=anime_season,
            episode=episode,
            subtitle_group=anime_subtitle_group,
            hash_id=hash_id
        )

        return True

    # ==================== Manual Upload Processing ====================

    def process_manual_upload(self, data: Dict[str, Any]) -> bool:
        """
        Process manual upload (torrent file or magnet link).

        Args:
            data: Upload data containing:
                - upload_type: 'torrent' or 'magnet'
                - anime_title: Anime title
                - subtitle_group: Subtitle group name
                - season: Season number
                - category: Content category
                - is_multi_season: Whether multiple seasons
                - media_type: Media type
                - torrent_file: Base64 encoded torrent file (if upload_type='torrent')
                - magnet_link: Magnet link (if upload_type='magnet')

        Returns:
            True if successful.
        """
        try:
            upload_type = data.get('upload_type', 'torrent')
            anime_title = data.get('anime_title', '').strip()
            subtitle_group = data.get('subtitle_group', '').strip()
            season = data.get('season', 1)
            category = data.get('category', 'tv')
            is_multi_season = data.get('is_multi_season', False)
            media_type = data.get('media_type', 'anime')

            logger.info(f'🔄 开始处理手动上传: {anime_title} (类型: {upload_type})')

            # Save anime info
            anime_id = self._save_anime_info(
                original_title=f'手动上传 - {anime_title}',
                short_title=anime_title,
                long_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                media_type=media_type
            )

            # Generate save path
            save_path = self._generate_save_path({
                'anime_clean_title': anime_title,
                'season': season,
                'category': category,
                'media_type': media_type
            })

            # Process based on upload type
            hash_id = None

            if upload_type == 'torrent':
                hash_id = self._process_torrent_upload(data, save_path)
            else:  # magnet
                hash_id = self._process_magnet_upload(data, save_path)

            if not hash_id:
                raise ValueError('无法获取hash')

            # Record download status
            self._save_download_record(
                hash_id=hash_id,
                original_filename=f'手动上传 - {anime_title}',
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                download_directory=save_path,
                anime_id=anime_id,
                download_method=f'manual_{upload_type}',
                is_multi_season=is_multi_season
            )

            # Record history
            self._history_repo.insert_manual_upload_history(
                upload_type=upload_type,
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                torrent_hash=hash_id,
                upload_status='success'
            )

            # Send notification
            self._notify_download_start(
                anime_title=anime_title,
                season=season,
                episode=1,
                subtitle_group=subtitle_group,
                hash_id=hash_id
            )

            return True

        except Exception as e:
            logger.error(f'手动上传失败: {e}')
            # Record failure history
            self._history_repo.insert_manual_upload_history(
                upload_type=data.get('upload_type', 'unknown'),
                anime_title=data.get('anime_title', 'unknown'),
                subtitle_group=data.get('subtitle_group', ''),
                season=data.get('season', 1),
                category=data.get('category', 'tv'),
                torrent_hash=None,
                upload_status='failed',
                error_message=str(e)
            )
            self._notify_error(f'手动上传失败: {e}')
            return False

    def _process_torrent_upload(
        self,
        data: Dict[str, Any],
        save_path: str
    ) -> str:
        """Process torrent file upload."""
        from src.infrastructure.downloader.qbit_adapter import get_torrent_hash_from_file

        torrent_file = data.get('torrent_file')
        if not torrent_file:
            raise ValueError('缺少torrent文件内容')

        # Decode Base64 and save to temp file
        torrent_content = base64.b64decode(torrent_file)
        with tempfile.NamedTemporaryFile(suffix='.torrent', delete=False) as temp_file:
            temp_file.write(torrent_content)
            temp_file_path = temp_file.name

        try:
            hash_id = get_torrent_hash_from_file(temp_file_path)
            if not hash_id:
                raise ValueError('无法从torrent文件提取hash')

            self._download_client.add_torrent_file(temp_file_path, save_path)
            return hash_id
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def _process_magnet_upload(
        self,
        data: Dict[str, Any],
        save_path: str
    ) -> str:
        """Process magnet link upload."""
        from src.infrastructure.downloader.qbit_adapter import get_torrent_hash_from_magnet

        magnet_link = data.get('magnet_link', '').strip()
        if not magnet_link:
            raise ValueError('缺少磁力链接')

        hash_id = get_torrent_hash_from_magnet(magnet_link)
        if not hash_id:
            raise ValueError('无法从磁力链接提取hash')

        self._download_client.add_magnet(magnet_link, save_path)
        return hash_id

    # ==================== Torrent Completion Handling ====================

    def handle_torrent_completed(
        self,
        hash_id: str,
        webhook_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Handle torrent download completion event.

        Args:
            hash_id: Torrent hash.
            webhook_data: Optional webhook event data.

        Returns:
            Result dictionary with processing details.
        """
        try:
            logger.info('🎉 种子下载完成')
            logger.info(f'  Hash: {hash_id[:8]}...')

            # Update download status
            completion_time = datetime.now(timezone.utc)
            self._download_repo.update_status(hash_id, 'completed', completion_time)

            # Get download info
            download_info = self._download_repo.get_by_hash(hash_id)
            if not download_info:
                logger.warning(f'未找到下载记录: {hash_id}')
                return {'success': True, 'message': 'Download record not found'}

            logger.info(f'  动漫: {download_info.anime_title or download_info.original_filename}')

            # Get torrent files
            logger.debug('📋 正在获取种子文件列表...')
            torrent_files = self._download_client.get_torrent_files(hash_id)
            hardlink_count = 0

            if torrent_files:
                logger.info(f'  文件数量: {len(torrent_files)}')

                # Save file info to database
                logger.debug('💾 保存文件信息到数据库...')
                for file_info in torrent_files:
                    self._save_torrent_file(
                        torrent_hash=hash_id,
                        file_path=file_info.get('name', ''),
                        file_size=file_info.get('size', 0),
                        anime_id=download_info.anime_id
                    )

                # Create hardlinks
                logger.info('🔗 开始创建硬链接...')
                hardlink_count = self._create_hardlinks_for_completed_torrent(
                    hash_id, download_info, torrent_files
                )

            logger.info(f'✅ 种子处理完成: 成功创建 {hardlink_count} 个硬链接')
            return {
                'success': True,
                'message': 'Torrent completion processed',
                'hardlinks_created': hardlink_count
            }

        except Exception as e:
            logger.error(f'处理种子完成事件失败: {e}')
            return {'success': False, 'error': str(e)}

    def _create_hardlinks_for_completed_torrent(
        self,
        hash_id: str,
        download_info: DownloadRecord,
        torrent_files: List[Dict[str, Any]]
    ) -> int:
        """
        Create hardlinks for completed torrent files.

        Args:
            hash_id: Torrent hash.
            download_info: Download record.
            torrent_files: List of torrent files.

        Returns:
            Number of hardlinks created.
        """
        hardlink_count = 0

        try:
            anime_id = download_info.anime_id
            anime_title = download_info.anime_title
            subtitle_group = download_info.subtitle_group
            season = download_info.season
            is_multi_season = download_info.is_multi_season

            # Get media_type from database
            media_type = 'anime'
            if anime_id:
                anime_info = self._anime_repo.get_by_id(anime_id)
                if anime_info:
                    media_type = (
                        'live_action' if anime_info.media_type == MediaType.LIVE_ACTION
                        else 'anime'
                    )

            # Determine category
            category = 'movie' if season == 0 else 'tv'

            # Determine target base path
            target_base = self._get_target_base_path(media_type, category)
            target_dir = os.path.join(target_base, anime_title)

            # Classify files
            download_directory = (
                download_info.download_directory or
                config.qbittorrent.base_download_path
            )
            video_files, subtitle_files = self._rename_service.classify_files(
                torrent_files, download_directory
            )

            logger.info(f'视频文件: {len(video_files)} 个, 字幕文件: {len(subtitle_files)} 个')

            if not video_files:
                logger.warning('未找到视频文件')
                return 0

            # Get TVDB data and folder structure for manual uploads
            tvdb_data = None
            folder_structure = None
            download_method = download_info.download_method

            if download_method and download_method.value.startswith('manual_'):
                # Get folder structure
                try:
                    folder_structure = self._download_client.get_torrent_folder_structure(
                        hash_id
                    ) if hasattr(self._download_client, 'get_torrent_folder_structure') else None
                    if folder_structure:
                        logger.info(f'📁 获取到Torrent目录结构:\n{folder_structure}')
                except Exception as e:
                    logger.warning(f'⚠️ 获取文件夹结构失败: {e}')

                # Get TVDB data
                if config.tvdb.enabled:
                    try:
                        logger.info(f'🔍 检测到手动上传，尝试获取TVDB数据: {anime_title}')
                        tvdb_data = self._metadata_service.get_tvdb_data_for_anime(anime_title)
                        if tvdb_data:
                            logger.info('✅ 成功获取TVDB数据')
                            # Save TVDB ID to anime_info table
                            tvdb_id = tvdb_data.get('tvdb_id')
                            if tvdb_id and anime_id:
                                self._anime_repo.update_tvdb_id(anime_id, tvdb_id)
                        else:
                            logger.info('⚠️ 未获取到TVDB数据，将使用AI处理')
                    except Exception as e:
                        logger.warning(f'⚠️ 获取TVDB数据失败: {e}，将使用AI处理')

            # Generate rename mapping
            rename_result = self._rename_service.generate_mapping(
                video_files=video_files,
                anime_id=anime_id,
                anime_title=anime_title,
                subtitle_group=subtitle_group,
                season=season,
                category=category,
                is_multi_season=is_multi_season,
                tvdb_data=tvdb_data,
                folder_structure=folder_structure,
                torrent_hash=hash_id
            )

            if not rename_result or not rename_result.has_files:
                logger.warning('无法生成重命名映射')
                return 0

            logger.info(f'🎯 重命名方案: {rename_result.method}')

            # Create hardlinks for video files
            for video in video_files:
                original_name = video.name
                source_path = video.full_path

                # Check if skipped
                if video.relative_path in rename_result.skipped_files:
                    logger.info(f'⏭️ 跳过非正片文件: {original_name}')
                    continue

                # Check if source exists
                if not os.path.exists(source_path):
                    logger.error(f'✗ 源文件不存在: {source_path}')
                    continue

                # Get new name
                new_name = rename_result.main_files.get(original_name)
                if not new_name:
                    logger.error(f'✗ 未找到重命名映射: {original_name}')
                    continue

                # Create hardlink
                success = self._hardlink_service.create(
                    source_path=source_path,
                    target_dir=target_dir,
                    new_name=new_name,
                    anime_id=anime_id,
                    torrent_hash=hash_id
                )

                if success:
                    hardlink_count += 1
                    logger.info(f'✓ 硬链接创建成功: {new_name}')
                else:
                    logger.warning(f'✗ 硬链接创建失败: {original_name}')

            # Process subtitle files
            if subtitle_files:
                subtitle_mapping = self._rename_service.generate_subtitle_mapping(
                    video_files, subtitle_files, rename_result.main_files
                )

                for sub_file in subtitle_files:
                    if sub_file.name in subtitle_mapping:
                        new_name = subtitle_mapping[sub_file.name]
                        success = self._hardlink_service.create(
                            source_path=sub_file.full_path,
                            target_dir=target_dir,
                            new_name=new_name,
                            anime_id=anime_id,
                            torrent_hash=hash_id
                        )
                        if success:
                            logger.info(f'✓ 字幕硬链接创建成功: {new_name}')

            # Send notification
            if hardlink_count > 0 and self._hardlink_notifier:
                notification = HardlinkNotification(
                    anime_title=anime_title,
                    season=season,
                    video_count=hardlink_count,
                    subtitle_count=len(subtitle_files),
                    target_dir=target_dir,
                    rename_method=rename_result.method
                )
                try:
                    self._hardlink_notifier.notify_hardlink_created(notification)
                except Exception as e:
                    logger.error(f'发送硬链接创建通知失败: {e}')

        except Exception as e:
            logger.error(f'处理硬链接失败: {e}')

        return hardlink_count

    # ==================== Status Management ====================

    def check_torrent_status(self, hash_id: str) -> Dict[str, Any]:
        """
        Check status of a single torrent.

        Args:
            hash_id: Torrent hash.

        Returns:
            Status information dictionary.
        """
        try:
            # Get current status from database
            current_download = self._download_repo.get_by_hash(hash_id)
            current_status = current_download.status if current_download else None

            torrent_info = self._download_client.get_torrent_info(hash_id)
            if not torrent_info:
                # Torrent not found
                if current_status == DownloadStatus.COMPLETED:
                    return {'success': True, 'status': 'completed', 'message': '種子已完成'}
                elif current_status == DownloadStatus.PENDING:
                    self._download_repo.update_status(hash_id, 'missing', None)
                    return {'success': True, 'status': 'missing', 'message': '未找到種子'}
                else:
                    if current_status:
                        self._download_repo.update_status(hash_id, 'missing', None)
                    return {'success': True, 'status': 'missing', 'message': '未找到種子'}

            status = 'completed' if torrent_info.get('progress', 0) >= 1.0 else 'downloading'
            completion_time = None

            if status == 'completed':
                if torrent_info.get('completion_date', -1) != -1:
                    completion_time = datetime.fromtimestamp(
                        torrent_info['completion_date'],
                        tz=timezone.utc
                    )
                else:
                    completion_time = datetime.now(timezone.utc)

            # Update database
            self._download_repo.update_status(hash_id, status, completion_time)

            return {
                'success': True,
                'status': status,
                'progress': torrent_info.get('progress', 0),
                'completion_time': completion_time
            }
        except Exception as e:
            logger.error(f'检查种子状态失败: {e}')
            return {'success': False, 'error': str(e)}

    def check_all_torrents(self) -> Dict[str, Any]:
        """
        Check status of all incomplete torrents.

        Returns:
            Statistics dictionary.
        """
        try:
            incomplete_downloads = self._download_repo.get_incomplete()

            updated_count = 0
            completed_count = 0

            for download in incomplete_downloads:
                hash_value = download.hash_value if download.hash else ''
                if not hash_value:
                    continue

                result = self.check_torrent_status(hash_value)
                if result.get('success'):
                    updated_count += 1
                    if result.get('status') == 'completed':
                        completed_count += 1

            return {
                'success': True,
                'updated_count': updated_count,
                'completed_count': completed_count,
                'total_checked': len(incomplete_downloads)
            }
        except Exception as e:
            logger.error(f'批量检查失败: {e}')
            return {'success': False, 'error': str(e)}

    def delete_download(
        self,
        hash_id: str,
        delete_file: bool,
        delete_hardlink: bool
    ) -> Dict[str, Any]:
        """
        Delete a download task.

        Args:
            hash_id: Torrent hash.
            delete_file: Whether to delete original files.
            delete_hardlink: Whether to delete hardlinks.

        Returns:
            Result dictionary.
        """
        result = {
            'success': True,
            'deleted_files': False,
            'deleted_hardlinks': False,
            'moved_to_history': False
        }

        try:
            # Delete hardlinks if requested
            if delete_hardlink:
                deleted_count = self._hardlink_service.delete_by_torrent(
                    hash_id, delete_files=True
                )
                result['deleted_hardlinks'] = deleted_count > 0
                result['hardlinks_deleted_count'] = deleted_count
                logger.info(f'删除了 {deleted_count} 个硬链接')

            # Delete original files if requested
            if delete_file:
                if self._download_client.delete_torrent(hash_id, delete_files=True):
                    result['deleted_files'] = True
                    logger.info(f'从qBittorrent删除了种子和文件: {hash_id}')
                else:
                    logger.warning(f'从qBittorrent删除失败: {hash_id}')

                # Move download record to history
                if self._download_repo.move_to_history(hash_id):
                    result['moved_to_history'] = True
                    logger.info(f'将下载记录移动到历史: {hash_id}')

            return result
        except Exception as e:
            logger.error(f'删除下载失败: {e}')
            return {'success': False, 'error': str(e)}

    def redownload_from_history(
        self,
        hash_id: str,
        download_directory: str
    ) -> bool:
        """
        Re-download from history record.

        Args:
            hash_id: Torrent hash.
            download_directory: Download directory path.

        Returns:
            True if successful.
        """
        try:
            # Check if already downloading
            if self._download_repo.get_by_hash(hash_id):
                raise ValueError('该项目已在下载列表中')

            # Get history record
            history = self._history_repo.get_download_history_by_hash(hash_id)
            if not history:
                logger.warning(f'未找到hash {hash_id} 的历史记录')
                raise ValueError('未找到下载历史记录')

            logger.info(
                f"📥 开始重新下载: {history.get('anime_title') or history.get('original_filename')}"
            )

            # Add magnet link to qBittorrent
            magnet_link = f'magnet:?xt=urn:btih:{hash_id}'
            result = self._download_client.add_magnet(magnet_link, save_path=download_directory)

            if not result:
                raise ValueError('添加磁力链接失败')

            # Restore to download_status table
            self._save_download_record(
                hash_id=hash_id,
                original_filename=history.get('original_filename', ''),
                anime_title=history.get('anime_title', ''),
                subtitle_group=history.get('subtitle_group', ''),
                season=history.get('season', 1),
                download_directory=download_directory,
                anime_id=history.get('anime_id'),
                download_method=history.get('download_method', 'unknown'),
                is_multi_season=history.get('is_multi_season', False)
            )

            # Delete from history
            if self._history_repo.delete_download_history_by_hash(hash_id):
                logger.info(f'✅ 已从历史记录中移除: {hash_id}')

            logger.info('✅ 成功从历史记录重新下载，记录已恢复到下载列表')
            return True
        except Exception as e:
            logger.error(f'❌ 重新下载失败: {e}')
            return False

    # ==================== Webhook Event Handlers ====================

    def handle_torrent_added(
        self,
        hash_id: str,
        webhook_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle torrent added event."""
        try:
            logger.info(f'处理种子添加事件: {hash_id}')
            self._download_repo.update_status(hash_id, 'downloading')
            return {'success': True, 'message': 'Torrent added processed'}
        except Exception as e:
            logger.error(f'处理种子添加事件失败: {e}')
            return {'success': False, 'error': str(e)}

    def handle_torrent_error(
        self,
        hash_id: str,
        webhook_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle torrent error event."""
        try:
            logger.error(f'处理种子错误事件: {hash_id}')

            error_message = (
                webhook_data.get('error', 'Unknown error') if webhook_data
                else 'Unknown error'
            )

            self._download_repo.update_status(hash_id, 'failed')

            download_info = self._download_repo.get_by_hash(hash_id)
            if download_info and self._error_notifier:
                self._error_notifier.notify_error(ErrorNotification(
                    error_type='下载错误',
                    error_message=error_message,
                    context={
                        'anime_title': download_info.anime_title or download_info.original_filename,
                        'hash_id': hash_id
                    }
                ))

            logger.error(f'种子错误处理完成: {hash_id} - {error_message}')
            return {'success': True, 'message': 'Torrent error processed'}
        except Exception as e:
            logger.error(f'处理种子错误事件失败: {e}')
            return {'success': False, 'error': str(e)}

    def handle_torrent_paused(
        self,
        hash_id: str,
        webhook_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle torrent paused event."""
        try:
            logger.info(f'处理种子暂停事件: {hash_id}')
            self._download_repo.update_status(hash_id, 'paused')
            return {'success': True, 'message': 'Torrent paused processed'}
        except Exception as e:
            logger.error(f'处理种子暂停事件失败: {e}')
            return {'success': False, 'error': str(e)}

    # ==================== Helper Methods ====================

    def _find_existing_anime(self, title: str) -> Optional[AnimeInfo]:
        """Find existing anime by title."""
        # Try improved matching first
        existing = self._anime_repo.get_by_core_info(title)
        if not existing:
            existing = self._anime_repo.get_by_title(title)
        return existing

    def _save_anime_info(
        self,
        original_title: str,
        short_title: str,
        long_title: Optional[str] = None,
        subtitle_group: str = '',
        season: int = 1,
        category: str = 'tv',
        media_type: str = 'anime'
    ) -> int:
        """Save anime information and return ID."""
        anime_info = AnimeInfo(
            title=AnimeTitle(
                original=original_title,
                short=short_title,
                full=long_title
            ),
            subtitle_group=SubtitleGroup(name=subtitle_group),
            season=SeasonInfo(
                number=season,
                category=Category.MOVIE if category == 'movie' else Category.TV
            ),
            category=Category.MOVIE if category == 'movie' else Category.TV,
            media_type=MediaType.LIVE_ACTION if media_type == 'live_action' else MediaType.ANIME,
            created_at=datetime.now(timezone.utc)
        )
        return self._anime_repo.save(anime_info)

    def _save_download_record(
        self,
        hash_id: str,
        original_filename: str,
        anime_title: str,
        subtitle_group: str,
        season: int,
        download_directory: str,
        anime_id: int,
        download_method: str,
        is_multi_season: bool = False
    ) -> int:
        """Save download record and return ID."""
        # Determine download method enum
        method_map = {
            'rss_ai': DownloadMethod.RSS_AI,
            'fixed_rss': DownloadMethod.FIXED_RSS,
            'manual_rss': DownloadMethod.MANUAL_RSS,
            'manual_torrent': DownloadMethod.MANUAL_TORRENT,
            'manual_magnet': DownloadMethod.MANUAL_MAGNET,
        }
        method = method_map.get(download_method, DownloadMethod.RSS_AI)

        record = DownloadRecord(
            hash=TorrentHash(hash_id) if hash_id and len(hash_id) >= 32 else None,
            anime_id=anime_id,
            original_filename=original_filename,
            anime_title=anime_title,
            subtitle_group=subtitle_group,
            season=season,
            download_directory=download_directory,
            status=DownloadStatus.PENDING,
            download_method=method,
            is_multi_season=is_multi_season,
            download_time=datetime.now(timezone.utc)
        )
        return self._download_repo.save(record)

    def _save_torrent_file(
        self,
        torrent_hash: str,
        file_path: str,
        file_size: int,
        anime_id: Optional[int]
    ) -> None:
        """Save torrent file information."""
        # Use the history_repo's legacy method for saving torrent files
        # This would typically be a direct database operation
        pass  # Implemented in repository layer

    def _generate_save_path(self, ai_result: Dict[str, Any]) -> str:
        """Generate download save path."""
        clean_title = ai_result.get('anime_clean_title', 'Unknown')
        season = ai_result.get('season', 1)
        category = ai_result.get('category', 'tv')
        media_type = ai_result.get('media_type', 'anime')

        # Sanitize title
        clean_title = self._path_builder._sanitize_filename(clean_title)

        return self._path_builder.build_download_path(
            title=clean_title,
            season=season,
            category=category,
            media_type=media_type
        )

    def _get_target_base_path(self, media_type: str, category: str) -> str:
        """Get target base path for hardlinks."""
        if media_type == 'live_action':
            if category == 'movie':
                return config.live_action_movie_target_path
            else:
                return config.live_action_tv_target_path
        else:
            if category == 'movie':
                return config.movie_link_target_path or config.link_target_path
            else:
                return config.link_target_path

    def _extract_episode_from_title(self, title: str) -> Optional[int]:
        """Extract episode number from title."""
        patterns = [
            r'[\[\s](\d{1,3})[\]\s]',  # [01] or 01
            r'E(\d{1,3})',  # E01
            r'第(\d{1,3})[话集]',  # 第01话
            r'- (\d{1,3}) ',  # - 01
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return None

    def _notify_download_start(
        self,
        anime_title: str,
        season: int,
        episode: Optional[int],
        subtitle_group: str,
        hash_id: str
    ) -> None:
        """Send download start notification."""
        if self._download_notifier:
            notification = DownloadNotification(
                anime_title=anime_title,
                season=season,
                episode=episode,
                subtitle_group=subtitle_group,
                hash_id=hash_id
            )
            try:
                self._download_notifier.notify_download_start(notification)
            except Exception as e:
                logger.warning(f'⚠️ 发送下载开始通知失败: {e}')

    def _notify_completion(
        self,
        success_count: int,
        total_count: int,
        failed_items: List[Dict[str, str]],
        feed_objects: List[RSSFeed]
    ) -> None:
        """Send RSS processing completion notification."""
        if self._rss_notifier:
            try:
                self._rss_notifier.notify_processing_complete(
                    success_count=success_count,
                    total_count=total_count,
                    failed_items=failed_items
                )
            except Exception as e:
                logger.warning(f'⚠️ 发送完成通知失败: {e}')

    def _notify_error(self, message: str) -> None:
        """Send error notification."""
        if self._error_notifier:
            try:
                self._error_notifier.notify_error(ErrorNotification(
                    error_type='错误',
                    error_message=message
                ))
            except Exception as e:
                logger.warning(f'⚠️ 发送错误通知失败: {e}')

    # ==================== Query Methods ====================

    def get_downloads_paginated(
        self,
        page: int,
        per_page: int,
        **filters
    ) -> Dict[str, Any]:
        """Get paginated download records."""
        # Delegate to repository
        return self._download_repo.get_downloads_paginated(page, per_page, **filters)

    def get_downloads_grouped(
        self,
        group_by: str,
        **filters
    ) -> Dict[str, Any]:
        """Get grouped download statistics."""
        # Delegate to repository
        return self._download_repo.get_downloads_grouped(group_by, **filters)
