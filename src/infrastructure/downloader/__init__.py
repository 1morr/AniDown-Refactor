"""
Downloader infrastructure module.

Provides download client adapters.
"""

from src.infrastructure.downloader.qbit_adapter import (
    QBitAdapter,
    get_torrent_hash_from_file,
    get_torrent_hash_from_magnet,
)

__all__ = [
    'QBitAdapter',
    'get_torrent_hash_from_file',
    'get_torrent_hash_from_magnet',
]
