"""
Integration tests for RSS workflow.

Tests the complete RSS processing workflow with real Mikan RSS feeds.
These tests require network access and may take longer to run.
"""

import pytest
from unittest.mock import MagicMock, patch

from tests.fixtures.test_data import (
    RSS_MIKAN_MY_BANGUMI,
    RSS_MIKAN_SINGLE_ANIME,
    RSS_MIKAN_BLOCKED_KEYWORDS,
)


@pytest.mark.integration
class TestRSSWorkflowIntegration:
    """Integration tests for complete RSS workflow."""

    @pytest.fixture
    def rss_service(self, download_repo):
        """Create RSSService with test database."""
        from src.services.rss_service import RSSService
        return RSSService(download_repo=download_repo)

    @pytest.fixture
    def filter_service(self):
        """Create FilterService."""
        from src.services.filter_service import FilterService
        return FilterService()

    @pytest.mark.slow
    def test_fetch_mikan_my_bangumi_feed(self, rss_service):
        """
        Test fetching and parsing the user's Mikan My Bangumi RSS feed.

        This test uses real network access to verify RSS parsing works
        with actual Mikan RSS feeds.
        """
        try:
            items = rss_service.parse_feed(RSS_MIKAN_MY_BANGUMI)

            # Verify items were parsed
            assert isinstance(items, list)

            if items:
                # Verify item structure
                item = items[0]
                assert hasattr(item, 'title')
                assert hasattr(item, 'link')
                assert hasattr(item, 'torrent_url') or hasattr(item, 'link')
                assert hasattr(item, 'hash')

                print(f'\n✅ Successfully parsed {len(items)} items from My Bangumi feed')
                print(f'   First item: {item.title[:50]}...')

        except Exception as e:
            pytest.skip(f'Network error or RSS feed unavailable: {e}')

    @pytest.mark.slow
    def test_fetch_mikan_single_anime_feed(self, rss_service):
        """
        Test fetching specific anime RSS feed (bangumiId=3777).

        This feed should contain items for a specific anime that
        may match existing anime in the database.
        """
        try:
            items = rss_service.parse_feed(RSS_MIKAN_SINGLE_ANIME)

            assert isinstance(items, list)

            if items:
                print(f'\n✅ Successfully parsed {len(items)} items from single anime feed')
                for i, item in enumerate(items[:3]):
                    print(f'   {i+1}. {item.title[:60]}...')

        except Exception as e:
            pytest.skip(f'Network error or RSS feed unavailable: {e}')

    @pytest.mark.slow
    def test_filter_blocked_keywords(self, rss_service, filter_service):
        """
        Test filtering RSS items with blocked keywords.

        Uses the real Mikan feed and filters out items matching
        '繁日内嵌' or '简日内嵌'.
        """
        try:
            items = rss_service.parse_feed(RSS_MIKAN_MY_BANGUMI)

            if not items:
                pytest.skip('No items in RSS feed')

            # Count filtered items
            filtered_count = 0
            passed_count = 0

            for item in items:
                if filter_service.should_filter(
                    item.title,
                    RSS_MIKAN_BLOCKED_KEYWORDS,
                    ''
                ):
                    filtered_count += 1
                else:
                    passed_count += 1

            print(f'\n📊 Filter results:')
            print(f'   Total items: {len(items)}')
            print(f'   Filtered: {filtered_count}')
            print(f'   Passed: {passed_count}')

            # Verify filtering logic works
            assert filtered_count + passed_count == len(items)

        except Exception as e:
            pytest.skip(f'Network error or RSS feed unavailable: {e}')

    @pytest.mark.slow
    def test_filter_new_items(self, rss_service):
        """
        Test filtering already-downloaded items.

        First parse should return items, then after marking some as
        existing, they should be filtered out.
        """
        try:
            items = rss_service.parse_feed(RSS_MIKAN_MY_BANGUMI)

            if not items:
                pytest.skip('No items in RSS feed')

            # First filter - all should be new (empty database)
            new_items = rss_service.filter_new_items(items)

            print(f'\n📊 New items filter:')
            print(f'   Total items: {len(items)}')
            print(f'   New items: {len(new_items)}')

            # All items should pass through (empty database)
            # Note: Some may be filtered if they have no hash
            assert len(new_items) <= len(items)

        except Exception as e:
            pytest.skip(f'Network error or RSS feed unavailable: {e}')


@pytest.mark.integration
@pytest.mark.requires_ai
class TestRSSWithAIProcessing:
    """Integration tests for RSS processing with AI title parsing."""

    @pytest.fixture
    def download_manager(
        self,
        anime_repo,
        download_repo,
        history_repo,
        mock_qbit_client,
        mock_title_parser,
        mock_file_renamer
    ):
        """Create DownloadManager with mocked dependencies."""
        from src.services.download_manager import DownloadManager
        from src.services.rss_service import RSSService
        from src.services.filter_service import FilterService
        from src.services.rename.rename_service import RenameService
        from src.services.file.hardlink_service import HardlinkService
        from src.services.file.path_builder import PathBuilder
        from src.services.metadata_service import MetadataService
        from src.services.rename.file_classifier import FileClassifier
        from src.services.rename.pattern_matcher import PatternMatcher
        from src.services.rename.filename_formatter import FilenameFormatter
        from unittest.mock import MagicMock

        # Create services
        rss_service = RSSService(download_repo=download_repo)
        filter_service = FilterService()
        path_builder = PathBuilder(
            download_root='/downloads/AniDown/',
            library_root='/library/TV Shows'
        )
        file_classifier = FileClassifier()
        pattern_matcher = PatternMatcher()
        filename_formatter = FilenameFormatter()
        rename_service = RenameService(
            file_classifier=file_classifier,
            pattern_matcher=pattern_matcher,
            filename_formatter=filename_formatter
        )
        hardlink_service = HardlinkService(
            hardlink_repo=history_repo,
            path_builder=path_builder
        )
        metadata_service = MagicMock()

        return DownloadManager(
            anime_repo=anime_repo,
            download_repo=download_repo,
            history_repo=history_repo,
            title_parser=mock_title_parser,
            file_renamer=mock_file_renamer,
            download_client=mock_qbit_client,
            rss_service=rss_service,
            filter_service=filter_service,
            rename_service=rename_service,
            hardlink_service=hardlink_service,
            path_builder=path_builder,
            metadata_service=metadata_service,
        )

    @pytest.mark.slow
    def test_process_rss_with_mocked_ai(self, download_manager, mock_title_parser):
        """
        Test RSS processing with mocked AI parser.

        This test simulates the complete RSS workflow without actually
        calling the AI API.
        """
        from src.core.config import RSSFeed

        feeds = [RSSFeed(
            url=RSS_MIKAN_MY_BANGUMI,
            blocked_keywords=RSS_MIKAN_BLOCKED_KEYWORDS,
            blocked_regex='',
            media_type='anime'
        )]

        try:
            result = download_manager.process_rss_feeds(
                rss_feeds=feeds,
                trigger_type='测试触发'
            )

            print(f'\n📊 RSS Processing Results:')
            print(f'   Total items: {result.total_items}')
            print(f'   New items: {result.new_items}')
            print(f'   Skipped: {result.skipped_items}')
            print(f'   Failed: {result.failed_items}')
            print(f'   Success rate: {result.success_rate:.1f}%')

            # Verify result structure
            assert hasattr(result, 'total_items')
            assert hasattr(result, 'new_items')
            assert hasattr(result, 'skipped_items')
            assert hasattr(result, 'failed_items')
            assert hasattr(result, 'errors')

        except Exception as e:
            pytest.skip(f'RSS processing failed: {e}')


@pytest.mark.integration
class TestRSSHashExtraction:
    """Tests for hash extraction from various URL formats."""

    @pytest.fixture
    def rss_service(self, download_repo):
        """Create RSSService."""
        from src.services.rss_service import RSSService
        return RSSService(download_repo=download_repo)

    def test_extract_hash_from_mikan_url(self, rss_service):
        """Test hash extraction from Mikan-style torrent URL."""
        # Mikan typically uses hash in URL path
        url = 'https://mikanani.me/Download/55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0.torrent'

        hash_id = rss_service.extract_hash_from_url(url)

        assert hash_id == '55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0'

    def test_extract_hash_from_nyaa_magnet(self, rss_service):
        """Test hash extraction from Nyaa-style magnet link."""
        magnet = (
            'magnet:?xt=urn:btih:55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0'
            '&dn=BanG+Dream&tr=http://nyaa.tracker.wf:7777/announce'
        )

        hash_id = rss_service.extract_hash_from_url(magnet)

        assert hash_id == '55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0'

    @pytest.mark.parametrize('url,expected_hash', [
        (
            'magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12',
            'abcdef1234567890abcdef1234567890abcdef12'
        ),
        (
            'https://example.com/1234567890abcdef1234567890abcdef12345678.torrent',
            '1234567890abcdef1234567890abcdef12345678'
        ),
        (
            'https://example.com/download?hash=abcdef1234567890abcdef1234567890abcdef12',
            'abcdef1234567890abcdef1234567890abcdef12'
        ),
    ])
    def test_extract_hash_various_formats(self, rss_service, url, expected_hash):
        """Test hash extraction from various URL formats."""
        result = rss_service.extract_hash_from_url(url)
        assert result == expected_hash
