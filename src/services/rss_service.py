"""
RSS service module.

Provides RSS/Atom feed parsing and item filtering functionality.
"""

import base64
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from src.core.exceptions import RSSError
from src.core.interfaces.adapters import IRSSParser, RSSItem
from src.core.interfaces.repositories import IDownloadRepository

logger = logging.getLogger(__name__)


class RSSService(IRSSParser):
    """
    RSS service implementation.

    Implements IRSSParser interface to parse RSS/Atom feeds
    and filter already-processed items.

    Example:
        >>> service = RSSService(download_repo)
        >>> items = service.parse_feed('https://example.com/rss')
        >>> new_items = service.filter_new_items(items)
    """

    # HTTP request configuration
    DEFAULT_TIMEOUT = 30
    DEFAULT_USER_AGENT = 'AniDown/1.0'

    # XML namespaces for various RSS formats
    NAMESPACES = {
        '': 'http://www.w3.org/2005/Atom',
        'atom': 'http://www.w3.org/2005/Atom',
        'media': 'http://search.yahoo.com/mrss/',
        'torrent': 'http://xmlns.ezrss.it/0.1/',
    }

    def __init__(
        self,
        download_repo: IDownloadRepository,
        timeout: int = DEFAULT_TIMEOUT
    ):
        """
        Initialize the RSS service.

        Args:
            download_repo: Repository for checking existing downloads.
            timeout: HTTP request timeout in seconds.
        """
        self._download_repo = download_repo
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self.DEFAULT_USER_AGENT
        })
        self._timeout = timeout

    def parse_feed(self, rss_url: str) -> List[RSSItem]:
        """
        Parse an RSS/Atom feed.

        Supports both RSS 2.0 and Atom formats. Automatically detects
        the format based on the root element.

        Args:
            rss_url: URL of the RSS feed.

        Returns:
            List of RSSItem objects parsed from the feed.

        Raises:
            RSSError: If fetching or parsing fails.
        """
        try:
            logger.info(f'🔍 正在解析RSS链接: {rss_url}')
            response = self._session.get(rss_url, timeout=self._timeout)

            if response.status_code != 200:
                logger.error(f'❌ RSS请求失败: {response.status_code}')
                raise RSSError(f'RSS request failed with status {response.status_code}')

            # Parse XML
            root = ET.fromstring(response.content)

            items = []

            # Detect feed format and parse accordingly
            if root.tag == 'feed' or root.tag.endswith('}feed'):
                # Atom format
                items = self._parse_atom_feed(root)
            else:
                # RSS 2.0 format
                items = self._parse_rss_feed(root)

            logger.info(f'✅ RSS解析完成，获取到{len(items)}个项目')
            return items

        except requests.RequestException as e:
            logger.error(f'❌ RSS请求异常: {e}')
            raise RSSError(f'Failed to fetch RSS feed: {e}')
        except ET.ParseError as e:
            logger.error(f'❌ RSS XML解析异常: {e}')
            raise RSSError(f'Failed to parse RSS XML: {e}')
        except Exception as e:
            logger.error(f'❌ RSS解析异常: {e}')
            raise RSSError(f'RSS parsing error: {e}')

    def filter_new_items(self, items: List[RSSItem]) -> List[RSSItem]:
        """
        Filter out items that already exist in the database.

        Checks each item's hash against the download repository.

        Args:
            items: List of RSS items to filter.

        Returns:
            List of new items not present in the database.
        """
        new_items = []

        for item in items:
            hash_id = item.hash
            if not hash_id:
                # Try to extract hash from URL
                hash_id = self.extract_hash_from_url(item.effective_url)

            if not hash_id:
                # Cannot determine hash, skip item
                logger.debug(f'⚠️ 无法获取 hash: {item.title[:50]}...')
                continue

            # Check if already exists in database
            existing = self._download_repo.get_by_hash(hash_id)
            if not existing:
                new_items.append(item)

        logger.info(f'✅ 过滤完成，找到{len(new_items)}个新项目')
        return new_items

    def extract_hash_from_url(self, url: str) -> str:
        """
        Extract torrent hash from a URL or magnet link.

        Supports:
        - Magnet links with btih (hex or base32 encoded)
        - Torrent URLs with hash in filename
        - URLs containing 40-character hex hash

        Args:
            url: Torrent URL or magnet link.

        Returns:
            Torrent hash string (lowercase hex), empty if not found.
        """
        if not url:
            return ''

        # Handle magnet links
        if url.startswith('magnet:'):
            return self._extract_hash_from_magnet(url)

        # Handle torrent URLs
        return self._extract_hash_from_torrent_url(url)

    def _parse_rss_feed(self, root: ET.Element) -> List[RSSItem]:
        """
        Parse RSS 2.0 format feed.

        Args:
            root: XML root element.

        Returns:
            List of parsed RSSItem objects.
        """
        items = []
        channel_items = root.findall('.//item')

        for item_elem in channel_items:
            parsed = self._parse_rss_item(item_elem)
            if parsed:
                items.append(parsed)

        return items

    def _parse_atom_feed(self, root: ET.Element) -> List[RSSItem]:
        """
        Parse Atom format feed.

        Args:
            root: XML root element.

        Returns:
            List of parsed RSSItem objects.
        """
        items = []

        # Find entries (with or without namespace)
        entries = root.findall('.//entry')
        if not entries:
            entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')

        for entry in entries:
            parsed = self._parse_atom_entry(entry)
            if parsed:
                items.append(parsed)

        return items

    def _parse_rss_item(self, item: ET.Element) -> Optional[RSSItem]:
        """
        Parse an RSS item element.

        Args:
            item: XML element for the item.

        Returns:
            RSSItem or None if required fields are missing.
        """
        try:
            title = self._get_text(item, 'title', '')
            link = self._get_text(item, 'link', '')
            description = self._get_text(item, 'description', '')
            pub_date = self._get_text(item, 'pubDate', '')

            # Get torrent URL from enclosure
            torrent_url = ''
            enclosure = item.find('enclosure')
            if enclosure is not None:
                enc_type = enclosure.get('type', '')
                if 'torrent' in enc_type or enc_type == 'application/x-bittorrent':
                    torrent_url = enclosure.get('url', '')

            # Try ezRSS namespace for torrent info
            if not torrent_url:
                torrent_elem = item.find(
                    'torrent:magnetURI',
                    {'torrent': 'http://xmlns.ezrss.it/0.1/'}
                )
                if torrent_elem is not None and torrent_elem.text:
                    torrent_url = torrent_elem.text

            # Determine effective URL
            effective_url = torrent_url or link
            hash_id = self.extract_hash_from_url(effective_url)

            return RSSItem(
                title=title,
                link=link,
                description=description,
                torrent_url=torrent_url,
                hash=hash_id,
                pub_date=pub_date
            )

        except Exception as e:
            logger.error(f'❌ RSS item解析异常: {e}')
            return None

    def _parse_atom_entry(self, entry: ET.Element) -> Optional[RSSItem]:
        """
        Parse an Atom entry element.

        Args:
            entry: XML element for the entry.

        Returns:
            RSSItem or None if required fields are missing.
        """
        try:
            # Get title
            title = self._get_text_with_ns(entry, 'title', '')

            # Get link (can be in href attribute)
            link = ''
            link_elem = entry.find('link') or entry.find(
                '{http://www.w3.org/2005/Atom}link'
            )
            if link_elem is not None:
                link = link_elem.get('href', '') or self._get_text(link_elem, '', '')

            # Get description (summary in Atom)
            description = self._get_text_with_ns(entry, 'summary', '')

            # Get publication date
            pub_date = self._get_text_with_ns(entry, 'published', '')
            if not pub_date:
                pub_date = self._get_text_with_ns(entry, 'updated', '')

            # Find torrent URL from media:content
            torrent_url = ''
            for content in entry.findall(
                'media:content',
                {'media': 'http://search.yahoo.com/mrss/'}
            ):
                if content.get('type') == 'application/x-bittorrent':
                    torrent_url = content.get('url', '')
                    break

            # Also check for enclosure-style links
            if not torrent_url:
                for link_elem in entry.findall('link') or entry.findall(
                    '{http://www.w3.org/2005/Atom}link'
                ):
                    rel = link_elem.get('rel', '')
                    if rel == 'enclosure':
                        torrent_url = link_elem.get('href', '')
                        break

            # Fallback: check if main link is a torrent
            if not torrent_url and link:
                if link.endswith('.torrent') or 'torrent' in link.lower():
                    torrent_url = link

            # Extract hash
            effective_url = torrent_url or link
            hash_id = self.extract_hash_from_url(effective_url)

            return RSSItem(
                title=title,
                link=link,
                description=description,
                torrent_url=torrent_url,
                hash=hash_id,
                pub_date=pub_date
            )

        except Exception as e:
            logger.error(f'❌ Atom entry解析异常: {e}')
            return None

    def _extract_hash_from_magnet(self, magnet_url: str) -> str:
        """
        Extract hash from a magnet link.

        Supports both hex and base32 encoded btih.

        Args:
            magnet_url: Magnet URI.

        Returns:
            Lowercase hex hash string.
        """
        hash_match = re.search(r'urn:btih:([a-zA-Z0-9]+)', magnet_url, re.IGNORECASE)
        if not hash_match:
            return ''

        hash_part = hash_match.group(1)

        # Check if it's base32 encoded (32 chars)
        if self._is_base32_hash(hash_part):
            try:
                # Pad base32 if needed
                padded = hash_part.upper() + '=' * (-len(hash_part) % 8)
                decoded_bytes = base64.b32decode(padded)
                return decoded_bytes.hex().lower()
            except Exception:
                pass

        # Check if it's hex (40 chars)
        if len(hash_part) == 40 and all(c in '0123456789abcdefABCDEF' for c in hash_part):
            return hash_part.lower()

        return ''

    def _extract_hash_from_torrent_url(self, url: str) -> str:
        """
        Extract hash from a torrent URL.

        Args:
            url: Torrent file URL.

        Returns:
            Lowercase hex hash string.
        """
        parsed_url = urlparse(url)
        path = parsed_url.path

        # Try to get hash from filename
        if '/' in path:
            filename = path.split('/')[-1]
            if filename.endswith('.torrent'):
                hash_part = filename[:-8]
                if len(hash_part) == 40 and all(
                    c in '0123456789abcdefABCDEF' for c in hash_part
                ):
                    return hash_part.lower()

        # Search for 40-char hex pattern in URL
        hash_match = re.search(r'([a-f0-9]{40})', url, re.IGNORECASE)
        if hash_match:
            return hash_match.group(1).lower()

        return ''

    def _is_base32_hash(self, hash_str: str) -> bool:
        """
        Check if a string is base32 encoded hash.

        Args:
            hash_str: String to check.

        Returns:
            True if it appears to be base32 encoded.
        """
        if len(hash_str) != 32:
            return False
        base32_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')
        return all(c.upper() in base32_chars for c in hash_str)

    def _get_text(
        self,
        element: ET.Element,
        tag: str,
        default: str = ''
    ) -> str:
        """
        Get text content from an XML element.

        Args:
            element: Parent element.
            tag: Tag name to find.
            default: Default value if not found.

        Returns:
            Text content or default.
        """
        if not tag:
            return element.text or default
        child = element.find(tag)
        return child.text if child is not None and child.text else default

    def _get_text_with_ns(
        self,
        element: ET.Element,
        tag: str,
        default: str = ''
    ) -> str:
        """
        Get text content from an XML element with namespace fallback.

        Args:
            element: Parent element.
            tag: Tag name to find.
            default: Default value if not found.

        Returns:
            Text content or default.
        """
        # Try without namespace
        child = element.find(tag)
        if child is not None and child.text:
            return child.text

        # Try with Atom namespace
        child = element.find(f'{{http://www.w3.org/2005/Atom}}{tag}')
        if child is not None and child.text:
            return child.text

        return default
