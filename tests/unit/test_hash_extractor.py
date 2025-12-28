"""
Unit tests for HashExtractor class.

Tests hash extraction caching and parallel batch processing.
"""

from time import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.interfaces.adapters import RSSItem


class TestHashExtractor:
    """Test suite for HashExtractor."""

    @pytest.fixture
    def mock_rss_service(self):
        """Create a mock RSSService for testing."""
        mock = MagicMock()
        mock.extract_hash_from_url.return_value = ''
        mock._fetch_hash_from_torrent_file.return_value = ''
        return mock

    @pytest.fixture
    def hash_extractor(self, mock_rss_service):
        """Create HashExtractor with mocked dependencies."""
        from src.services.rss_service import HashExtractor
        return HashExtractor(
            rss_service=mock_rss_service,
            cache_ttl=3600,
            max_workers=5,
            fetch_timeout=5
        )

    def test_batch_extract_empty_list(self, hash_extractor):
        """Test batch extraction with empty URL list."""
        result = hash_extractor.batch_extract([])
        assert result == {}

    def test_batch_extract_fast_extraction(self, hash_extractor, mock_rss_service):
        """Test batch extraction using fast URL parsing."""
        # Setup: fast extraction returns hash for magnet URLs
        mock_rss_service.extract_hash_from_url.side_effect = lambda url: (
            'abc123' if 'magnet:' in url else ''
        )

        urls = [
            'magnet:?xt=urn:btih:abc123',
            'https://example.com/test.torrent'
        ]

        result = hash_extractor.batch_extract(urls, skip_slow_fetch=True)

        # Only the magnet URL should have a hash
        assert result.get('magnet:?xt=urn:btih:abc123') == 'abc123'
        assert 'https://example.com/test.torrent' not in result

    def test_batch_extract_cache_hit(self, hash_extractor, mock_rss_service):
        """Test that cached hashes are returned without re-extraction."""
        mock_rss_service.extract_hash_from_url.return_value = 'test_hash'

        urls = ['magnet:?xt=urn:btih:test_hash']

        # First call - should extract
        result1 = hash_extractor.batch_extract(urls)
        assert result1.get(urls[0]) == 'test_hash'
        assert mock_rss_service.extract_hash_from_url.call_count == 1

        # Reset mock to verify cache is used
        mock_rss_service.extract_hash_from_url.reset_mock()

        # Second call - should use cache
        result2 = hash_extractor.batch_extract(urls)
        assert result2.get(urls[0]) == 'test_hash'
        # extract_hash_from_url should not be called again
        assert mock_rss_service.extract_hash_from_url.call_count == 0

    def test_batch_extract_cache_expired(self, hash_extractor, mock_rss_service):
        """Test that expired cache entries trigger re-extraction."""
        from src.services.rss_service import CachedHash

        mock_rss_service.extract_hash_from_url.return_value = 'new_hash'

        # Add an expired cache entry
        url = 'magnet:?xt=urn:btih:old_hash'
        expired_time = time() - 7200  # 2 hours ago
        hash_extractor._cache[url] = CachedHash(
            hash_id='old_hash',
            timestamp=expired_time
        )

        result = hash_extractor.batch_extract([url])

        # Should have re-extracted since cache was expired
        assert result.get(url) == 'new_hash'
        mock_rss_service.extract_hash_from_url.assert_called_once_with(url)

    def test_batch_extract_parallel_fetch(self, hash_extractor, mock_rss_service):
        """Test parallel fetching of torrent URLs."""
        # Setup: fast extraction fails, need to download torrent
        mock_rss_service.extract_hash_from_url.return_value = ''
        mock_rss_service._fetch_hash_from_torrent_file.side_effect = lambda url: (
            f'hash_{url[-5:-8]}' if url.endswith('.torrent') else ''
        )

        urls = [
            'https://example.com/file1.torrent',
            'https://example.com/file2.torrent',
            'https://example.com/file3.torrent'
        ]

        result = hash_extractor.batch_extract(urls, skip_slow_fetch=False)

        # All torrent URLs should have been fetched
        assert mock_rss_service._fetch_hash_from_torrent_file.call_count == 3

    def test_batch_extract_skip_slow_fetch(self, hash_extractor, mock_rss_service):
        """Test skipping slow fetch when skip_slow_fetch=True."""
        mock_rss_service.extract_hash_from_url.return_value = ''

        urls = [
            'https://example.com/file1.torrent',
            'https://example.com/file2.torrent'
        ]

        result = hash_extractor.batch_extract(urls, skip_slow_fetch=True)

        # No torrent files should be downloaded
        assert mock_rss_service._fetch_hash_from_torrent_file.call_count == 0
        assert result == {}

    def test_clear_cache(self, hash_extractor, mock_rss_service):
        """Test clearing the cache."""
        mock_rss_service.extract_hash_from_url.return_value = 'test_hash'

        urls = ['magnet:?xt=urn:btih:test_hash']
        hash_extractor.batch_extract(urls)

        # Verify cache has entry
        stats = hash_extractor.get_cache_stats()
        assert stats['size'] == 1

        # Clear cache
        hash_extractor.clear_cache()

        # Verify cache is empty
        stats = hash_extractor.get_cache_stats()
        assert stats['size'] == 0

    def test_get_cache_stats(self, hash_extractor, mock_rss_service):
        """Test getting cache statistics."""
        mock_rss_service.extract_hash_from_url.side_effect = lambda url: url[-10:]

        urls = ['url1_hash123', 'url2_hash456', 'url3_hash789']
        hash_extractor.batch_extract(urls)

        stats = hash_extractor.get_cache_stats()

        assert stats['size'] == 3
        assert stats['ttl'] == 3600

    def test_batch_extract_handles_none_urls(self, hash_extractor):
        """Test that None and empty URLs are handled gracefully."""
        urls = [None, '', 'magnet:?xt=urn:btih:valid']
        hash_extractor._rss_service.extract_hash_from_url.side_effect = lambda url: (
            'valid_hash' if url and 'valid' in url else ''
        )

        result = hash_extractor.batch_extract(urls)

        # Only the valid URL should be processed
        assert 'magnet:?xt=urn:btih:valid' in result

    def test_parallel_fetch_exception_handling(self, hash_extractor, mock_rss_service):
        """Test that exceptions in parallel fetch are handled gracefully."""
        mock_rss_service.extract_hash_from_url.return_value = ''
        mock_rss_service._fetch_hash_from_torrent_file.side_effect = Exception(
            'Network error'
        )

        urls = ['https://example.com/file.torrent']

        # Should not raise exception
        result = hash_extractor.batch_extract(urls, skip_slow_fetch=False)

        # Result should be empty since fetch failed
        assert result == {}


class TestRSSServiceHashIntegration:
    """Integration tests for RSSService hash extraction methods."""

    @pytest.fixture
    def rss_service(self, download_repo):
        """Create RSSService with test dependencies."""
        from src.services.rss_service import RSSService
        return RSSService(download_repo=download_repo)

    def test_batch_extract_hashes_with_rss_items(self, rss_service):
        """Test batch_extract_hashes with RSSItem objects."""
        items = [
            RSSItem(
                title='Test Item 1',
                link='magnet:?xt=urn:btih:aaaa' + 'a' * 36,
                torrent_url='',
                hash='',
                pub_date=''
            ),
            RSSItem(
                title='Test Item 2',
                link='https://example.com/test.torrent',
                torrent_url='',
                hash='bbbb' + 'b' * 36,  # Already has hash
                pub_date=''
            )
        ]

        result = rss_service.batch_extract_hashes(items, skip_slow_fetch=True)

        # Item 1 should have extracted hash from magnet
        assert 'magnet:?xt=urn:btih:' + 'a' * 40 in result

    def test_get_hash_extractor_stats(self, rss_service):
        """Test getting hash extractor statistics."""
        stats = rss_service.get_hash_extractor_stats()

        assert 'size' in stats
        assert 'ttl' in stats

    def test_clear_hash_extractor_cache(self, rss_service):
        """Test clearing hash extractor cache."""
        # Extract some hashes to populate cache
        items = [
            RSSItem(
                title='Test',
                link='magnet:?xt=urn:btih:' + 'c' * 40,
                torrent_url='',
                hash='',
                pub_date=''
            )
        ]
        rss_service.batch_extract_hashes(items, skip_slow_fetch=True)

        # Clear cache
        rss_service.clear_hash_extractor_cache()

        # Verify cache is empty
        stats = rss_service.get_hash_extractor_stats()
        assert stats['size'] == 0
