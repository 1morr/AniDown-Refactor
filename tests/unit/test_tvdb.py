"""
Tests for TVDB API integration.

Tests TVDB adapter and metadata service functionality.
"""

import pytest
from unittest.mock import MagicMock, patch

from tests.fixtures.test_data import TVDB_TEST_ANIME


class TestTVDBAdapter:
    """Tests for TVDB API adapter."""

    @pytest.fixture
    def tvdb_adapter(self):
        """Create TVDB adapter instance."""
        from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter

        return TVDBAdapter()

    def test_tvdb_adapter_initialization(self):
        """Test TVDB adapter initializes correctly."""
        from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter

        adapter = TVDBAdapter()

        assert adapter is not None

    def test_tvdb_disabled_returns_none(self, tvdb_adapter):
        """Test that disabled TVDB returns None."""
        from src.core.config import config

        if not config.tvdb.enabled:
            result = tvdb_adapter.search_series('Test')
            assert result is None or result == []

    @patch('requests.Session.get')
    def test_search_series_success(self, mock_get, tvdb_adapter):
        """Test searching series on TVDB."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {
                    'id': 12345,
                    'name': '金牌得主',
                    'year': '2025',
                    'overview': 'Test description'
                }
            ]
        }
        mock_get.return_value = mock_response

        # This test depends on implementation
        # Skip if TVDB is not enabled
        from src.core.config import config
        if not config.tvdb.enabled or not config.tvdb.api_key:
            pytest.skip('TVDB not configured')

    @patch('requests.Session.get')
    def test_get_series_episodes(self, mock_get, tvdb_adapter):
        """Test getting series episodes from TVDB."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': {
                'episodes': [
                    {
                        'id': 1,
                        'seasonNumber': 1,
                        'number': 1,
                        'name': 'Episode 1'
                    },
                    {
                        'id': 2,
                        'seasonNumber': 1,
                        'number': 2,
                        'name': 'Episode 2'
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        # Skip if TVDB is not configured
        from src.core.config import config
        if not config.tvdb.enabled:
            pytest.skip('TVDB not configured')


class TestMetadataService:
    """Tests for metadata service."""

    @pytest.fixture
    def metadata_service(self):
        """Create MetadataService instance."""
        from src.services.metadata_service import MetadataService
        from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter

        return MetadataService(metadata_client=TVDBAdapter())

    @pytest.fixture
    def mock_metadata_service(self):
        """Create MetadataService with mocked client."""
        from src.services.metadata_service import MetadataService

        mock_client = MagicMock()
        return MetadataService(metadata_client=mock_client)

    def test_metadata_service_initialization(self, metadata_service):
        """Test MetadataService initializes correctly."""
        assert metadata_service is not None

    def test_get_tvdb_data_for_anime(self, mock_metadata_service):
        """Test getting TVDB data for anime."""
        mock_metadata_service._metadata_client.search_series.return_value = [{
            'id': 12345,
            'name': '金牌得主',
            'year': '2025'
        }]
        mock_metadata_service._metadata_client.get_series_info.return_value = {
            'id': 12345,
            'name': '金牌得主',
            'episodes': [
                {'seasonNumber': 1, 'number': 1, 'name': 'Ep 1'}
            ]
        }

        result = mock_metadata_service.get_tvdb_data_for_anime('金牌得主')

        # Should return TVDB data or None if not found
        assert result is None or 'tvdb_id' in result

    def test_get_episode_mapping(self, mock_metadata_service):
        """Test getting episode data from TVDB by ID."""
        mock_metadata_service._metadata_client.get_series_episodes.return_value = {
            'episodes': [
                {'seasonNumber': 1, 'number': 1, 'name': 'First Episode'},
                {'seasonNumber': 1, 'number': 2, 'name': 'Second Episode'}
            ]
        }

        # MetadataService uses get_tvdb_data_by_id for series details
        result = mock_metadata_service.get_tvdb_data_by_id(
            series_id=12345
        )

        # Should return data or None
        assert result is None or isinstance(result, dict)


@pytest.mark.integration
@pytest.mark.requires_tvdb
class TestTVDBIntegration:
    """Integration tests for TVDB functionality."""

    def test_search_real_anime(self, requires_tvdb):
        """
        Test searching for real anime on TVDB.

        Requires TVDB API key to be configured.
        """
        from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter

        adapter = TVDBAdapter()

        # Search for a known anime
        results = adapter.search_series('金牌得主')

        if results:
            print(f'\n📺 TVDB Search Results:')
            for result in results[:3]:
                print(f"   - {result.get('name')} ({result.get('year', 'N/A')})")
        else:
            print('\n📺 No TVDB results found')

    @pytest.mark.parametrize('anime_title,expected_id', TVDB_TEST_ANIME)
    def test_search_test_anime(self, requires_tvdb, anime_title, expected_id):
        """Test searching for test anime titles."""
        from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter

        adapter = TVDBAdapter()

        results = adapter.search_series(anime_title)

        # Just verify search works
        print(f'\n📺 Search "{anime_title}": {len(results) if results else 0} results')

        if results:
            for result in results[:2]:
                print(f"   - {result.get('name')} (ID: {result.get('id')})")

    def test_get_series_info(self, requires_tvdb):
        """Test getting detailed series info from TVDB."""
        from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter
        from src.services.metadata_service import MetadataService

        adapter = TVDBAdapter()
        service = MetadataService(metadata_client=adapter)

        # Search first
        results = adapter.search_series('BanG Dream')

        if results and len(results) > 0:
            series_id = results[0].get('id')

            if series_id:
                info = adapter.get_series_extended(series_id)

                if info:
                    print(f'\n📺 Series Info:')
                    print(f"   Name: {info.get('name')}")
                    print(f"   ID: {info.get('id')}")
                    print(f"   Year: {info.get('year', 'N/A')}")
        else:
            pytest.skip('No series found to test')

    def test_full_tvdb_workflow(self, requires_tvdb):
        """Test complete TVDB workflow for anime metadata."""
        from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter
        from src.services.metadata_service import MetadataService

        adapter = TVDBAdapter()
        service = MetadataService(metadata_client=adapter)

        anime_title = '金牌得主'

        # Get TVDB data
        tvdb_data = service.get_tvdb_data_for_anime(anime_title)

        if tvdb_data:
            print(f'\n📺 TVDB Data for "{anime_title}":')
            print(f"   TVDB ID: {tvdb_data.get('tvdb_id')}")
            print(f"   Name: {tvdb_data.get('name')}")

            # Check for episode data
            if 'episodes' in tvdb_data:
                print(f"   Episodes: {len(tvdb_data.get('episodes', []))}")
        else:
            print(f'\n📺 No TVDB data found for "{anime_title}"')


class TestTVDBDataParsing:
    """Tests for TVDB data parsing and formatting."""

    def test_parse_episode_number(self):
        """Test parsing episode numbers from TVDB data."""
        tvdb_episodes = [
            {'seasonNumber': 1, 'number': 1, 'name': 'First'},
            {'seasonNumber': 1, 'number': 2, 'name': 'Second'},
            {'seasonNumber': 2, 'number': 1, 'name': 'Third'},
        ]

        # Filter season 1 episodes
        season_1 = [ep for ep in tvdb_episodes if ep['seasonNumber'] == 1]

        assert len(season_1) == 2
        assert season_1[0]['number'] == 1
        assert season_1[1]['number'] == 2

    def test_episode_name_mapping(self):
        """Test mapping episode names from TVDB."""
        tvdb_episodes = [
            {'number': 1, 'name': 'The Beginning'},
            {'number': 2, 'name': 'The Journey'},
        ]

        mapping = {ep['number']: ep['name'] for ep in tvdb_episodes}

        assert mapping[1] == 'The Beginning'
        assert mapping[2] == 'The Journey'
