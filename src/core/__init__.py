"""
Core layer module.

Contains domain models, interfaces, and exception definitions.
"""

from src.core.exceptions import (
    AniDownError,
    AIError,
    AIRateLimitError,
    AICircuitBreakerError,
    AIKeyExhaustedError,
    AIResponseParseError,
    DownloadError,
    TorrentAddError,
    TorrentNotFoundError,
    FileOperationError,
    HardlinkError,
    ConfigError,
    DatabaseError,
    ParseError,
    TitleParseError,
)

__all__ = [
    # Exceptions
    'AniDownError',
    'AIError',
    'AIRateLimitError',
    'AICircuitBreakerError',
    'AIKeyExhaustedError',
    'AIResponseParseError',
    'DownloadError',
    'TorrentAddError',
    'TorrentNotFoundError',
    'FileOperationError',
    'HardlinkError',
    'ConfigError',
    'DatabaseError',
    'ParseError',
    'TitleParseError',
]
