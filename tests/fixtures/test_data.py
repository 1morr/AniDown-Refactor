"""
Test data fixtures for AniDown integration tests.

This module contains real test data provided by the user for testing
the complete workflow functionality.
"""

# ==================== RSS Test Data ====================

# Mikan RSS Feed 1: Personal subscription with multiple anime
RSS_MIKAN_MY_BANGUMI = (
    'https://mikanani.me/RSS/MyBangumi?token=GTd1ABkavs6Qa8O5ZwF3tw%3d%3d'
)
RSS_MIKAN_BLOCKED_KEYWORDS = '繁日内嵌\n简日内嵌'

# Mikan RSS Feed 2: Specific anime subscription (should match existing anime)
RSS_MIKAN_SINGLE_ANIME = (
    'https://mikanani.me/RSS/Bangumi?bangumiId=3777&subgroupid=576'
)


# ==================== Torrent File Test Data ====================

TORRENT_FILE_CONFIG = {
    'filename': '[Nekomoe kissaten&VCB-Studio] Medalist [Ma10p_1080p].torrent',
    'anime_title': '金牌得主',
    'subtitle_group': '喵萌奶茶屋&VCB-Studio',
    'category': 'tv',
    'season': 1,
    'media_type': 'anime'
}


# ==================== Magnet Link Test Data ====================

MAGNET_CONFIG = {
    'hash': '55118aa1dbf75eebad500ec2ddd6a6de06e8f4d0',
    'anime_title': "BanG Dream! It's MyGO!!!!!",
    'subtitle_group': '喵萌Production&VCB-Studio',
    'category': 'tv',
    'season': 1,
    'media_type': 'anime'
}


# ==================== Sample Anime Titles for Testing ====================

SAMPLE_ANIME_TITLES = [
    # Format: (original_title, expected_clean_title, expected_group, expected_season, expected_ep)
    (
        '[ANi] 狼與香辛料 MERCHANT MEETS THE WISE WOLF - 26 [1080P][Baha][WEB-DL][AAC AVC][CHT].mp4',
        '狼與香辛料',
        'ANi',
        1,
        26
    ),
    (
        '[Nekomoe kissaten&LoliHouse] Tensei Shitara Slime Datta Ken S3 - 24 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv',
        'Tensei Shitara Slime Datta Ken',
        'Nekomoe kissaten&LoliHouse',
        3,
        24
    ),
    (
        '[VCB-Studio] BanG Dream! Its MyGO!!!!! [Ma10p_1080p]',
        "BanG Dream! It's MyGO!!!!!",
        'VCB-Studio',
        1,
        None  # Collection, no specific episode
    ),
    (
        '[桜都字幕组] 金牌得主 / Medalist [01][1080p][简繁内封]',
        '金牌得主',
        '桜都字幕组',
        1,
        1
    ),
    (
        '[喵萌奶茶屋&VCB-Studio] 金牌得主 / Medalist [Ma10p_1080p]',
        '金牌得主',
        '喵萌奶茶屋&VCB-Studio',
        1,
        None  # Collection
    ),
]


# ==================== Path Generation Test Data ====================

PATH_TEST_CASES = [
    # Format: (title, season, category, media_type, expected_path_contains)
    # Note: The actual path structure is /downloads/AniDown/{MediaType}/{Title}/Season {N}
    (
        '狼與香辛料',
        1,
        'tv',
        'anime',
        ['Anime', '狼與香辛料', 'Season 1']
    ),
    (
        '金牌得主',
        1,
        'tv',
        'anime',
        ['Anime', '金牌得主', 'Season 1']
    ),
    (
        'Test Movie',
        0,
        'movie',
        'anime',
        ['Anime', 'Test Movie']
    ),
    (
        'Live Action Drama',
        1,
        'tv',
        'live_action',
        ['LiveAction', 'Live Action Drama', 'Season 1']
    ),
]


# ==================== Filename Sanitization Test Data ====================

FILENAME_SANITIZE_CASES = [
    # Format: (input, expected_output)
    ('Test/Anime', 'Test-Anime'),
    ('Test\\Anime', 'Test-Anime'),
    ("Test's Anime", "Test's Anime"),  # Apostrophe should be kept
    ('Test: The Anime', 'Test - The Anime'),
    ('Test? The Anime!', 'Test - The Anime!'),
    ('Test*Anime', 'Test-Anime'),
    ('<Test>', '-Test-'),
    ('Test|Anime', 'Test-Anime'),
    ('Test "Anime"', "Test 'Anime'"),
    ('  Multiple   Spaces  ', 'Multiple Spaces'),
]


# ==================== Discord Notification Test Data ====================

DISCORD_TEST_NOTIFICATION = {
    'title': 'AniDown 测试通知',
    'description': '这是一条测试消息，用于验证 Discord 通知功能是否正常工作。',
    'color': 0x00FF00,  # Green
    'fields': [
        {'name': '动漫名称', 'value': '金牌得主', 'inline': True},
        {'name': '季数', 'value': '第1季', 'inline': True},
        {'name': '字幕组', 'value': '喵萌奶茶屋&VCB-Studio', 'inline': True},
    ]
}


# ==================== Queue Test Data ====================

QUEUE_TEST_EVENTS = {
    'webhook_torrent_completed': {
        'type': 'torrent_completed',
        'hash_id': 'abc123def456789012345678901234567890',
        'name': 'Test Torrent',
        'save_path': '/downloads/test'
    },
    'webhook_torrent_added': {
        'type': 'torrent_added',
        'hash_id': 'abc123def456789012345678901234567890',
        'name': 'Test Torrent',
    },
    'rss_scheduled_check': {
        'type': 'scheduled_check',
        'rss_url': RSS_MIKAN_MY_BANGUMI,
        'trigger_type': '定时触发'
    },
    'rss_manual_check': {
        'type': 'manual_check',
        'rss_url': RSS_MIKAN_MY_BANGUMI,
        'trigger_type': '手动触发'
    }
}


# ==================== Key Pool Test Data ====================

KEY_POOL_TEST_KEYS = [
    {
        'key_id': 'test_key_1',
        'name': 'Test Key 1',
        'api_key': 'sk-test-key-1-xxx',
        'base_url': 'https://api.openai.com/v1',
        'rpm_limit': 60,
        'rpd_limit': 1000,
        'enabled': True
    },
    {
        'key_id': 'test_key_2',
        'name': 'Test Key 2',
        'api_key': 'sk-test-key-2-xxx',
        'base_url': 'https://api.openai.com/v1',
        'rpm_limit': 30,
        'rpd_limit': 500,
        'enabled': True
    },
    {
        'key_id': 'test_key_3',
        'name': 'Test Key 3 (Disabled)',
        'api_key': 'sk-test-key-3-xxx',
        'base_url': 'https://api.openai.com/v1',
        'rpm_limit': 10,
        'rpd_limit': 100,
        'enabled': False
    },
]


# ==================== WebUI Test Data ====================

WEBUI_TEST_PAGES = [
    ('/', 'Dashboard'),
    ('/anime', 'Anime'),
    ('/downloads', 'Downloads'),
    ('/rss', 'RSS'),
    ('/config', 'Config'),
    ('/database', 'Database'),
    ('/system/ai-status', 'System Status'),
    ('/system/ai-queue', 'Queue Status'),
    ('/manual_upload', 'Manual Upload'),
]

WEBUI_API_ENDPOINTS = [
    ('GET', '/api/anime', 200),
    ('GET', '/api/downloads', 200),
    ('GET', '/api/rss_history', 200),
    ('GET', '/api/table_data', 200),
    ('GET', '/api/system/status', 200),
]


# ==================== TVDB Test Data ====================

TVDB_TEST_ANIME = [
    # Format: (anime_title, expected_tvdb_id or None if not found)
    ('金牌得主', None),  # May or may not find in TVDB
    ('BanG Dream! It\'s MyGO!!!!!', None),
    ('狼與香辛料', None),
]
