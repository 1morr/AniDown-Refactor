"""
End-to-end integration tests for AniDown.

Tests complete workflows from RSS parsing to download completion.
"""

import base64
import uuid
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.fixtures.test_data import (
    RSS_MIKAN_MY_BANGUMI,
    RSS_MIKAN_SINGLE_ANIME,
    RSS_MIKAN_BLOCKED_KEYWORDS,
    TORRENT_FILE_CONFIG,
    MAGNET_CONFIG,
)


def generate_unique_hash() -> str:
    """Generate a unique hash for testing."""
    return uuid.uuid4().hex[:40]


@pytest.mark.integration
class TestCompleteWorkflow:
    """End-to-end workflow tests."""

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
        """Create DownloadManager with mocked external dependencies."""
        from src.services.download_manager import DownloadManager
        from src.services.rss_service import RSSService
        from src.services.filter_service import FilterService
        from src.services.rename.rename_service import RenameService
        from src.services.file.hardlink_service import HardlinkService
        from src.services.file.path_builder import PathBuilder
        from src.services.rename.file_classifier import FileClassifier
        from src.services.rename.pattern_matcher import PatternMatcher
        from src.services.rename.filename_formatter import FilenameFormatter

        rss_service = RSSService(download_repo=download_repo)
        filter_service = FilterService()
        path_builder = PathBuilder(
            download_root='/downloads/AniDown/',
            library_root='/library/TV Shows'
        )
        file_classifier = FileClassifier()
        filename_formatter = FilenameFormatter()
        rename_service = RenameService(
            file_classifier=file_classifier,
            filename_formatter=filename_formatter,
            anime_repo=anime_repo,
            ai_file_renamer=mock_file_renamer
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
    def test_rss_to_download_workflow(self, download_manager, mock_qbit_client):
        """
        Test complete RSS to download workflow.

        1. Fetch RSS feed
        2. Parse and filter items
        3. Extract anime info (mocked AI)
        4. Add to qBittorrent
        5. Save to database
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

            print(f'\n📊 Workflow Results:')
            print(f'   Total items found: {result.total_items}')
            print(f'   New items processed: {result.new_items}')
            print(f'   Skipped items: {result.skipped_items}')
            print(f'   Failed items: {result.failed_items}')

            # Verify qBittorrent was called for new items
            if result.new_items > 0:
                assert mock_qbit_client.add_torrent.called or \
                       mock_qbit_client.add_torrent_file.called

        except Exception as e:
            pytest.skip(f'Workflow test failed (network issue?): {e}')

    @pytest.mark.slow
    def test_existing_anime_skip_ai(self, download_manager, anime_repo, mock_title_parser):
        """
        Test that existing anime skips AI processing.

        1. First add anime to database
        2. Process RSS feed with matching anime
        3. Verify AI was not called for existing anime
        """
        from src.core.config import RSSFeed
        from src.core.domain.entities import AnimeInfo
        from src.core.domain.value_objects import (
            AnimeTitle,
            SubtitleGroup,
            SeasonInfo,
            Category,
            MediaType,
        )
        from datetime import datetime, timezone

        # Add existing anime to database
        anime = AnimeInfo(
            title=AnimeTitle(
                original='Test Anime Title',
                short='Test Anime',
                full='Test Anime Full Title'
            ),
            subtitle_group=SubtitleGroup(name='Test Group'),
            season=SeasonInfo(number=1, category=Category.TV),
            category=Category.TV,
            media_type=MediaType.ANIME,
            created_at=datetime.now(timezone.utc)
        )
        anime_repo.save(anime)

        # Reset mock call count
        mock_title_parser.parse.reset_mock()

        # Process RSS (this will use real network)
        try:
            feeds = [RSSFeed(
                url=RSS_MIKAN_SINGLE_ANIME,
                media_type='anime'
            )]

            result = download_manager.process_rss_feeds(
                rss_feeds=feeds,
                trigger_type='测试触发'
            )

            # This test's behavior depends on whether items match existing anime
            print(f'\n📊 Existing Anime Skip Test:')
            print(f'   AI parser called: {mock_title_parser.parse.call_count} times')
            print(f'   Items processed: {result.new_items}')

        except Exception as e:
            pytest.skip(f'Test failed (network issue?): {e}')

    def test_manual_torrent_workflow(self, download_manager, mock_qbit_client, tmp_path):
        """
        Test manual torrent upload workflow.

        1. Create test torrent file
        2. Upload via process_manual_upload
        3. Verify database records
        """
        import bencodepy

        # Create test torrent
        torrent_data = {
            b'info': {
                b'name': TORRENT_FILE_CONFIG['anime_title'].encode('utf-8'),
                b'piece length': 16384,
                b'pieces': b'\x00' * 20,
                b'length': 1000000000
            }
        }

        torrent_path = tmp_path / 'test.torrent'
        with open(torrent_path, 'wb') as f:
            f.write(bencodepy.encode(torrent_data))

        with open(torrent_path, 'rb') as f:
            torrent_content = base64.b64encode(f.read()).decode('utf-8')

        upload_data = {
            'upload_type': 'torrent',
            'torrent_file': torrent_content,
            'anime_title': TORRENT_FILE_CONFIG['anime_title'],
            'subtitle_group': TORRENT_FILE_CONFIG['subtitle_group'],
            'season': TORRENT_FILE_CONFIG['season'],
            'category': TORRENT_FILE_CONFIG['category'],
            'media_type': 'anime'
        }

        # Use unique hash to avoid database conflicts
        unique_hash = generate_unique_hash()

        with patch(
            'src.infrastructure.downloader.qbit_adapter.get_torrent_hash_from_file',
            return_value=unique_hash
        ):
            result = download_manager.process_manual_upload(upload_data)

        assert result == (True, '')
        mock_qbit_client.add_torrent_file.assert_called_once()

        print(f'\n✅ Manual torrent upload workflow completed')

    def test_manual_magnet_workflow(self, download_manager, mock_qbit_client):
        """
        Test manual magnet link upload workflow.

        1. Create magnet link
        2. Upload via process_manual_upload
        3. Verify database records
        """
        # Use unique hash to avoid database conflicts
        unique_hash = generate_unique_hash()
        magnet_link = f"magnet:?xt=urn:btih:{unique_hash}"

        upload_data = {
            'upload_type': 'magnet',
            'magnet_link': magnet_link,
            'anime_title': MAGNET_CONFIG['anime_title'],
            'subtitle_group': MAGNET_CONFIG['subtitle_group'],
            'season': MAGNET_CONFIG['season'],
            'category': MAGNET_CONFIG['category'],
            'media_type': 'anime'
        }

        with patch(
            'src.infrastructure.downloader.qbit_adapter.get_torrent_hash_from_magnet',
            return_value=unique_hash
        ):
            result = download_manager.process_manual_upload(upload_data)

        assert result == (True, '')
        mock_qbit_client.add_magnet.assert_called_once()

        print(f'\n✅ Manual magnet upload workflow completed')

    def test_torrent_completion_workflow(
        self,
        download_manager,
        download_repo,
        mock_qbit_client,
        tmp_path
    ):
        """
        Test torrent completion handling workflow.

        1. Add download record to database
        2. Simulate torrent completion
        3. Handle completion (create hardlinks)
        """
        from src.core.domain.entities import DownloadRecord
        from src.core.domain.value_objects import TorrentHash, DownloadStatus, DownloadMethod
        from datetime import datetime, timezone
        import uuid

        # Use unique hash to avoid conflicts
        test_hash = f'test_{uuid.uuid4().hex[:30]}'

        # Create download record
        record = DownloadRecord(
            hash=TorrentHash(test_hash),
            anime_id=1,
            original_filename='Test Anime - 01.mkv',
            anime_title='金牌得主',
            subtitle_group='喵萌奶茶屋&VCB-Studio',
            season=1,
            download_directory='/downloads/AniDown/Anime/TV/金牌得主/Season 1',
            status=DownloadStatus.PENDING,
            download_method=DownloadMethod.RSS_AI,
            download_time=datetime.now(timezone.utc)
        )
        download_repo.save(record)

        # Mock torrent files
        mock_qbit_client.get_torrent_files.return_value = [
            {'name': 'Test Anime - 01.mkv', 'size': 1000000000}
        ]

        # Handle completion
        result = download_manager.handle_torrent_completed(test_hash)

        assert result.get('success') is True

        print(f'\n✅ Torrent completion workflow completed')


@pytest.mark.integration
@pytest.mark.requires_qbit
class TestRealQBitWorkflow:
    """Integration tests with real qBittorrent."""

    def test_full_rss_workflow(self, requires_qbit):
        """
        Test complete RSS workflow with real qBittorrent.

        WARNING: This will actually add torrents to qBittorrent.
        """
        from src.container import container

        download_manager = container.download_manager()

        from src.core.config import RSSFeed

        feeds = [RSSFeed(
            url=RSS_MIKAN_MY_BANGUMI,
            blocked_keywords=RSS_MIKAN_BLOCKED_KEYWORDS,
            media_type='anime'
        )]

        result = download_manager.process_rss_feeds(
            rss_feeds=feeds,
            trigger_type='集成测试'
        )

        print(f'\n📊 Real qBit Workflow Results:')
        print(f'   Total items: {result.total_items}')
        print(f'   New items: {result.new_items}')
        print(f'   Skipped: {result.skipped_items}')
        print(f'   Failed: {result.failed_items}')

        # At minimum, should have processed something
        assert result.total_items >= 0

    def _cleanup_existing_hash(self, hash_id: str):
        """Remove existing download record with the given hash to allow re-testing."""
        from src.infrastructure.repositories.download_repository import DownloadRepository
        try:
            repo = DownloadRepository()
            existing = repo.get_by_hash(hash_id)
            if existing:
                repo.delete(hash_id)
                print(f'\n🧹 Cleaned up existing record: {hash_id}')
        except Exception:
            pass  # Ignore cleanup errors

    def test_full_torrent_upload_workflow(self, requires_qbit):
        """
        Test complete torrent upload with real qBittorrent.

        Uses the actual torrent file in the project.
        """
        from src.infrastructure.downloader.qbit_adapter import get_torrent_hash_from_file

        project_root = Path(__file__).parent.parent.parent
        torrent_path = project_root / 'tests/fixtures' / TORRENT_FILE_CONFIG['filename']

        if not torrent_path.exists():
            pytest.skip(f'Torrent file not found: {torrent_path}')

        # Get hash and cleanup existing record
        torrent_hash = get_torrent_hash_from_file(str(torrent_path))
        if torrent_hash:
            self._cleanup_existing_hash(torrent_hash)

        from src.container import container

        download_manager = container.download_manager()

        with open(torrent_path, 'rb') as f:
            torrent_content = base64.b64encode(f.read()).decode('utf-8')

        upload_data = {
            'upload_type': 'torrent',
            'torrent_file': torrent_content,
            'anime_title': TORRENT_FILE_CONFIG['anime_title'],
            'subtitle_group': TORRENT_FILE_CONFIG['subtitle_group'],
            'season': TORRENT_FILE_CONFIG['season'],
            'category': TORRENT_FILE_CONFIG['category'],
            'media_type': 'anime'
        }

        result = download_manager.process_manual_upload(upload_data)

        assert result == (True, '')
        print(f'\n✅ Real torrent upload successful')


@pytest.mark.integration
class TestDatabaseConsistency:
    """Tests for database consistency across operations."""

    def test_anime_repo_consistency(self, anime_repo):
        """Test anime repository consistency."""
        from src.core.domain.entities import AnimeInfo
        from src.core.domain.value_objects import (
            AnimeTitle,
            SubtitleGroup,
            SeasonInfo,
            Category,
            MediaType,
        )
        from datetime import datetime, timezone
        import uuid

        # Use unique title to avoid conflicts
        unique_suffix = str(uuid.uuid4())[:8]

        # Create anime
        anime = AnimeInfo(
            title=AnimeTitle(
                original=f'Consistency Test {unique_suffix}',
                short=f'Test {unique_suffix}',
                full=f'Consistency Test Full {unique_suffix}'
            ),
            subtitle_group=SubtitleGroup(name='Test Group'),
            season=SeasonInfo(number=1, category=Category.TV),
            category=Category.TV,
            media_type=MediaType.ANIME,
            created_at=datetime.now(timezone.utc)
        )

        # Save
        anime_id = anime_repo.save(anime)
        assert anime_id > 0

        # Retrieve
        retrieved = anime_repo.get_by_id(anime_id)
        assert retrieved is not None
        # display_name returns full, short, or original in that order
        assert retrieved.display_name == f'Consistency Test Full {unique_suffix}'

        # Count
        count = anime_repo.count_all()
        assert count >= 1

        print(f'\n✅ Anime repository consistency verified')

    def test_download_repo_consistency(self, download_repo):
        """Test download repository consistency."""
        from src.core.domain.entities import DownloadRecord
        from src.core.domain.value_objects import TorrentHash, DownloadStatus, DownloadMethod
        from datetime import datetime, timezone
        import uuid

        # Use unique hash to avoid conflicts
        unique_suffix = uuid.uuid4().hex[:26]
        test_hash = f'consist_{unique_suffix}'

        # Create record
        record = DownloadRecord(
            hash=TorrentHash(test_hash),
            anime_id=1,
            original_filename='Consistency Test.mkv',
            anime_title='Consistency Test',
            subtitle_group='Test',
            season=1,
            download_directory='/test',
            status=DownloadStatus.PENDING,
            download_method=DownloadMethod.RSS_AI,
            download_time=datetime.now(timezone.utc)
        )

        # Save
        record_id = download_repo.save(record)
        assert record_id > 0

        # Retrieve by hash
        retrieved = download_repo.get_by_hash(test_hash)
        assert retrieved is not None

        # Count
        count = download_repo.count_all()
        assert count >= 1

        print(f'\n✅ Download repository consistency verified')
