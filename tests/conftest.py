"""
Test configuration and fixtures for AniDown tests.

This module provides:
- Test configuration with real test data
- Pytest fixtures for common test scenarios
- Mock objects for external dependencies
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator, Optional
from unittest.mock import MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ==================== Test Data ====================

class TestData:
    """Test data constants using real data from user."""

    # Mikan RSS feeds for testing
    RSS_MIKAN_MY_BANGUMI = (
        'https://mikanani.me/RSS/MyBangumi?token=GTd1ABkavs6Qa8O5ZwF3tw%3d%3d'
    )
    RSS_MIKAN_SINGLE_ANIME = (
        'https://mikanani.me/RSS/Bangumi?bangumiId=3777&subgroupid=576'
    )

    # Blocked keywords for RSS filtering
    RSS_BLOCKED_KEYWORDS = '繁日内嵌\n简日内嵌'

    # Torrent file test data
    TORRENT_FILE = '[Nekomoe kissaten&VCB-Studio] Medalist [Ma10p_1080p].torrent'
    TORRENT_ANIME_TITLE = '金牌得主'
    TORRENT_SUBTITLE_GROUP = '喵萌奶茶屋&VCB-Studio'
    TORRENT_CATEGORY = 'tv'
    TORRENT_SEASON = 1

    # Magnet link test data
    MAGNET_HASH = '55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0'
    MAGNET_ANIME_TITLE = 'BanG Dream! It\'s MyGO!!!!!'
    MAGNET_SUBTITLE_GROUP = '喵萌Production&VCB-Studio'
    MAGNET_CATEGORY = 'tv'
    MAGNET_SEASON = 1

    # Discord test data
    DISCORD_TEST_MESSAGE = 'AniDown 测试消息'

    # Sample anime titles for AI parsing
    SAMPLE_TITLES = [
        '[ANi] 狼與香辛料 MERCHANT MEETS THE WISE WOLF - 26 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
        '[Nekomoe kissaten&LoliHouse] Tensei Shitara Slime Datta Ken S3 - 24 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv',
        '[VCB-Studio] BanG Dream! Its MyGO!!!!! [Ma10p_1080p]',
    ]


# ==================== Test Configuration ====================

@pytest.fixture(scope='session')
def test_config_path(tmp_path_factory) -> Path:
    """Create a temporary test configuration file."""
    config_dir = tmp_path_factory.mktemp('config')
    config_path = config_dir / 'test_config.json'

    test_config = {
        'rss': {
            'fixed_urls': [
                {
                    'url': TestData.RSS_MIKAN_MY_BANGUMI,
                    'blocked_keywords': TestData.RSS_BLOCKED_KEYWORDS,
                    'blocked_regex': '',
                    'media_type': 'anime'
                }
            ],
            'check_interval': 3600
        },
        'discord': {
            'enabled': False,
            'rss_webhook_url': '',
            'hardlink_webhook_url': ''
        },
        'qbittorrent': {
            'url': 'http://localhost:8080',
            'username': 'admin',
            'password': 'adminadmin',
            'base_download_path': '/downloads/AniDown/',
            'category': 'AniDown',
            'anime_folder_name': 'Anime',
            'live_action_folder_name': 'LiveAction',
            'tv_folder_name': 'TV',
            'movie_folder_name': 'Movies'
        },
        'openai': {
            'key_pools': [],
            'title_parse': {
                'pool_name': '',
                'api_key': '',
                'base_url': 'https://api.openai.com/v1',
                'model': 'gpt-4',
                'extra_body': '',
                'timeout': 180,
                'retries': 3
            },
            'multi_file_rename': {
                'pool_name': '',
                'api_key': '',
                'base_url': 'https://api.openai.com/v1',
                'model': 'gpt-4',
                'extra_body': '',
                'timeout': 360,
                'retries': 3,
                'max_batch_size': 30,
                'batch_processing_retries': 2
            },
            'subtitle_match': {
                'pool_name': '',
                'api_key': '',
                'base_url': 'https://api.openai.com/v1',
                'model': 'gpt-4',
                'extra_body': '',
                'timeout': 180,
                'retries': 3
            },
            'rate_limits': {
                'max_consecutive_errors': 5,
                'key_cooldown_seconds': 30,
                'circuit_breaker_cooldown_seconds': 900,
                'max_backoff_seconds': 300
            }
        },
        'webhook': {
            'host': '0.0.0.0',
            'port': 5678,
            'enabled': True
        },
        'webui': {
            'host': '0.0.0.0',
            'port': 8081,
            'enabled': True
        },
        'path_conversion': {
            'enabled': False,
            'source_base_path': '/downloads/AniDown/',
            'target_base_path': '/path/to/target/'
        },
        'tvdb': {
            'api_key': '',
            'max_data_length': 10000
        },
        'link_target_path': '/library/TV Shows',
        'movie_link_target_path': '/library/Movies',
        'live_action_tv_target_path': '/library/LiveAction/TV Shows',
        'live_action_movie_target_path': '/library/LiveAction/Movies',
        'use_consistent_naming_tv': False,
        'use_consistent_naming_movie': False
    }

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(test_config, f, ensure_ascii=False, indent=2)

    return config_path


@pytest.fixture(scope='session')
def test_db_path(tmp_path_factory) -> Path:
    """Create a temporary test database path."""
    db_dir = tmp_path_factory.mktemp('db')
    return db_dir / 'test_anidown.db'


@pytest.fixture
def temp_download_dir(tmp_path) -> Path:
    """Create a temporary download directory."""
    download_dir = tmp_path / 'downloads' / 'AniDown'
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


@pytest.fixture
def temp_library_dir(tmp_path) -> Path:
    """Create a temporary library directory."""
    library_dir = tmp_path / 'library'
    (library_dir / 'TV Shows').mkdir(parents=True, exist_ok=True)
    (library_dir / 'Movies').mkdir(parents=True, exist_ok=True)
    return library_dir


# ==================== Mock Fixtures ====================

@pytest.fixture
def mock_qbit_client():
    """Mock qBittorrent client."""
    mock = MagicMock()
    mock.is_connected.return_value = True
    mock.add_torrent.return_value = True
    mock.add_torrent_file.return_value = True
    mock.add_magnet.return_value = True
    mock.get_torrent_info.return_value = {
        'hash': 'abc123',
        'name': 'Test Torrent',
        'progress': 1.0,
        'state': 'completed'
    }
    mock.get_torrent_files.return_value = [
        {'name': 'test_video.mkv', 'size': 1000000000}
    ]
    mock.get_all_torrents.return_value = []
    mock.delete_torrent.return_value = True
    return mock


@pytest.fixture
def mock_title_parser():
    """Mock AI title parser."""
    mock = MagicMock()

    class MockResult:
        def __init__(self):
            self.original_title = TestData.SAMPLE_TITLES[0]
            self.clean_title = '狼與香辛料'
            self.full_title = '狼與香辛料 MERCHANT MEETS THE WISE WOLF'
            self.subtitle_group = 'ANi'
            self.season = 1
            self.episode = 26
            self.category = 'tv'
            self.is_collection = False

    mock.parse.return_value = MockResult()
    return mock


@pytest.fixture
def mock_file_renamer():
    """Mock AI file renamer."""
    mock = MagicMock()
    mock.process_multi_file_rename.return_value = {
        'success': True,
        'files': {
            'test_video.mkv': '狼與香辛料 S01E26.mkv'
        }
    }
    return mock


@pytest.fixture
def mock_discord_webhook():
    """Mock Discord webhook client."""
    from src.infrastructure.notification.discord.webhook_client import WebhookResponse

    mock = MagicMock()
    # Return WebhookResponse objects, not bools
    mock_response = WebhookResponse(success=True, status_code=204)
    mock.send.return_value = mock_response
    mock.send_embed.return_value = mock_response
    mock.send_message.return_value = mock_response
    return mock


@pytest.fixture
def mock_rss_response():
    """Mock RSS feed response."""
    return '''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
    <channel>
        <title>Mikan Project</title>
        <item>
            <title>[ANi] 狼與香辛料 - 26 [1080P][Baha][WEB-DL].mp4</title>
            <link>https://mikanani.me/Home/Episode/abc123</link>
            <enclosure url="https://mikanani.me/Download/abc123.torrent" type="application/x-bittorrent"/>
            <pubDate>Sat, 01 Jan 2025 12:00:00 +0800</pubDate>
        </item>
        <item>
            <title>[Nekomoe] Tensei Slime S3 - 24 [1080p].mkv</title>
            <link>https://mikanani.me/Home/Episode/def456</link>
            <enclosure url="https://mikanani.me/Download/def456.torrent" type="application/x-bittorrent"/>
            <pubDate>Sat, 01 Jan 2025 11:00:00 +0800</pubDate>
        </item>
    </channel>
</rss>'''


# ==================== Integration Test Fixtures ====================

@pytest.fixture
def real_config():
    """
    Load real configuration for integration tests.

    Skips test if required configuration is not available.
    """
    config_path = os.getenv('CONFIG_PATH', 'config.json')
    if not os.path.exists(config_path):
        pytest.skip('Configuration file not found')

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def requires_qbit(real_config):
    """
    Fixture that requires qBittorrent to be configured and accessible.

    Skips test if qBittorrent is not available.
    """
    from src.infrastructure.downloader.qbit_adapter import QBitAdapter

    qb = QBitAdapter()
    if not qb.is_connected():
        pytest.skip('qBittorrent not available')
    return qb


@pytest.fixture
def requires_discord(real_config):
    """
    Fixture that requires Discord webhook to be configured.

    Skips test if Discord is not configured.
    """
    if not real_config.get('discord', {}).get('enabled', False):
        pytest.skip('Discord not configured')
    if not real_config.get('discord', {}).get('rss_webhook_url'):
        pytest.skip('Discord RSS webhook URL not configured')
    return real_config['discord']


@pytest.fixture
def requires_ai(real_config):
    """
    Fixture that requires OpenAI API to be configured.

    Skips test if OpenAI is not configured.
    """
    openai_config = real_config.get('openai', {})
    title_parse = openai_config.get('title_parse', {})
    key_pools = openai_config.get('key_pools', [])

    # 检查是否有独立配置或使用了 key_pool
    has_standalone = bool(title_parse.get('api_key'))
    has_pool = bool(title_parse.get('pool_name') and key_pools)

    if not has_standalone and not has_pool:
        pytest.skip('OpenAI API not configured')
    return title_parse


@pytest.fixture
def requires_tvdb(real_config):
    """
    Fixture that requires TVDB to be configured.

    Skips test if TVDB is not configured.
    """
    if not real_config.get('tvdb', {}).get('enabled', False):
        pytest.skip('TVDB not configured')
    if not real_config.get('tvdb', {}).get('api_key'):
        pytest.skip('TVDB API key not configured')
    return real_config['tvdb']


# ==================== Database Fixtures ====================

@pytest.fixture
def test_db_session(test_db_path):
    """Create a test database session."""
    from src.infrastructure.database.session import DatabaseSessionManager

    # Create manager with test database path directly
    db_manager = DatabaseSessionManager(db_path=str(test_db_path))

    # Initialize database
    db_manager.init_db()

    yield db_manager


@pytest.fixture
def anime_repo(test_db_session):
    """Create anime repository with test database."""
    from src.infrastructure.repositories.anime_repository import AnimeRepository
    return AnimeRepository()


@pytest.fixture
def download_repo(test_db_session):
    """Create download repository with test database."""
    from src.infrastructure.repositories.download_repository import DownloadRepository
    return DownloadRepository()


@pytest.fixture
def history_repo(test_db_session):
    """Create history repository with test database."""
    from src.infrastructure.repositories.history_repository import HistoryRepository
    return HistoryRepository()


# ==================== Test Helpers ====================

def assert_valid_hash(hash_str: str) -> None:
    """Assert that a string is a valid torrent hash."""
    assert hash_str, 'Hash should not be empty'
    assert len(hash_str) == 40, f'Hash should be 40 characters, got {len(hash_str)}'
    assert all(c in '0123456789abcdef' for c in hash_str.lower()), \
        'Hash should contain only hex characters'


def create_test_torrent_file(directory: Path, name: str = 'test.torrent') -> Path:
    """Create a minimal test torrent file."""
    import bencodepy

    torrent_data = {
        b'info': {
            b'name': b'Test File',
            b'piece length': 16384,
            b'pieces': b'\x00' * 20,
            b'length': 1000000
        },
        b'announce': b'udp://tracker.example.com:8080/announce'
    }

    torrent_path = directory / name
    with open(torrent_path, 'wb') as f:
        f.write(bencodepy.encode(torrent_data))

    return torrent_path


def create_test_video_file(directory: Path, name: str = 'test_video.mkv') -> Path:
    """Create a test video file (empty placeholder)."""
    video_path = directory / name
    video_path.write_bytes(b'\x00' * 1000)  # Minimal placeholder
    return video_path
