"""
RSS processing service.

Handles all RSS feed parsing, filtering, and download initiation.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.core.config import RSSFeed
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
    AniDownError,
    AnimeInfoExtractionError,
    TorrentAddError,
)
from src.core.interfaces.adapters import (
    IDownloadClient,
    IRSSParser,
    ITitleParser,
    RSSItem,
)
from src.core.interfaces.repositories import (
    IAnimeRepository,
    IDownloadRepository,
    IHardlinkRepository,
)
from src.services.download.download_notifier import DownloadNotifier
from src.services.file.path_builder import PathBuilder
from src.services.rss.filter_service import FilterService

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
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        processed = self.new_items + self.failed_items
        if processed == 0:
            return 0.0
        return (self.new_items / processed) * 100


class RSSProcessor:
    """
    RSS processing service.

    Handles all RSS-related operations:
    - Feed parsing and filtering
    - New anime detection and AI parsing
    - Existing anime matching
    - Download initiation
    """

    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        history_repo: IHardlinkRepository,
        title_parser: ITitleParser,
        download_client: IDownloadClient,
        rss_service: IRSSParser,
        filter_service: FilterService,
        path_builder: PathBuilder,
        notifier: DownloadNotifier
    ):
        """
        Initialize the RSS processor.

        Args:
            anime_repo: Repository for anime information.
            download_repo: Repository for download records.
            history_repo: Repository for history records.
            title_parser: AI title parser.
            download_client: Download client (qBittorrent).
            rss_service: RSS parser service.
            filter_service: Content filter service.
            path_builder: Path construction service.
            notifier: Download notifier service.
        """
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._history_repo = history_repo
        self._title_parser = title_parser
        self._download_client = download_client
        self._rss_service = rss_service
        self._filter_service = filter_service
        self._path_builder = path_builder
        self._notifier = notifier

    def process_feeds(
        self,
        rss_feeds: list,
        trigger_type: str = '定时触发',
        blocked_keywords: str | None = None,
        blocked_regex: str | None = None
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
        logger.info(f'📤 准备发送RSS开始通知，共 {len(feed_objects)} 个订阅源')
        for feed in feed_objects:
            self._notifier.notify_rss_start(trigger_type, feed.url)

        # Parse and process each feed
        all_items = []
        total_items_found = 0

        for feed in feed_objects:
            try:
                items = self._rss_service.parse_feed(feed.url)
                total_items_found += len(items)

                # Process each item
                new_items = self._filter_feed_items(items, feed, history_id)
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
            self._notifier.notify_completion(0, 0, [])
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
        self._notifier.notify_completion(
            result.new_items, len(all_items), result.errors
        )

        return result

    def process_single_rss_item(
        self,
        item: dict[str, Any],
        trigger_type: str = 'queue'
    ) -> bool:
        """
        Process a single RSS item (called from queue).

        Args:
            item: RSS item dictionary with title, torrent_url, hash, media_type etc.
            trigger_type: Trigger type.

        Returns:
            True if processing was successful, False otherwise.

        Raises:
            Exception: When processing fails, contains error details.
        """
        title = item.get('title', '')
        logger.info(f'🔄 [队列] 处理项目: {title[:50]}...')

        try:
            # Call internal processing method
            success = self._process_single_item(item)

            if success:
                logger.info(f'✅ [队列] 项目处理成功: {title[:50]}...')
            else:
                logger.warning(f'⚠️ [队列] 项目处理失败: {title[:50]}...')

            return success

        except AniDownError as e:
            # Expected business error, log message only
            logger.error(f'❌ [队列] 处理项目失败: {title[:50]}... - {e}')
            raise
        except Exception as e:
            # Unexpected error, log full stack for debugging
            logger.error(f'❌ [队列] 处理项目失败 (意外错误): {title[:50]}... - {e}', exc_info=True)
            raise

    def process_manual_anime_rss(
        self,
        rss_url: str,
        short_title: str,
        subtitle_group: str,
        season: int,
        category: str,
        trigger_type: str,
        blocked_keywords: str | None = None,
        blocked_regex: str | None = None,
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
            save_path = self._path_builder.build_download_path(
                title=short_title,
                season=season,
                category=category,
                media_type=media_type
            )

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

                    # Save torrent files information
                    self._save_torrent_files_on_add(hash_id, anime_id)

                    result.new_items += 1
                    self._history_repo.insert_rss_detail(history_id, title, 'success')

                    # Send notification
                    self._notifier.notify_download_start(
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

    # ==================== Private Methods ====================

    def _normalize_feeds(
        self,
        feeds: list,
        blocked_keywords: str | None,
        blocked_regex: str | None
    ) -> list[RSSFeed]:
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
        items: list[RSSItem],
        feed: RSSFeed,
        history_id: int
    ) -> list[dict[str, Any]]:
        """Filter and process feed items."""
        new_items = []

        # Debug log: show filter configuration
        if feed.blocked_keywords or feed.blocked_regex:
            logger.info('🔍 过滤器已启用:')
            if feed.blocked_keywords:
                keywords_preview = feed.blocked_keywords.replace('\n', ', ')[:100]
                logger.info(f'  屏蔽词: {keywords_preview}')
            if feed.blocked_regex:
                regex_preview = feed.blocked_regex.replace('\n', ', ')[:100]
                logger.info(f'  正则: {regex_preview}')
        else:
            logger.debug('📋 未配置过滤器')

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

    def _process_single_item(self, item: dict[str, Any]) -> bool:
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

    def _process_new_anime(self, item: dict[str, Any], media_type: str = 'anime') -> bool:
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

        # Ensure valid hash (may need to download torrent file)
        hash_id = self._rss_service.ensure_valid_hash(hash_id, torrent_url)

        try:
            # AI title parsing
            parse_result = self._title_parser.parse(title)
            if not parse_result:
                raise AnimeInfoExtractionError('AI解析失败')

            # Send AI usage notification
            self._notifier.notify_ai_usage(
                reason='新动漫标题解析',
                project_name=parse_result.clean_title,
                context='rss',
                operation='title_parsing'
            )

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
            save_path = self._path_builder.build_download_path(
                title=parse_result.clean_title,
                season=parse_result.season,
                category=parse_result.category,
                media_type=media_type
            )

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

            # Save torrent files information
            self._save_torrent_files_on_add(hash_id, anime_id)

            # Send download task notification (immediate)
            self._notifier.notify_download_task(
                project_name=title,
                hash_id=hash_id,
                anime_title=parse_result.clean_title,
                subtitle_group=parse_result.subtitle_group,
                download_path=save_path,
                season=parse_result.season,
                episode=parse_result.episode
            )

            return True

        except Exception as e:
            logger.error(f'处理新动漫失败: {e}')
            raise

    def _process_existing_anime(
        self,
        item: dict[str, Any],
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

        # Ensure valid hash (may need to download torrent file)
        hash_id = self._rss_service.ensure_valid_hash(hash_id, torrent_url)

        anime_id = anime_info.id
        anime_short_title = anime_info.short_title  # Use short_title for file naming
        anime_subtitle_group = anime_info.subtitle_group_name
        anime_season = anime_info.season_number
        anime_category = 'movie' if anime_info.category == Category.MOVIE else 'tv'

        # Try to extract episode number from title (using database regex if available)
        episode = self._extract_episode_from_title(title, anime_id=anime_id)

        # Generate save path
        save_path = self._path_builder.build_download_path(
            title=anime_short_title,
            season=anime_season,
            category=anime_category
        )

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

        # Save torrent files information
        self._save_torrent_files_on_add(hash_id, anime_id)

        # Send download task notification (immediate)
        self._notifier.notify_download_task(
            project_name=title,
            hash_id=hash_id,
            anime_title=anime_short_title,
            subtitle_group=anime_subtitle_group,
            download_path=save_path,
            season=anime_season,
            episode=episode
        )

        return True

    def _find_existing_anime(self, title: str) -> AnimeInfo | None:
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
        long_title: str | None = None,
        subtitle_group: str = '',
        season: int = 1,
        category: str = 'tv',
        media_type: str = 'anime',
        tvdb_id: int | None = None
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
            tvdb_id=tvdb_id,
            created_at=datetime.now(UTC)
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
        is_multi_season: bool = False,
        requires_tvdb: bool = False
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
            requires_tvdb=requires_tvdb,
            download_time=datetime.now(UTC)
        )
        return self._download_repo.save(record)

    def _save_torrent_file(
        self,
        torrent_hash: str,
        file_path: str,
        file_size: int,
        anime_id: int | None
    ) -> None:
        """Save torrent file information."""
        # Determine file type based on extension
        file_type = 'other'
        file_lower = file_path.lower()

        if file_lower.endswith(('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')):
            file_type = 'video'
        elif file_lower.endswith(('.srt', '.ass', '.ssa', '.vtt', '.sub')):
            file_type = 'subtitle'

        # Save to database via repository
        try:
            self._download_repo.insert_torrent_file(
                torrent_hash=torrent_hash,
                file_path=file_path,
                file_size=file_size,
                file_type=file_type,
                anime_id=anime_id
            )
        except Exception as e:
            logger.warning(f'⚠️ Failed to save torrent file to database: {e}')

    def _save_torrent_files_on_add(
        self,
        hash_id: str,
        anime_id: int | None,
        max_retries: int = 5,
        retry_delay: float = 1.0
    ) -> None:
        """
        Save torrent file information when download starts.

        Waits for qBittorrent to parse the torrent and retrieves file list.
        For magnet links, may need multiple retries to get metadata.

        Args:
            hash_id: Torrent hash.
            anime_id: Anime ID for records.
            max_retries: Maximum retry attempts for getting file list.
            retry_delay: Delay between retries in seconds.
        """
        logger.debug(f'💾 正在保存种子文件信息: {hash_id[:8]}...')

        torrent_files = []
        for attempt in range(max_retries):
            torrent_files = self._download_client.get_torrent_files(hash_id)
            if torrent_files:
                break
            # Wait and retry (torrent may still be loading metadata)
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                logger.debug(f'  重试获取文件列表 ({attempt + 2}/{max_retries})...')

        if not torrent_files:
            logger.warning(f'⚠️ 无法获取种子文件列表: {hash_id[:8]} (可能是磁力链接等待元数据)')
            return

        logger.info(f'📋 获取到 {len(torrent_files)} 个文件，正在保存到数据库...')
        for file_info in torrent_files:
            self._save_torrent_file(
                torrent_hash=hash_id,
                file_path=file_info.get('name', ''),
                file_size=file_info.get('size', 0),
                anime_id=anime_id
            )
        logger.debug(f'✅ 种子文件信息保存完成: {hash_id[:8]}')

    def _extract_episode_from_title(
        self,
        title: str,
        anime_id: int | None = None
    ) -> int | None:
        """
        Extract episode number from title.

        Args:
            title: Original title string.
            anime_id: Optional anime ID to use database-stored regex pattern.

        Returns:
            Episode number or None.
        """
        # First try using database-stored episode_regex if anime_id provided
        if anime_id:
            try:
                patterns = self._anime_repo.get_patterns(anime_id)
                if patterns and patterns.get('episode_regex'):
                    episode_regex = patterns['episode_regex']
                    match = re.search(episode_regex, title, re.IGNORECASE)
                    if match:
                        try:
                            return int(match.group(1))
                        except (ValueError, IndexError):
                            pass
                    logger.debug(f'📺 数据库正则 "{episode_regex}" 未匹配到集数')
            except Exception as e:
                logger.warning(f'⚠️ 获取数据库正则失败: {e}')

        # Fallback to default patterns
        default_patterns = [
            r'[\[\s](\d{1,3})[\]\s]',  # [01] or 01
            r'E(\d{1,3})',  # E01
            r'第(\d{1,3})[话集]',  # 第01话
            r'- (\d{1,3}) ',  # - 01
        ]

        for pattern in default_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return None
