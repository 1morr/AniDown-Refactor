"""
控制器模块。

包含所有 Flask Blueprint 控制器。
"""

from .ai_queue_status import ai_queue_bp

__all__ = ['ai_queue_bp']
