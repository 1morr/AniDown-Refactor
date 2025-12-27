"""
Core layer module.

Contains domain models, interfaces, and exception definitions.
"""

from src.core.exceptions import (
    AniDownError,
    AIError,
    AICircuitBreakerError,
    AIKeyExhaustedError,
    AIResponseParseError,
    DownloadError,
    TorrentAddError,
    FileOperationError,
    HardlinkError,
    DatabaseError,
    ParseError,
    TitleParseError,
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
