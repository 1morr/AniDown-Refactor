"""
Webhook interface module.

Contains webhook handlers for processing external notifications.
"""

from src.interface.webhook.handler import (
    webhook_bp,
    create_webhook_blueprint,
)

__all__ = [
    'webhook_bp',
    'create_webhook_blueprint',
]
