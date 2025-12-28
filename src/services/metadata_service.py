"""
Metadata service module.

Provides anime metadata fetching and caching functionality.
"""

import json
import logging
from typing import Any

from src.core.config import config
from src.core.interfaces import IMetadataClient

logger = logging.getLogger(__name__)


class MetadataService:
    """
    Metadata service for anime information.

    Orchestrates metadata fetching from external sources (TVDB, etc.)
    and provides caching and data simplification.
    """

    def __init__(self, metadata_client: IMetadataClient):
        """
        Initialize the metadata service.

        Args:
            metadata_client: Metadata client implementation (e.g., TVDBAdapter).
        """
        self._metadata_client = metadata_client

    def get_tvdb_data_for_anime(self, anime_name: str) -> dict[str, Any] | None:
        """
        Get TVDB data for an anime by name.

        Searches for exact match and returns AI-formatted data.

        Args:
            anime_name: Anime name to search for.

        Returns:
            AI-formatted TVDB data if found, None otherwise.
        """
        # Check API Key
        if not config.tvdb.api_key:
            logger.warning('⚠️ TVDB API Key未配置')
            return None

        try:
            # Login to TVDB
            if not self._metadata_client.login():
                logger.error('❌ TVDB登录失败')
                return None

            # Search for exact match
            matched_series = self._metadata_client.find_exact_match(anime_name)

            if not matched_series:
                logger.info(f'⚠️ 未找到与 \'{anime_name}\' 精确匹配的TVDB系列')
                return None

            # Get all episodes
            series_id = matched_series.get('id')
            episodes = self._metadata_client.get_all_episodes(series_id)

            # Generate AI format
            ai_data = self._metadata_client.generate_ai_format(
                matched_series,
                episodes
            )

            # Check and simplify if data is too large
            ai_data = self._simplify_if_needed(ai_data)

            logger.info(
                f'✅ 成功获取TVDB数据: {ai_data["series_name"]} '
                f'({ai_data["total_seasons"]} 季)'
            )
            return ai_data

        except Exception as e:
            logger.error(f'❌ 获取TVDB数据失败: {e}')
            return None

    def get_tvdb_data_by_id(
        self,
        series_id: int
    ) -> dict[str, Any] | None:
        """
        Get TVDB data by series ID.

        Args:
            series_id: TVDB series ID.

        Returns:
            AI-formatted TVDB data if found, None otherwise.
        """
        # Check API Key
        if not config.tvdb.api_key:
            logger.warning('⚠️ TVDB API Key未配置')
            return None

        try:
            # Login to TVDB
            if not self._metadata_client.login():
                logger.error('❌ TVDB登录失败')
                return None

            # Get series extended info
            series_data = self._metadata_client.get_series_extended(series_id)
            if not series_data:
                logger.info(f'⚠️ 未找到ID为 \'{series_id}\' 的TVDB系列')
                return None

            # Get all episodes
            episodes = self._metadata_client.get_all_episodes(series_id)

            # Generate AI format
            ai_data = self._metadata_client.generate_ai_format(
                series_data,
                episodes
            )

            # Check and simplify if data is too large
            ai_data = self._simplify_if_needed(ai_data)

            logger.info(
                f'✅ 成功获取TVDB数据 (ID: {series_id}): '
                f'{ai_data["series_name"]} ({ai_data["total_seasons"]} 季)'
            )
            return ai_data

        except Exception as e:
            logger.error(f'❌ 获取TVDB数据失败 (ID: {series_id}): {e}')
            return None

    def _simplify_if_needed(
        self,
        ai_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Simplify AI data if it exceeds maximum length.

        Args:
            ai_data: AI format data to check.

        Returns:
            Original or simplified data.
        """
        json_str = json.dumps(ai_data, ensure_ascii=False)
        max_length = config.tvdb.max_data_length

        if len(json_str) > max_length:
            logger.info(
                f'📦 TVDB数据过大 ({len(json_str)} 字符)，使用简化版本'
            )
            return self._metadata_client.simplify_ai_format(ai_data)
        else:
            logger.info(f'📦 TVDB数据大小: {len(json_str)} 字符')
            return ai_data

