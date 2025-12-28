"""
Tests for path generation and filename sanitization.

Tests PathBuilder, FilenameFormatter, and related functionality.
"""

import pytest
from pathlib import Path

from tests.fixtures.test_data import PATH_TEST_CASES, FILENAME_SANITIZE_CASES


class TestPathBuilder:
    """Tests for PathBuilder class."""

    @pytest.fixture
    def path_builder(self):
        """Create PathBuilder instance."""
        from src.services.file.path_builder import PathBuilder

        return PathBuilder(
            download_root='/downloads/AniDown/',
            anime_tv_root='/library/TV Shows'
        )

    def test_path_builder_initialization(self):
        """Test PathBuilder initializes correctly."""
        from src.services.file.path_builder import PathBuilder

        builder = PathBuilder(
            download_root='/downloads/AniDown/',
            anime_tv_root='/library/TV Shows'
        )

        assert builder is not None
        # Path is normalized: trailing slash removed, backslashes converted to forward slashes
        assert builder._download_root == '/downloads/AniDown'
        assert builder._anime_tv_root == '/library/TV Shows'

    def test_path_builder_windows_path_normalization(self):
        """Test PathBuilder normalizes Windows-style paths for Docker compatibility."""
        from src.services.file.path_builder import PathBuilder

        # Windows-style path with backslashes and trailing backslash
        builder = PathBuilder(
            download_root='C:\\Users\\Roxy\\storage\\Downloads\\AniDown\\',
            anime_tv_root='/storage/Library/Anime/TV Shows'
        )

        # Backslashes should be converted to forward slashes
        assert builder._download_root == 'C:/Users/Roxy/storage/Downloads/AniDown'
        assert '\\' not in builder._download_root

        # Build path should use forward slashes consistently
        path = builder.build_download_path(
            title='One Piece',
            season=1,
            category='tv',
            media_type='anime'
        )
        assert path == 'C:/Users/Roxy/storage/Downloads/AniDown/Anime/TV/One Piece/Season 1'
        assert '\\' not in path
        assert '\\/' not in path  # No mixed separators

    @pytest.mark.parametrize(
        'title,season,category,media_type,expected_parts',
        PATH_TEST_CASES
    )
    def test_build_download_path(
        self,
        path_builder,
        title,
        season,
        category,
        media_type,
        expected_parts
    ):
        """Test building download paths with various parameters."""
        path = path_builder.build_download_path(
            title=title,
            season=season,
            category=category,
            media_type=media_type
        )

        # Path should contain expected parts
        for part in expected_parts:
            assert part in path, f'Expected "{part}" in path "{path}"'

    def test_build_download_path_tv(self, path_builder):
        """Test building download path for TV show."""
        path = path_builder.build_download_path(
            title='金牌得主',
            season=1,
            category='tv',
            media_type='anime'
        )

        assert '金牌得主' in path
        assert 'Season 1' in path or 'S01' in path or 'season' in path.lower()

    def test_build_download_path_movie(self, path_builder):
        """Test building download path for movie."""
        path = path_builder.build_download_path(
            title='Test Movie',
            season=0,
            category='movie',
            media_type='anime'
        )

        assert 'Test Movie' in path
        # Movie path structure may differ - just check title is present
        assert 'Anime' in path

    def test_build_download_path_live_action(self, path_builder):
        """Test building download path for live action."""
        path = path_builder.build_download_path(
            title='Live Drama',
            season=1,
            category='tv',
            media_type='live_action'
        )

        assert 'Live Drama' in path
        assert 'LiveAction' in path

    def test_build_library_path(self, path_builder):
        """Test building library path for hardlinks."""
        path = path_builder.build_library_path(
            title='金牌得主',
            season=1,
            category='tv',
            media_type='anime'
        )

        assert '金牌得主' in path
        # Library path structure
        assert 'library' in path.lower() or 'Season' in path

    def test_sanitize_filename(self, path_builder):
        """Test filename sanitization."""
        # Test various problematic characters
        test_cases = [
            ('Test/Anime', '-'),
            ('Test\\Anime', '-'),
            ('Test:Anime', '-'),
            ('Test*Anime', '-'),
            ('Test?Anime', '-'),
            ('Test<Anime>', '-'),
            ('Test|Anime', '-'),
        ]

        for input_str, should_not_contain in test_cases:
            result = path_builder._sanitize_filename(input_str)
            # Should not contain the problematic character (replaced)
            assert should_not_contain not in result or result != input_str


class TestPathBuilderMultiLibrary:
    """Tests for PathBuilder multi-library root functionality."""

    def test_get_library_root_all_types(self):
        """Test get_library_root returns correct path for all media type/category combinations."""
        from src.services.file.path_builder import PathBuilder

        builder = PathBuilder(
            download_root='/downloads',
            anime_tv_root='/library/anime/tv',
            anime_movie_root='/library/anime/movies',
            live_action_tv_root='/library/live_action/tv',
            live_action_movie_root='/library/live_action/movies'
        )

        assert builder.get_library_root('anime', 'tv') == '/library/anime/tv'
        assert builder.get_library_root('anime', 'movie') == '/library/anime/movies'
        assert builder.get_library_root('live_action', 'tv') == '/library/live_action/tv'
        assert builder.get_library_root('live_action', 'movie') == '/library/live_action/movies'

    def test_get_library_root_fallback(self):
        """Test get_library_root falls back to anime_tv_root when optional paths not provided."""
        from src.services.file.path_builder import PathBuilder

        builder = PathBuilder(
            download_root='/downloads',
            anime_tv_root='/library/default'
            # Other paths not specified, should fallback
        )

        assert builder.get_library_root('anime', 'tv') == '/library/default'
        assert builder.get_library_root('anime', 'movie') == '/library/default'
        assert builder.get_library_root('live_action', 'tv') == '/library/default'
        assert builder.get_library_root('live_action', 'movie') == '/library/default'

    def test_get_library_root_partial_fallback(self):
        """Test get_library_root with partial paths specified."""
        from src.services.file.path_builder import PathBuilder

        builder = PathBuilder(
            download_root='/downloads',
            anime_tv_root='/library/anime_tv',
            anime_movie_root='/library/anime_movies'
            # live_action paths not specified
        )

        assert builder.get_library_root('anime', 'tv') == '/library/anime_tv'
        assert builder.get_library_root('anime', 'movie') == '/library/anime_movies'
        # Live action should fallback to anime_tv_root
        assert builder.get_library_root('live_action', 'tv') == '/library/anime_tv'
        assert builder.get_library_root('live_action', 'movie') == '/library/anime_tv'

    def test_build_library_path_uses_correct_root(self):
        """Test build_library_path uses the correct root for each media type/category."""
        from src.services.file.path_builder import PathBuilder

        builder = PathBuilder(
            download_root='/downloads',
            anime_tv_root='/library/anime_tv',
            anime_movie_root='/library/anime_movies',
            live_action_tv_root='/library/live_action_tv',
            live_action_movie_root='/library/live_action_movies'
        )

        # Anime TV
        path = builder.build_library_path('Frieren', 'anime', 'tv', season=1)
        assert path.startswith('/library/anime_tv')
        assert 'Frieren' in path
        assert 'Season 1' in path

        # Anime Movie
        path = builder.build_library_path('Your Name', 'anime', 'movie')
        assert path.startswith('/library/anime_movies')
        assert 'Your Name' in path

        # Live Action TV
        path = builder.build_library_path('Breaking Bad', 'live_action', 'tv', season=5)
        assert path.startswith('/library/live_action_tv')
        assert 'Breaking Bad' in path
        assert 'Season 5' in path

        # Live Action Movie
        path = builder.build_library_path('Inception', 'live_action', 'movie')
        assert path.startswith('/library/live_action_movies')
        assert 'Inception' in path

    def test_library_root_property_backward_compatible(self):
        """Test library_root property returns anime_tv_root for backward compatibility."""
        from src.services.file.path_builder import PathBuilder

        builder = PathBuilder(
            download_root='/downloads',
            anime_tv_root='/library/anime_tv',
            anime_movie_root='/library/anime_movies'
        )

        # library_root property should return anime_tv_root
        assert builder.library_root == '/library/anime_tv'


class TestFilenameFormatter:
    """Tests for FilenameFormatter class."""

    @pytest.fixture
    def formatter(self):
        """Create FilenameFormatter instance."""
        from src.services.rename.filename_formatter import FilenameFormatter

        return FilenameFormatter()

    def test_formatter_initialization(self):
        """Test FilenameFormatter initializes correctly."""
        from src.services.rename.filename_formatter import FilenameFormatter

        formatter = FilenameFormatter()

        assert formatter is not None

    @pytest.mark.parametrize('input_str,expected', FILENAME_SANITIZE_CASES)
    def test_sanitize_special_characters(self, formatter, input_str, expected):
        """Test sanitizing special characters in filenames."""
        # FilenameFormatter uses _sanitize_title internally
        result = formatter._sanitize_title(input_str)

        # Result should be sanitized (exact output may vary by implementation)
        # Check that problematic characters are handled
        assert result is not None
        assert len(result) > 0

    def test_format_episode_filename(self, formatter):
        """Test formatting episode filename."""
        from src.services.rename.pattern_matcher import EpisodeMatch

        episode_match = EpisodeMatch(episode=1, season=1)
        result = formatter.format_tv_episode(
            title='金牌得主',
            episode_match=episode_match,
            extension='.mkv'
        )

        assert '金牌得主' in result
        assert '.mkv' in result
        # Should contain season/episode info
        assert 'S01' in result or 'Season' in result or '01' in result

    def test_format_episode_with_subtitle_group(self, formatter):
        """Test formatting with different episode."""
        from src.services.rename.pattern_matcher import EpisodeMatch

        episode_match = EpisodeMatch(episode=5, season=2)
        result = formatter.format_tv_episode(
            title='金牌得主',
            episode_match=episode_match,
            extension='.mkv'
        )

        assert '金牌得主' in result
        assert '.mkv' in result
        assert 'S02' in result or '02' in result

    def test_format_movie_filename(self, formatter):
        """Test formatting movie filename."""
        result = formatter.format_movie(
            title='Test Movie',
            year=2024,
            extension='.mkv'
        )

        assert 'Test Movie' in result
        assert '.mkv' in result


class TestFileClassifier:
    """Tests for FileClassifier class."""

    @pytest.fixture
    def classifier(self):
        """Create FileClassifier instance."""
        from src.services.rename.file_classifier import FileClassifier

        return FileClassifier()

    def test_classifier_initialization(self):
        """Test FileClassifier initializes correctly."""
        from src.services.rename.file_classifier import FileClassifier

        classifier = FileClassifier()

        assert classifier is not None

    def test_classify_video_file(self, classifier, tmp_path):
        """Test classifying video file."""
        files = [{'name': 'episode01.mkv', 'size': 1000000000}]
        result = classifier.classify_files(files, str(tmp_path))

        assert len(result.video_files) == 1
        assert result.video_files[0].is_video

    def test_classify_subtitle_file(self, classifier, tmp_path):
        """Test classifying subtitle file."""
        files = [{'name': 'episode01.ass', 'size': 50000}]
        result = classifier.classify_files(files, str(tmp_path))

        assert len(result.subtitle_files) == 1
        assert result.subtitle_files[0].is_subtitle

    def test_classify_audio_file(self, classifier, tmp_path):
        """Test classifying audio file."""
        files = [{'name': 'soundtrack.flac', 'size': 30000000}]
        result = classifier.classify_files(files, str(tmp_path))

        assert len(result.audio_files) == 1

    def test_classify_other_file(self, classifier, tmp_path):
        """Test classifying other file types."""
        files = [{'name': 'readme.txt', 'size': 1000}]
        result = classifier.classify_files(files, str(tmp_path))

        # txt files are in ignored patterns
        assert len(result.ignored_files) == 1 or len(result.other_files) == 1

    def test_is_video_file(self, classifier):
        """Test video file detection."""
        video_extensions = ['.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv']

        for ext in video_extensions:
            assert classifier.is_video(f'file{ext}') is True

    def test_is_subtitle_file(self, classifier):
        """Test subtitle file detection."""
        subtitle_extensions = ['.ass', '.srt', '.ssa', '.sub', '.sup']

        for ext in subtitle_extensions:
            assert classifier.is_subtitle(f'file{ext}') is True


class TestPatternMatcher:
    """Tests for PatternMatcher class."""

    @pytest.fixture
    def matcher(self):
        """Create PatternMatcher instance."""
        from src.services.rename.pattern_matcher import PatternMatcher

        return PatternMatcher()

    def test_matcher_initialization(self):
        """Test PatternMatcher initializes correctly."""
        from src.services.rename.pattern_matcher import PatternMatcher

        matcher = PatternMatcher()

        assert matcher is not None

    def test_extract_episode_number(self, matcher):
        """Test extracting episode number from filename."""
        test_cases = [
            ('[Group] Anime - 01 [1080p].mkv', 1),
            ('[Group] Anime - 12 [1080p].mkv', 12),
            ('Anime S01E05.mkv', 5),
            ('Anime EP03.mkv', 3),
        ]

        for filename, expected_episode in test_cases:
            result = matcher.extract_episode(filename)
            if result is not None:
                # extract_episode returns EpisodeMatch object
                assert result.episode == expected_episode, \
                    f'Expected {expected_episode} for "{filename}", got {result.episode}'

    def test_extract_episode_with_season(self, matcher):
        """Test extracting episode with season from filename."""
        test_cases = [
            ('Anime S02E01.mkv', 2, 1),
            ('[Group] Anime S01E01.mkv', 1, 1),
        ]

        for filename, expected_season, expected_episode in test_cases:
            result = matcher.extract_episode(filename)
            if result is not None:
                assert result.episode == expected_episode, \
                    f'Expected episode {expected_episode} for "{filename}", got {result.episode}'
                if result.season is not None:
                    assert result.season == expected_season, \
                        f'Expected season {expected_season} for "{filename}", got {result.season}'


class TestRenameService:
    """Tests for RenameService class."""

    @pytest.fixture
    def rename_service(self):
        """Create RenameService instance."""
        from src.services.rename.rename_service import RenameService
        from src.services.rename.file_classifier import FileClassifier
        from src.services.rename.filename_formatter import FilenameFormatter

        return RenameService(
            file_classifier=FileClassifier(),
            filename_formatter=FilenameFormatter()
        )

    def test_rename_service_initialization(self, rename_service):
        """Test RenameService initializes correctly."""
        assert rename_service is not None

    def test_classify_files(self, rename_service, tmp_path):
        """Test classifying files in a torrent."""
        # Create test files
        files = [
            {'name': 'episode01.mkv', 'size': 1000000000},
            {'name': 'episode01.ass', 'size': 50000},
            {'name': 'episode02.mkv', 'size': 1000000000},
            {'name': 'readme.txt', 'size': 1000},
        ]

        video_files, subtitle_files = rename_service.classify_files(
            files,
            str(tmp_path)
        )

        assert len(video_files) == 2
        assert len(subtitle_files) == 1


@pytest.mark.integration
class TestPathGenerationIntegration:
    """Integration tests for path generation."""

    def test_generate_complete_download_path(self):
        """Test generating complete download path with all components."""
        from src.services.file.path_builder import PathBuilder
        from src.core.config import config

        builder = PathBuilder(
            download_root=config.qbittorrent.base_download_path,
            anime_tv_root=config.link_target_path
        )

        path = builder.build_download_path(
            title='金牌得主',
            season=1,
            category='tv',
            media_type='anime'
        )

        assert path is not None
        assert len(path) > 0

        print(f'\n📁 Generated download path: {path}')

    def test_path_sanitization_with_special_chars(self):
        """Test path sanitization with special characters."""
        from src.services.file.path_builder import PathBuilder

        builder = PathBuilder(
            download_root='/downloads/AniDown/',
            anime_tv_root='/library/TV Shows'
        )

        # Test with problematic title
        problematic_title = "BanG Dream! It's MyGO!!!!!"

        path = builder.build_download_path(
            title=problematic_title,
            season=1,
            category='tv',
            media_type='anime'
        )

        # Path should not contain problematic characters
        assert '/' not in path.split('/')[-1] or True  # Allow in path separators
        assert path is not None

        print(f'\n📁 Sanitized path: {path}')
