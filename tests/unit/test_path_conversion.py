"""
Tests for path conversion functionality.

Tests the path conversion feature used in Docker environments
to map paths between container and host.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.services.file.file_service import FileService


class TestPathConversion:
    """Tests for FileService.convert_path() method."""

    @pytest.fixture
    def file_service(self):
        """Create FileService with mocked repository."""
        mock_repo = MagicMock()
        return FileService(history_repo=mock_repo)

    def test_convert_path_disabled(self, file_service):
        """
        Test path conversion when disabled.

        When path_conversion.enabled is False, paths should remain unchanged.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = False

            original_path = '/downloads/AniDown/Anime/test.mkv'
            result = file_service.convert_path(original_path)

            assert result == original_path

    def test_convert_path_enabled_matching_path(self, file_service):
        """
        Test path conversion when enabled with matching path.

        When path starts with source_base_path, it should be converted.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = '/downloads/AniDown/'
            mock_config.path_conversion.target_base_path = '/storage/Downloads/AniDown/'

            original_path = '/downloads/AniDown/Anime/test.mkv'
            result = file_service.convert_path(original_path)

            expected = '/storage/Downloads/AniDown/Anime/test.mkv'
            assert result == expected

    def test_convert_path_enabled_non_matching_path(self, file_service):
        """
        Test path conversion when enabled with non-matching path.

        When path doesn't start with source_base_path, it should remain unchanged.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = '/downloads/AniDown/'
            mock_config.path_conversion.target_base_path = '/storage/Downloads/AniDown/'

            original_path = '/other/path/test.mkv'
            result = file_service.convert_path(original_path)

            assert result == original_path

    def test_convert_path_only_replaces_first_occurrence(self, file_service):
        """
        Test that path conversion only replaces the first occurrence.

        If the source_base_path appears multiple times, only the first should be replaced.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = '/downloads/'
            mock_config.path_conversion.target_base_path = '/storage/'

            # Path with source pattern appearing twice
            original_path = '/downloads/backup/downloads/test.mkv'
            result = file_service.convert_path(original_path)

            # Only first occurrence should be replaced
            expected = '/storage/backup/downloads/test.mkv'
            assert result == expected

    def test_convert_path_empty_path(self, file_service):
        """
        Test path conversion with empty path.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = '/downloads/AniDown/'
            mock_config.path_conversion.target_base_path = '/storage/Downloads/AniDown/'

            result = file_service.convert_path('')

            assert result == ''

    def test_convert_path_partial_match_no_replace(self, file_service):
        """
        Test that partial matches are not converted.

        If the path contains source_base_path but doesn't start with it,
        no conversion should happen.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = '/downloads/AniDown/'
            mock_config.path_conversion.target_base_path = '/storage/Downloads/AniDown/'

            # Path contains source but doesn't start with it
            original_path = '/mnt/downloads/AniDown/test.mkv'
            result = file_service.convert_path(original_path)

            assert result == original_path

    def test_convert_path_exact_match(self, file_service):
        """
        Test path conversion with exact match (just the base path).
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = '/downloads/AniDown/'
            mock_config.path_conversion.target_base_path = '/storage/Downloads/AniDown/'

            original_path = '/downloads/AniDown/'
            result = file_service.convert_path(original_path)

            expected = '/storage/Downloads/AniDown/'
            assert result == expected

    def test_convert_path_with_special_characters(self, file_service):
        """
        Test path conversion with special characters in filename.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = '/downloads/AniDown/'
            mock_config.path_conversion.target_base_path = '/storage/Downloads/AniDown/'

            original_path = "/downloads/AniDown/Anime/[Group] Title - 01 (1080p).mkv"
            result = file_service.convert_path(original_path)

            expected = "/storage/Downloads/AniDown/Anime/[Group] Title - 01 (1080p).mkv"
            assert result == expected

    def test_convert_path_with_unicode(self, file_service):
        """
        Test path conversion with Unicode characters in path.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = '/downloads/AniDown/'
            mock_config.path_conversion.target_base_path = '/storage/Downloads/AniDown/'

            original_path = '/downloads/AniDown/Anime/狼與香辛料 S01E01.mkv'
            result = file_service.convert_path(original_path)

            expected = '/storage/Downloads/AniDown/Anime/狼與香辛料 S01E01.mkv'
            assert result == expected

    def test_convert_path_windows_style(self, file_service):
        """
        Test path conversion with Windows-style paths.

        Note: convert_path normalizes all paths to POSIX style (forward slashes)
        for Docker/Linux compatibility.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = 'C:\\Downloads\\AniDown\\'
            mock_config.path_conversion.target_base_path = '/storage/AniDown/'

            original_path = 'C:\\Downloads\\AniDown\\Anime\\test.mkv'
            result = file_service.convert_path(original_path)

            # Output uses POSIX style slashes for Docker compatibility
            expected = '/storage/AniDown/Anime/test.mkv'
            assert result == expected

    def test_convert_path_mixed_separators(self, file_service):
        """
        Test path conversion with mixed Windows and Unix separators.

        This is common when Windows qBittorrent webhook data contains
        paths that get concatenated with Unix-style relative paths.
        """
        with patch('src.services.file.file_service.config') as mock_config:
            mock_config.path_conversion.enabled = True
            mock_config.path_conversion.source_base_path = 'C:\\Users\\Roxy\\storage\\Downloads\\AniDown\\'
            mock_config.path_conversion.target_base_path = '/storage/Downloads/AniDown/'

            # Mixed separator path (Windows base + Unix relative)
            original_path = 'C:\\Users\\Roxy\\storage\\Downloads\\AniDown\\/Anime/TV/test.mkv'
            result = file_service.convert_path(original_path)

            expected = '/storage/Downloads/AniDown/Anime/TV/test.mkv'
            assert result == expected
            assert '//' not in result  # No double slashes


class TestPathConversionConfig:
    """Tests for PathConversionConfig model."""

    def test_default_config_values(self):
        """Test default configuration values."""
        from src.core.config import PathConversionConfig

        config = PathConversionConfig()

        assert config.enabled is False
        assert config.source_base_path == '/storage/Downloads/AniDown/'
        assert config.target_base_path == '/storage/Downloads/AniDown/'

    def test_custom_config_values(self):
        """Test custom configuration values."""
        from src.core.config import PathConversionConfig

        config = PathConversionConfig(
            enabled=True,
            source_base_path='/custom/source/',
            target_base_path='/custom/target/'
        )

        assert config.enabled is True
        assert config.source_base_path == '/custom/source/'
        assert config.target_base_path == '/custom/target/'


class TestPathConversionIntegration:
    """Integration tests for path conversion with real config."""

    def test_path_conversion_with_real_config(self):
        """
        Test path conversion using actual config loading.
        """
        from src.core.config import config
        from src.services.file.file_service import FileService

        mock_repo = MagicMock()
        file_service = FileService(history_repo=mock_repo)

        # Get the current config values
        enabled = config.path_conversion.enabled
        source_path = config.path_conversion.source_base_path
        target_path = config.path_conversion.target_base_path

        test_path = f'{source_path}test/file.mkv'
        result = file_service.convert_path(test_path)

        if enabled:
            expected = f'{target_path}test/file.mkv'
            assert result == expected
        else:
            assert result == test_path

    def test_config_get_set_path_conversion(self):
        """
        Test getting and setting path conversion config values.
        """
        from src.core.config import config

        # Test getting values
        enabled = config.get('path_conversion.enabled')
        source = config.get('path_conversion.source_base_path')
        target = config.get('path_conversion.target_base_path')

        assert isinstance(enabled, bool)
        assert isinstance(source, str)
        assert isinstance(target, str)

        # Test setting values (save original first)
        original_enabled = enabled

        try:
            config.set('path_conversion.enabled', not original_enabled)
            new_enabled = config.get('path_conversion.enabled')
            assert new_enabled == (not original_enabled)
        finally:
            # Restore original value
            config.set('path_conversion.enabled', original_enabled)
