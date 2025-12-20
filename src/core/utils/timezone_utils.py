"""
Timezone utilities module.

Provides unified time handling functions for the application.

Features:
1. All database times are stored in UTC
2. Provides unified time formatting functions
3. Ensures consistency across time zones
"""

from datetime import datetime, timezone
from typing import Optional


def get_utc_now() -> datetime:
    """
    Get the current UTC time.

    Returns:
        datetime: Current time with UTC timezone info.
    """
    return datetime.now(timezone.utc)


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert a datetime object to UTC time.

    Args:
        dt: The datetime object to convert.

    Returns:
        datetime: UTC time, or None if input is None.
    """
    if dt is None:
        return None

    # If already has timezone info, convert to UTC
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)

    # If no timezone info, assume it's UTC (database time)
    return dt.replace(tzinfo=timezone.utc)


def format_datetime_iso(dt: Optional[datetime]) -> Optional[str]:
    """
    Format a datetime to ISO 8601 string (with timezone info).
    Used for database storage and API transmission.

    Args:
        dt: The datetime object to format.

    Returns:
        str: ISO 8601 formatted string, e.g., "2025-11-29T10:30:00+00:00"
             Returns None if input is None.
    """
    if dt is None:
        return None

    # Ensure it's UTC time
    utc_dt = to_utc(dt)

    # Return ISO 8601 format
    return utc_dt.isoformat()


def format_datetime_display(dt: Optional[datetime], format_type: str = 'full') -> str:
    """
    Format a datetime for display (ISO 8601 format).
    Frontend JavaScript will automatically convert to user's local timezone.

    Args:
        dt: The datetime object to format.
        format_type: Format type (kept for compatibility).

    Returns:
        str: ISO 8601 formatted string, or '-' if input is None.
    """
    if dt is None:
        return '-'

    return format_datetime_iso(dt)


def parse_iso_datetime(iso_string: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO 8601 formatted time string.

    Args:
        iso_string: ISO 8601 formatted time string.

    Returns:
        datetime: Datetime object with timezone info, or None if parsing fails.
    """
    if not iso_string:
        return None

    try:
        # Python 3.7+ supports fromisoformat
        return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


# Aliases for backward compatibility
utc_now = get_utc_now
to_iso = format_datetime_iso
from_iso = parse_iso_datetime
