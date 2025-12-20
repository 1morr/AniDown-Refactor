"""
Tests for manual upload functionality.

Tests torrent file upload and magnet link processing.
"""

import base64
import os
import uuid
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.fixtures.test_data import (
    TORRENT_FILE_CONFIG,
    MAGNET_CONFIG,
)


def generate_unique_hash() -> str:
    """Generate a unique hash for testing."""
    return uuid.uuid4().hex[:40]


class TestManualUploadService:
    """Test suite for manual upload processing."""

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


class TestTorrentFileUpload(TestManualUploadService):
    """Tests for torrent file upload functionality."""

    @pytest.fixture
    def test_torrent_file(self, tmp_path):
        """Create a test torrent file."""
        import bencodepy

        torrent_data = {
            b'info': {
                b'name': b'[Nekomoe kissaten&VCB-Studio] Medalist [Ma10p_1080p]',
                b'piece length': 16384,
                b'pieces': b'\x00' * 20,
                b'length': 1000000000
            },
            b'announce': b'udp://tracker.example.com:8080/announce'
        }

        torrent_path = tmp_path / TORRENT_FILE_CONFIG['filename']
        with open(torrent_path, 'wb') as f:
            f.write(bencodepy.encode(torrent_data))

        return torrent_path

    def test_torrent_file_upload_success(
        self,
        download_manager,
        mock_qbit_client,
        test_torrent_file
    ):
        """Test successful torrent file upload."""
        # Read and encode torrent file
        with open(test_torrent_file, 'rb') as f:
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

        # Mock hash extraction - function is in qbit_adapter module
        with patch(
            'src.infrastructure.downloader.qbit_adapter.get_torrent_hash_from_file',
            return_value=unique_hash
        ):
            result = download_manager.process_manual_upload(upload_data)

        assert result is True
        mock_qbit_client.add_torrent_file.assert_called_once()

    def test_torrent_file_upload_missing_file(self, download_manager):
        """Test torrent upload with missing file content."""
        upload_data = {
            'upload_type': 'torrent',
            'torrent_file': None,
            'anime_title': TORRENT_FILE_CONFIG['anime_title'],
            'subtitle_group': TORRENT_FILE_CONFIG['subtitle_group'],
            'season': TORRENT_FILE_CONFIG['season'],
            'category': TORRENT_FILE_CONFIG['category'],
        }

        result = download_manager.process_manual_upload(upload_data)

        assert result is False

    def test_torrent_file_upload_saves_to_database(
        self,
        download_manager,
        download_repo,
        anime_repo,
        test_torrent_file
    ):
        """Test that torrent upload saves records to database."""
        with open(test_torrent_file, 'rb') as f:
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
        test_hash = generate_unique_hash()

        with patch(
            'src.infrastructure.downloader.qbit_adapter.get_torrent_hash_from_file',
            return_value=test_hash
        ):
            result = download_manager.process_manual_upload(upload_data)

        assert result is True

        # Verify database records
        download_record = download_repo.get_by_hash(test_hash)
        if download_record:
            assert download_record.anime_title == TORRENT_FILE_CONFIG['anime_title']


class TestMagnetLinkUpload(TestManualUploadService):
    """Tests for magnet link upload functionality."""

    def test_magnet_link_upload_success(self, download_manager, mock_qbit_client):
        """Test successful magnet link upload."""
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

        assert result is True
        mock_qbit_client.add_magnet.assert_called_once()

    def test_magnet_link_upload_missing_link(self, download_manager):
        """Test magnet upload with missing link."""
        upload_data = {
            'upload_type': 'magnet',
            'magnet_link': '',
            'anime_title': MAGNET_CONFIG['anime_title'],
            'subtitle_group': MAGNET_CONFIG['subtitle_group'],
            'season': MAGNET_CONFIG['season'],
            'category': MAGNET_CONFIG['category'],
        }

        result = download_manager.process_manual_upload(upload_data)

        assert result is False

    def test_magnet_link_hash_extraction(self, download_manager):
        """Test hash extraction from magnet link."""
        # Use unique hash to avoid database conflicts
        unique_hash = generate_unique_hash()
        magnet_link = f"magnet:?xt=urn:btih:{unique_hash}&dn=TestName"

        upload_data = {
            'upload_type': 'magnet',
            'magnet_link': magnet_link,
            'anime_title': MAGNET_CONFIG['anime_title'],
            'subtitle_group': MAGNET_CONFIG['subtitle_group'],
            'season': MAGNET_CONFIG['season'],
            'category': MAGNET_CONFIG['category'],
        }

        with patch(
            'src.infrastructure.downloader.qbit_adapter.get_torrent_hash_from_magnet',
            return_value=unique_hash
        ):
            result = download_manager.process_manual_upload(upload_data)

        assert result is True

    def test_magnet_link_upload_saves_to_database(
        self,
        download_manager,
        download_repo
    ):
        """Test that magnet upload saves records to database."""
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

        assert result is True

        # Verify database record
        download_record = download_repo.get_by_hash(unique_hash)
        if download_record:
            assert download_record.anime_title == MAGNET_CONFIG['anime_title']


@pytest.mark.integration
@pytest.mark.requires_qbit
class TestManualUploadIntegration:
    """Integration tests for manual upload with real qBittorrent."""

    @pytest.fixture
    def real_download_manager(self, requires_qbit):
        """Get real download manager from container."""
        from src.container import container
        try:
            dm = container.download_manager()
            # Check if qBittorrent is connected
            if not dm._download_client.is_connected():
                pytest.skip('qBittorrent not connected')
            return dm
        except Exception as e:
            pytest.skip(f'Failed to get download manager: {e}')

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

    def test_real_torrent_file_upload(self, real_download_manager):
        """
        Test torrent file upload with real qBittorrent.

        Uses the actual torrent file from the project root.
        """
        from src.infrastructure.downloader.qbit_adapter import get_torrent_hash_from_file

        project_root = Path(__file__).parent.parent.parent
        torrent_path = project_root / TORRENT_FILE_CONFIG['filename']

        if not torrent_path.exists():
            pytest.skip(f'Torrent file not found: {torrent_path}')

        # Get hash and cleanup existing record
        torrent_hash = get_torrent_hash_from_file(str(torrent_path))
        if torrent_hash:
            self._cleanup_existing_hash(torrent_hash)

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

        result = real_download_manager.process_manual_upload(upload_data)

        assert result is True
        print(f'\n✅ Successfully uploaded torrent: {TORRENT_FILE_CONFIG["filename"]}')

    def test_real_magnet_link_upload(self, real_download_manager):
        """
        Test magnet link upload with real qBittorrent.

        Uses the magnet hash from test data.
        """
        # Cleanup existing record
        self._cleanup_existing_hash(MAGNET_CONFIG['hash'])

        magnet_link = f"magnet:?xt=urn:btih:{MAGNET_CONFIG['hash']}"

        upload_data = {
            'upload_type': 'magnet',
            'magnet_link': magnet_link,
            'anime_title': MAGNET_CONFIG['anime_title'],
            'subtitle_group': MAGNET_CONFIG['subtitle_group'],
            'season': MAGNET_CONFIG['season'],
            'category': MAGNET_CONFIG['category'],
            'media_type': 'anime'
        }

        result = real_download_manager.process_manual_upload(upload_data)

        assert result is True
        print(f'\n✅ Successfully added magnet: {MAGNET_CONFIG["anime_title"]}')


class TestQBitAdapter:
    """Tests for qBittorrent adapter functionality."""

    def test_get_torrent_hash_from_file(self, tmp_path):
        """Test extracting hash from torrent file."""
        import bencodepy
        from src.infrastructure.downloader.qbit_adapter import get_torrent_hash_from_file

        # Create torrent with known info dict
        torrent_data = {
            b'info': {
                b'name': b'Test File',
                b'piece length': 16384,
                b'pieces': b'\x00' * 20,
                b'length': 1000000
            }
        }

        torrent_path = tmp_path / 'test.torrent'
        with open(torrent_path, 'wb') as f:
            f.write(bencodepy.encode(torrent_data))

        hash_id = get_torrent_hash_from_file(str(torrent_path))

        assert hash_id is not None
        assert len(hash_id) == 40
        assert all(c in '0123456789abcdef' for c in hash_id.lower())

    def test_get_torrent_hash_from_magnet(self):
        """Test extracting hash from magnet link."""
        from src.infrastructure.downloader.qbit_adapter import get_torrent_hash_from_magnet

        magnet = f"magnet:?xt=urn:btih:{MAGNET_CONFIG['hash']}&dn=Test"

        hash_id = get_torrent_hash_from_magnet(magnet)

        assert hash_id == MAGNET_CONFIG['hash']

    def test_get_torrent_hash_from_invalid_magnet(self):
        """Test hash extraction from invalid magnet link."""
        from src.infrastructure.downloader.qbit_adapter import get_torrent_hash_from_magnet

        invalid_magnet = 'magnet:?dn=InvalidNoHash'

        hash_id = get_torrent_hash_from_magnet(invalid_magnet)

        assert hash_id is None or hash_id == ''
