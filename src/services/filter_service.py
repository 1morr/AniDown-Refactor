"""
Filter service module.

Provides content filtering functionality using keywords and regular expressions.
"""

import logging
import re
from typing import Dict, Any, List, Pattern

logger = logging.getLogger(__name__)


class FilterService:
    """
    Filter service for content filtering.

    Provides keyword and regex-based filtering for RSS items and other content.
    """

    def __init__(self):
        """Initialize the filter service."""
        self._compiled_regex_cache: Dict[str, Pattern] = {}

    def apply_keyword_filter(
        self,
        items: List[Dict[str, Any]],
        blocked_keywords: str
    ) -> List[Dict[str, Any]]:
        """
        Apply keyword filter to a list of items.

        Args:
            items: List of items to filter (each with a 'title' key).
            blocked_keywords: Newline-separated list of keywords to block.

        Returns:
            Filtered list of items.
        """
        if not blocked_keywords or not blocked_keywords.strip():
            return items

        keyword_filters = [
            kw.strip().lower()
            for kw in blocked_keywords.split('\n')
            if kw.strip()
        ]

        if not keyword_filters:
            return items

        filtered_items = []

        for item in items:
            title = item.get('title', '')
            title_lower = title.lower()
            should_skip = False

            for keyword in keyword_filters:
                if keyword in title_lower:
                    should_skip = True
                    logger.info(f'⏭️ 跳过项目: {title} - 匹配屏蔽词: {keyword}')
                    break

            if not should_skip:
                filtered_items.append(item)

        return filtered_items

    def apply_regex_filter(
        self,
        items: List[Dict[str, Any]],
        blocked_regex: str
    ) -> List[Dict[str, Any]]:
        """
        Apply regular expression filter to a list of items.

        Args:
            items: List of items to filter (each with a 'title' key).
            blocked_regex: Newline-separated list of regex patterns to block.

        Returns:
            Filtered list of items.
        """
        if not blocked_regex or not blocked_regex.strip():
            return items

        regex_filters = self._compile_regex_patterns(blocked_regex)

        if not regex_filters:
            return items

        filtered_items = []

        for item in items:
            title = item.get('title', '')
            should_skip = False

            for regex in regex_filters:
                if regex.search(title):
                    should_skip = True
                    logger.info(
                        f'⏭️ 跳过项目: {title} - 匹配正则表达式: {regex.pattern}'
                    )
                    break

            if not should_skip:
                filtered_items.append(item)

        return filtered_items

    def should_filter(
        self,
        title: str,
        blocked_keywords: str = None,
        blocked_regex: str = None
    ) -> bool:
        """
        Check if a title should be filtered.

        Args:
            title: Title to check.
            blocked_keywords: Newline-separated list of keywords to block.
            blocked_regex: Newline-separated list of regex patterns to block.

        Returns:
            True if the title should be filtered, False otherwise.
        """
        # Check keyword filter
        if blocked_keywords:
            keyword_filters = [
                kw.strip().lower()
                for kw in blocked_keywords.split('\n')
                if kw.strip()
            ]
            title_lower = title.lower()

            for keyword in keyword_filters:
                if keyword in title_lower:
                    logger.info(f'⏭️ 过滤项目: {title} - 匹配屏蔽词: {keyword}')
                    return True

        # Check regex filter
        if blocked_regex:
            regex_filters = self._compile_regex_patterns(blocked_regex)

            for regex in regex_filters:
                if regex.search(title):
                    logger.info(
                        f'⏭️ 过滤项目: {title} - 匹配正则表达式: {regex.pattern}'
                    )
                    return True

        return False

    def _compile_regex_patterns(self, patterns_str: str) -> List[Pattern]:
        """
        Compile regex patterns from a newline-separated string.

        Uses caching for performance.

        Args:
            patterns_str: Newline-separated regex patterns.

        Returns:
            List of compiled regex patterns.
        """
        compiled_patterns = []

        for pattern in patterns_str.split('\n'):
            pattern = pattern.strip()
            if not pattern:
                continue

            # Check cache first
            if pattern in self._compiled_regex_cache:
                compiled_patterns.append(self._compiled_regex_cache[pattern])
            else:
                try:
                    compiled = re.compile(pattern)
                    self._compiled_regex_cache[pattern] = compiled
                    compiled_patterns.append(compiled)
                except re.error as e:
                    logger.warning(f'⚠️ 无效的正则表达式: {pattern} - {e}')

        return compiled_patterns

    def clear_cache(self) -> None:
        """Clear the compiled regex cache."""
        self._compiled_regex_cache.clear()
        logger.debug('🧹 已清除正则表达式缓存')


# Global filter service instance
_filter_service: FilterService = None


def get_filter_service() -> FilterService:
    """
    Get the global filter service instance.

    Returns:
        FilterService instance.
    """
    global _filter_service
    if _filter_service is None:
        _filter_service = FilterService()
    return _filter_service
