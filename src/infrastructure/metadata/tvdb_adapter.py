"""
TVDB adapter module.

Provides integration with TVDB API v4 for fetching anime metadata.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.core.config import config
from src.core.interfaces import IMetadataClient

logger = logging.getLogger(__name__)


class TVDBAdapter(IMetadataClient):
    """
    TVDB API v4 adapter.

    Implements IMetadataClient interface for fetching anime metadata from TVDB.
    """

    BASE_URL = 'https://api4.thetvdb.com/v4'
    DEFAULT_TIMEOUT = 10

    def __init__(self):
        """Initialize the TVDB adapter."""
        self._api_key = config.tvdb.api_key
        self._enabled = config.tvdb.enabled
        self._token: Optional[str] = None

    @property
    def is_enabled(self) -> bool:
        """Check if TVDB integration is enabled."""
        return self._enabled and bool(self._api_key)

    def login(self) -> bool:
        """
        Authenticate with TVDB API using API key.

        Returns:
            True if login was successful, False otherwise.
        """
        if not self.is_enabled:
            logger.debug('TVDB功能未启用或未配置API Key')
            return False

        try:
            url = f'{self.BASE_URL}/login'
            headers = {'Content-Type': 'application/json'}
            data = {'apikey': self._api_key}

            response = requests.post(
                url,
                json=data,
                headers=headers,
                timeout=self.DEFAULT_TIMEOUT
            )
            response.raise_for_status()

            result = response.json()
            self._token = result.get('data', {}).get('token')

            if self._token:
                logger.info('✅ TVDB登录成功')
                return True
            else:
                logger.error('❌ TVDB登录失败：未获取到token')
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f'❌ TVDB登录失败：{e}')
            return False

    def _get_headers(self) -> Dict[str, str]:
        """
        Get request headers with authentication token.

        Returns:
            Headers dictionary with authorization.
        """
        if not self._token:
            self.login()

        return {
            'Authorization': f'Bearer {self._token}',
            'Content-Type': 'application/json'
        }

    def search_series(self, name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Search for a series by name.

        Args:
            name: Series name to search for.

        Returns:
            List of search results if successful, None otherwise.
        """
        if not self._enabled:
            return None

        try:
            url = f'{self.BASE_URL}/search'
            params = {'query': name, 'type': 'series'}

            response = requests.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=self.DEFAULT_TIMEOUT
            )
            response.raise_for_status()

            result = response.json()
            search_results = result.get('data', [])
            logger.info(f'🔍 TVDB搜索 \'{name}\' 找到 {len(search_results)} 个结果')
            return search_results

        except requests.exceptions.RequestException as e:
            logger.error(f'❌ TVDB搜索失败：{e}')
            return None

    def get_series_extended(self, series_id: int) -> Optional[Dict[str, Any]]:
        """
        Get extended information for a series.

        Args:
            series_id: Series identifier.

        Returns:
            Series extended data if found, None otherwise.
        """
        if not self._enabled:
            return None

        try:
            url = f'{self.BASE_URL}/series/{series_id}/extended'
            params = {'meta': 'translations'}

            response = requests.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=self.DEFAULT_TIMEOUT
            )
            response.raise_for_status()

            result = response.json()
            return result.get('data', {})

        except requests.exceptions.RequestException as e:
            logger.error(f'❌ 获取TVDB系列详情失败：{e}')
            return None

    def get_series_episodes(
        self,
        series_id: int,
        page: int = 0,
        language: str = 'default'
    ) -> Optional[Dict[str, Any]]:
        """
        Get episodes for a series with pagination.

        Args:
            series_id: Series identifier.
            page: Page number for pagination.
            language: Language code ('default' for original, 'eng' for English).

        Returns:
            Episode data if found, None otherwise.
        """
        if not self._enabled:
            return None

        try:
            if language == 'default':
                url = f'{self.BASE_URL}/series/{series_id}/episodes/default'
            else:
                url = f'{self.BASE_URL}/series/{series_id}/episodes/default/{language}'

            params = {'page': page}

            response = requests.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=self.DEFAULT_TIMEOUT
            )
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f'❌ 获取TVDB剧集失败：{e}')
            return None

    def get_all_episodes(self, series_id: int) -> List[Dict[str, Any]]:
        """
        Get all episodes for a series with pagination handling.

        Also fetches English translations and merges them with original data.

        Args:
            series_id: Series identifier.

        Returns:
            List of all episodes with both original and English names.
        """
        if not self._enabled:
            return []

        # Fetch original language episodes
        logger.info('  获取原文名称...')
        original_episodes = self._fetch_all_pages(series_id, 'default')

        # Fetch English translations
        logger.info('  获取英文翻译...')
        eng_episodes = self._fetch_all_pages(series_id, 'eng')

        # Create English name lookup dictionary
        eng_names = {}
        for ep in eng_episodes:
            ep_id = ep.get('id')
            if ep_id:
                eng_names[ep_id] = ep.get('name', '')

        # Merge English names into original episodes
        for ep in original_episodes:
            ep_id = ep.get('id')
            if ep_id and ep_id in eng_names:
                ep['englishName'] = eng_names[ep_id]

        logger.info(f'📋 获取到 {len(original_episodes)} 集')
        return original_episodes

    def _fetch_all_pages(
        self,
        series_id: int,
        language: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch all pages of episodes for a series.

        Args:
            series_id: Series identifier.
            language: Language code.

        Returns:
            List of all episodes.
        """
        all_episodes = []
        page = 0

        while True:
            result = self.get_series_episodes(series_id, page, language)
            if not result:
                break

            episodes = result.get('data', {}).get('episodes', [])
            if not episodes:
                break

            all_episodes.extend(episodes)

            # Check for next page
            links = result.get('links', {})
            if not links.get('next'):
                break

            page += 1

        return all_episodes

    def _check_name_match(
        self,
        series_data: Dict[str, Any],
        target_name: str
    ) -> Tuple[bool, str]:
        """
        Check if target name matches any series name or alias.

        Args:
            series_data: Series data with names and aliases.
            target_name: Name to match against.

        Returns:
            Tuple of (is_match, matched_name).
        """
        all_names = []

        # Main name
        main_name = series_data.get('name', '')
        if main_name:
            all_names.append(main_name)

        # Aliases
        aliases = series_data.get('aliases', [])
        for alias in aliases:
            alias_name = alias.get('name', '')
            if alias_name:
                all_names.append(alias_name)

        # Translations
        translations = series_data.get('translations', {})
        name_translations = translations.get('nameTranslations', [])
        for trans in name_translations:
            trans_name = trans.get('name', '')
            if trans_name:
                all_names.append(trans_name)

        # Check for exact match
        for name in all_names:
            if name == target_name:
                return True, name

        return False, ''

    def find_exact_match(
        self,
        anime_name: str,
        max_check: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        Search and find an exact match for anime name.

        Args:
            anime_name: Anime name to search for.
            max_check: Maximum number of results to check.

        Returns:
            Matched series data if found, None otherwise.
        """
        if not self._enabled:
            return None

        # Search for the name
        search_results = self.search_series(anime_name)
        if not search_results:
            logger.warning(f'⚠️ TVDB搜索 \'{anime_name}\' 无结果')
            return None

        # Check top N results for exact match
        check_count = min(max_check, len(search_results))
        logger.info(f'🔎 在前 {check_count} 个结果中寻找精确匹配...')

        for i, result in enumerate(search_results[:check_count], 1):
            series_id = result.get('tvdb_id')
            result_name = result.get('name', 'N/A')

            if not series_id:
                continue

            logger.debug(f'  检查 {i}/{check_count}: {result_name}')

            # Get extended info for name matching
            series_data = self.get_series_extended(series_id)
            if not series_data:
                logger.debug('    获取详情失败')
                continue

            # Check for exact match
            is_match, matched_name = self._check_name_match(series_data, anime_name)

            if is_match:
                logger.info(
                    f'✅ 找到精确匹配: {result_name} (匹配名称: {matched_name})'
                )
                return series_data

        logger.info(
            f'⚠️ 在前 {check_count} 个结果中未找到与 \'{anime_name}\' '
            f'精确匹配的系列'
        )
        return None

    def generate_ai_format(
        self,
        series_data: Dict[str, Any],
        episodes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate AI-friendly format for series data.

        Args:
            series_data: Series information.
            episodes: List of episodes.

        Returns:
            AI-formatted data structure.
        """
        main_name = series_data.get('name', '')

        # Group episodes by season
        seasons_dict: Dict[int, List[Dict[str, Any]]] = {}
        for episode in episodes:
            season_num = episode.get('seasonNumber')
            if season_num is not None:
                if season_num not in seasons_dict:
                    seasons_dict[season_num] = []
                seasons_dict[season_num].append(episode)

        # Build season data
        seasons = []
        for season_num in sorted(seasons_dict.keys()):
            season_episodes = seasons_dict[season_num]
            # Sort by episode number
            season_episodes.sort(key=lambda x: x.get('number', 0))

            episodes_list = []
            for ep in season_episodes:
                original_title = ep.get('name', 'Untitled')
                english_title = ep.get('englishName', '')

                # Build display title with English in parentheses
                if (english_title and
                        english_title != original_title and
                        english_title.strip()):
                    display_title = f'{original_title} ({english_title})'
                else:
                    display_title = original_title

                episodes_list.append({
                    'episode': ep.get('number'),
                    'title': display_title
                })

            seasons.append({
                'season': season_num,
                'total_episodes': len(season_episodes),
                'episodes': episodes_list
            })

        return {
            'series_name': main_name,
            'tvdb_id': series_data.get('id'),
            'total_seasons': len(seasons),
            'seasons': seasons
        }

    def simplify_ai_format(
        self,
        ai_format_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Simplify AI format data for reduced token usage.

        Removes individual episode titles to save tokens.

        Args:
            ai_format_data: Full AI format data.

        Returns:
            Simplified data structure.
        """
        simplified_data = {
            'series_name': ai_format_data['series_name'],
            'tvdb_id': ai_format_data['tvdb_id'],
            'total_seasons': ai_format_data['total_seasons'],
            'seasons': []
        }

        for season in ai_format_data['seasons']:
            simplified_data['seasons'].append({
                'season': season['season'],
                'total_episodes': season['total_episodes']
                # Omit episodes array to reduce tokens
            })

        return simplified_data
