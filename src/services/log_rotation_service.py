"""
Log rotation service module.

Provides log file rotation and cleanup functionality.
"""

import glob
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class LogRotationService:
    """
    Log rotation service.

    Handles automatic log file rotation and cleanup based on age.
    """

    DEFAULT_MAX_DAYS = 5

    def __init__(
        self,
        log_file: str = 'anidown.log',
        max_days: int = DEFAULT_MAX_DAYS
    ):
        """
        Initialize the log rotation service.

        Args:
            log_file: Path to the main log file.
            max_days: Maximum number of days to keep old logs.
        """
        self._log_file = log_file
        self._max_days = max_days
        self._log_dir = os.path.dirname(log_file) or '.'
        self._log_name = os.path.basename(log_file)
        self._log_base = os.path.splitext(self._log_name)[0]

    @property
    def log_file(self) -> str:
        """Get the main log file path."""
        return self._log_file

    @property
    def max_days(self) -> int:
        """Get the maximum days to keep logs."""
        return self._max_days

    def rotate_log(self) -> str | None:
        """
        Rotate the current log file.

        Renames the log file with today's date suffix.

        Returns:
            Path to the rotated file if successful, None otherwise.
        """
        if not os.path.exists(self._log_file):
            return None

        # Generate dated filename
        today = datetime.now().strftime('%Y-%m-%d')
        rotated_name = f'{self._log_base}_{today}.log'
        rotated_path = os.path.join(self._log_dir, rotated_name)

        # Skip if today's log already exists
        if os.path.exists(rotated_path):
            return None

        # Rename current log file
        try:
            os.rename(self._log_file, rotated_path)
            logger.info(f'🔄 日志已轮转: {rotated_path}')
            return rotated_path
        except OSError as e:
            # File might be in use
            logger.debug(f'无法轮转日志文件: {e}')
            return None

    def cleanup_old_logs(self) -> int:
        """
        Clean up old log files.

        Removes log files older than max_days.

        Returns:
            Number of files deleted.
        """
        pattern = os.path.join(self._log_dir, f'{self._log_base}_*.log')
        log_files = glob.glob(pattern)

        cutoff_date = datetime.now() - timedelta(days=self._max_days)
        deleted_count = 0

        for log_file in log_files:
            try:
                # Extract date from filename
                basename = os.path.basename(log_file)
                date_str = basename.replace(f'{self._log_base}_', '').replace('.log', '')
                file_date = datetime.strptime(date_str, '%Y-%m-%d')

                if file_date < cutoff_date:
                    os.remove(log_file)
                    deleted_count += 1
                    logger.debug(f'🗑️ 已删除旧日志: {basename}')

            except (ValueError, OSError):
                # Skip files that can't be parsed or deleted
                continue

        if deleted_count > 0:
            logger.info(f'🧹 清理了 {deleted_count} 个旧日志文件')

        return deleted_count

    def setup_rotation(self) -> None:
        """
        Set up log rotation.

        Rotates current log and cleans up old ones.
        """
        self.rotate_log()
        self.cleanup_old_logs()

    def get_log_files(self) -> list[str]:
        """
        Get list of all log files.

        Returns:
            List of log file paths sorted by date (newest first).
        """
        pattern = os.path.join(self._log_dir, f'{self._log_base}_*.log')
        log_files = glob.glob(pattern)

        # Add current log if it exists
        if os.path.exists(self._log_file):
            log_files.append(self._log_file)

        # Sort by modification time
        return sorted(log_files, key=os.path.getmtime, reverse=True)

    def get_log_size_mb(self) -> float:
        """
        Get total size of all log files in MB.

        Returns:
            Total size in megabytes.
        """
        total_size = 0
        for log_file in self.get_log_files():
            try:
                total_size += os.path.getsize(log_file)
            except OSError:
                continue

        return total_size / (1024 * 1024)


# Global log rotation service instance
_log_rotation_service: LogRotationService | None = None


def get_log_rotation_service(
    log_file: str = 'anidown.log'
) -> LogRotationService:
    """
    Get the global log rotation service instance.

    Args:
        log_file: Path to the main log file.

    Returns:
        LogRotationService instance.
    """
    global _log_rotation_service
    if _log_rotation_service is None:
        _log_rotation_service = LogRotationService(log_file)
    return _log_rotation_service
