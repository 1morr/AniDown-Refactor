"""
系统状态控制器

提供系统运行状态、AI 队列状态等 API
"""
import threading
from datetime import UTC, datetime

from flask import Blueprint, render_template

from src.core.config import config
from src.interface.web.utils import APIResponse, WebLogger, handle_api_errors

logger = WebLogger(__name__)
system_status_bp = Blueprint('system_status', __name__)


class SystemStatusManager:
    """系统状态管理器（单例模式）"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._webui_running = False
        self._webhook_running = False
        self._rss_scheduler_running = False
        self._initialized = True

    def set_webui_status(self, running: bool):
        """设置 Web UI 运行状态"""
        self._webui_running = running
        logger.db_update("系统状态", f"WebUI: {'运行' if running else '停止'}")

    def set_webhook_status(self, running: bool):
        """设置 Webhook 服务器运行状态"""
        self._webhook_running = running
        logger.db_update("系统状态", f"Webhook: {'运行' if running else '停止'}")

    def set_rss_scheduler_status(self, running: bool):
        """设置 RSS 调度器运行状态"""
        self._rss_scheduler_running = running
        logger.db_update("系统状态", f"RSS调度器: {'运行' if running else '停止'}")

    def get_status(self) -> dict:
        """获取所有服务状态"""
        # WebUI 和 Webhook 始终启用
        webui_status = 'running' if self._webui_running else 'stopped'
        webhook_status = 'running' if self._webhook_running else 'stopped'
        rss_status = 'running' if self._rss_scheduler_running else 'stopped'

        # 整体状态：至少有一个服务在运行则为运行中
        overall_running = (
            self._webui_running or
            self._webhook_running or
            self._rss_scheduler_running
        )

        return {
            'overall': 'running' if overall_running else 'stopped',
            'services': {
                'webui': webui_status,
                'webhook': webhook_status,
                'rss_scheduler': rss_status
            }
        }


# 创建全局实例
system_status_manager = SystemStatusManager()


@system_status_bp.route('/system/ai-status')
def ai_status_page():
    """AI / 队列状态页面"""
    return render_template('ai_status.html', config=config)


@system_status_bp.route('/api/system/status', methods=['GET'])
@handle_api_errors
def get_system_status():
    """获取系统运行状态"""
    logger.debug("🚀 API请求: GET 获取系统状态")

    status = system_status_manager.get_status()

    logger.debug(f"✅ API成功: /api/system/status - 整体状态: {status['overall']}")
    return APIResponse.success(data=status)


@system_status_bp.route('/api/system/ai-status', methods=['GET'])
@handle_api_errors
def get_ai_status():
    """获取 AI key pool / 限流 / webhook 队列 / rss 队列状态（用于状态页轮询）"""
    logger.debug("🚀 API请求: GET 获取AI/队列状态")

    # Webhook queue
    from src.services import webhook_queue as wq
    webhook_worker = wq.webhook_queue_worker
    if webhook_worker is None:
        webhook_queue_status = {
            "initialized": False,
            "queue_len": 0,
            "thread_alive": False,
            "stopped": False,
            "consecutive_failures": 0,
            "max_consecutive_failures": int(
                getattr(config.openai.rate_limits, "max_consecutive_errors", 5) or 5
            ),
            "current_event": None,
            "pending_events": [],
        }
    else:
        webhook_queue_status = {"initialized": True, **webhook_worker.get_status_snapshot()}

    # RSS queue
    from src.services import rss_queue as rq
    rss_worker = rq.rss_queue_worker
    if rss_worker is None:
        rss_queue_status = {
            "initialized": False,
            "queue_len": 0,
            "thread_alive": False,
            "stopped": False,
            "consecutive_failures": 0,
            "max_consecutive_failures": int(
                getattr(config.openai.rate_limits, "max_consecutive_errors", 5) or 5
            ),
            "current_event": None,
            "pending_events": [],
            "stats": {
                "total_processed": 0,
                "total_success": 0,
                "total_failed": 0,
            }
        }
    else:
        rss_queue_status = {"initialized": True, **rss_worker.get_status_snapshot()}

    # AI limiter
    from src.infrastructure.ai.rate_limiter import ai_rate_limiter
    ai_status = ai_rate_limiter.get_detailed_snapshot()

    payload = {
        "now_utc": datetime.now(UTC).isoformat(),
        "queue": webhook_queue_status,  # 保持兼容性，webhook队列仍用 "queue" 键
        "rss_queue": rss_queue_status,   # 新增 RSS 队列
        "ai": ai_status,
    }

    return APIResponse.success(data=payload)


@system_status_bp.route('/api/system/ai-key-history', methods=['GET'])
@handle_api_errors
def get_ai_key_history():
    """获取指定 AI Key 的使用历史"""
    from flask import request

    from src.infrastructure.repositories.ai_key_repository import ai_key_repository

    purpose = request.args.get('purpose', '')
    key_id = request.args.get('key_id', '')
    limit = min(int(request.args.get('limit', 100)), 500)  # 最多 500 条
    offset = int(request.args.get('offset', 0))

    if not purpose or not key_id:
        return APIResponse.error(message="Missing required parameters: purpose, key_id")

    logger.api_request(f"获取AI Key历史: purpose={purpose}, key_id={key_id}")

    records = ai_key_repository.get_usage_history(
        purpose=purpose,
        key_id=key_id,
        limit=limit,
        offset=offset,
    )

    return APIResponse.success(data={
        "purpose": purpose,
        "key_id": key_id,
        "records": records,
        "count": len(records),
    })
