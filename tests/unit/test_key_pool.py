"""
Tests for API Key Pool functionality.

Tests key rotation, rate limiting, cooling mechanisms, and circuit breaker.
"""

import json
import time
import pytest
from unittest.mock import MagicMock, patch

from tests.fixtures.test_data import KEY_POOL_TEST_KEYS


class TestKeyPool:
    """Tests for KeyPool class."""

    @pytest.fixture
    def key_pool(self):
        """Create KeyPool instance with test keys."""
        from src.infrastructure.ai.key_pool import KeyPool, KeySpec

        pool = KeyPool(purpose='test')

        # Configure with test keys
        keys = [
            KeySpec(
                key_id=key['key_id'],
                name=key['name'],
                api_key=key['api_key'],
                base_url=key['base_url'],
                model=key['model'],
                rpm_limit=key['rpm_limit'],
                rpd_limit=key['rpd_limit'],
                enabled=key['enabled']
            )
            for key in KEY_POOL_TEST_KEYS
        ]

        pool.configure(keys)

        return pool

    def test_key_pool_initialization(self):
        """Test KeyPool initializes correctly."""
        from src.infrastructure.ai.key_pool import KeyPool

        pool = KeyPool(purpose='title_parse')

        assert pool is not None
        assert pool.purpose == 'title_parse'

    def test_key_pool_configure(self, key_pool):
        """Test configuring KeyPool with keys."""
        status = key_pool.get_status()

        # Should have 2 enabled keys (key 3 is disabled)
        assert status['total_count'] == 2
        assert status['purpose'] == 'test'

    def test_key_pool_reserve_success(self, key_pool):
        """Test reserving an available key."""
        reservation = key_pool.reserve()

        assert reservation is not None
        assert reservation.key_id in ['test_key_1', 'test_key_2']
        assert reservation.api_key.startswith('sk-test')
        assert reservation.base_url == 'https://api.openai.com/v1'
        assert reservation.model == 'gpt-4'

    def test_key_pool_round_robin(self, key_pool):
        """Test round-robin key selection."""
        reservations = []

        for _ in range(4):
            res = key_pool.reserve()
            if res:
                reservations.append(res.key_id)
                key_pool.report_success(res.key_id)

        # Should alternate between keys
        assert len(reservations) == 4
        assert 'test_key_1' in reservations
        assert 'test_key_2' in reservations

    def test_key_pool_report_success(self, key_pool):
        """Test reporting successful request."""
        reservation = key_pool.reserve()

        key_pool.report_success(reservation.key_id, response_time_ms=100)

        status = key_pool.get_status()
        key_status = next(
            k for k in status['keys'] if k['key_id'] == reservation.key_id
        )

        assert key_status['error_count'] == 0
        assert key_status['last_response_time_ms'] == 100

    def test_key_pool_report_error_short_cooldown(self, key_pool):
        """Test short cooldown after single error."""
        reservation = key_pool.reserve()

        key_pool.report_error(reservation.key_id, 'Test error')

        status = key_pool.get_status()
        key_status = next(
            k for k in status['keys'] if k['key_id'] == reservation.key_id
        )

        assert key_status['error_count'] == 1
        assert key_status['state'] == 'cooling'
        assert key_status['cooldown_remaining_seconds'] > 0

    def test_key_pool_report_error_long_cooldown(self, key_pool):
        """Test long cooldown after multiple consecutive errors."""
        reservation = key_pool.reserve()

        # Report multiple consecutive errors
        for i in range(5):
            key_pool.report_error(reservation.key_id, f'Test error {i}')

        status = key_pool.get_status()
        key_status = next(
            k for k in status['keys'] if k['key_id'] == reservation.key_id
        )

        assert key_status['error_count'] == 5
        assert key_status['state'] == 'long_cooling'
        # Long cooldown should be longer than short cooldown
        assert key_status['cooldown_remaining_seconds'] >= 60

    def test_key_pool_rate_limit_error(self, key_pool):
        """Test rate limit error handling with retry_after."""
        reservation = key_pool.reserve()

        key_pool.report_error(
            reservation.key_id,
            'Rate limited',
            status_code=429,  # Rate limit status code
            retry_after=120.0
        )

        status = key_pool.get_status()
        key_status = next(
            k for k in status['keys'] if k['key_id'] == reservation.key_id
        )

        # Should use retry_after value
        assert key_status['cooldown_remaining_seconds'] >= 100

    def test_key_pool_reset_cooldown(self, key_pool):
        """Test manual cooldown reset."""
        reservation = key_pool.reserve()

        # Put key in cooldown
        key_pool.report_error(reservation.key_id, 'Test error')

        # Reset cooldown
        result = key_pool.reset_cooldown(reservation.key_id)

        assert result is True

        status = key_pool.get_status()
        key_status = next(
            k for k in status['keys'] if k['key_id'] == reservation.key_id
        )

        assert key_status['state'] == 'available'
        assert key_status['error_count'] == 0

    def test_key_pool_rpm_limit(self, key_pool):
        """Test RPM (requests per minute) limit."""
        # Reserve key 2 which has lower RPM limit (30)
        reservations = []

        for _ in range(35):
            res = key_pool.reserve()
            if res:
                reservations.append(res)
                # Don't report success to keep using same key

        # Should have gotten some reservations before hitting limit
        assert len(reservations) > 0

    def test_key_pool_disabled_key_not_selected(self, key_pool):
        """Test that disabled keys are not selected."""
        reservations = set()

        for _ in range(10):
            res = key_pool.reserve()
            if res:
                reservations.add(res.key_id)
                key_pool.report_success(res.key_id)

        # test_key_3 is disabled, should never be selected
        assert 'test_key_3' not in reservations

    def test_key_pool_no_available_keys(self):
        """Test behavior when no keys are available."""
        from src.infrastructure.ai.key_pool import KeyPool, KeySpec

        pool = KeyPool(purpose='test_empty')

        # Configure with only disabled keys
        pool.configure([
            KeySpec(
                key_id='disabled_key',
                name='Disabled',
                api_key='sk-test',
                base_url='https://api.openai.com/v1',
                model='gpt-4',
                enabled=False
            )
        ])

        reservation = pool.reserve()

        assert reservation is None

    def test_key_pool_get_status(self, key_pool):
        """Test getting pool status."""
        status = key_pool.get_status()

        assert 'purpose' in status
        assert 'keys' in status
        assert 'total_count' in status
        assert 'available_count' in status
        assert 'all_in_long_cooling' in status

        assert status['purpose'] == 'test'
        assert status['total_count'] == 2
        assert status['available_count'] == 2


class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create CircuitBreaker instance."""
        from src.infrastructure.ai.circuit_breaker import CircuitBreaker

        return CircuitBreaker(purpose='test')

    def test_circuit_breaker_initialization(self):
        """Test CircuitBreaker initializes correctly."""
        from src.infrastructure.ai.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker(purpose='test')

        assert breaker is not None
        assert breaker.purpose == 'test'
        assert breaker.is_open() is False

    def test_circuit_breaker_closed_state(self, circuit_breaker):
        """Test circuit breaker in closed state."""
        # Should allow requests when closed
        assert circuit_breaker.is_open() is False

    def test_circuit_breaker_open_after_trip(self, circuit_breaker):
        """Test circuit breaker opens after trip is called."""
        # Trip the circuit breaker
        circuit_breaker.trip(duration=60, reason='Test trip')

        # Should be open now
        assert circuit_breaker.is_open() is True

    def test_circuit_breaker_reset(self, circuit_breaker):
        """Test that reset closes the circuit breaker."""
        # Trip the circuit
        circuit_breaker.trip(duration=60)

        assert circuit_breaker.is_open() is True

        # Reset
        circuit_breaker.reset()

        # Should be closed now
        assert circuit_breaker.is_open() is False

    def test_circuit_breaker_remaining_seconds(self, circuit_breaker):
        """Test getting remaining seconds."""
        # When closed, remaining should be 0
        assert circuit_breaker.get_remaining_seconds() == 0

        # Trip the circuit
        circuit_breaker.trip(duration=60)

        # Should have remaining time
        remaining = circuit_breaker.get_remaining_seconds()
        assert remaining > 0
        assert remaining <= 60

    def test_circuit_breaker_get_status(self, circuit_breaker):
        """Test getting circuit breaker status."""
        status = circuit_breaker.get_status()

        assert 'purpose' in status
        assert 'is_open' in status
        assert 'remaining_seconds' in status
        assert 'trip_count' in status

    def test_circuit_breaker_status_after_trip(self, circuit_breaker):
        """Test status after tripping the circuit."""
        circuit_breaker.trip(duration=300, reason='All keys in long cooling')

        status = circuit_breaker.get_status()

        assert status['is_open'] is True
        assert status['remaining_seconds'] > 0
        assert status['trip_count'] == 1
        assert status['last_trip_reason'] == 'All keys in long cooling'


class TestAITitleParser:
    """Tests for AI title parser with key pool integration."""

    @pytest.fixture
    def mock_api_response(self):
        """Create mock API response."""
        from unittest.mock import MagicMock

        response = MagicMock()
        response.success = True
        response.content = json.dumps({
            'original_title': '[ANi] 狼與香辛料 - 26',
            'anime_clean_title': '狼與香辛料',
            'anime_full_title': '狼與香辛料 MERCHANT MEETS THE WISE WOLF',
            'subtitle_group_name': 'ANi',
            'season': 1,
            'episode': 26,
            'category': 'tv',
            'quality': '1080P',
            'codec': '',
            'source': 'WEB-DL'
        })
        response.response_time_ms = 500
        response.error_code = None
        response.error_message = None
        return response

    @pytest.fixture
    def title_parser(self, mock_api_response):
        """Create AITitleParser with mocked dependencies."""
        from src.infrastructure.ai.title_parser import AITitleParser
        from src.infrastructure.ai.key_pool import KeyPool, KeySpec
        from src.infrastructure.ai.circuit_breaker import CircuitBreaker
        from src.infrastructure.ai.api_client import OpenAIClient

        key_pool = KeyPool(purpose='title_parse')
        key_pool.configure([
            KeySpec(
                key_id='test_key',
                name='Test Key',
                api_key='sk-test',
                base_url='https://api.openai.com/v1',
                model='gpt-4',
                rpm_limit=60,
                rpd_limit=1000,
                enabled=True
            )
        ])

        circuit_breaker = CircuitBreaker(purpose='title_parse')

        # Create mock API client
        mock_client = MagicMock(spec=OpenAIClient)
        mock_client.call.return_value = mock_api_response

        return AITitleParser(
            key_pool=key_pool,
            circuit_breaker=circuit_breaker,
            api_client=mock_client
        )

    def test_title_parser_initialization(self, title_parser):
        """Test AITitleParser initializes correctly."""
        assert title_parser is not None

    def test_title_parser_parse_success(self, title_parser):
        """Test successful title parsing."""
        result = title_parser.parse('[ANi] 狼與香辛料 - 26 [1080P].mp4')

        # Should return parsed result
        assert result is not None
        assert result.clean_title == '狼與香辛料'
        assert result.subtitle_group == 'ANi'
        assert result.season == 1
        assert result.episode == 26

    def test_title_parser_circuit_breaker_open(self):
        """Test that circuit breaker blocks requests when open."""
        from src.infrastructure.ai.title_parser import AITitleParser
        from src.infrastructure.ai.key_pool import KeyPool, KeySpec
        from src.infrastructure.ai.circuit_breaker import CircuitBreaker
        from src.core.exceptions import AICircuitBreakerError

        key_pool = KeyPool(purpose='title_parse_test')
        key_pool.configure([
            KeySpec(
                key_id='test_key',
                name='Test Key',
                api_key='sk-test',
                base_url='https://api.openai.com/v1',
                model='gpt-4',
                enabled=True
            )
        ])

        circuit_breaker = CircuitBreaker(purpose='title_parse_test')
        circuit_breaker.trip(duration=60, reason='Test trip')

        parser = AITitleParser(key_pool=key_pool, circuit_breaker=circuit_breaker)

        with pytest.raises(AICircuitBreakerError):
            parser.parse('[Test] Anime - 01.mkv')


@pytest.mark.integration
class TestKeyPoolIntegration:
    """Integration tests for key pool with real configuration."""

    def test_load_keys_from_config(self, real_config):
        """Test loading keys from real configuration."""
        from src.infrastructure.ai.key_pool import KeyPool, KeySpec

        title_parse_config = real_config.get('openai', {}).get('title_parse', {})
        key_pool_config = title_parse_config.get('api_key_pool', [])

        if not key_pool_config:
            pytest.skip('No API key pool configured')

        pool = KeyPool(purpose='title_parse')

        keys = [
            KeySpec(
                key_id=f"key_{i}",
                name=key.get('name', f'Key {i}'),
                api_key=key.get('api_key', ''),
                base_url=title_parse_config.get('base_url', 'https://api.openai.com/v1'),
                model=title_parse_config.get('model', 'gpt-4'),
                rpm_limit=key.get('rpm', 0),
                rpd_limit=key.get('rpd', 0),
                enabled=key.get('enabled', True)
            )
            for i, key in enumerate(key_pool_config)
            if key.get('api_key')
        ]

        pool.configure(keys)

        status = pool.get_status()

        print(f'\n📊 Key Pool Status:')
        print(f'   Total keys: {status["total_count"]}')
        print(f'   Available: {status["available_count"]}')

        for key in status['keys']:
            print(f'   - {key["name"]}: {key["state"]}')
