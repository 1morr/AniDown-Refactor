"""
Webhook interface module.

Contains webhook handlers for processing external notifications.
"""

from src.interface.webhook.handler import (
    create_webhook_blueprint,
    webhook_bp,
)

__all__ = [
    'webhook_bp',
    'create_webhook_blueprint',
]
