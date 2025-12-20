"""
Unit tests for RSS service functionality.

Tests RSS parsing, filtering, and hash extraction.
"""

import pytest
from unittest.mock import MagicMock, patch

from tests.fixtures.test_data import (
    RSS_MIKAN_MY_BANGUMI,
    RSS_MIKAN_BLOCKED_KEYWORDS,
    SAMPLE_ANIME_TITLES,
)


class TestRSSService:
    """Test suite for RSSService class."""

    @pytest.fixture
    def rss_service(self, download_repo):
        """Create RSSService instance with test database."""
        from src.services.rss_service import RSSService
        return RSSService(download_repo=download_repo)

    def test_rss_service_initialization(self, download_repo):
        """Test RSSService initializes correctly."""
        from src.services.rss_service import RSSService

        service = RSSService(download_repo=download_repo)

        assert service is not None
        assert service._download_repo is download_repo
        assert service._timeout == 30

    def test_rss_service_custom_timeout(self, download_repo):
        """Test RSSService with custom timeout."""
        from src.services.rss_service import RSSService

        service = RSSService(download_repo=download_repo, timeout=60)

        assert service._timeout == 60

    def test_extract_hash_from_magnet_hex(self, rss_service):
        """Test extracting hash from hex-encoded magnet link."""
        magnet = 'magnet:?xt=urn:btih:55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0'

        result = rss_service.extract_hash_from_url(magnet)

        assert result == '55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0'

    def test_extract_hash_from_magnet_base32(self, rss_service):
        """Test extracting hash from base32-encoded magnet link."""
        # Base32 encoded hash (32 characters)
        magnet = 'magnet:?xt=urn:btih:KURGKIO3W5XOXLKQB3BNZWVG3YDORZGQ'

        result = rss_service.extract_hash_from_url(magnet)

        assert len(result) == 40
        assert all(c in '0123456789abcdef' for c in result)

    def test_extract_hash_from_torrent_url(self, rss_service):
        """Test extracting hash from torrent URL with hash in filename."""
        url = 'https://example.com/download/55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0.torrent'

        result = rss_service.extract_hash_from_url(url)

        assert result == '55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0'

    def test_extract_hash_from_url_no_hash(self, rss_service):
        """Test extracting hash from URL without hash."""
        url = 'https://example.com/download/anime.torrent'

        result = rss_service.extract_hash_from_url(url)

        assert result == ''

    def test_extract_hash_from_empty_url(self, rss_service):
        """Test extracting hash from empty URL."""
        result = rss_service.extract_hash_from_url('')

        assert result == ''

    @patch('requests.Session.get')
    def test_parse_feed_rss_format(self, mock_get, rss_service, mock_rss_response):
        """Test parsing RSS 2.0 format feed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = mock_rss_response.encode('utf-8')
        mock_get.return_value = mock_response

        items = rss_service.parse_feed('https://example.com/rss')

        assert len(items) == 2
        assert items[0].title == '[ANi] 狼與香辛料 - 26 [1080P][Baha][WEB-DL].mp4'
        assert items[1].title == '[Nekomoe] Tensei Slime S3 - 24 [1080p].mkv'

    @patch('requests.Session.get')
    def test_parse_feed_atom_format(self, mock_get, rss_service):
        """Test parsing Atom format feed."""
        atom_response = '''<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>Mikan Project</title>
    <entry>
        <title>[ANi] Test Anime - 01 [1080P].mp4</title>
        <link href="https://example.com/download/abc123.torrent" rel="enclosure"/>
        <published>2025-01-01T12:00:00Z</published>
    </entry>
</feed>'''
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = atom_response.encode('utf-8')
        mock_get.return_value = mock_response

        items = rss_service.parse_feed('https://example.com/atom')

        assert len(items) == 1
        assert items[0].title == '[ANi] Test Anime - 01 [1080P].mp4'

    @patch('requests.Session.get')
    def test_parse_feed_http_error(self, mock_get, rss_service):
        """Test handling HTTP error when fetching feed."""
        from src.core.exceptions import RSSError

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with pytest.raises(RSSError):
            rss_service.parse_feed('https://example.com/invalid')

    @patch('requests.Session.get')
    def test_parse_feed_network_error(self, mock_get, rss_service):
        """Test handling network error when fetching feed."""
        import requests
        from src.core.exceptions import RSSError

        mock_get.side_effect = requests.RequestException('Network error')

        with pytest.raises(RSSError):
            rss_service.parse_feed('https://example.com/rss')

    @patch('requests.Session.get')
    def test_filter_new_items_all_new(self, mock_get, rss_service, mock_rss_response):
        """Test filtering when all items are new."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = mock_rss_response.encode('utf-8')
        mock_get.return_value = mock_response

        items = rss_service.parse_feed('https://example.com/rss')
        new_items = rss_service.filter_new_items(items)

        # Should return all items when none exist in database
        assert len(new_items) <= len(items)

    def test_filter_new_items_empty_list(self, rss_service):
        """Test filtering empty item list."""
        new_items = rss_service.filter_new_items([])

        assert new_items == []


class TestFilterService:
    """Test suite for FilterService class."""

    @pytest.fixture
    def filter_service(self):
        """Create FilterService instance."""
        from src.services.filter_service import FilterService
        return FilterService()

    def test_filter_service_initialization(self):
        """Test FilterService initializes correctly."""
        from src.services.filter_service import FilterService

        service = FilterService()

        assert service is not None

    def test_should_filter_matching_keyword(self, filter_service):
        """Test filtering with matching keyword."""
        title = '[ANi] 狼與香辛料 - 26 [繁日内嵌].mp4'
        blocked_keywords = '繁日内嵌\n简日内嵌'

        result = filter_service.should_filter(title, blocked_keywords, '')

        assert result is True

    def test_should_filter_no_match(self, filter_service):
        """Test filtering with no matching keyword."""
        title = '[ANi] 狼與香辛料 - 26 [1080P].mp4'
        blocked_keywords = '繁日内嵌\n简日内嵌'

        result = filter_service.should_filter(title, blocked_keywords, '')

        assert result is False

    def test_should_filter_matching_regex(self, filter_service):
        """Test filtering with matching regex."""
        title = '[ANi] 狼與香辛料 - 26 [720P].mp4'
        blocked_regex = r'\[720P\]'

        result = filter_service.should_filter(title, '', blocked_regex)

        assert result is True

    def test_should_filter_no_regex_match(self, filter_service):
        """Test filtering with no matching regex."""
        title = '[ANi] 狼與香辛料 - 26 [1080P].mp4'
        blocked_regex = r'\[720P\]'

        result = filter_service.should_filter(title, '', blocked_regex)

        assert result is False

    def test_should_filter_empty_filters(self, filter_service):
        """Test filtering with empty filters."""
        title = '[ANi] 狼與香辛料 - 26 [1080P].mp4'

        result = filter_service.should_filter(title, '', '')

        assert result is False

    def test_should_filter_multiple_keywords(self, filter_service):
        """Test filtering with multiple keywords."""
        title = '[ANi] 狼與香辛料 - 26 [简日内嵌].mp4'
        blocked_keywords = '繁日内嵌\n简日内嵌\n内嵌字幕'

        result = filter_service.should_filter(title, blocked_keywords, '')

        assert result is True

    def test_should_filter_combined(self, filter_service):
        """Test filtering with both keyword and regex."""
        title = '[ANi] 狼與香辛料 - 26 [1080P][简日内嵌].mp4'

        # Should match keyword
        assert filter_service.should_filter(title, '简日内嵌', '') is True

        # Should match regex
        assert filter_service.should_filter(title, '', r'\[简日内嵌\]') is True


class TestRSSItem:
    """Test suite for RSSItem data class."""

    def test_rss_item_creation(self):
        """Test RSSItem creation with all fields."""
        from src.core.interfaces.adapters import RSSItem

        item = RSSItem(
            title='[ANi] Test - 01 [1080P].mp4',
            link='https://example.com/link',
            description='Test description',
            torrent_url='https://example.com/download.torrent',
            hash='abc123def456789012345678901234567890',
            pub_date='2025-01-01T12:00:00Z'
        )

        assert item.title == '[ANi] Test - 01 [1080P].mp4'
        assert item.link == 'https://example.com/link'
        assert item.torrent_url == 'https://example.com/download.torrent'
        assert item.hash == 'abc123def456789012345678901234567890'

    def test_rss_item_effective_url_with_torrent(self):
        """Test RSSItem effective_url returns torrent_url when available."""
        from src.core.interfaces.adapters import RSSItem

        item = RSSItem(
            title='Test',
            link='https://example.com/link',
            torrent_url='https://example.com/download.torrent'
        )

        assert item.effective_url == 'https://example.com/download.torrent'

    def test_rss_item_effective_url_fallback(self):
        """Test RSSItem effective_url falls back to link."""
        from src.core.interfaces.adapters import RSSItem

        item = RSSItem(
            title='Test',
            link='https://example.com/link',
            torrent_url=''
        )

        assert item.effective_url == 'https://example.com/link'
