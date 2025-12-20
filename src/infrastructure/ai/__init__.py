"""
AI 服务模块。

提供 OpenAI API 集成功能，包括：
- API 客户端（HTTP 通信）
- Key Pool（API Key 管理和轮询）
- 熔断器（故障保护）
- 标题解析器（AI 解析动漫标题）
- 文件重命名器（AI 生成重命名映射）
"""

from src.infrastructure.ai.api_client import APIResponse, OpenAIClient
from src.infrastructure.ai.circuit_breaker import CircuitBreaker
from src.infrastructure.ai.file_renamer import AIFileRenamer
from src.infrastructure.ai.key_pool import (
    KeyPool,
    KeyReservation,
    KeySpec,
    KeyState,
    KeyUsage,
)
from src.infrastructure.ai.title_parser import AITitleParser

__all__ = [
    'OpenAIClient',
    'APIResponse',
    'KeyPool',
    'KeySpec',
    'KeyReservation',
    'KeyState',
    'KeyUsage',
    'CircuitBreaker',
    'AITitleParser',
    'AIFileRenamer',
]
