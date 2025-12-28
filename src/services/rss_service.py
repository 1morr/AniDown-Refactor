"""
RSS service module.

Provides RSS/Atom feed parsing, item filtering, and hash extraction functionality.
"""

import base64
import logging
import re
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests

from src.core.exceptions import RSSError
from src.core.interfaces.adapters import IRSSParser, RSSItem
from src.core.interfaces.repositories import IDownloadRepository

if TYPE_CHECKING:
    from src.services.rss_service import RSSService

logger = logging.getLogger(__name__)


@dataclass
class CachedHash:
    """缓存的 Hash 条目。"""
    hash_id: str
    timestamp: float


class HashExtractor:
    """
    Hash 提取服务，支持缓存和并行批量获取。

    用于 RSS 预览时快速获取 torrent hash，优化用户体验。

    Example:
        >>> extractor = HashExtractor(rss_service)
        >>> hashes = extractor.batch_extract(['url1', 'url2', 'url3'])
        >>> print(hashes)  # {'url1': 'hash1', 'url2': 'hash2', ...}
    """

    def __init__(
        self,
        rss_service: 'RSSService',
        cache_ttl: int = 3600,
        max_workers: int = 10,
        fetch_timeout: int = 10
    ):
        """
        初始化 HashExtractor。

        Args:
            rss_service: RSS 服务实例，用于调用底层提取方法。
            cache_ttl: 缓存过期时间（秒），默认 1 小时。
            max_workers: 并行下载的最大线程数，默认 10。
            fetch_timeout: 单个下载超时时间（秒），默认 10 秒。
        """
        self._rss_service = rss_service
        self._cache: dict[str, CachedHash] = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = cache_ttl
        self._max_workers = max_workers
        self._fetch_timeout = fetch_timeout

    def batch_extract(
        self,
        urls: list[str],
        skip_slow_fetch: bool = False
    ) -> dict[str, str]:
        """
        批量提取多个 URL 的 hash。

        优先使用缓存和快速 URL 解析，对需要下载的 URL 并行处理。

        Args:
            urls: 需要提取 hash 的 URL 列表。
            skip_slow_fetch: 是否跳过需要下载 torrent 的慢速提取。

        Returns:
            URL 到 hash 的映射字典。
        """
        results: dict[str, str] = {}
        urls_to_fetch: list[str] = []
        current_time = time()

        # 统计计数
        stats = {'cache': 0, 'fast': 0, 'fetch': 0, 'skipped': 0}

        # 1. 先从缓存和 URL 模式中快速提取
        for url in urls:
            if not url:
                continue

            # 检查缓存
            cached = self._get_from_cache(url, current_time)
            if cached:
                results[url] = cached
                stats['cache'] += 1
                logger.debug(f'📦 [cache] hash={cached[:8]}... url={url[:50]}...')
                continue

            # 快速 URL 模式提取
            fast_hash = self._rss_service.extract_hash_from_url(url)
            if fast_hash:
                results[url] = fast_hash
                self._add_to_cache(url, fast_hash, current_time)
                stats['fast'] += 1
                logger.debug(f'⚡ [fast] hash={fast_hash[:8]}... url={url[:50]}...')
            elif not skip_slow_fetch and url.endswith('.torrent'):
                urls_to_fetch.append(url)
            else:
                stats['skipped'] += 1

        # 2. 对需要下载的 URL 并行处理
        if urls_to_fetch:
            logger.debug(f'🔄 开始并行下载 {len(urls_to_fetch)} 个 torrent 文件提取 hash')
            fetched = self._parallel_fetch(urls_to_fetch)
            for url, hash_id in fetched.items():
                results[url] = hash_id
                self._add_to_cache(url, hash_id, current_time)
                stats['fetch'] += 1
                logger.debug(f'🌐 [fetch] hash={hash_id[:8]}... url={url[:50]}...')

        # 输出统计信息
        logger.debug(
            f'📊 HashExtractor 统计: '
            f'cache={stats["cache"]}, fast={stats["fast"]}, '
            f'fetch={stats["fetch"]}, skipped={stats["skipped"]}, '
            f'total={len(results)}'
        )

        return results

    def _get_from_cache(self, url: str, current_time: float) -> str | None:
        """从缓存获取 hash，检查 TTL。"""
        with self._cache_lock:
            cached = self._cache.get(url)
            if cached and (current_time - cached.timestamp) < self._cache_ttl:
                return cached.hash_id
            return None

    def _add_to_cache(self, url: str, hash_id: str, current_time: float) -> None:
        """添加 hash 到缓存。"""
        with self._cache_lock:
            self._cache[url] = CachedHash(hash_id=hash_id, timestamp=current_time)

    def _parallel_fetch(self, urls: list[str]) -> dict[str, str]:
        """并行下载 torrent 文件并提取 hash。"""
        results: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_url = {
                executor.submit(
                    self._rss_service._fetch_hash_from_torrent_file, url
                ): url
                for url in urls
            }

            for future in as_completed(future_to_url, timeout=30):
                url = future_to_url[future]
                try:
                    hash_id = future.result(timeout=self._fetch_timeout)
                    if hash_id:
                        results[url] = hash_id
                except Exception as e:
                    logger.debug(f'⚠️ [fetch] 失败: {url[:50]}... - {e}')

        return results

    def clear_cache(self) -> None:
        """清空缓存。"""
        with self._cache_lock:
            self._cache.clear()
            logger.debug('🧹 HashExtractor 缓存已清空')

    def get_cache_stats(self) -> dict[str, int]:
        """获取缓存统计信息。"""
        with self._cache_lock:
            return {
                'size': len(self._cache),
                'ttl': self._cache_ttl
            }


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
        'nyaa': 'https://nyaa.si/xmlns/nyaa',
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
        self._hash_extractor = HashExtractor(self)

    def parse_feed(self, rss_url: str) -> list[RSSItem]:
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

    def filter_new_items(self, items: list[RSSItem]) -> list[RSSItem]:
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

    def batch_extract_hashes(
        self,
        items: list[RSSItem],
        skip_slow_fetch: bool = False
    ) -> dict[str, str]:
        """
        批量提取 RSS 项目的 hash。

        使用缓存和并行处理优化性能。

        Args:
            items: RSS 项目列表。
            skip_slow_fetch: 是否跳过需要下载 torrent 文件的慢速提取。

        Returns:
            URL 到 hash 的映射。
        """
        urls = []
        for item in items:
            if not item.hash:
                effective_url = item.torrent_url or item.link
                if effective_url:
                    urls.append(effective_url)

        return self._hash_extractor.batch_extract(urls, skip_slow_fetch)

    def get_hash_extractor_stats(self) -> dict[str, int]:
        """获取 hash 提取器的缓存统计。"""
        return self._hash_extractor.get_cache_stats()

    def clear_hash_extractor_cache(self) -> None:
        """清空 hash 提取器的缓存。"""
        self._hash_extractor.clear_cache()

    def ensure_valid_hash(self, hash_id: str, torrent_url: str) -> str:
        """
        Ensure a valid torrent hash is available.

        If the provided hash is invalid (empty or less than 32 chars),
        attempts to download the torrent file and extract the real info_hash.

        This method should be called during actual processing, not during
        RSS parsing, to avoid slowing down previews.

        Args:
            hash_id: Current hash value (may be empty or invalid).
            torrent_url: URL to the torrent file.

        Returns:
            Valid hash string (40 chars), or empty if unable to obtain.
        """
        # Check if hash is already valid
        if hash_id and len(hash_id) >= 32:
            return hash_id

        # Try to download torrent file and extract hash
        if torrent_url and torrent_url.endswith('.torrent'):
            fetched_hash = self._fetch_hash_from_torrent_file(torrent_url)
            if fetched_hash:
                logger.debug(f'🔑 从torrent文件获取hash: {fetched_hash[:8]}...')
                return fetched_hash

        return hash_id

    def _parse_rss_feed(self, root: ET.Element) -> list[RSSItem]:
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

    def _parse_atom_feed(self, root: ET.Element) -> list[RSSItem]:
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

    def _parse_rss_item(self, item: ET.Element) -> RSSItem | None:
        """
        Parse an RSS item element.

        Supports multiple RSS sources:
        - Standard RSS 2.0 with enclosure
        - nyaa.si with nyaa:infoHash tag
        - bangumi.moe with hash in link
        - share.acgnx.se with magnet in enclosure
        - acg.rip with torrent URL in enclosure

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
            hash_id = ''
            enclosure = item.find('enclosure')
            if enclosure is not None:
                enc_url = enclosure.get('url', '')
                enc_type = enclosure.get('type', '')
                if enc_url:
                    # Check if enclosure URL is a magnet link (share.acgnx.se)
                    if enc_url.startswith('magnet:'):
                        torrent_url = enc_url
                        hash_id = self._extract_hash_from_magnet(enc_url)
                    elif 'torrent' in enc_type or enc_type == 'application/x-bittorrent':
                        torrent_url = enc_url

            # Try ezRSS namespace for torrent info
            if not torrent_url:
                torrent_elem = item.find(
                    'torrent:magnetURI',
                    {'torrent': 'http://xmlns.ezrss.it/0.1/'}
                )
                if torrent_elem is not None and torrent_elem.text:
                    torrent_url = torrent_elem.text

            # Try nyaa:infoHash namespace (nyaa.si)
            if not hash_id:
                nyaa_hash = item.find(
                    'nyaa:infoHash',
                    {'nyaa': 'https://nyaa.si/xmlns/nyaa'}
                )
                if nyaa_hash is not None and nyaa_hash.text:
                    hash_id = nyaa_hash.text.lower()

            # Fallback: extract hash from effective URL
            if not hash_id:
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

    def _parse_atom_entry(self, entry: ET.Element) -> RSSItem | None:
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

        Supports multiple torrent URL formats:
        - Standard torrent URLs with hash in filename
        - URLs containing 40-character hex hash anywhere

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

    def _fetch_hash_from_torrent_file(self, torrent_url: str) -> str:
        """
        Download a torrent file and extract the info hash.

        This is used for sites like acg.rip where the hash is not
        available in the URL or RSS metadata.

        Args:
            torrent_url: URL to the torrent file.

        Returns:
            Lowercase hex hash string, empty if failed.
        """
        import hashlib

        try:
            response = self._session.get(torrent_url, timeout=self._timeout)
            if response.status_code != 200:
                logger.debug(f'⚠️ 无法下载torrent文件: {torrent_url}')
                return ''

            torrent_data = response.content

            # Parse bencode and extract info hash
            info_dict = self._extract_info_from_bencode(torrent_data)
            if info_dict:
                # Re-encode the info dict and calculate SHA1 hash
                info_bencoded = self._bencode(info_dict)
                info_hash = hashlib.sha1(info_bencoded).hexdigest().lower()
                logger.debug(f'✅ 从torrent文件提取hash: {info_hash}')
                return info_hash

        except Exception as e:
            logger.debug(f'⚠️ 从torrent文件提取hash失败: {e}')

        return ''

    def _extract_info_from_bencode(self, data: bytes) -> dict[str, Any] | None:
        """
        Parse bencoded data and extract the 'info' dictionary.

        Args:
            data: Bencoded torrent file data.

        Returns:
            The 'info' dictionary if found, None otherwise.
        """
        try:
            decoded, _ = self._bdecode(data, 0)
            if isinstance(decoded, dict) and b'info' in decoded:
                return decoded[b'info']
        except Exception:
            pass
        return None

    def _bdecode(self, data: bytes, idx: int) -> tuple:
        """
        Decode bencoded data starting at the given index.

        Args:
            data: Bencoded data.
            idx: Starting index.

        Returns:
            Tuple of (decoded_value, next_index).
        """
        char = chr(data[idx])

        if char == 'd':  # Dictionary
            idx += 1
            result = {}
            while chr(data[idx]) != 'e':
                key, idx = self._bdecode(data, idx)
                value, idx = self._bdecode(data, idx)
                result[key] = value
            return result, idx + 1

        elif char == 'l':  # List
            idx += 1
            result = []
            while chr(data[idx]) != 'e':
                value, idx = self._bdecode(data, idx)
                result.append(value)
            return result, idx + 1

        elif char == 'i':  # Integer
            idx += 1
            end = data.index(b'e', idx)
            return int(data[idx:end]), end + 1

        elif char.isdigit():  # String
            colon = data.index(b':', idx)
            length = int(data[idx:colon])
            idx = colon + 1
            return data[idx:idx + length], idx + length

        raise ValueError(f'Invalid bencode at position {idx}')

    def _bencode(self, data: Any) -> bytes:
        """
        Encode data into bencode format.

        Args:
            data: Data to encode (dict, list, int, bytes, or str).

        Returns:
            Bencoded bytes.
        """
        if isinstance(data, dict):
            result = b'd'
            for key in sorted(data.keys()):
                result += self._bencode(key) + self._bencode(data[key])
            return result + b'e'

        elif isinstance(data, list):
            result = b'l'
            for item in data:
                result += self._bencode(item)
            return result + b'e'

        elif isinstance(data, int):
            return f'i{data}e'.encode()

        elif isinstance(data, bytes):
            return f'{len(data)}:'.encode() + data

        elif isinstance(data, str):
            encoded = data.encode('utf-8')
            return f'{len(encoded)}:'.encode() + encoded

        raise ValueError(f'Cannot bencode type {type(data)}')

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
