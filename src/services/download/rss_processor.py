"""
RSS processor module.

Provides RSS feed parsing and download task creation functionality.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from xml.etree import ElementTree

import requests

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
from src.core.exceptions import AniDownError, RSSError
from src.core.interfaces.adapters import IDownloadClient, ITitleParser, TitleParseResult
from src.core.interfaces.notifications import IDownloadNotifier, IRSSNotifier, RSSNotification
from src.core.interfaces.repositories import IAnimeRepository, IDownloadRepository
from src.services.file.path_builder import PathBuilder

logger = logging.getLogger(__name__)


@dataclass
class RSSItem:
    """
    RSS feed item.

    Represents a single item from an RSS feed.

    Attributes:
        title: Item title.
        link: Torrent or magnet link.
        guid: Unique identifier for the item.
        pub_date: Publication date.
        description: Item description.
        hash_id: Torrent hash (if available in feed).
        size: File size in bytes.
    """
    title: str
    link: str
    guid: str = ''
    pub_date: Optional[datetime] = None
    description: str = ''
    hash_id: str = ''
    size: int = 0

    def __post_init__(self):
        # Generate GUID from link if not provided
        if not self.guid and self.link:
            self.guid = hashlib.md5(self.link.encode()).hexdigest()

    @property
    def is_magnet(self) -> bool:
        """Check if link is a magnet link."""
        return self.link.startswith('magnet:')

    @property
    def short_title(self) -> str:
        """Return shortened title for logging."""
        if len(self.title) > 60:
            return self.title[:57] + '...'
        return self.title


@dataclass
class RSSProcessResult:
    """
    RSS processing result.

    Contains statistics and details about RSS processing.
    """
    total_items: int = 0
    new_items: int = 0
    skipped_items: int = 0
    failed_items: int = 0
    added_downloads: List[str] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        processed = self.new_items + self.failed_items
        if processed == 0:
            return 0.0
        return (self.new_items / processed) * 100


class RSSProcessor:
    """
    RSS processor service.

    Fetches and processes RSS feeds to discover and download new anime episodes.
    Supports AI-based title parsing, fixed subscriptions, and manual downloads.
    """

    # Request configuration
    DEFAULT_TIMEOUT = 30
    DEFAULT_USER_AGENT = 'AniDown/1.0'

    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        download_client: IDownloadClient,
        title_parser: ITitleParser,
        path_builder: PathBuilder,
        rss_notifier: Optional[IRSSNotifier] = None,
        download_notifier: Optional[IDownloadNotifier] = None
    ):
        """
        Initialize the RSS processor.

        Args:
            anime_repo: Repository for anime information.
            download_repo: Repository for download records.
            download_client: Download client for adding torrents.
            title_parser: Title parser for extracting metadata.
            path_builder: Path builder for constructing paths.
            rss_notifier: Optional notifier for RSS events.
            download_notifier: Optional notifier for download events.
        """
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._download_client = download_client
        self._title_parser = title_parser
        self._path_builder = path_builder
        self._rss_notifier = rss_notifier
        self._download_notifier = download_notifier
        self._processed_guids: Set[str] = set()

    def process_feed(
        self,
        rss_url: str,
        trigger_type: str = 'scheduled'
    ) -> RSSProcessResult:
        """
        Process an RSS feed.

        Fetches the feed, parses items, and creates downloads for new anime.

        Args:
            rss_url: URL of the RSS feed.
            trigger_type: How the processing was triggered.

        Returns:
            RSSProcessResult with processing statistics.
        """
        result = RSSProcessResult()

        logger.info(f'🚀 Processing RSS feed: {rss_url}')

        # Notify start
        if self._rss_notifier:
            self._rss_notifier.notify_processing_start(
                RSSNotification(trigger_type=trigger_type, rss_url=rss_url)
            )

        try:
            # Fetch RSS feed
            items = self._fetch_feed(rss_url)
            result.total_items = len(items)

            if not items:
                logger.info(f'📭 No items found in RSS feed')
                return result

            logger.info(f'📥 Found {len(items)} items in RSS feed')

            # Process each item
            for item in items:
                try:
                    if self._is_processed(item):
                        result.skipped_items += 1
                        continue

                    success = self._process_item(item)
                    if success:
                        result.new_items += 1
                        result.added_downloads.append(item.title)
                    else:
                        result.skipped_items += 1

                except Exception as e:
                    logger.error(f'❌ Failed to process item: {item.short_title} - {e}')
                    result.failed_items += 1
                    result.errors.append({
                        'title': item.title,
                        'error': str(e)
                    })

            logger.info(
                f'✅ RSS processing complete: {result.new_items} new, '
                f'{result.skipped_items} skipped, {result.failed_items} failed'
            )

        except RSSError as e:
            logger.error(f'❌ RSS feed error: {e}')
            result.errors.append({'error': str(e)})
        except Exception as e:
            logger.exception(f'❌ Unexpected error processing RSS: {e}')
            result.errors.append({'error': str(e)})

        # Notify completion
        if self._rss_notifier:
            self._rss_notifier.notify_processing_complete(
                success_count=result.new_items,
                total_count=result.total_items,
                failed_items=result.errors
            )

        return result

    def _fetch_feed(self, url: str) -> List[RSSItem]:
        """
        Fetch and parse RSS feed.

        Args:
            url: RSS feed URL.

        Returns:
            List of RSS items.

        Raises:
            RSSError: If fetching or parsing fails.
        """
        try:
            response = requests.get(
                url,
                timeout=self.DEFAULT_TIMEOUT,
                headers={'User-Agent': self.DEFAULT_USER_AGENT}
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise RSSError(f'Failed to fetch RSS feed: {e}')

        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as e:
            raise RSSError(f'Failed to parse RSS XML: {e}')

        items = []
        for item_elem in root.findall('.//item'):
            item = self._parse_item(item_elem)
            if item:
                items.append(item)

        return items

    def _parse_item(self, item_elem: ElementTree.Element) -> Optional[RSSItem]:
        """
        Parse an RSS item element.

        Args:
            item_elem: XML element for the item.

        Returns:
            RSSItem or None if required fields are missing.
        """
        title = item_elem.findtext('title', '')
        link = item_elem.findtext('link', '')

        if not title or not link:
            return None

        # Try to get enclosure link if main link is not a torrent/magnet
        enclosure = item_elem.find('enclosure')
        if enclosure is not None and not (link.endswith('.torrent') or link.startswith('magnet:')):
            enclosure_url = enclosure.get('url', '')
            if enclosure_url:
                link = enclosure_url

        guid = item_elem.findtext('guid', '')
        description = item_elem.findtext('description', '')

        # Parse publication date
        pub_date_str = item_elem.findtext('pubDate', '')
        pub_date = self._parse_date(pub_date_str) if pub_date_str else None

        # Try to extract hash from magnet link
        hash_id = ''
        if link.startswith('magnet:'):
            match = re.search(r'btih:([a-fA-F0-9]{40})', link)
            if match:
                hash_id = match.group(1).lower()

        # Try to get size from enclosure
        size = 0
        if enclosure is not None:
            try:
                size = int(enclosure.get('length', 0))
            except ValueError:
                pass

        return RSSItem(
            title=title,
            link=link,
            guid=guid,
            pub_date=pub_date,
            description=description,
            hash_id=hash_id,
            size=size
        )

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse RSS date string.

        Args:
            date_str: Date string in RSS format.

        Returns:
            datetime object or None.
        """
        # Common RSS date formats
        formats = [
            '%a, %d %b %Y %H:%M:%S %z',
            '%a, %d %b %Y %H:%M:%S GMT',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%d %H:%M:%S'
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def _is_processed(self, item: RSSItem) -> bool:
        """
        Check if an RSS item has already been processed.

        Args:
            item: RSS item to check.

        Returns:
            True if already processed.
        """
        # Check in-memory cache
        if item.guid in self._processed_guids:
            return True

        # Check database by hash or GUID
        if item.hash_id:
            existing = self._download_repo.get_by_hash(item.hash_id)
            if existing:
                self._processed_guids.add(item.guid)
                return True

        return False

    def _process_item(self, item: RSSItem) -> bool:
        """
        Process a single RSS item.

        Args:
            item: RSS item to process.

        Returns:
            True if download was added successfully.
        """
        logger.debug(f'🔄 Processing item: {item.short_title}')

        # Parse title using AI/pattern parser
        parse_result = self._title_parser.parse(item.title)
        if not parse_result:
            logger.warning(f'⚠️ Could not parse title: {item.short_title}')
            return False

        # Find or create anime info
        anime_info = self._find_or_create_anime(parse_result)
        if not anime_info:
            return False

        # Build download path
        download_path = self._path_builder.build_download_path(
            title=parse_result.clean_title,
            season=parse_result.season,
            category=parse_result.category,
            media_type='anime',
            subtitle_group=parse_result.subtitle_group
        )

        # Add torrent
        success = self._add_torrent(item, download_path)
        if not success:
            return False

        # Create download record
        record = self._create_download_record(
            item=item,
            anime_info=anime_info,
            parse_result=parse_result,
            download_path=download_path
        )

        if record:
            self._processed_guids.add(item.guid)
            logger.info(f'✅ Added download: {item.short_title}')
            return True

        return False

    def _find_or_create_anime(
        self,
        parse_result: TitleParseResult
    ) -> Optional[AnimeInfo]:
        """
        Find existing anime or create new entry.

        Args:
            parse_result: Parsed title information.

        Returns:
            AnimeInfo entity.
        """
        # Try to find existing anime
        existing = self._anime_repo.find_by_title_and_group(
            title=parse_result.clean_title,
            subtitle_group=parse_result.subtitle_group
        )
        if existing:
            return existing

        # Create new anime info
        anime_info = AnimeInfo(
            title=AnimeTitle(
                original=parse_result.original_title,
                short=parse_result.clean_title,
                full=parse_result.full_title
            ),
            subtitle_group=SubtitleGroup(name=parse_result.subtitle_group),
            season=SeasonInfo(
                number=parse_result.season,
                category=Category.MOVIE if parse_result.is_movie else Category.TV
            ),
            category=Category.MOVIE if parse_result.is_movie else Category.TV,
            media_type=MediaType.ANIME,
            created_at=datetime.now(timezone.utc)
        )

        anime_id = self._anime_repo.save(anime_info)
        anime_info.id = anime_id

        logger.info(f'📺 Created anime entry: {parse_result.clean_title}')
        return anime_info

    def _add_torrent(self, item: RSSItem, save_path: str) -> bool:
        """
        Add torrent to download client.

        Args:
            item: RSS item with torrent link.
            save_path: Directory to save downloaded files.

        Returns:
            True if torrent was added successfully.
        """
        try:
            if item.is_magnet:
                result = self._download_client.add_magnet(item.link, save_path)
            else:
                result = self._download_client.add_torrent(item.link, save_path)

            return result is not None and result
        except Exception as e:
            logger.error(f'❌ Failed to add torrent: {e}')
            return False

    def _create_download_record(
        self,
        item: RSSItem,
        anime_info: AnimeInfo,
        parse_result: TitleParseResult,
        download_path: str
    ) -> Optional[DownloadRecord]:
        """
        Create download record in database.

        Args:
            item: RSS item.
            anime_info: Associated anime info.
            parse_result: Parsed title information.
            download_path: Download directory.

        Returns:
            Created DownloadRecord.
        """
        try:
            hash_value = item.hash_id or ''
            torrent_hash = TorrentHash(hash_value) if hash_value else None

            record = DownloadRecord(
                hash=torrent_hash,
                anime_id=anime_info.id,
                original_filename=item.title,
                anime_title=parse_result.clean_title,
                subtitle_group=parse_result.subtitle_group,
                season=parse_result.season,
                download_directory=download_path,
                status=DownloadStatus.PENDING,
                download_method=DownloadMethod.RSS_AI,
                download_time=datetime.now(timezone.utc)
            )

            record_id = self._download_repo.save(record)
            record.id = record_id

            return record

        except Exception as e:
            logger.error(f'❌ Failed to create download record: {e}')
            return None

    def clear_processed_cache(self) -> None:
        """Clear the in-memory processed items cache."""
        self._processed_guids.clear()
        logger.debug('Cleared processed items cache')
