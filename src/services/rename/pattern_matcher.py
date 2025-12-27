"""
Pattern matcher module.

Provides regex-based pattern matching for episode and season extraction.
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EpisodeMatch:
    """
    Episode match result.

    Represents extracted episode information from a filename.

    Attributes:
        episode: Episode number.
        season: Season number (1 if not detected).
        version: Version number (e.g., 'v2').
        special: Special episode indicator.
        match_text: The text that was matched.
    """
    episode: int
    season: int = 1
    version: str | None = None
    special: str | None = None
    match_text: str = ''

    @property
    def formatted_episode(self) -> str:
        """Return formatted episode string (e.g., 'E05')."""
        if self.special:
            return f'{self.special}{self.episode:02d}'
        return f'E{self.episode:02d}'

    @property
    def formatted_season_episode(self) -> str:
        """Return formatted season-episode string (e.g., 'S01E05')."""
        return f'S{self.season:02d}{self.formatted_episode}'


class PatternMatcher:
    """
    Pattern matcher service.

    Extracts episode and season information from filenames using regex patterns.
    """

    # Episode patterns (ordered by specificity)
    EPISODE_PATTERNS: list[tuple[str, str]] = [
        # S01E05 or S1E5 format
        (r'[Ss](\d{1,2})[Ee](\d{1,4})', 'season_episode'),
        # - 05 - or [05] format (common in fansubs)
        (r'[\s\-\[\(](\d{2,4})[\s\-\]\)]', 'episode_only'),
        # EP05 or Ep.05 format
        (r'[Ee][Pp]\.?\s*(\d{1,4})', 'ep_prefix'),
        # #05 format
        (r'#(\d{1,4})', 'hash_prefix'),
        # Episode 05 or 第5話 format
        (r'[Ee]pisode\s*(\d{1,4})', 'episode_word'),
        (r'第(\d{1,4})[話话集]', 'japanese_format'),
        # End of filename number before extension
        (r'[\s_\-\.](\d{2,4})(?:\s*[vV]\d)?(?:\s*(?:END|FIN|Final))?\.', 'trailing'),
        # Version marker (v2, v3, etc.)
        (r'(\d{2,4})\s*[vV](\d)', 'with_version'),
    ]

    # Season patterns
    SEASON_PATTERNS: list[tuple[str, str]] = [
        # Season 2 or Season2 or S2
        (r'[Ss]eason\s*(\d{1,2})', 'season_word'),
        (r'[Ss](\d{1,2})[Ee]', 'season_prefix'),
        # 第2季 or 第二季
        (r'第(\d{1,2})[季期]', 'japanese_season'),
        (r'第([一二三四五六七八九十]+)[季期]', 'japanese_season_kanji'),
        # Part 2 or Part2
        (r'[Pp]art\s*(\d{1,2})', 'part_number'),
        # II, III, IV etc. at the end
        (r'\s+(II|III|IV|V|VI|VII|VIII|IX|X)\s*(?:\[|$)', 'roman_numeral'),
    ]

    # Special episode patterns
    SPECIAL_PATTERNS: list[tuple[str, str]] = [
        (r'[Ss][Pp](\d{1,2})', 'sp_number'),
        (r'[Ss]pecial\s*(\d{1,2})?', 'special_word'),
        (r'[Oo][Aa][Dd]\s*(\d{1,2})?', 'oad'),
        (r'[Oo][Vv][Aa]\s*(\d{1,2})?', 'ova'),
        (r'[Nn][Cc][Oo][Pp]', 'ncop'),
        (r'[Nn][Cc][Ee][Dd]', 'nced'),
    ]

    # Kanji to number mapping
    KANJI_NUMBERS = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
    }

    # Roman numeral mapping
    ROMAN_NUMERALS = {
        'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
        'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10
    }

    def __init__(self):
        """Initialize the pattern matcher."""
        # Pre-compile patterns for performance
        self._episode_patterns = [
            (re.compile(pattern), name) for pattern, name in self.EPISODE_PATTERNS
        ]
        self._season_patterns = [
            (re.compile(pattern), name) for pattern, name in self.SEASON_PATTERNS
        ]
        self._special_patterns = [
            (re.compile(pattern), name) for pattern, name in self.SPECIAL_PATTERNS
        ]

    def extract_episode(self, filename: str) -> EpisodeMatch | None:
        """
        Extract episode information from a filename.

        Args:
            filename: The filename to parse.

        Returns:
            EpisodeMatch if found, None otherwise.
        """
        # First check for special episodes
        special_match = self._match_special(filename)
        if special_match:
            return special_match

        # Try season+episode patterns first
        for pattern, name in self._episode_patterns:
            match = pattern.search(filename)
            if match:
                result = self._parse_episode_match(match, name)
                if result:
                    # Also try to extract season
                    season = self._extract_season(filename)
                    if season and name != 'season_episode':
                        result.season = season
                    return result

        return None

    def _parse_episode_match(
        self,
        match: re.Match,
        pattern_name: str
    ) -> EpisodeMatch | None:
        """
        Parse a regex match into an EpisodeMatch.

        Args:
            match: Regex match object.
            pattern_name: Name of the pattern that matched.

        Returns:
            EpisodeMatch or None.
        """
        try:
            if pattern_name == 'season_episode':
                season = int(match.group(1))
                episode = int(match.group(2))
                return EpisodeMatch(
                    episode=episode,
                    season=season,
                    match_text=match.group(0)
                )
            elif pattern_name == 'with_version':
                episode = int(match.group(1))
                version = f'v{match.group(2)}'
                return EpisodeMatch(
                    episode=episode,
                    version=version,
                    match_text=match.group(0)
                )
            else:
                # Single episode number patterns
                episode = int(match.group(1))
                # Sanity check: episode numbers typically under 1000
                if episode > 1000:
                    return None
                return EpisodeMatch(
                    episode=episode,
                    match_text=match.group(0)
                )
        except (ValueError, IndexError):
            return None

    def _extract_season(self, filename: str) -> int | None:
        """
        Extract season number from filename.

        Args:
            filename: The filename to parse.

        Returns:
            Season number if found, None otherwise.
        """
        for pattern, name in self._season_patterns:
            match = pattern.search(filename)
            if match:
                try:
                    if name == 'japanese_season_kanji':
                        return self._kanji_to_number(match.group(1))
                    elif name == 'roman_numeral':
                        return self.ROMAN_NUMERALS.get(match.group(1), None)
                    else:
                        return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None

    def _match_special(self, filename: str) -> EpisodeMatch | None:
        """
        Match special episode patterns.

        Args:
            filename: The filename to parse.

        Returns:
            EpisodeMatch for special episode, or None.
        """
        for pattern, name in self._special_patterns:
            match = pattern.search(filename)
            if match:
                try:
                    episode_num = 1
                    if match.lastindex and match.group(1):
                        episode_num = int(match.group(1))

                    special_type = name.upper()
                    if name == 'sp_number':
                        special_type = 'SP'
                    elif name == 'special_word':
                        special_type = 'SP'

                    return EpisodeMatch(
                        episode=episode_num,
                        special=special_type,
                        match_text=match.group(0)
                    )
                except (ValueError, IndexError):
                    continue
        return None

    def _kanji_to_number(self, kanji: str) -> int:
        """
        Convert Japanese kanji numbers to integers.

        Args:
            kanji: Kanji number string (e.g., '二').

        Returns:
            Integer value.
        """
        if len(kanji) == 1:
            return self.KANJI_NUMBERS.get(kanji, 1)

        # Handle compound numbers like 十二 (12)
        total = 0
        for char in kanji:
            if char == '十':
                total = (total or 1) * 10
            else:
                total += self.KANJI_NUMBERS.get(char, 0)
        return total or 1

    def extract_quality_info(self, filename: str) -> dict:
        """
        Extract quality information from filename.

        Args:
            filename: The filename to parse.

        Returns:
            Dictionary with quality info (resolution, codec, source, etc.).
        """
        info = {}

        # Resolution patterns
        resolution_patterns = [
            (r'(3840\s*[xX×]\s*2160|4[kK]|UHD)', '4K'),
            (r'(2560\s*[xX×]\s*1440|1440[pP]|2[kK])', '1440p'),
            (r'(1920\s*[xX×]\s*1080|1080[pP]|[Ff][Hh][Dd])', '1080p'),
            (r'(1280\s*[xX×]\s*720|720[pP]|[Hh][Dd])', '720p'),
            (r'(854\s*[xX×]\s*480|480[pP]|[Ss][Dd])', '480p'),
        ]

        for pattern, resolution in resolution_patterns:
            if re.search(pattern, filename):
                info['resolution'] = resolution
                break

        # Codec patterns
        codec_patterns = [
            (r'[Hh]\.?265|[Hh][Ee][Vv][Cc]', 'HEVC'),
            (r'[Hh]\.?264|[Aa][Vv][Cc]', 'AVC'),
            (r'[Aa][Vv]1', 'AV1'),
            (r'[Xx]265', 'x265'),
            (r'[Xx]264', 'x264'),
        ]

        for pattern, codec in codec_patterns:
            if re.search(pattern, filename):
                info['codec'] = codec
                break

        # Source patterns
        source_patterns = [
            (r'[Bb][Dd][Rr][Ii][Pp]|[Bb]lu-?[Rr]ay', 'BDRip'),
            (r'[Ww][Ee][Bb]-?[Dd][Ll]', 'WEB-DL'),
            (r'[Ww][Ee][Bb][Rr][Ii][Pp]', 'WEBRip'),
            (r'[Hh][Dd][Tt][Vv]', 'HDTV'),
            (r'[Dd][Vv][Dd][Rr][Ii][Pp]', 'DVDRip'),
        ]

        for pattern, source in source_patterns:
            if re.search(pattern, filename):
                info['source'] = source
                break

        # Audio codec
        audio_patterns = [
            (r'[Ff][Ll][Aa][Cc]', 'FLAC'),
            (r'[Aa][Aa][Cc]', 'AAC'),
            (r'[Dd][Tt][Ss]', 'DTS'),
            (r'[Aa][Cc]3|[Dd][Dd]5\.?1', 'AC3'),
        ]

        for pattern, audio in audio_patterns:
            if re.search(pattern, filename):
                info['audio'] = audio
                break

        return info

    def clean_filename_for_matching(self, filename: str) -> str:
        """
        Clean a filename for better pattern matching.

        Removes common noise and normalizes spacing.

        Args:
            filename: Original filename.

        Returns:
            Cleaned filename.
        """
        # Remove extension
        name = re.sub(r'\.[a-zA-Z0-9]{2,4}$', '', filename)

        # Replace underscores and dots with spaces
        name = re.sub(r'[_.]', ' ', name)

        # Normalize spaces
        name = re.sub(r'\s+', ' ', name)

        return name.strip()
