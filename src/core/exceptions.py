"""
Exceptions module.

Contains the exception hierarchy for the AniDown application.
All custom exceptions inherit from AniDownError for consistent handling.
"""

from typing import Any, Dict, Optional


class AniDownError(Exception):
    """
    Base exception for all AniDown errors.

    All custom exceptions in the application should inherit from this class
    to enable consistent error handling and logging.

    Attributes:
        message: Human-readable error description.
        code: Machine-readable error code.
        context: Additional context information for debugging.
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code or 'UNKNOWN_ERROR'
        self.context = context or {}

    def __str__(self) -> str:
        """Return formatted error message."""
        if self.context:
            return f'[{self.code}] {self.message} - Context: {self.context}'
        return f'[{self.code}] {self.message}'


# AI-related exceptions

class AIError(AniDownError):
    """Base exception for AI service errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code or 'AI_ERROR', context)


class AIRateLimitError(AIError):
    """
    Exception raised when AI API rate limit is exceeded.

    Attributes:
        retry_after: Suggested wait time in seconds before retrying.
    """

    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, 'AI_RATE_LIMITED', context)
        self.retry_after = retry_after


class AICircuitBreakerError(AIError):
    """
    Exception raised when the circuit breaker is open.

    Attributes:
        remaining_seconds: Time remaining until the circuit breaker resets.
    """

    def __init__(
        self,
        message: str,
        remaining_seconds: float,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, 'AI_CIRCUIT_OPEN', context)
        self.remaining_seconds = remaining_seconds


class AIKeyExhaustedError(AIError):
    """Exception raised when all API keys are exhausted or cooling down."""

    def __init__(
        self,
        message: str = 'All API keys are exhausted or in cooldown',
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, 'AI_KEYS_EXHAUSTED', context)


class AIResponseParseError(AIError):
    """
    Exception raised when AI response cannot be parsed.

    Attributes:
        raw_response: The raw response that failed to parse.
    """

    def __init__(
        self,
        message: str,
        raw_response: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        ctx = context or {}
        if raw_response:
            ctx['raw_response'] = raw_response[:500]  # Truncate for logging
        super().__init__(message, 'AI_PARSE_ERROR', ctx)
        self.raw_response = raw_response


# Download-related exceptions

class DownloadError(AniDownError):
    """Base exception for download service errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code or 'DOWNLOAD_ERROR', context)


class TorrentAddError(DownloadError):
    """
    Exception raised when adding a torrent fails.

    Attributes:
        torrent_url: URL or path of the torrent that failed to add.
    """

    def __init__(
        self,
        message: str,
        torrent_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        ctx = context or {}
        if torrent_url:
            ctx['torrent_url'] = torrent_url
        super().__init__(message, 'TORRENT_ADD_FAILED', ctx)
        self.torrent_url = torrent_url


class TorrentNotFoundError(DownloadError):
    """
    Exception raised when a torrent cannot be found.

    Attributes:
        hash_id: The hash of the torrent that was not found.
    """

    def __init__(
        self,
        message: str,
        hash_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        ctx = context or {}
        if hash_id:
            ctx['hash_id'] = hash_id
        super().__init__(message, 'TORRENT_NOT_FOUND', ctx)
        self.hash_id = hash_id


# File operation exceptions

class FileOperationError(AniDownError):
    """Base exception for file operation errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code or 'FILE_OPERATION_ERROR', context)


class HardlinkError(FileOperationError):
    """
    Exception raised when hardlink creation fails.

    Attributes:
        source_path: Source file path.
        target_path: Target hardlink path.
    """

    def __init__(
        self,
        message: str,
        source_path: Optional[str] = None,
        target_path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        ctx = context or {}
        if source_path:
            ctx['source_path'] = source_path
        if target_path:
            ctx['target_path'] = target_path
        super().__init__(message, 'HARDLINK_ERROR', ctx)
        self.source_path = source_path
        self.target_path = target_path


# Configuration exceptions

class ConfigError(AniDownError):
    """Base exception for configuration errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code or 'CONFIG_ERROR', context)


class ConfigValidationError(ConfigError):
    """
    Exception raised when configuration validation fails.

    Attributes:
        field_name: Name of the field that failed validation.
        field_value: The invalid value.
    """

    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        field_value: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        ctx = context or {}
        if field_name:
            ctx['field_name'] = field_name
        if field_value is not None:
            ctx['field_value'] = str(field_value)
        super().__init__(message, 'CONFIG_VALIDATION_ERROR', ctx)
        self.field_name = field_name
        self.field_value = field_value


# Database exceptions

class DatabaseError(AniDownError):
    """Base exception for database errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code or 'DATABASE_ERROR', context)


class RecordNotFoundError(DatabaseError):
    """
    Exception raised when a database record cannot be found.

    Attributes:
        table_name: Name of the table.
        record_id: ID of the record that was not found.
    """

    def __init__(
        self,
        message: str,
        table_name: Optional[str] = None,
        record_id: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        ctx = context or {}
        if table_name:
            ctx['table_name'] = table_name
        if record_id is not None:
            ctx['record_id'] = str(record_id)
        super().__init__(message, 'RECORD_NOT_FOUND', ctx)
        self.table_name = table_name
        self.record_id = record_id


# Parse exceptions

class ParseError(AniDownError):
    """Base exception for parsing errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, code or 'PARSE_ERROR', context)


class RSSParseError(ParseError):
    """
    Exception raised when RSS feed parsing fails.

    Attributes:
        feed_url: URL of the RSS feed that failed to parse.
    """

    def __init__(
        self,
        message: str,
        feed_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        ctx = context or {}
        if feed_url:
            ctx['feed_url'] = feed_url
        super().__init__(message, 'RSS_PARSE_ERROR', ctx)
        self.feed_url = feed_url


class TitleParseError(ParseError):
    """
    Exception raised when title parsing fails.

    Attributes:
        title: The title that failed to parse.
    """

    def __init__(
        self,
        message: str,
        title: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        ctx = context or {}
        if title:
            ctx['title'] = title[:200]  # Truncate for logging
        super().__init__(message, 'TITLE_PARSE_ERROR', ctx)
        self.title = title
