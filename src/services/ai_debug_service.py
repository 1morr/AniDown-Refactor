"""
AI debug service module.

Provides logging and debugging functionality for AI interactions.
"""

import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


class AIDebugService:
    """
    AI debug logging service.

    Records AI interactions for debugging and analysis.
    """

    DEFAULT_DEBUG_DIR = 'ai_debug_logs'
    DEFAULT_MAX_LOGS = 5

    def __init__(
        self,
        debug_dir: Optional[str] = None,
        max_logs: int = DEFAULT_MAX_LOGS
    ):
        """
        Initialize the AI debug service.

        Args:
            debug_dir: Directory for storing debug logs.
            max_logs: Maximum number of log files to retain.
        """
        # Use environment variable or default path
        if debug_dir:
            self._debug_dir = Path(debug_dir)
        else:
            ai_log_path = os.getenv('AI_LOG_PATH', self.DEFAULT_DEBUG_DIR)
            self._debug_dir = Path(ai_log_path)

        self._max_logs = max_logs
        self._enabled = False
        self._log_files: Deque[Path] = deque(maxlen=max_logs)

    @property
    def is_enabled(self) -> bool:
        """Check if debug mode is enabled."""
        return self._enabled

    @property
    def debug_dir(self) -> Path:
        """Get the debug directory path."""
        return self._debug_dir

    def enable(self) -> None:
        """
        Enable debug mode.

        Creates debug directory if it doesn't exist.
        """
        self._enabled = True
        self._debug_dir.mkdir(exist_ok=True)
        logger.info(f'🐛 AI Debug模式已启用，日志将保存到: {self._debug_dir}')

        # Clean up old log files
        self._cleanup_old_logs()

    def disable(self) -> None:
        """Disable debug mode."""
        self._enabled = False
        logger.info('🐛 AI Debug模式已禁用')

    def log_ai_interaction(
        self,
        system_prompt: str,
        user_prompt: str,
        ai_response: Optional[Dict[str, Any]],
        model: str,
        context: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Log an AI interaction.

        Args:
            system_prompt: System prompt text.
            user_prompt: User prompt text.
            ai_response: Parsed AI response.
            model: AI model name.
            context: Additional context information.
            error: Error message if any.
        """
        if not self._enabled:
            return

        try:
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            log_file = self._debug_dir / f'ai_debug_{timestamp}.json'

            # Build log data
            log_data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'model': model,
                'system_prompt': system_prompt,
                'user_prompt': user_prompt,
                'ai_response': ai_response,
                'context': context or {},
                'error': error
            }

            # Write log file
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

            logger.info(f'🐛 AI交互已记录: {log_file.name}')

            # Add to queue and cleanup
            self._log_files.append(log_file)
            self._cleanup_old_logs()

        except Exception as e:
            logger.error(f'❌ 记录AI交互失败: {e}', exc_info=True)

    def get_latest_logs(self, count: int = 10) -> List[str]:
        """
        Get the latest log file paths.

        Args:
            count: Number of logs to retrieve.

        Returns:
            List of log file paths.
        """
        if not self._debug_dir.exists():
            return []

        log_files = sorted(
            self._debug_dir.glob('ai_debug_*.json'),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        return [str(f) for f in log_files[:count]]

    def read_log(self, log_file: str) -> Optional[Dict[str, Any]]:
        """
        Read a log file.

        Args:
            log_file: Path to the log file.

        Returns:
            Log data dictionary if successful, None otherwise.
        """
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f'❌ 读取日志文件失败 {log_file}: {e}')
            return None

    def _cleanup_old_logs(self) -> None:
        """Clean up old log files, keeping only the newest max_logs."""
        if not self._debug_dir.exists():
            return

        # Get all log files sorted by modification time
        log_files = sorted(
            self._debug_dir.glob('ai_debug_*.json'),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        # Delete files beyond the limit
        for old_file in log_files[self._max_logs:]:
            try:
                old_file.unlink()
                logger.debug(f'🗑️ 已删除旧的AI debug日志: {old_file.name}')
            except Exception as e:
                logger.warning(f'⚠️ 删除旧日志文件失败 {old_file.name}: {e}')

    def clear_all_logs(self) -> int:
        """
        Clear all debug log files.

        Returns:
            Number of files deleted.
        """
        if not self._debug_dir.exists():
            return 0

        count = 0
        for log_file in self._debug_dir.glob('ai_debug_*.json'):
            try:
                log_file.unlink()
                count += 1
            except Exception as e:
                logger.warning(f'⚠️ 删除日志文件失败 {log_file.name}: {e}')

        self._log_files.clear()
        logger.info(f'🗑️ 已清除 {count} 个AI debug日志')
        return count


# Global AI debug service instance
_ai_debug_service: Optional[AIDebugService] = None


def get_ai_debug_service() -> AIDebugService:
    """
    Get the global AI debug service instance.

    Returns:
        AIDebugService instance.
    """
    global _ai_debug_service
    if _ai_debug_service is None:
        _ai_debug_service = AIDebugService()
    return _ai_debug_service


# 全局实例 (向后兼容)
ai_debug_service = get_ai_debug_service()
