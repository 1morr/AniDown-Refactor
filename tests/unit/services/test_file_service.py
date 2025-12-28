"""Unit tests for FileService."""

import os
import tempfile
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.file_service import FileService
from src.core.domain.entities import HardlinkRecord


class TestFileServiceCreate:
    """Tests for FileService.create() method."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_history_repo(self):
        """Create a mock history repository."""
        return MagicMock()

    @pytest.fixture
    def mock_path_builder(self):
        """Create a mock path builder."""
        mock = MagicMock()
        mock.ensure_directory.return_value = True
        return mock

    @pytest.fixture
    def file_service(self, mock_history_repo, mock_path_builder):
        """Create a FileService instance with mocked dependencies."""
        return FileService(
            history_repo=mock_history_repo,
            path_builder=mock_path_builder,
        )

    def test_create_new_hardlink_success(
        self, file_service, temp_dir, mock_history_repo
    ):
        """Should create hardlink and save database record for new file."""
        # Setup: Create source file
        source_path = os.path.join(temp_dir, 'source', 'video.mkv')
        os.makedirs(os.path.dirname(source_path), exist_ok=True)
        with open(source_path, 'w') as f:
            f.write('test content')

        target_dir = os.path.join(temp_dir, 'target')
        os.makedirs(target_dir, exist_ok=True)

        # Action
        result = file_service.create(
            source_path=source_path,
            target_dir=target_dir,
            new_name='renamed.mkv',
            anime_id=123,
            torrent_hash='abc123',
        )

        # Assert
        assert result is True
        target_path = os.path.join(target_dir, 'renamed.mkv')
        assert os.path.exists(target_path)
        mock_history_repo.save.assert_called_once()

        # Verify record content
        saved_record = mock_history_repo.save.call_args[0][0]
        assert isinstance(saved_record, HardlinkRecord)
        assert saved_record.anime_id == 123
        assert saved_record.torrent_hash == 'abc123'
        assert saved_record.original_file_path == source_path
        assert saved_record.hardlink_path == target_path

    def test_create_replaces_existing_file(
        self, file_service, temp_dir, mock_history_repo
    ):
        """Should delete existing file, create new hardlink, and save database record."""
        # Setup: Create source file
        source_path = os.path.join(temp_dir, 'source', 'video.mkv')
        os.makedirs(os.path.dirname(source_path), exist_ok=True)
        with open(source_path, 'w') as f:
            f.write('new source content')

        # Create existing target file (different content)
        target_dir = os.path.join(temp_dir, 'target')
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, 'renamed.mkv')
        with open(target_path, 'w') as f:
            f.write('old existing content')

        # Get original inode of target
        original_inode = os.stat(target_path).st_ino

        # Action
        result = file_service.create(
            source_path=source_path,
            target_dir=target_dir,
            new_name='renamed.mkv',
            anime_id=456,
            torrent_hash='def456',
        )

        # Assert
        assert result is True
        assert os.path.exists(target_path)

        # Verify file was replaced (new inode)
        new_inode = os.stat(target_path).st_ino
        assert new_inode != original_inode, 'File should have been replaced with new hardlink'

        # Verify content matches source
        with open(target_path, 'r') as f:
            assert f.read() == 'new source content'

        # Verify database record was saved
        mock_history_repo.save.assert_called_once()
        saved_record = mock_history_repo.save.call_args[0][0]
        assert saved_record.anime_id == 456
        assert saved_record.torrent_hash == 'def456'

    def test_create_returns_false_when_delete_fails(
        self, file_service, temp_dir, mock_history_repo
    ):
        """Should return False when unable to delete existing file."""
        # Setup: Create source file
        source_path = os.path.join(temp_dir, 'source', 'video.mkv')
        os.makedirs(os.path.dirname(source_path), exist_ok=True)
        with open(source_path, 'w') as f:
            f.write('test content')

        target_dir = os.path.join(temp_dir, 'target')
        target_path = os.path.join(target_dir, 'renamed.mkv')
        os.makedirs(target_dir, exist_ok=True)
        with open(target_path, 'w') as f:
            f.write('existing content')

        # Mock os.remove to raise OSError (patch the module-level import)
        with patch.object(os, 'remove', side_effect=OSError('Permission denied')):
            result = file_service.create(
                source_path=source_path,
                target_dir=target_dir,
                new_name='renamed.mkv',
                anime_id=789,
                torrent_hash='ghi789',
            )

        # Assert
        assert result is False
        mock_history_repo.save.assert_not_called()

    def test_create_returns_false_when_source_missing(
        self, file_service, temp_dir, mock_history_repo
    ):
        """Should return False when source file does not exist."""
        # Setup: No source file
        source_path = os.path.join(temp_dir, 'nonexistent.mkv')
        target_dir = os.path.join(temp_dir, 'target')

        # Action
        result = file_service.create(
            source_path=source_path,
            target_dir=target_dir,
            new_name='renamed.mkv',
        )

        # Assert
        assert result is False
        mock_history_repo.save.assert_not_called()

    def test_create_with_subdirectory_in_name(
        self, file_service, temp_dir, mock_history_repo, mock_path_builder
    ):
        """Should handle new_name containing subdirectory path."""
        # Setup: Create source file
        source_path = os.path.join(temp_dir, 'source', 'video.mkv')
        os.makedirs(os.path.dirname(source_path), exist_ok=True)
        with open(source_path, 'w') as f:
            f.write('test content')

        target_dir = os.path.join(temp_dir, 'target')
        os.makedirs(target_dir, exist_ok=True)

        # Mock path_builder to actually create subdirectory
        def ensure_dir_side_effect(path):
            os.makedirs(path, exist_ok=True)
            return True
        mock_path_builder.ensure_directory.side_effect = ensure_dir_side_effect

        # Action: Create with subdirectory in name
        result = file_service.create(
            source_path=source_path,
            target_dir=target_dir,
            new_name='Season 1/episode01.mkv',
            anime_id=100,
        )

        # Assert
        assert result is True
        expected_target = os.path.join(target_dir, 'Season 1', 'episode01.mkv')
        assert os.path.exists(expected_target)
        mock_history_repo.save.assert_called_once()
