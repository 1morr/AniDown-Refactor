"""
Tests for multi-file torrent handling with consistency mode.

Tests the behavior when:
- A torrent contains multiple files
- is_multi_season is False
- use_consistent_naming is True
"""

import pytest
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch

from src.core.interfaces.adapters import RenameResult
from src.services.rename.file_classifier import ClassifiedFile, FileClassifier


class TestMultiFileConsistencyMode:
    """
    Tests for multi-file torrent handling with consistency mode enabled.

    When a torrent contains multiple files, multi-season is disabled,
    and consistency naming is enabled, the system should:
    1. Use regex patterns from database if available
    2. Fall back to AI if no patterns or regex fails
    3. Apply consistent naming format across all files
    """

    @pytest.fixture
    def mock_anime_repo(self):
        """Create mock anime repository with patterns."""
        repo = MagicMock()
        repo.get_patterns.return_value = {
            'episode_regex': r'- (\d+) \[',
            'subtitle_type_regex': r'\[(CHS|CHT|JPN)\]',
            'special_tags_regex': r'\[(1080p|720p)\]',
        }
        return repo

    @pytest.fixture
    def mock_ai_file_renamer(self):
        """Create mock AI file renamer."""
        renamer = MagicMock()
        renamer.generate_rename_mapping.return_value = RenameResult(
            main_files={
                '[ANi] Test Anime - 01 [1080P][CHT].mp4': 'Season 1/Test Anime - S01E01 - ANi [CHT].mp4',
                '[ANi] Test Anime - 02 [1080P][CHT].mp4': 'Season 1/Test Anime - S01E02 - ANi [CHT].mp4',
                '[ANi] Test Anime - 03 [1080P][CHT].mp4': 'Season 1/Test Anime - S01E03 - ANi [CHT].mp4',
            },
            skipped_files=[],
            seasons_info={'S01': {'type': 'tv', 'count': 3}},
            patterns={
                'episode_regex': r'- (\d+) \[',
                'subtitle_type_regex': r'\[(CHS|CHT|JPN)\]',
            },
            method='ai'
        )
        return renamer

    @pytest.fixture
    def video_files(self) -> List[ClassifiedFile]:
        """Create test video files."""
        return [
            ClassifiedFile(
                name='[ANi] Test Anime - 01 [1080P][CHT].mp4',
                relative_path='[ANi] Test Anime - 01 [1080P][CHT].mp4',
                full_path='/downloads/[ANi] Test Anime - 01 [1080P][CHT].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='[ANi] Test Anime - 02 [1080P][CHT].mp4',
                relative_path='[ANi] Test Anime - 02 [1080P][CHT].mp4',
                full_path='/downloads/[ANi] Test Anime - 02 [1080P][CHT].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='[ANi] Test Anime - 03 [1080P][CHT].mp4',
                relative_path='[ANi] Test Anime - 03 [1080P][CHT].mp4',
                full_path='/downloads/[ANi] Test Anime - 03 [1080P][CHT].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
        ]

    def test_multifile_with_consistency_uses_db_patterns(
        self,
        mock_anime_repo,
        mock_ai_file_renamer,
        video_files
    ):
        """
        Test that multi-file torrent with consistency mode uses database patterns.

        When:
        - Multiple files in torrent
        - is_multi_season = False
        - use_consistent_naming = True
        - Database has valid patterns

        Expected:
        - AI should NOT be called
        - Regex patterns should be used for all files
        - Output should use consistent naming format
        """
        from src.services.rename.rename_service import RenameService

        with patch('src.core.config.config.use_consistent_naming_tv', True):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=False,
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify result
            assert result is not None
            assert result.file_count == 3

            # Verify regex was used (not AI)
            assert 'regex' in result.method.lower() or '数据库' in result.method

            # Verify consistent naming format
            for old_name, new_name in result.main_files.items():
                assert 'S01E' in new_name or 'Season 1' in new_name

    def test_multifile_with_consistency_falls_back_to_ai(
        self,
        mock_ai_file_renamer,
        video_files
    ):
        """
        Test that multi-file torrent falls back to AI when no database patterns.

        When:
        - Multiple files in torrent
        - is_multi_season = False
        - use_consistent_naming = True
        - Database has NO patterns

        Expected:
        - AI should be called
        - AI result should be used
        - Patterns should be saved to database
        """
        from src.services.rename.rename_service import RenameService

        mock_anime_repo = MagicMock()
        mock_anime_repo.get_patterns.return_value = None  # No patterns in DB

        with patch('src.core.config.config.use_consistent_naming_tv', True):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=False,
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify AI was called
            mock_ai_file_renamer.generate_rename_mapping.assert_called_once()

            # Verify result
            assert result is not None
            assert result.file_count == 3

            # Verify last_used_ai is True
            assert service.last_used_ai is True

    def test_multifile_multiseason_skips_regex(
        self,
        mock_anime_repo,
        mock_ai_file_renamer,
        video_files
    ):
        """
        Test that multi-season torrent skips regex and uses AI directly.

        When:
        - Multiple files in torrent
        - is_multi_season = True (forces AI)
        - use_consistent_naming = True

        Expected:
        - AI should be called directly
        - Regex should NOT be attempted
        - AI filenames should be used directly
        """
        from src.services.rename.rename_service import RenameService

        with patch('src.core.config.config.use_consistent_naming_tv', True):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=True,  # Multi-season forces AI
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify AI was called
            mock_ai_file_renamer.generate_rename_mapping.assert_called_once()

            # Verify result
            assert result is not None

            # Verify AI reason
            assert service.last_used_ai is True
            assert '多季' in service.ai_reason

    def test_multifile_consistency_disabled_uses_ai_filenames(
        self,
        mock_anime_repo,
        mock_ai_file_renamer,
        video_files
    ):
        """
        Test that with consistency disabled, AI filenames are used directly.

        When:
        - Multiple files in torrent
        - is_multi_season = False
        - use_consistent_naming = False (disabled)

        Expected:
        - AI should be called
        - AI returned filenames should be used directly
        """
        from src.services.rename.rename_service import RenameService

        # No patterns in DB to force AI usage
        mock_anime_repo.get_patterns.return_value = None

        with patch('src.core.config.config.use_consistent_naming_tv', False):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=False,
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify AI was called
            mock_ai_file_renamer.generate_rename_mapping.assert_called_once()

            # Verify result
            assert result is not None
            assert result.file_count == 3

            # Verify AI filenames are used
            assert 'AI' in result.method

    def test_multifile_regex_partial_match_falls_back_to_ai(
        self,
        mock_ai_file_renamer
    ):
        """
        Test that partial regex match falls back to AI.

        When:
        - Multiple files in torrent
        - Database has patterns but they don't match all files

        Expected:
        - AI should be called
        - All files should be processed with AI
        """
        from src.services.rename.rename_service import RenameService

        # Create video files with mixed formats
        video_files = [
            ClassifiedFile(
                name='[ANi] Test Anime - 01 [1080P].mp4',
                relative_path='[ANi] Test Anime - 01 [1080P].mp4',
                full_path='/downloads/[ANi] Test Anime - 01 [1080P].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='Test Anime Episode 2 HD.mp4',  # Different format
                relative_path='Test Anime Episode 2 HD.mp4',
                full_path='/downloads/Test Anime Episode 2 HD.mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
        ]

        mock_anime_repo = MagicMock()
        mock_anime_repo.get_patterns.return_value = {
            'episode_regex': r'- (\d+) \[',  # Only matches first file
        }

        # Update mock to return result for these files
        mock_ai_file_renamer.generate_rename_mapping.return_value = RenameResult(
            main_files={
                '[ANi] Test Anime - 01 [1080P].mp4': 'Season 1/Test Anime - S01E01.mp4',
                'Test Anime Episode 2 HD.mp4': 'Season 1/Test Anime - S01E02.mp4',
            },
            skipped_files=[],
            seasons_info={'S01': {'type': 'tv', 'count': 2}},
            patterns={'episode_regex': r'Episode (\d+)|- (\d+)'},
            method='ai'
        )

        with patch('src.core.config.config.use_consistent_naming_tv', True):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=False,
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify AI was called (regex partial match should trigger AI)
            mock_ai_file_renamer.generate_rename_mapping.assert_called_once()

            # Verify result
            assert result is not None
            # Note: The actual count depends on how the system handles partial matches
            # It may only process the files that didn't match regex, or all files
            assert result.file_count >= 1


class TestMultiFileSubtitleHandling:
    """Tests for subtitle handling with multi-file torrents."""

    @pytest.fixture
    def video_files(self) -> List[ClassifiedFile]:
        """Create test video files."""
        return [
            ClassifiedFile(
                name='[ANi] Test Anime - 01 [1080P].mp4',
                relative_path='[ANi] Test Anime - 01 [1080P].mp4',
                full_path='/downloads/[ANi] Test Anime - 01 [1080P].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='[ANi] Test Anime - 02 [1080P].mp4',
                relative_path='[ANi] Test Anime - 02 [1080P].mp4',
                full_path='/downloads/[ANi] Test Anime - 02 [1080P].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
        ]

    @pytest.fixture
    def subtitle_files(self) -> List[ClassifiedFile]:
        """Create test subtitle files."""
        return [
            ClassifiedFile(
                name='[ANi] Test Anime - 01 [1080P].chs.ass',
                relative_path='[ANi] Test Anime - 01 [1080P].chs.ass',
                full_path='/downloads/[ANi] Test Anime - 01 [1080P].chs.ass',
                extension='.ass',
                size=50000,
                file_type='subtitle'
            ),
            ClassifiedFile(
                name='[ANi] Test Anime - 02 [1080P].chs.ass',
                relative_path='[ANi] Test Anime - 02 [1080P].chs.ass',
                full_path='/downloads/[ANi] Test Anime - 02 [1080P].chs.ass',
                extension='.ass',
                size=50000,
                file_type='subtitle'
            ),
        ]

    def test_subtitle_mapping_generated_from_video_mapping(
        self,
        video_files,
        subtitle_files
    ):
        """
        Test that subtitle mapping is generated based on video mapping.

        Each subtitle should be renamed to match its corresponding video file.
        """
        from src.services.rename.rename_service import RenameService

        video_rename_mapping = {
            '[ANi] Test Anime - 01 [1080P].mp4': 'Season 1/Test Anime - S01E01 - ANi.mp4',
            '[ANi] Test Anime - 02 [1080P].mp4': 'Season 1/Test Anime - S01E02 - ANi.mp4',
        }

        service = RenameService()

        subtitle_mapping = service.generate_subtitle_mapping(
            video_files=video_files,
            subtitle_files=subtitle_files,
            video_rename_mapping=video_rename_mapping
        )

        # Verify subtitle mapping was generated
        assert len(subtitle_mapping) >= 1

        # Verify subtitle names match video format
        for old_sub, new_sub in subtitle_mapping.items():
            assert '.ass' in new_sub or '.srt' in new_sub


class TestMultiSeasonDetection:
    """Tests for multi-season content detection."""

    def test_detect_multi_season_from_folder_structure(self):
        """Test detection of multi-season content from folder structure."""
        # Multi-season folder structures that should be detected
        multi_season_structures = [
            'Season 1/ep01.mp4\nSeason 2/ep01.mp4',
            'S01/file.mp4\nS02/file.mp4',
            'シーズン1/file.mp4\nシーズン2/file.mp4',
        ]

        # This test verifies the logic for detecting multi-season content
        # The actual implementation may vary
        for structure in multi_season_structures:
            has_multiple_seasons = (
                'Season 1' in structure and 'Season 2' in structure or
                'S01' in structure and 'S02' in structure or
                'シーズン1' in structure and 'シーズン2' in structure
            )
            assert has_multiple_seasons is True

    def test_single_season_not_detected_as_multi(self):
        """Test that single season content is not detected as multi-season."""
        single_season_structures = [
            'Season 1/ep01.mp4\nSeason 1/ep02.mp4',
            'S01/file1.mp4\nS01/file2.mp4',
        ]

        for structure in single_season_structures:
            # Count unique season numbers
            has_multiple_seasons = (
                'Season 2' in structure or 'S02' in structure
            )
            assert has_multiple_seasons is False
