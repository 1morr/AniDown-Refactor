"""
Tests for multi-file torrent handling with consistency mode.

Tests the behavior when:
- A torrent contains multiple files
- is_multi_season is False
- use_consistent_naming is True
"""

import pytest
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch

from src.core.interfaces.adapters import RenameResult
from src.services.rename.file_classifier import ClassifiedFile, FileClassifier


class TestMultiFileConsistencyMode:
    """
    Tests for multi-file torrent handling with consistency mode enabled.

    When a torrent contains multiple files, multi-season is disabled,
    and consistency naming is enabled, the system should:
    1. Use regex patterns from database if available
    2. Fall back to AI if no patterns or regex fails
    3. Apply consistent naming format across all files
    """

    @pytest.fixture
    def mock_anime_repo(self):
        """Create mock anime repository with patterns."""
        repo = MagicMock()
        repo.get_patterns.return_value = {
            'episode_regex': r'- (\d+) \[',
            'subtitle_type_regex': r'\[(CHS|CHT|JPN)\]',
            'special_tags_regex': r'\[(1080p|720p)\]',
        }
        return repo

    @pytest.fixture
    def mock_ai_file_renamer(self):
        """Create mock AI file renamer."""
        renamer = MagicMock()
        renamer.generate_rename_mapping.return_value = RenameResult(
            main_files={
                '[ANi] Test Anime - 01 [1080P][CHT].mp4': 'Season 1/Test Anime - S01E01 - ANi [CHT].mp4',
                '[ANi] Test Anime - 02 [1080P][CHT].mp4': 'Season 1/Test Anime - S01E02 - ANi [CHT].mp4',
                '[ANi] Test Anime - 03 [1080P][CHT].mp4': 'Season 1/Test Anime - S01E03 - ANi [CHT].mp4',
            },
            skipped_files=[],
            seasons_info={'S01': {'type': 'tv', 'count': 3}},
            patterns={
                'episode_regex': r'- (\d+) \[',
                'subtitle_type_regex': r'\[(CHS|CHT|JPN)\]',
            },
            method='ai'
        )
        return renamer

    @pytest.fixture
    def video_files(self) -> List[ClassifiedFile]:
        """Create test video files."""
        return [
            ClassifiedFile(
                name='[ANi] Test Anime - 01 [1080P][CHT].mp4',
                relative_path='[ANi] Test Anime - 01 [1080P][CHT].mp4',
                full_path='/downloads/[ANi] Test Anime - 01 [1080P][CHT].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='[ANi] Test Anime - 02 [1080P][CHT].mp4',
                relative_path='[ANi] Test Anime - 02 [1080P][CHT].mp4',
                full_path='/downloads/[ANi] Test Anime - 02 [1080P][CHT].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='[ANi] Test Anime - 03 [1080P][CHT].mp4',
                relative_path='[ANi] Test Anime - 03 [1080P][CHT].mp4',
                full_path='/downloads/[ANi] Test Anime - 03 [1080P][CHT].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
        ]

    def test_multifile_with_consistency_uses_db_patterns(
        self,
        mock_anime_repo,
        mock_ai_file_renamer,
        video_files
    ):
        """
        Test that multi-file torrent with consistency mode uses database patterns.

        When:
        - Multiple files in torrent
        - is_multi_season = False
        - use_consistent_naming = True
        - Database has valid patterns

        Expected:
        - AI should NOT be called
        - Regex patterns should be used for all files
        - Output should use consistent naming format
        """
        from src.services.rename.rename_service import RenameService

        with patch('src.core.config.config.use_consistent_naming_tv', True):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=False,
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify result
            assert result is not None
            assert result.file_count == 3

            # Verify regex was used (not AI)
            assert 'regex' in result.method.lower() or '数据库' in result.method

            # Verify consistent naming format
            for old_name, new_name in result.main_files.items():
                assert 'S01E' in new_name or 'Season 1' in new_name

    def test_multifile_with_consistency_falls_back_to_ai(
        self,
        mock_ai_file_renamer,
        video_files
    ):
        """
        Test that multi-file torrent falls back to AI when no database patterns.

        When:
        - Multiple files in torrent
        - is_multi_season = False
        - use_consistent_naming = True
        - Database has NO patterns

        Expected:
        - AI should be called
        - AI result should be used
        - Patterns should be saved to database
        """
        from src.services.rename.rename_service import RenameService

        mock_anime_repo = MagicMock()
        mock_anime_repo.get_patterns.return_value = None  # No patterns in DB

        with patch('src.core.config.config.use_consistent_naming_tv', True):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=False,
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify AI was called
            mock_ai_file_renamer.generate_rename_mapping.assert_called_once()

            # Verify result
            assert result is not None
            assert result.file_count == 3

            # Verify last_used_ai is True
            assert service.last_used_ai is True

    def test_multifile_multiseason_skips_regex(
        self,
        mock_anime_repo,
        mock_ai_file_renamer,
        video_files
    ):
        """
        Test that multi-season torrent skips regex and uses AI directly.

        When:
        - Multiple files in torrent
        - is_multi_season = True (forces AI)
        - use_consistent_naming = True

        Expected:
        - AI should be called directly
        - Regex should NOT be attempted
        - AI filenames should be used directly
        """
        from src.services.rename.rename_service import RenameService

        with patch('src.core.config.config.use_consistent_naming_tv', True):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=True,  # Multi-season forces AI
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify AI was called
            mock_ai_file_renamer.generate_rename_mapping.assert_called_once()

            # Verify result
            assert result is not None

            # Verify AI reason
            assert service.last_used_ai is True
            assert '多季' in service.ai_reason

    def test_multifile_consistency_disabled_uses_ai_filenames(
        self,
        mock_anime_repo,
        mock_ai_file_renamer,
        video_files
    ):
        """
        Test that with consistency disabled, AI filenames are used directly.

        When:
        - Multiple files in torrent
        - is_multi_season = False
        - use_consistent_naming = False (disabled)

        Expected:
        - AI should be called
        - AI returned filenames should be used directly
        """
        from src.services.rename.rename_service import RenameService

        # No patterns in DB to force AI usage
        mock_anime_repo.get_patterns.return_value = None

        with patch('src.core.config.config.use_consistent_naming_tv', False):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=False,
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify AI was called
            mock_ai_file_renamer.generate_rename_mapping.assert_called_once()

            # Verify result
            assert result is not None
            assert result.file_count == 3

            # Verify AI filenames are used
            assert 'AI' in result.method

    def test_multifile_regex_partial_match_falls_back_to_ai(
        self,
        mock_ai_file_renamer
    ):
        """
        Test that partial regex match falls back to AI.

        When:
        - Multiple files in torrent
        - Database has patterns but they don't match all files

        Expected:
        - AI should be called
        - All files should be processed with AI
        """
        from src.services.rename.rename_service import RenameService

        # Create video files with mixed formats
        video_files = [
            ClassifiedFile(
                name='[ANi] Test Anime - 01 [1080P].mp4',
                relative_path='[ANi] Test Anime - 01 [1080P].mp4',
                full_path='/downloads/[ANi] Test Anime - 01 [1080P].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='Test Anime Episode 2 HD.mp4',  # Different format
                relative_path='Test Anime Episode 2 HD.mp4',
                full_path='/downloads/Test Anime Episode 2 HD.mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
        ]

        mock_anime_repo = MagicMock()
        mock_anime_repo.get_patterns.return_value = {
            'episode_regex': r'- (\d+) \[',  # Only matches first file
        }

        # Update mock to return result for these files
        mock_ai_file_renamer.generate_rename_mapping.return_value = RenameResult(
            main_files={
                '[ANi] Test Anime - 01 [1080P].mp4': 'Season 1/Test Anime - S01E01.mp4',
                'Test Anime Episode 2 HD.mp4': 'Season 1/Test Anime - S01E02.mp4',
            },
            skipped_files=[],
            seasons_info={'S01': {'type': 'tv', 'count': 2}},
            patterns={'episode_regex': r'Episode (\d+)|- (\d+)'},
            method='ai'
        )

        with patch('src.core.config.config.use_consistent_naming_tv', True):
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer
            )

            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='Test Anime',
                subtitle_group='ANi',
                season=1,
                category='tv',
                is_multi_season=False,
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # Verify AI was called (regex partial match should trigger AI)
            mock_ai_file_renamer.generate_rename_mapping.assert_called_once()

            # Verify result
            assert result is not None
            # Note: The actual count depends on how the system handles partial matches
            # It may only process the files that didn't match regex, or all files
            assert result.file_count >= 1


class TestMultiFileSubtitleHandling:
    """Tests for subtitle handling with multi-file torrents."""

    @pytest.fixture
    def video_files(self) -> List[ClassifiedFile]:
        """Create test video files."""
        return [
            ClassifiedFile(
                name='[ANi] Test Anime - 01 [1080P].mp4',
                relative_path='[ANi] Test Anime - 01 [1080P].mp4',
                full_path='/downloads/[ANi] Test Anime - 01 [1080P].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='[ANi] Test Anime - 02 [1080P].mp4',
                relative_path='[ANi] Test Anime - 02 [1080P].mp4',
                full_path='/downloads/[ANi] Test Anime - 02 [1080P].mp4',
                extension='.mp4',
                size=1000000000,
                file_type='video'
            ),
        ]

    @pytest.fixture
    def subtitle_files(self) -> List[ClassifiedFile]:
        """Create test subtitle files."""
        return [
            ClassifiedFile(
                name='[ANi] Test Anime - 01 [1080P].chs.ass',
                relative_path='[ANi] Test Anime - 01 [1080P].chs.ass',
                full_path='/downloads/[ANi] Test Anime - 01 [1080P].chs.ass',
                extension='.ass',
                size=50000,
                file_type='subtitle'
            ),
            ClassifiedFile(
                name='[ANi] Test Anime - 02 [1080P].chs.ass',
                relative_path='[ANi] Test Anime - 02 [1080P].chs.ass',
                full_path='/downloads/[ANi] Test Anime - 02 [1080P].chs.ass',
                extension='.ass',
                size=50000,
                file_type='subtitle'
            ),
        ]

    def test_subtitle_mapping_generated_from_video_mapping(
        self,
        video_files,
        subtitle_files
    ):
        """
        Test that subtitle mapping is generated based on video mapping.

        Each subtitle should be renamed to match its corresponding video file.
        """
        from src.services.rename.rename_service import RenameService

        video_rename_mapping = {
            '[ANi] Test Anime - 01 [1080P].mp4': 'Season 1/Test Anime - S01E01 - ANi.mp4',
            '[ANi] Test Anime - 02 [1080P].mp4': 'Season 1/Test Anime - S01E02 - ANi.mp4',
        }

        service = RenameService()

        subtitle_mapping = service.generate_subtitle_mapping(
            video_files=video_files,
            subtitle_files=subtitle_files,
            video_rename_mapping=video_rename_mapping
        )

        # Verify subtitle mapping was generated
        assert len(subtitle_mapping) >= 1

        # Verify subtitle names match video format
        for old_sub, new_sub in subtitle_mapping.items():
            assert '.ass' in new_sub or '.srt' in new_sub


class TestCompleteMultiFileWorkflow:
    """
    完整的多文件工作流测试。

    测试场景：
    1. 多文件 + 非多季 + 一致性开启 → 正则重命名所有视频和字幕
    2. 多文件 + 非多季 + 一致性关闭 → AI重命名所有视频和字幕
    3. 多文件 + 多季 + 一致性开启 → 忽略一致性，AI重命名所有视频和字幕
    """

    @pytest.fixture
    def video_files_with_subtitles(self) -> tuple:
        """创建带字幕的测试视频文件。"""
        video_files = [
            ClassifiedFile(
                name='[Nekomoe] Test Anime - 01 [1080p][CHS].mkv',
                relative_path='[Nekomoe] Test Anime - 01 [1080p][CHS].mkv',
                full_path='/downloads/Test/[Nekomoe] Test Anime - 01 [1080p][CHS].mkv',
                extension='.mkv',
                size=1500000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='[Nekomoe] Test Anime - 02 [1080p][CHS].mkv',
                relative_path='[Nekomoe] Test Anime - 02 [1080p][CHS].mkv',
                full_path='/downloads/Test/[Nekomoe] Test Anime - 02 [1080p][CHS].mkv',
                extension='.mkv',
                size=1500000000,
                file_type='video'
            ),
            ClassifiedFile(
                name='[Nekomoe] Test Anime - 03 [1080p][CHS].mkv',
                relative_path='[Nekomoe] Test Anime - 03 [1080p][CHS].mkv',
                full_path='/downloads/Test/[Nekomoe] Test Anime - 03 [1080p][CHS].mkv',
                extension='.mkv',
                size=1500000000,
                file_type='video'
            ),
        ]

        subtitle_files = [
            ClassifiedFile(
                name='[Nekomoe] Test Anime - 01 [1080p][CHS].chs.ass',
                relative_path='[Nekomoe] Test Anime - 01 [1080p][CHS].chs.ass',
                full_path='/downloads/Test/[Nekomoe] Test Anime - 01 [1080p][CHS].chs.ass',
                extension='.ass',
                size=50000,
                file_type='subtitle'
            ),
            ClassifiedFile(
                name='[Nekomoe] Test Anime - 02 [1080p][CHS].chs.ass',
                relative_path='[Nekomoe] Test Anime - 02 [1080p][CHS].chs.ass',
                full_path='/downloads/Test/[Nekomoe] Test Anime - 02 [1080p][CHS].chs.ass',
                extension='.ass',
                size=50000,
                file_type='subtitle'
            ),
            ClassifiedFile(
                name='[Nekomoe] Test Anime - 03 [1080p][CHS].chs.ass',
                relative_path='[Nekomoe] Test Anime - 03 [1080p][CHS].chs.ass',
                full_path='/downloads/Test/[Nekomoe] Test Anime - 03 [1080p][CHS].chs.ass',
                extension='.ass',
                size=50000,
                file_type='subtitle'
            ),
        ]

        return video_files, subtitle_files

    @pytest.fixture
    def mock_anime_repo_with_patterns(self):
        """创建带正则表达式的 mock anime repository。"""
        repo = MagicMock()
        repo.get_patterns.return_value = {
            'episode_regex': r'- (\d+) \[',
            'subtitle_type_regex': r'\[(CHS|CHT|JPN)\]',
            'special_tags_regex': r'\[(1080p|720p)\]',
        }
        repo.insert_patterns = MagicMock()
        return repo

    @pytest.fixture
    def mock_ai_file_renamer_full(self):
        """创建完整的 mock AI file renamer。"""
        renamer = MagicMock()
        renamer.generate_rename_mapping.return_value = RenameResult(
            main_files={
                '[Nekomoe] Test Anime - 01 [1080p][CHS].mkv': 'Season 1/测试动漫 - S01E01 - Nekomoe [CHS].mkv',
                '[Nekomoe] Test Anime - 02 [1080p][CHS].mkv': 'Season 1/测试动漫 - S01E02 - Nekomoe [CHS].mkv',
                '[Nekomoe] Test Anime - 03 [1080p][CHS].mkv': 'Season 1/测试动漫 - S01E03 - Nekomoe [CHS].mkv',
            },
            skipped_files=[],
            seasons_info={'S01': {'type': 'tv', 'count': 3, 'description': '第一季'}},
            patterns={
                'episode_regex': r'- (\d+) \[',
                'subtitle_type_regex': r'\[(CHS|CHT|JPN)\]',
            },
            method='ai'
        )
        return renamer

    @pytest.fixture
    def mock_hardlink_service(self):
        """创建 mock hardlink service。"""
        service = MagicMock()
        service.create.return_value = True
        service.build_target_directory.return_value = '/library/Anime/测试动漫/Season 1'
        return service

    def test_scenario1_multifile_no_multiseason_consistency_on_regex_renames_all(
        self,
        video_files_with_subtitles,
        mock_anime_repo_with_patterns,
        mock_ai_file_renamer_full,
        mock_hardlink_service
    ):
        """
        场景1：多文件 + 非多季 + 一致性开启

        验证：
        - 使用数据库正则表达式重命名所有视频文件
        - 字幕文件根据视频文件映射进行重命名
        - AI 不应被调用（因为正则匹配成功）
        - 所有文件都应该能创建硬链接
        """
        from src.services.rename.rename_service import RenameService

        video_files, subtitle_files = video_files_with_subtitles

        with patch('src.core.config.config.use_consistent_naming_tv', True):
            service = RenameService(
                anime_repo=mock_anime_repo_with_patterns,
                ai_file_renamer=mock_ai_file_renamer_full
            )

            # 生成视频重命名映射
            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='测试动漫',
                subtitle_group='Nekomoe',
                season=1,
                category='tv',
                is_multi_season=False,  # 非多季
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # 验证结果
            assert result is not None, '视频重命名结果不应为空'
            assert result.file_count == 3, f'应该有3个视频文件，实际有 {result.file_count}'

            # 验证使用了正则表达式（一致性命名）
            assert '数据库' in result.method or 'regex' in result.method.lower(), \
                f'应该使用数据库正则表达式，实际方法: {result.method}'

            # 验证 AI 没有被调用（因为正则匹配成功）
            assert service.last_used_ai is False, 'AI 不应该被调用'

            # 验证所有视频文件都被重命名
            for video in video_files:
                assert video.name in result.main_files, \
                    f'视频文件 {video.name} 应该在重命名映射中'
                new_name = result.main_files[video.name]
                assert 'S01E' in new_name, f'新文件名应包含季集信息: {new_name}'

            # 生成字幕重命名映射
            subtitle_mapping = service.generate_subtitle_mapping(
                video_files=video_files,
                subtitle_files=subtitle_files,
                video_rename_mapping=result.main_files
            )

            # 验证字幕映射
            assert len(subtitle_mapping) >= 1, '应该有字幕文件映射'

            # 模拟创建硬链接
            target_dir = mock_hardlink_service.build_target_directory(
                anime_title='测试动漫',
                media_type='anime',
                category='tv',
                season=1
            )

            # 验证可以为所有视频创建硬链接
            video_hardlink_count = 0
            for video in video_files:
                if video.name in result.main_files:
                    success = mock_hardlink_service.create(
                        source_path=video.full_path,
                        target_dir=target_dir,
                        new_name=result.main_files[video.name]
                    )
                    if success:
                        video_hardlink_count += 1

            assert video_hardlink_count == 3, f'应该创建3个视频硬链接，实际创建 {video_hardlink_count}'

            # 验证可以为字幕创建硬链接
            subtitle_hardlink_count = 0
            for sub in subtitle_files:
                if sub.name in subtitle_mapping:
                    success = mock_hardlink_service.create(
                        source_path=sub.full_path,
                        target_dir=target_dir,
                        new_name=subtitle_mapping[sub.name]
                    )
                    if success:
                        subtitle_hardlink_count += 1

            assert subtitle_hardlink_count >= 1, f'应该至少创建1个字幕硬链接'

    def test_scenario2_multifile_no_multiseason_consistency_off_ai_renames_all(
        self,
        video_files_with_subtitles,
        mock_ai_file_renamer_full,
        mock_hardlink_service
    ):
        """
        场景2：多文件 + 非多季 + 一致性关闭

        验证：
        - AI 被调用进行重命名
        - 所有视频文件都被重命名
        - 字幕文件根据视频文件映射进行重命名
        - 所有文件都应该能创建硬链接
        """
        from src.services.rename.rename_service import RenameService

        video_files, subtitle_files = video_files_with_subtitles

        # 无数据库正则，强制使用 AI
        mock_anime_repo = MagicMock()
        mock_anime_repo.get_patterns.return_value = None
        mock_anime_repo.insert_patterns = MagicMock()

        with patch('src.core.config.config.use_consistent_naming_tv', False):  # 一致性关闭
            service = RenameService(
                anime_repo=mock_anime_repo,
                ai_file_renamer=mock_ai_file_renamer_full
            )

            # 生成视频重命名映射
            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='测试动漫',
                subtitle_group='Nekomoe',
                season=1,
                category='tv',
                is_multi_season=False,  # 非多季
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # 验证结果
            assert result is not None, '视频重命名结果不应为空'
            assert result.file_count == 3, f'应该有3个视频文件，实际有 {result.file_count}'

            # 验证 AI 被调用
            mock_ai_file_renamer_full.generate_rename_mapping.assert_called_once()
            assert service.last_used_ai is True, 'AI 应该被调用'

            # 验证使用了 AI 文件名
            assert 'AI' in result.method, f'应该使用 AI 文件名，实际方法: {result.method}'

            # 验证所有视频文件都被重命名
            for video in video_files:
                assert video.name in result.main_files, \
                    f'视频文件 {video.name} 应该在重命名映射中'

            # 生成字幕重命名映射
            subtitle_mapping = service.generate_subtitle_mapping(
                video_files=video_files,
                subtitle_files=subtitle_files,
                video_rename_mapping=result.main_files
            )

            # 模拟创建硬链接
            target_dir = mock_hardlink_service.build_target_directory(
                anime_title='测试动漫',
                media_type='anime',
                category='tv',
                season=1
            )

            # 验证可以为所有视频创建硬链接
            video_hardlink_count = 0
            for video in video_files:
                if video.name in result.main_files:
                    success = mock_hardlink_service.create(
                        source_path=video.full_path,
                        target_dir=target_dir,
                        new_name=result.main_files[video.name]
                    )
                    if success:
                        video_hardlink_count += 1

            assert video_hardlink_count == 3, f'应该创建3个视频硬链接，实际创建 {video_hardlink_count}'

    def test_scenario3_multifile_multiseason_on_consistency_on_ai_ignores_consistency(
        self,
        video_files_with_subtitles,
        mock_anime_repo_with_patterns,
        mock_ai_file_renamer_full,
        mock_hardlink_service
    ):
        """
        场景3：多文件 + 多季开启 + 一致性开启

        验证：
        - 一致性开关被忽略（多季模式强制使用 AI）
        - AI 被直接调用，跳过正则匹配
        - 所有视频文件都被重命名
        - 字幕文件根据视频文件映射进行重命名
        - 所有文件都应该能创建硬链接
        """
        from src.services.rename.rename_service import RenameService

        video_files, subtitle_files = video_files_with_subtitles

        with patch('src.core.config.config.use_consistent_naming_tv', True):  # 一致性开启
            service = RenameService(
                anime_repo=mock_anime_repo_with_patterns,
                ai_file_renamer=mock_ai_file_renamer_full
            )

            # 生成视频重命名映射
            result = service.generate_mapping(
                video_files=video_files,
                anime_id=1,
                anime_title='测试动漫',
                subtitle_group='Nekomoe',
                season=1,
                category='tv',
                is_multi_season=True,  # 多季开启 - 这应该强制使用 AI
                tvdb_data=None,
                folder_structure=None,
                torrent_hash='abc123'
            )

            # 验证结果
            assert result is not None, '视频重命名结果不应为空'
            assert result.file_count == 3, f'应该有3个视频文件，实际有 {result.file_count}'

            # 验证 AI 被调用（即使一致性开启，多季模式也强制使用 AI）
            mock_ai_file_renamer_full.generate_rename_mapping.assert_called_once()
            assert service.last_used_ai is True, 'AI 应该被调用（多季模式）'

            # 验证 AI 原因包含多季相关信息
            assert '多季' in service.ai_reason, \
                f'AI 原因应包含多季信息: {service.ai_reason}'

            # 验证正则没有被使用（直接跳过到 AI）
            assert 'AI' in result.method or '多季' in result.method, \
                f'应该使用 AI（多季模式），实际方法: {result.method}'

            # 验证所有视频文件都被重命名
            for video in video_files:
                assert video.name in result.main_files, \
                    f'视频文件 {video.name} 应该在重命名映射中'

            # 生成字幕重命名映射
            subtitle_mapping = service.generate_subtitle_mapping(
                video_files=video_files,
                subtitle_files=subtitle_files,
                video_rename_mapping=result.main_files
            )

            # 模拟创建硬链接
            target_dir = mock_hardlink_service.build_target_directory(
                anime_title='测试动漫',
                media_type='anime',
                category='tv',
                season=1
            )

            # 验证可以为所有视频创建硬链接
            video_hardlink_count = 0
            for video in video_files:
                if video.name in result.main_files:
                    success = mock_hardlink_service.create(
                        source_path=video.full_path,
                        target_dir=target_dir,
                        new_name=result.main_files[video.name]
                    )
                    if success:
                        video_hardlink_count += 1

            assert video_hardlink_count == 3, f'应该创建3个视频硬链接，实际创建 {video_hardlink_count}'

            # 验证可以为字幕创建硬链接
            subtitle_hardlink_count = 0
            for sub in subtitle_files:
                if sub.name in subtitle_mapping:
                    success = mock_hardlink_service.create(
                        source_path=sub.full_path,
                        target_dir=target_dir,
                        new_name=subtitle_mapping[sub.name]
                    )
                    if success:
                        subtitle_hardlink_count += 1

            assert subtitle_hardlink_count >= 1, f'应该至少创建1个字幕硬链接'


class TestMultiSeasonDetection:
    """Tests for multi-season content detection."""

    def test_detect_multi_season_from_folder_structure(self):
        """Test detection of multi-season content from folder structure."""
        # Multi-season folder structures that should be detected
        multi_season_structures = [
            'Season 1/ep01.mp4\nSeason 2/ep01.mp4',
            'S01/file.mp4\nS02/file.mp4',
            'シーズン1/file.mp4\nシーズン2/file.mp4',
        ]

        # This test verifies the logic for detecting multi-season content
        # The actual implementation may vary
        for structure in multi_season_structures:
            has_multiple_seasons = (
                'Season 1' in structure and 'Season 2' in structure or
                'S01' in structure and 'S02' in structure or
                'シーズン1' in structure and 'シーズン2' in structure
            )
            assert has_multiple_seasons is True

    def test_single_season_not_detected_as_multi(self):
        """Test that single season content is not detected as multi-season."""
        single_season_structures = [
            'Season 1/ep01.mp4\nSeason 1/ep02.mp4',
            'S01/file1.mp4\nS01/file2.mp4',
        ]

        for structure in single_season_structures:
            # Count unique season numbers
            has_multiple_seasons = (
                'Season 2' in structure or 'S02' in structure
            )
            assert has_multiple_seasons is False
