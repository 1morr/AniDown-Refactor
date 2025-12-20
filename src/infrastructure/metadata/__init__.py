"""
Infrastructure metadata module.

Contains adapters for fetching anime metadata from external sources.
"""

from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter

__all__ = [
    'TVDBAdapter',
]
