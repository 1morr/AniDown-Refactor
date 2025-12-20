"""
File classifier module.

Provides file classification functionality based on file extensions.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


# File extension categories
VIDEO_EXTENSIONS: Set[str] = {
    '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts'
}

SUBTITLE_EXTENSIONS: Set[str] = {
    '.ass', '.srt', '.sub', '.ssa', '.vtt', '.idx', '.sup'
}

AUDIO_EXTENSIONS: Set[str] = {
    '.mp3', '.flac', '.aac', '.m4a', '.ogg', '.wav', '.opus'
}

IMAGE_EXTENSIONS: Set[str] = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'
}

ARCHIVE_EXTENSIONS: Set[str] = {
    '.zip', '.rar', '.7z', '.tar', '.gz'
}

# Files to ignore
IGNORE_PATTERNS: Set[str] = {
    '.txt', '.nfo', '.url', '.html', '.xml', '.log', '.sfv', '.md5', '.sha1'
}


@dataclass
class ClassifiedFile:
    """
    Classified file data class.

    Represents a file with its classification and metadata.

    Attributes:
        name: File name without path.
        relative_path: Relative path from download root.
        full_path: Full absolute path to the file.
        extension: File extension (lowercase with dot).
        file_type: Classified type ('video', 'subtitle', 'audio', 'image', 'archive', 'other').
        size: File size in bytes.
    """
    name: str
    relative_path: str
    full_path: str
    extension: str
    file_type: str
    size: int = 0

    @property
    def is_video(self) -> bool:
        """Check if this is a video file."""
        return self.file_type == 'video'

    @property
    def is_subtitle(self) -> bool:
        """Check if this is a subtitle file."""
        return self.file_type == 'subtitle'

    @property
    def stem(self) -> str:
        """Return filename without extension."""
        if '.' in self.name:
            return self.name.rsplit('.', 1)[0]
        return self.name


@dataclass
class ClassificationResult:
    """
    File classification result.

    Contains all classified files organized by type.
    """
    video_files: List[ClassifiedFile] = field(default_factory=list)
    subtitle_files: List[ClassifiedFile] = field(default_factory=list)
    audio_files: List[ClassifiedFile] = field(default_factory=list)
    image_files: List[ClassifiedFile] = field(default_factory=list)
    archive_files: List[ClassifiedFile] = field(default_factory=list)
    other_files: List[ClassifiedFile] = field(default_factory=list)
    ignored_files: List[ClassifiedFile] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        """Return total number of non-ignored files."""
        return (
            len(self.video_files) +
            len(self.subtitle_files) +
            len(self.audio_files) +
            len(self.image_files) +
            len(self.archive_files) +
            len(self.other_files)
        )

    @property
    def has_videos(self) -> bool:
        """Check if there are any video files."""
        return len(self.video_files) > 0


class FileClassifier:
    """
    File classifier service.

    Classifies files based on their extensions into different categories.
    """

    def __init__(
        self,
        video_extensions: Set[str] = VIDEO_EXTENSIONS,
        subtitle_extensions: Set[str] = SUBTITLE_EXTENSIONS,
        audio_extensions: Set[str] = AUDIO_EXTENSIONS,
        image_extensions: Set[str] = IMAGE_EXTENSIONS,
        archive_extensions: Set[str] = ARCHIVE_EXTENSIONS,
        ignore_patterns: Set[str] = IGNORE_PATTERNS
    ):
        """
        Initialize the file classifier.

        Args:
            video_extensions: Set of video file extensions.
            subtitle_extensions: Set of subtitle file extensions.
            audio_extensions: Set of audio file extensions.
            image_extensions: Set of image file extensions.
            archive_extensions: Set of archive file extensions.
            ignore_patterns: Set of file patterns to ignore.
        """
        self._video_extensions = video_extensions
        self._subtitle_extensions = subtitle_extensions
        self._audio_extensions = audio_extensions
        self._image_extensions = image_extensions
        self._archive_extensions = archive_extensions
        self._ignore_patterns = ignore_patterns

    def classify_files(
        self,
        files: List[Dict[str, Any]],
        base_directory: str = ''
    ) -> ClassificationResult:
        """
        Classify a list of files.

        Args:
            files: List of file dictionaries with 'name' and optionally
                   'relative_path', 'full_path', 'size' keys.
            base_directory: Base directory for constructing full paths.

        Returns:
            ClassificationResult with files organized by type.
        """
        result = ClassificationResult()

        for file_info in files:
            classified = self._classify_single_file(file_info, base_directory)

            if classified.file_type == 'video':
                result.video_files.append(classified)
            elif classified.file_type == 'subtitle':
                result.subtitle_files.append(classified)
            elif classified.file_type == 'audio':
                result.audio_files.append(classified)
            elif classified.file_type == 'image':
                result.image_files.append(classified)
            elif classified.file_type == 'archive':
                result.archive_files.append(classified)
            elif classified.file_type == 'ignored':
                result.ignored_files.append(classified)
            else:
                result.other_files.append(classified)

        logger.debug(
            f'📂 Classified {result.total_files} files: '
            f'{len(result.video_files)} video, '
            f'{len(result.subtitle_files)} subtitle, '
            f'{len(result.ignored_files)} ignored'
        )

        return result

    def _classify_single_file(
        self,
        file_info: Dict[str, Any],
        base_directory: str
    ) -> ClassifiedFile:
        """
        Classify a single file.

        Args:
            file_info: File information dictionary.
            base_directory: Base directory for path construction.

        Returns:
            ClassifiedFile with type assigned.
        """
        name = file_info.get('name', '')
        relative_path = file_info.get('relative_path', name)
        full_path = file_info.get('full_path', '')
        size = file_info.get('size', 0)

        # Construct full path if not provided
        if not full_path and base_directory:
            full_path = os.path.join(base_directory, relative_path)

        # Get extension
        extension = os.path.splitext(name)[1].lower()

        # Classify by extension
        file_type = self._get_file_type(extension)

        return ClassifiedFile(
            name=name,
            relative_path=relative_path,
            full_path=full_path,
            extension=extension,
            file_type=file_type,
            size=size
        )

    def _get_file_type(self, extension: str) -> str:
        """
        Get file type based on extension.

        Args:
            extension: File extension (lowercase with dot).

        Returns:
            File type string.
        """
        if extension in self._video_extensions:
            return 'video'
        elif extension in self._subtitle_extensions:
            return 'subtitle'
        elif extension in self._audio_extensions:
            return 'audio'
        elif extension in self._image_extensions:
            return 'image'
        elif extension in self._archive_extensions:
            return 'archive'
        elif extension in self._ignore_patterns:
            return 'ignored'
        else:
            return 'other'

    def is_video(self, filename: str) -> bool:
        """Check if a filename is a video file."""
        ext = os.path.splitext(filename)[1].lower()
        return ext in self._video_extensions

    def is_subtitle(self, filename: str) -> bool:
        """Check if a filename is a subtitle file."""
        ext = os.path.splitext(filename)[1].lower()
        return ext in self._subtitle_extensions

    def should_ignore(self, filename: str) -> bool:
        """Check if a file should be ignored."""
        ext = os.path.splitext(filename)[1].lower()
        return ext in self._ignore_patterns

    def get_main_subtitle(
        self,
        video_file: ClassifiedFile,
        subtitle_files: List[ClassifiedFile]
    ) -> ClassifiedFile:
        """
        Find the main subtitle file for a video file.

        Matches based on filename stem.

        Args:
            video_file: The video file to match.
            subtitle_files: List of available subtitle files.

        Returns:
            Best matching subtitle file, or None if no match.
        """
        video_stem = video_file.stem.lower()

        # First try exact match
        for sub in subtitle_files:
            if sub.stem.lower() == video_stem:
                return sub

        # Then try partial match (video stem contained in subtitle stem)
        for sub in subtitle_files:
            if video_stem in sub.stem.lower():
                return sub

        return None
