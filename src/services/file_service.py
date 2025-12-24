"""
File service module.

Provides file operations including hardlink creation, deletion, and renaming.
This is a compatibility layer for the web controllers.
"""

import logging
import os
import shutil
from typing import Optional

from src.core.config import config
from src.infrastructure.repositories.history_repository import HistoryRepository
from src.infrastructure.database.session import db_manager
from src.infrastructure.database.models import Hardlink

logger = logging.getLogger(__name__)


class FileService:
    """
    文件操作服务。

    提供硬链接创建、删除和重命名功能。
    """

    def __init__(self, history_repo: HistoryRepository):
        """
        初始化文件服务。

        Args:
            history_repo: 历史记录仓储。
        """
        self._history_repo = history_repo

    def create_hardlink(
        self,
        source_path: str,
        target_path: str,
        anime_id: Optional[int] = None,
        torrent_hash: Optional[str] = None
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
            logger.debug(f'🔗 准备创建硬链接...')
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
                logger.info(f'✅ 硬链接创建成功')
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
                logger.info(f'✅ 文件复制成功')
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

    def rename_hardlink(self, hardlink_id: int, new_name: str) -> Optional[str]:
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
