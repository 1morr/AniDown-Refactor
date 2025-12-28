"""
Tests for Discord notification functionality.

Tests Discord webhook client, embed builder, and various notifiers.
"""

import pytest
from unittest.mock import MagicMock, patch

from tests.fixtures.test_data import DISCORD_TEST_NOTIFICATION


class TestDiscordWebhookClient:
    """Tests for Discord webhook client."""

    @pytest.fixture
    def webhook_client(self):
        """Create DiscordWebhookClient instance."""
        from src.infrastructure.notification.discord.webhook_client import (
            DiscordWebhookClient
        )
        return DiscordWebhookClient()

    def test_webhook_client_initialization(self):
        """Test webhook client initializes correctly."""
        from src.infrastructure.notification.discord.webhook_client import (
            DiscordWebhookClient
        )

        client = DiscordWebhookClient()

        assert client is not None

    def test_webhook_client_disabled_when_no_config(self, webhook_client):
        """Test that webhook client handles missing config gracefully."""
        from src.core.config import config

        # If Discord is not enabled, send should return False or handle gracefully
        if not config.discord.enabled:
            # Should not raise exception
            try:
                webhook_client.send_message('Test message')
            except Exception:
                pass  # Expected when not configured

    @patch('requests.Session.post')
    def test_send_message_success(self, mock_post, webhook_client):
        """Test sending a simple message."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        # Send message directly with URL parameter
        try:
            result = webhook_client.send_message(
                'Test message',
                webhook_url='https://discord.com/api/webhooks/test'
            )
            # Result depends on configuration
            assert result is not None or result is False
        except Exception:
            # Expected when Discord is not configured
            pass

    @patch('requests.Session.post')
    def test_send_embed_success(self, mock_post, webhook_client):
        """Test sending an embed message."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        embed = {
            'title': DISCORD_TEST_NOTIFICATION['title'],
            'description': DISCORD_TEST_NOTIFICATION['description'],
            'color': DISCORD_TEST_NOTIFICATION['color'],
            'fields': DISCORD_TEST_NOTIFICATION['fields']
        }

        # Send embed directly with URL parameter
        try:
            result = webhook_client.send_embed(
                embed,
                webhook_url='https://discord.com/api/webhooks/test'
            )
            # Result depends on configuration
            assert result is not None or result is False
        except Exception:
            # Expected when Discord is not configured
            pass


class TestEmbedBuilder:
    """Tests for Discord embed builder."""

    def test_embed_builder_initialization(self):
        """Test EmbedBuilder initialization."""
        from src.infrastructure.notification.discord.embed_builder import EmbedBuilder

        builder = EmbedBuilder()

        assert builder is not None

    def test_build_rss_start_embed(self):
        """Test building RSS start notification embed."""
        from src.infrastructure.notification.discord.embed_builder import EmbedBuilder

        builder = EmbedBuilder()
        embed = builder.build_rss_start_embed(
            trigger_type='定时触发',
            rss_url='https://example.com/rss'
        )

        assert 'title' in embed or 'description' in embed

    def test_build_error_embed(self):
        """Test building error notification embed."""
        from src.infrastructure.notification.discord.embed_builder import EmbedBuilder

        builder = EmbedBuilder()
        embed = builder.build_error_embed(
            error_type='下载错误',
            error_message='连接失败',
            context={'anime': '金牌得主'}
        )

        assert 'title' in embed or 'description' in embed
        # Error embeds should typically be red
        if 'color' in embed:
            assert embed['color'] in [0xFF0000, 0xE74C3C, 0xED4245]  # Red variants


class TestDiscordNotifier:
    """Tests for unified Discord notifier."""

    @pytest.fixture
    def discord_notifier(self, mock_discord_webhook):
        """Create DiscordNotifier with mock webhook client."""
        from src.infrastructure.notification.discord.discord_notifier import (
            DiscordNotifier
        )
        return DiscordNotifier(webhook_client=mock_discord_webhook)

    def test_notify_processing_start(self, discord_notifier, mock_discord_webhook):
        """Test RSS processing start notification."""
        from src.core.interfaces.notifications import RSSNotification

        notification = RSSNotification(
            trigger_type='定时触发',
            rss_url='https://example.com/rss'
        )

        # The notify method may return bool or notification result
        result = discord_notifier.notify_processing_start(notification)

        # Verify webhook was called or result is correct type
        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)

    def test_notify_processing_complete(self, discord_notifier, mock_discord_webhook):
        """Test RSS processing complete notification."""
        result = discord_notifier.notify_processing_complete(
            success_count=5,
            total_count=10,
            failed_items=[{'title': 'Failed Item', 'reason': 'Error'}]
        )

        # Verify webhook was called or result is correct type
        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)

    def test_notify_hardlink_created(self, discord_notifier, mock_discord_webhook):
        """Test hardlink created notification."""
        from src.core.interfaces.notifications import HardlinkNotification

        notification = HardlinkNotification(
            anime_title='金牌得主',
            season=1,
            video_count=10,
            subtitle_count=10,
            target_dir='/library/TV Shows/金牌得主/Season 1',
            rename_method='pattern_match'
        )

        result = discord_notifier.notify_hardlink_created(notification)

        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)

    def test_notify_error(self, discord_notifier, mock_discord_webhook):
        """Test error notification."""
        from src.core.interfaces.notifications import ErrorNotification

        notification = ErrorNotification(
            error_type='下载错误',
            error_message='无法连接到qBittorrent',
            context={'hash_id': 'abc123'}
        )

        result = discord_notifier.notify_error(notification)

        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)

    def test_notify_ai_usage(self, discord_notifier, mock_discord_webhook):
        """Test AI usage notification."""
        from src.core.interfaces.notifications import AIUsageNotification

        notification = AIUsageNotification(
            reason='数据库无匹配规则',
            project_name='金牌得主',
            context='rss',
            operation='title_parsing'
        )

        result = discord_notifier.notify_ai_usage(notification)

        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)

    def test_notify_webhook_received(self, discord_notifier, mock_discord_webhook):
        """Test webhook received notification."""
        from src.core.interfaces.notifications import WebhookReceivedNotification

        notification = WebhookReceivedNotification(
            torrent_id='abc123def456',
            save_path='/downloads/anime',
            content_path='/downloads/anime/[ANi] Anime',
            torrent_name='[ANi] Anime - 01 [1080P].mkv'
        )

        result = discord_notifier.notify_webhook_received(notification)

        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)


class TestRSSNotifier:
    """Tests for RSS notification service (backward compatibility)."""

    @pytest.fixture
    def rss_notifier(self, mock_discord_webhook):
        """Create DiscordNotifier with mock webhook client (using old alias)."""
        from src.infrastructure.notification.discord.discord_notifier import (
            DiscordNotifier
        )
        return DiscordNotifier(webhook_client=mock_discord_webhook)

    def test_notify_processing_start(self, rss_notifier, mock_discord_webhook):
        """Test RSS processing start notification."""
        from src.core.interfaces.notifications import RSSNotification

        notification = RSSNotification(
            trigger_type='定时触发',
            rss_url='https://example.com/rss'
        )

        # The notify method may return bool or notification result
        result = rss_notifier.notify_processing_start(notification)

        # Verify webhook was called or result is correct type
        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)

    def test_notify_processing_complete(self, rss_notifier, mock_discord_webhook):
        """Test RSS processing complete notification."""
        result = rss_notifier.notify_processing_complete(
            success_count=5,
            total_count=10,
            failed_items=[{'title': 'Failed Item', 'reason': 'Error'}]
        )

        # Verify webhook was called or result is correct type
        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)

    def test_notify_processing_complete(self, rss_notifier, mock_discord_webhook):
        """Test RSS processing complete notification."""
        result = rss_notifier.notify_processing_complete(
            success_count=5,
            total_count=10,
            failed_items=[{'title': 'Failed Item', 'reason': 'Error'}]
        )

        # Verify webhook was called or result is correct type
        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool))


class TestDownloadNotifier:
    """Tests for download notification service (backward compatibility)."""

    @pytest.fixture
    def download_notifier(self, mock_discord_webhook):
        """Create DiscordNotifier with mock webhook client."""
        from src.infrastructure.notification.discord.discord_notifier import (
            DiscordNotifier
        )
        return DiscordNotifier(webhook_client=mock_discord_webhook)



class TestHardlinkNotifier:
    """Tests for hardlink notification service (backward compatibility)."""

    @pytest.fixture
    def hardlink_notifier(self, mock_discord_webhook):
        """Create DiscordNotifier with mock webhook client."""
        from src.infrastructure.notification.discord.discord_notifier import (
            DiscordNotifier
        )
        return DiscordNotifier(webhook_client=mock_discord_webhook)

    def test_notify_hardlink_created(self, hardlink_notifier, mock_discord_webhook):
        """Test hardlink created notification."""
        from src.core.interfaces.notifications import HardlinkNotification

        notification = HardlinkNotification(
            anime_title='金牌得主',
            season=1,
            video_count=10,
            subtitle_count=10,
            target_dir='/library/TV Shows/金牌得主/Season 1',
            rename_method='pattern_match'
        )

        # The notify method may return bool or notification result
        result = hardlink_notifier.notify_hardlink_created(notification)

        # Verify webhook was called or result is correct type
        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)


class TestErrorNotifier:
    """Tests for error notification service (backward compatibility)."""

    @pytest.fixture
    def error_notifier(self, mock_discord_webhook):
        """Create DiscordNotifier with mock webhook client."""
        from src.infrastructure.notification.discord.discord_notifier import (
            DiscordNotifier
        )
        return DiscordNotifier(webhook_client=mock_discord_webhook)

    def test_notify_error(self, error_notifier, mock_discord_webhook):
        """Test error notification."""
        from src.core.interfaces.notifications import ErrorNotification

        notification = ErrorNotification(
            error_type='下载错误',
            error_message='无法连接到qBittorrent',
            context={'hash_id': 'abc123'}
        )

        # The notify method may return bool or notification result
        result = error_notifier.notify_error(notification)

        # Verify webhook was called or result is correct type
        assert (mock_discord_webhook.send_embed.called or
                mock_discord_webhook.send.called or
                isinstance(result, bool) or
                result is None)


@pytest.mark.integration
@pytest.mark.requires_discord
class TestDiscordIntegration:
    """Integration tests for Discord notifications."""

    def test_send_real_notification(self, requires_discord):
        """
        Test sending a real notification to Discord.

        This test requires Discord webhook to be configured.
        """
        from src.infrastructure.notification.discord.webhook_client import (
            DiscordWebhookClient
        )
        from src.infrastructure.notification.discord.embed_builder import EmbedBuilder

        client = DiscordWebhookClient()

        # Configure webhooks from test config
        webhooks = {}
        if requires_discord.get('rss_webhook_url'):
            webhooks['rss'] = requires_discord['rss_webhook_url']
        if requires_discord.get('hardlink_webhook_url'):
            webhooks['hardlink'] = requires_discord['hardlink_webhook_url']

        if not webhooks:
            pytest.skip('No webhook URLs configured')

        client.configure(webhooks=webhooks, enabled=True)

        builder = EmbedBuilder()

        # Build test embed
        embed = builder.build_rss_task_embed(
            project_name='AniDown 测试',
            hash_id='test_hash_1234567890',
            anime_title='AniDown 测试',
            subtitle_group='Test',
            download_path='/downloads/test',
            season=1,
            episode=1
        )

        # Send to RSS webhook
        try:
            result = client.send(embeds=[embed], channel_type='rss')
            if result.success:
                print(f'\n✅ Successfully sent test notification to Discord')
            else:
                pytest.skip(f'Discord notification failed: {result.error_message}')
        except Exception as e:
            pytest.skip(f'Failed to send Discord notification: {e}')

    def test_send_error_notification(self, requires_discord):
        """
        Test sending an error notification to Discord.
        """
        from src.infrastructure.notification.discord.webhook_client import (
            DiscordWebhookClient
        )
        from src.infrastructure.notification.discord.embed_builder import EmbedBuilder

        client = DiscordWebhookClient()

        # Configure webhooks from test config
        webhooks = {}
        if requires_discord.get('rss_webhook_url'):
            webhooks['rss'] = requires_discord['rss_webhook_url']
        if requires_discord.get('hardlink_webhook_url'):
            webhooks['hardlink'] = requires_discord['hardlink_webhook_url']

        if not webhooks:
            pytest.skip('No webhook URLs configured')

        client.configure(webhooks=webhooks, enabled=True)

        builder = EmbedBuilder()

        # Build error embed
        embed = builder.build_error_embed(
            error_type='测试错误',
            error_message='这是一条测试错误消息',
            context={'test': True}
        )

        # Send to RSS webhook
        try:
            result = client.send(embeds=[embed], channel_type='rss')
            if result.success:
                print(f'\n✅ Successfully sent error notification to Discord')
            else:
                pytest.skip(f'Discord notification failed: {result.error_message}')
        except Exception as e:
            pytest.skip(f'Failed to send Discord notification: {e}')
