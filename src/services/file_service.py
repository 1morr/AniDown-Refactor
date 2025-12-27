"""
File service module.

Provides file operations including hardlink creation, deletion, and renaming.
Consolidated from FileService and HardlinkService for unified file management.
"""

import logging
import os
import shutil
from datetime import UTC, datetime
from typing import Any

from src.core.config import config
from src.core.domain.entities import HardlinkRecord
from src.core.exceptions import HardlinkError
from src.core.interfaces.repositories import IHardlinkRepository
from src.infrastructure.database.models import Hardlink
from src.infrastructure.database.session import db_manager
from src.services.file.path_builder import PathBuilder

logger = logging.getLogger(__name__)


class FileService:
    """
    文件操作服务。

    提供硬链接创建、删除和重命名功能。
    整合了原 HardlinkService 的所有功能。
    """

    def __init__(
        self,
        history_repo: IHardlinkRepository,
        path_builder: PathBuilder | None = None
    ):
        """
        初始化文件服务。

        Args:
            history_repo: 历史记录仓储（同时用作硬链接仓储）。
            path_builder: 路径构建器（可选，用于构建目标目录）。
        """
        self._history_repo = history_repo
        self._path_builder = path_builder

    # =========================================================================
    # Methods from original FileService
    # =========================================================================

    def create_hardlink(
        self,
        source_path: str,
        target_path: str,
        anime_id: int | None = None,
        torrent_hash: str | None = None
    ) -> bool:
        """
        创建硬链接。

        如果硬链接创建失败（例如跨文件系统），会降级为文件复制。

        Args:
            source_path: 源文件路径。
            target_path: 目标文件路径。
            anime_id: 关联的动漫ID。
            torrent_hash: 关联的种子哈希。

        Returns:
            是否成功创建硬链接或复制文件。
        """
        try:
            logger.debug('🔗 准备创建硬链接...')
            logger.debug(f'  源文件: {source_path}')
            logger.debug(f'  目标文件: {target_path}')

            # 确保目标目录存在
            target_dir = os.path.dirname(target_path)
            os.makedirs(target_dir, exist_ok=True)

            # 如果目标文件已存在，先删除
            if os.path.exists(target_path):
                logger.warning(f'目标文件已存在，将被覆盖: {target_path}')
                os.remove(target_path)

            # 尝试创建硬链接
            try:
                os.link(source_path, target_path)
                file_size = os.path.getsize(source_path)
                logger.info('✅ 硬链接创建成功')
                logger.debug(f'  文件大小: {file_size / (1024*1024):.2f} MB')

                # 记录成功
                self._history_repo.insert_hardlink(
                    original_file_path=source_path,
                    hardlink_path=target_path,
                    file_size=file_size,
                    anime_id=anime_id,
                    torrent_hash=torrent_hash
                )

                self._history_repo.insert_hardlink_attempt(
                    original_file_path=source_path,
                    target_path=target_path,
                    success=True,
                    anime_id=anime_id,
                    torrent_hash=torrent_hash,
                    file_size=file_size,
                    link_method='hardlink'
                )
                return True

            except OSError as e:
                # 如果硬链接失败（例如跨文件系统），尝试复制
                logger.warning(f'⚠️ 硬链接失败 ({e})，降级为文件复制')
                logger.debug(f'  正在复制: {source_path} -> {target_path}')
                shutil.copy2(source_path, target_path)
                file_size = os.path.getsize(source_path)
                logger.info('✅ 文件复制成功')
                logger.debug(f'  文件大小: {file_size / (1024*1024):.2f} MB')

                # 记录尝试（虽然是复制，但也算成功完成了文件转移）
                self._history_repo.insert_hardlink_attempt(
                    original_file_path=source_path,
                    target_path=target_path,
                    success=True,
                    anime_id=anime_id,
                    torrent_hash=torrent_hash,
                    file_size=file_size,
                    link_method='copy'
                )
                return True

        except Exception as e:
            logger.error(f'文件操作失败: {e}')

            # 记录失败
            self._history_repo.insert_hardlink_attempt(
                original_file_path=source_path,
                target_path=target_path,
                success=False,
                anime_id=anime_id,
                torrent_hash=torrent_hash,
                failure_reason=str(e)
            )
            return False

    def delete_hardlink(self, hardlink_id: int) -> bool:
        """
        删除硬链接。

        Args:
            hardlink_id: 硬链接记录ID。

        Returns:
            是否成功删除。
        """
        try:
            with db_manager.session() as session:
                hardlink = session.query(Hardlink).filter_by(id=hardlink_id).first()
                if not hardlink:
                    logger.warning(f'硬链接记录不存在: {hardlink_id}')
                    return False

                # 在 session 內讀取路徑
                hardlink_path = hardlink.hardlink_path

            # 刪除物理文件
            if os.path.exists(hardlink_path):
                try:
                    os.remove(hardlink_path)
                    logger.info(f'已删除硬链接文件: {hardlink_path}')
                except Exception as e:
                    logger.warning(f'删除硬链接文件失败: {e}')
                    # 即使文件删除失败，也尝试删除数据库记录

            # 删除数据库记录
            return self._history_repo.delete_hardlink_by_id(hardlink_id)

        except Exception as e:
            logger.error(f'删除硬链接操作失败: {e}')
            return False

    def rename_hardlink(self, hardlink_id: int, new_name: str) -> str | None:
        """
        重命名硬链接。

        Args:
            hardlink_id: 硬链接记录ID。
            new_name: 新文件名。

        Returns:
            新文件路径，如果失败则返回 None。
        """
        try:
            with db_manager.session() as session:
                hardlink = session.query(Hardlink).filter_by(id=hardlink_id).first()
                if not hardlink:
                    logger.warning(f'硬链接记录不存在: {hardlink_id}')
                    return None

                old_path = hardlink.hardlink_path
                new_path = os.path.join(os.path.dirname(old_path), new_name)

                # 重命名文件
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)
                    logger.info(f'已重命名硬链接: {old_path} -> {new_path}')

                    # 更新数据库记录
                    hardlink.hardlink_path = new_path
                    session.commit()
                    return new_path
                else:
                    logger.warning(f'硬链接文件不存在: {old_path}')
                    return None

        except Exception as e:
            logger.error(f'重命名硬链接失败: {e}')
            return None

    def convert_path(self, path: str) -> str:
        """
        路径转换（用于Docker环境）。

        将Windows路径转换为Docker容器内的POSIX路径。
        处理混合路径分隔符（如 C:\\path\\/subpath）。

        Args:
            path: 原始路径。

        Returns:
            转换后的路径（使用POSIX风格斜杠）。
        """
        if not config.path_conversion.enabled:
            return path

        source_base = config.path_conversion.source_base_path
        target_base = config.path_conversion.target_base_path

        # Normalize Windows backslashes to forward slashes for comparison
        normalized_path = path.replace('\\', '/')
        normalized_source = source_base.replace('\\', '/')

        if normalized_path.startswith(normalized_source):
            # Replace source prefix with target prefix
            converted = normalized_path.replace(normalized_source, target_base, 1)
            # Remove any double slashes (except after protocol like http://)
            while '//' in converted:
                converted = converted.replace('//', '/')
            return converted

        return path

    def delete_original_file(self, original_path: str) -> bool:
        """
        删除源文件。

        Args:
            original_path: 源文件路径。

        Returns:
            是否成功删除。
        """
        try:
            if os.path.exists(original_path):
                if os.path.isfile(original_path):
                    os.remove(original_path)
                elif os.path.isdir(original_path):
                    shutil.rmtree(original_path)
                logger.info(f'已删除源文件: {original_path}')
                return True
            else:
                logger.warning(f'源文件不存在: {original_path}')
                return False
        except Exception as e:
            logger.error(f'删除源文件失败: {e}')
            return False

    # =========================================================================
    # Methods migrated from HardlinkService
    # =========================================================================

    def create(
        self,
        source_path: str,
        target_dir: str,
        new_name: str,
        anime_id: int | None = None,
        torrent_hash: str | None = None
    ) -> bool:
        """
        Create a hardlink from source to target directory.

        Args:
            source_path: Full path to the source file.
            target_dir: Target directory for the hardlink.
            new_name: New filename for the hardlink (may include subdirectory like "Season 1/file.mkv").
            anime_id: Optional anime ID for record keeping.
            torrent_hash: Optional torrent hash for record keeping.

        Returns:
            True if successful, False otherwise.

        Raises:
            HardlinkError: If hardlink creation fails and fallback is disabled.
        """
        # Validate source exists
        if not os.path.exists(source_path):
            logger.error(f'❌ Source file does not exist: {source_path}')
            return False

        # Normalize path separators to OS-specific
        new_name = new_name.replace('/', os.sep).replace('\\', os.sep)

        # Build target path - handle subdirectory in new_name (e.g., "Season 1/file.mkv")
        target_path = os.path.join(target_dir, new_name)

        # Ensure full target directory exists (including any subdirectory in new_name)
        target_file_dir = os.path.dirname(target_path)
        if self._path_builder:
            if not self._path_builder.ensure_directory(target_file_dir):
                logger.error(f'❌ Failed to create target directory: {target_file_dir}')
                return False
        else:
            os.makedirs(target_file_dir, mode=0o775, exist_ok=True)

        # Skip if target already exists
        if os.path.exists(target_path):
            logger.warning(f'⚠️ Target already exists, skipping: {target_path}')
            return True

        # Attempt hardlink creation
        link_method = self._create_link(source_path, target_path)

        if link_method:
            # Get file size for record
            try:
                file_size = os.path.getsize(source_path)
            except OSError:
                file_size = 0

            # Save record
            record = HardlinkRecord(
                anime_id=anime_id,
                torrent_hash=torrent_hash or '',
                original_file_path=source_path,
                hardlink_path=target_path,
                file_size=file_size,
                link_method=link_method,
                created_at=datetime.now(UTC)
            )
            self._history_repo.save(record)

            logger.info(
                f'🔗 Created {link_method}: '
                f'{os.path.basename(source_path)} -> {new_name}'
            )
            return True

        return False

    def _create_link(self, source: str, target: str) -> str | None:
        """
        Create a link from source to target, using hardlink or copy fallback.

        Args:
            source: Source file path.
            target: Target link path.

        Returns:
            Link method used ('hardlink' or 'copy'), or None if failed.
        """
        # Try hardlink first
        try:
            os.link(source, target)
            return 'hardlink'
        except OSError as e:
            logger.debug(f'Hardlink failed ({e}), falling back to copy')

        # Fallback to copy
        try:
            shutil.copy2(source, target)
            return 'copy'
        except (OSError, shutil.Error) as e:
            logger.error(f'❌ Failed to copy file: {e}')
            return None

    def build_target_directory(
        self,
        anime_title: str,
        media_type: str,
        category: str,
        season: int | None = None
    ) -> str:
        """
        Build target directory for hardlink creation.

        Args:
            anime_title: Title of the anime.
            media_type: Media type ('anime' or 'live_action').
            category: Content category ('tv' or 'movie').
            season: Optional season number.

        Returns:
            Target directory path.
        """
        if not self._path_builder:
            raise HardlinkError('PathBuilder not configured for FileService')
        return self._path_builder.build_target_directory(
            anime_title=anime_title,
            media_type=media_type,
            category=category,
            season=season
        )

    def delete_by_torrent(self, torrent_hash: str, delete_files: bool = False) -> int:
        """
        Delete hardlink records for a torrent.

        Args:
            torrent_hash: Torrent hash to delete records for.
            delete_files: Whether to also delete the hardlink files.

        Returns:
            Number of records deleted.
        """
        records = self._history_repo.get_by_torrent_hash(torrent_hash)
        deleted_count = 0

        for record in records:
            try:
                # Delete file if requested
                if delete_files and record.hardlink_path:
                    if os.path.exists(record.hardlink_path):
                        os.remove(record.hardlink_path)
                        logger.debug(f'Deleted file: {record.hardlink_path}')

                # Delete record
                if record.id:
                    self._history_repo.delete(record.id)
                    deleted_count += 1
            except OSError as e:
                logger.warning(f'⚠️ Failed to delete hardlink: {e}')

        if deleted_count > 0:
            logger.info(f'🗑️ Deleted {deleted_count} hardlink records for {torrent_hash[:8]}')

        return deleted_count

    def get_stats(self, torrent_hash: str) -> dict[str, Any]:
        """
        Get statistics for hardlinks created for a torrent.

        Args:
            torrent_hash: Torrent hash to get stats for.

        Returns:
            Dictionary with hardlink statistics.
        """
        records = self._history_repo.get_by_torrent_hash(torrent_hash)

        total_size = sum(r.file_size for r in records)
        hardlink_count = sum(1 for r in records if r.is_hardlink)
        copy_count = sum(1 for r in records if r.is_copy)

        return {
            'total_files': len(records),
            'hardlinks': hardlink_count,
            'copies': copy_count,
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024) if total_size else 0
        }

    def verify_hardlink(self, record: HardlinkRecord) -> bool:
        """
        Verify that a hardlink still exists and is valid.

        Args:
            record: Hardlink record to verify.

        Returns:
            True if the hardlink exists and is valid.
        """
        if not record.hardlink_path:
            return False

        if not os.path.exists(record.hardlink_path):
            return False

        # For hardlinks, verify inode matches
        if record.is_hardlink and record.original_file_path:
            if os.path.exists(record.original_file_path):
                try:
                    source_stat = os.stat(record.original_file_path)
                    target_stat = os.stat(record.hardlink_path)
                    return source_stat.st_ino == target_stat.st_ino
                except OSError:
                    return False

        return True
