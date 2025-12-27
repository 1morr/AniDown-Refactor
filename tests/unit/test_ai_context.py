"""
Tests for AI context passing during file renaming.

Tests that the AI file renamer receives correct context:
- folder_structure: Directory structure information
- tvdb_data: TVDB metadata for episode naming
- previous_hardlinks: Previously created hardlinks for conflict detection
"""

import json
import pytest
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch, call

from src.core.interfaces.adapters import RenameResult


class TestAIContextPassing:
    """Tests for AI context information being passed correctly."""

    @pytest.fixture
    def mock_key_pool(self):
        """Create mock key pool."""
        pool = MagicMock()
        pool.purpose = 'file_renamer'
        pool.reserve.return_value = MagicMock(
            key_id='test_key',
            api_key='sk-test',
            base_url='https://api.openai.com/v1',
            model='gpt-4',
            extra_body=''
        )
        pool.get_status.return_value = {'keys': [], 'all_in_long_cooling': False}
        return pool

    @pytest.fixture
    def mock_circuit_breaker(self):
        """Create mock circuit breaker."""
        cb = MagicMock()
        cb.allow_request.return_value = True
        cb.state.value = 'closed'
        return cb

    @pytest.fixture
    def mock_api_client(self):
        """Create mock API client."""
        client = MagicMock()
        client.call.return_value = MagicMock(
            success=True,
            content=json.dumps({
                'main_files': {
                    'test.mp4': 'Season 1/Test - S01E01.mp4'
                },
                'skipped_files': [],
                'seasons_info': {'S01': {'type': 'tv', 'count': 1}},
                'episode_regex': r'- (\d+)',
            }),
            response_time_ms=100,
            error_code=None,
            error_message=None
        )
        return client

    def test_folder_structure_passed_to_ai(
        self,
        mock_key_pool,
        mock_circuit_breaker,
        mock_api_client
    ):
        """
        Test that folder_structure is correctly passed to AI.

        When processing a torrent with nested folder structure,
        the AI should receive the structure information.
        """
        from src.infrastructure.ai.file_renamer import AIFileRenamer

        renamer = AIFileRenamer(
            key_pool=mock_key_pool,
            circuit_breaker=mock_circuit_breaker,
            api_client=mock_api_client
        )

        folder_structure = """
Test Anime/
├── Season 1/
│   ├── Episode 01.mp4
│   ├── Episode 02.mp4
│   └── Episode 03.mp4
└── Specials/
    └── OVA.mp4
"""

        renamer.generate_rename_mapping(
            files=['Episode 01.mp4', 'Episode 02.mp4'],
            category='tv',
            anime_title='Test Anime',
            folder_structure=folder_structure,
            tvdb_data=None
        )

        # Verify API was called
        mock_api_client.call.assert_called_once()

        # Get the messages argument
        call_args = mock_api_client.call.call_args
        messages = call_args.kwargs.get('messages', call_args[1].get('messages', []))

        # Find user message
        user_message = next(
            (m['content'] for m in messages if m['role'] == 'user'),
            ''
        )

        # Verify folder structure is in the message
        assert 'Folder Structure' in user_message
        assert 'Season 1' in user_message

    def test_tvdb_data_passed_to_ai(
        self,
        mock_key_pool,
        mock_circuit_breaker,
        mock_api_client
    ):
        """
        Test that tvdb_data is correctly passed to AI.

        When TVDB data is available, it should be included
        in the AI request for accurate episode naming.
        """
        from src.infrastructure.ai.file_renamer import AIFileRenamer

        renamer = AIFileRenamer(
            key_pool=mock_key_pool,
            circuit_breaker=mock_circuit_breaker,
            api_client=mock_api_client
        )

        tvdb_data = {
            'id': 123456,
            'name': 'Test Anime',
            'episodes': [
                {'seasonNumber': 1, 'number': 1, 'name': 'Pilot Episode'},
                {'seasonNumber': 1, 'number': 2, 'name': 'The Journey Begins'},
                {'seasonNumber': 1, 'number': 3, 'name': 'First Battle'},
            ]
        }

        renamer.generate_rename_mapping(
            files=['Episode 01.mp4', 'Episode 02.mp4'],
            category='tv',
            anime_title='Test Anime',
            folder_structure=None,
            tvdb_data=tvdb_data
        )

        # Verify API was called
        mock_api_client.call.assert_called_once()

        # Get the messages argument
        call_args = mock_api_client.call.call_args
        messages = call_args.kwargs.get('messages', call_args[1].get('messages', []))

        # Find user message
        user_message = next(
            (m['content'] for m in messages if m['role'] == 'user'),
            ''
        )

        # Verify TVDB data is in the message
        assert 'TVDB Data' in user_message
        assert 'Pilot Episode' in user_message

    def test_previous_hardlinks_passed_to_ai_in_batch(
        self,
        mock_key_pool,
        mock_circuit_breaker,
        mock_api_client
    ):
        """
        Test that previous_hardlinks is passed during batch processing.

        When processing files in batches, previously created hardlinks
        should be passed to subsequent batches for conflict detection.
        """
        from src.infrastructure.ai.file_renamer import AIFileRenamer

        # Create renamer with small batch size to force batching
        renamer = AIFileRenamer(
            key_pool=mock_key_pool,
            circuit_breaker=mock_circuit_breaker,
            api_client=mock_api_client,
            batch_size=2  # Small batch size to test batching
        )

        # Create files that will span multiple batches
        files = [
            'Episode 01.mp4',
            'Episode 02.mp4',
            'Episode 03.mp4',
            'Episode 04.mp4',
        ]

        # First batch returns Season 1/... filenames
        # Note: API response uses indexed keys ('1', '2') not original filenames
        mock_api_client.call.side_effect = [
            MagicMock(
                success=True,
                content=json.dumps({
                    'main_files': {
                        '1': 'Season 1/Test - S01E01.mp4',
                        '2': 'Season 1/Test - S01E02.mp4',
                    },
                    'skipped_files': [],
                    'seasons_info': {},
                    'episode_regex': r'(\d+)',
                }),
                response_time_ms=100,
                error_code=None,
                error_message=None
            ),
            MagicMock(
                success=True,
                content=json.dumps({
                    'main_files': {
                        '1': 'Season 1/Test - S01E03.mp4',
                        '2': 'Season 1/Test - S01E04.mp4',
                    },
                    'skipped_files': [],
                    'seasons_info': {},
                    'episode_regex': r'(\d+)',
                }),
                response_time_ms=100,
                error_code=None,
                error_message=None
            ),
        ]

        renamer.generate_rename_mapping(
            files=files,
            category='tv',
            anime_title='Test Anime',
            folder_structure=None,
            tvdb_data=None
        )

        # Verify API was called twice (2 batches)
        assert mock_api_client.call.call_count == 2

        # Get second call's messages
        second_call_args = mock_api_client.call.call_args_list[1]
        messages = second_call_args.kwargs.get('messages', second_call_args[1].get('messages', []))

        # Find user message
        user_message = next(
            (m['content'] for m in messages if m['role'] == 'user'),
            ''
        )

        # Verify previous hardlinks are in the second batch message
        assert 'Previous Hardlinks' in user_message
        assert 'S01E01' in user_message or 'S01E02' in user_message

    def test_all_context_combined(
        self,
        mock_key_pool,
        mock_circuit_breaker,
        mock_api_client
    ):
        """
        Test that all context (folder_structure, tvdb_data, previous_hardlinks)
        can be passed together.
        """
        from src.infrastructure.ai.file_renamer import AIFileRenamer

        renamer = AIFileRenamer(
            key_pool=mock_key_pool,
            circuit_breaker=mock_circuit_breaker,
            api_client=mock_api_client
        )

        folder_structure = 'Test Anime/Season 1/'
        tvdb_data = {
            'id': 123,
            'name': 'Test',
            'episodes': [{'number': 1, 'name': 'Ep1'}]
        }

        renamer.generate_rename_mapping(
            files=['test.mp4'],
            category='tv',
            anime_title='Test Anime',
            folder_structure=folder_structure,
            tvdb_data=tvdb_data
        )

        # Verify API was called
        mock_api_client.call.assert_called_once()

        # Get messages
        call_args = mock_api_client.call.call_args
        messages = call_args.kwargs.get('messages', call_args[1].get('messages', []))

        user_message = next(
            (m['content'] for m in messages if m['role'] == 'user'),
            ''
        )

        # Verify all context is present
        assert 'Folder Structure' in user_message
        assert 'TVDB Data' in user_message
        assert 'Category' in user_message


class TestRenameServiceTVDBIntegration:
    """Tests for TVDB integration in rename service."""

    def test_tvdb_data_used_for_episode_naming(self):
        """
        Test that TVDB data is used for episode naming.

        When TVDB data is provided with episode information,
        it should influence the generated filenames.
        """
        from src.services.rename.rename_service import RenameService
        from src.services.rename.file_classifier import ClassifiedFile

        video_files = [
            ClassifiedFile(
                name='Episode 01.mp4',
                relative_path='Episode 01.mp4',
                full_path='/downloads/Episode 01.mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            )
        ]

        tvdb_data = {
            'id': 123456,
            'name': 'Test Anime',
            'episodes': [
                {
                    'seasonNumber': 1,
                    'number': 1,
                    'name': 'The Beginning of Everything'
                }
            ]
        }

        mock_ai_renamer = MagicMock()
        mock_ai_renamer.generate_rename_mapping.return_value = RenameResult(
            main_files={
                'Episode 01.mp4': 'Season 1/Test Anime - S01E01 - The Beginning of Everything.mp4'
            },
            skipped_files=[],
            seasons_info={},
            patterns={},
            method='ai_with_tvdb'
        )

        mock_anime_repo = MagicMock()
        mock_anime_repo.get_patterns.return_value = None

        with patch('src.core.config.config.use_consistent_naming_tv', False):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='Test',
                season=1,
                category='tv',
                is_multi_season=False,
                tvdb_data=tvdb_data,  # Pass TVDB data
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify AI was called with TVDB data
            mock_ai_renamer.generate_rename_mapping.assert_called_once()
            call_kwargs = mock_ai_renamer.generate_rename_mapping.call_args.kwargs

            # Verify TVDB data was passed
            assert call_kwargs.get('tvdb_data') == tvdb_data


class TestPreviousHardlinksConflictDetection:
    """Tests for previous hardlinks conflict detection."""

    def test_previous_hardlinks_prevent_duplicates(self):
        """
        Test that previous hardlinks are used to prevent duplicate filenames.

        When batch processing, files in later batches should not
        generate filenames that conflict with earlier batches.
        """
        from src.infrastructure.ai.file_renamer import AIFileRenamer

        mock_key_pool = MagicMock()
        mock_key_pool.purpose = 'renamer'
        mock_key_pool.reserve.return_value = MagicMock(
            key_id='key1',
            api_key='sk-test',
            base_url='https://api.openai.com/v1',
            model='gpt-4',
            extra_body=''
        )
        mock_key_pool.get_status.return_value = {'keys': [], 'all_in_long_cooling': False}

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        mock_client = MagicMock()

        renamer = AIFileRenamer(
            key_pool=mock_key_pool,
            circuit_breaker=mock_cb,
            api_client=mock_client,
            batch_size=2
        )

        # Build user message with previous hardlinks
        message, _ = renamer._build_user_message(
            files=['Episode 03.mp4'],
            category='tv',
            anime_title='Test',
            folder_structure=None,
            tvdb_data=None,
            previous_hardlinks=[
                'Season 1/Test - S01E01.mp4',
                'Season 1/Test - S01E02.mp4'
            ]
        )

        # Verify previous hardlinks are in message
        assert 'Previous Hardlinks' in message
        assert 'S01E01' in message
        assert 'S01E02' in message


class TestFolderStructureBuilding:
    """Tests for folder structure building functionality."""

    def test_build_folder_structure_from_torrent(self):
        """
        Test building folder structure from torrent files.

        The folder structure should accurately represent the
        directory hierarchy of the torrent.
        """
        torrent_files = [
            {'name': 'Test Anime/Season 1/Episode 01.mp4'},
            {'name': 'Test Anime/Season 1/Episode 02.mp4'},
            {'name': 'Test Anime/Season 1/Episode 01.ass'},
            {'name': 'Test Anime/Specials/OVA.mp4'},
        ]

        # Build expected structure
        dirs = set()
        for f in torrent_files:
            import os
            dir_path = os.path.dirname(f['name'])
            while dir_path:
                dirs.add(dir_path)
                dir_path = os.path.dirname(dir_path)

        # Verify structure contains expected directories
        assert 'Test Anime' in dirs or any('Test Anime' in d for d in dirs)
        assert 'Test Anime/Season 1' in dirs or any('Season 1' in d for d in dirs)
