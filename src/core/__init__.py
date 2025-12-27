"""
Core layer module.

Contains domain models, interfaces, and exception definitions.
"""

from src.core.exceptions import (
    AICircuitBreakerError,
    AIError,
    AIKeyExhaustedError,
    AIResponseParseError,
    AniDownError,
    DatabaseError,
    DownloadError,
    FileOperationError,
    HardlinkError,
    ParseError,
    TitleParseError,
    TorrentAddError,
)

__all__ = [
    # Exceptions
    'AniDownError',
    'AIError',
    'AICircuitBreakerError',
    'AIKeyExhaustedError',
    'AIResponseParseError',
    'DownloadError',
    'TorrentAddError',
    'FileOperationError',
    'HardlinkError',
    'DatabaseError',
    'ParseError',
    'TitleParseError',
]
