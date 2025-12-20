"""
接口层模块。

提供 Web UI、API 和 Webhook 接口。
"""

from .web.controllers import ai_queue_bp

__all__ = ['ai_queue_bp']
