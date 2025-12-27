"""
Webhook handler module.

Handles qBittorrent webhook callbacks for torrent events.
"""

import logging
from datetime import UTC

from flask import Blueprint, jsonify, request

from src.services.queue.webhook_queue import (
    WebhookPayload,
    get_webhook_queue,
)

logger = logging.getLogger(__name__)


def create_webhook_blueprint(prefix: str = '/webhook') -> Blueprint:
    """
    Create a Flask Blueprint for webhook endpoints.

    Args:
        prefix: URL prefix for the blueprint.

    Returns:
        Configured Flask Blueprint.
    """
    bp = Blueprint('webhook', __name__, url_prefix=prefix)

    @bp.route('/qbit', methods=['POST'])
    def handle_qbit_webhook() -> tuple:
        """
        Handle qBittorrent webhook callback.

        Processes torrent completion and other events from qBittorrent.

        Returns:
            JSON response with processing status.
        """
        try:
            data = request.json
            if not data:
                logger.warning('⚠️ Webhook received empty data')
                return jsonify({'error': 'No data provided'}), 400

            event_type = data.get('event_type', 'unknown')
            hash_id = data.get('hash', '')
            torrent_name = data.get('name', data.get('torrent_name', '未知'))

            logger.info('📨 收到 qBittorrent webhook')
            logger.info(f'  事件类型: {event_type}')
            logger.info(f'  种子Hash: {hash_id[:8]}...' if hash_id else '  种子Hash: (空)')
            logger.info(f'  种子名称: {torrent_name}')

            if not hash_id:
                logger.warning('⚠️ Webhook缺少hash信息')
                return jsonify({'error': 'Missing hash'}), 400

            # Get or initialize the queue worker
            queue_worker = get_webhook_queue()

            # Prepare payload
            payload = WebhookPayload(
                hash_id=hash_id,
                name=torrent_name,
                category=data.get('category', ''),
                status=data.get('status', ''),
                save_path=data.get('save_path', data.get('content_path', '')),
                extra_data=data
            )

            # Enqueue the event using the convenience method
            queued_event = queue_worker.enqueue_event(
                event_type=event_type,
                payload=payload
            )

            logger.info(f'✅ 已将事件加入队列 (queue_id: {queued_event.queue_id})')

            from datetime import datetime
            return jsonify({
                'success': True,
                'queued': True,
                'queue_id': queued_event.queue_id,
                'received_at_utc': datetime.now(UTC).isoformat(),
                'queue_len': queue_worker.qsize()
            }), 202

        except Exception as e:
            logger.error(f'❌ 处理 webhook 失败: {e}')
            return jsonify({'error': str(e)}), 500

    @bp.route('/health', methods=['GET'])
    def webhook_health() -> tuple:
        """
        Health check endpoint for webhook service.

        Returns:
            JSON response with health status.
        """
        return jsonify({
            'status': 'healthy',
            'service': 'webhook'
        }), 200

    @bp.route('/status', methods=['GET'])
    def webhook_status() -> tuple:
        """
        Get webhook queue status.

        Returns:
            JSON response with queue status.
        """
        try:
            queue_worker = get_webhook_queue()
            status = queue_worker.get_status()
            return jsonify({
                'success': True,
                'data': status
            }), 200
        except Exception as e:
            logger.error(f'❌ 获取队列状态失败: {e}')
            return jsonify({'error': str(e)}), 500

    return bp


# Default blueprint instance
webhook_bp = create_webhook_blueprint()
