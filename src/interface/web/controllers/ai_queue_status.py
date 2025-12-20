"""
AI/队列状态控制器模块。

提供 AI Key 使用情况、队列状态和熔断器状态的监控和管理 API。
"""

import logging
from typing import Any, Dict, Optional

from flask import Blueprint, render_template, request

from src.interface.web.utils import APIResponse, handle_api_errors, WebLogger
from src.infrastructure.ai.key_pool import get_pool, get_all_pools
from src.infrastructure.ai.circuit_breaker import get_breaker, get_all_breakers
from src.services.queue.webhook_queue import get_webhook_queue
from src.services.queue.rss_queue import get_rss_queue


logger = WebLogger(__name__)

ai_queue_bp = Blueprint('ai_queue', __name__)


@ai_queue_bp.route('/system/ai-queue')
def ai_queue_page():
    """
    AI/队列状态页面。

    显示 AI Key 使用情况、队列状态和熔断器状态的监控界面。

    Returns:
        渲染的 HTML 页面
    """
    logger.api_request('/system/ai-queue', 'GET')
    return render_template('ai_queue_status.html')


@ai_queue_bp.route('/api/ai-queue/status', methods=['GET'])
@handle_api_errors
def get_status():
    """
    获取完整的 AI/队列状态。

    返回所有队列、Key Pool 和熔断器的当前状态。

    Returns:
        JSON 响应包含:
        - webhook_queue: Webhook 队列状态
        - rss_queue: RSS 队列状态
        - key_pools: 所有 Key Pool 状态
        - circuit_breakers: 所有熔断器状态
    """
    logger.api_request('/api/ai-queue/status', 'GET')

    # 获取队列状态
    webhook_queue = get_webhook_queue()
    rss_queue = get_rss_queue()

    # 获取所有 Key Pool 状态
    key_pools_status = {}
    for purpose, pool in get_all_pools().items():
        key_pools_status[purpose] = pool.get_status()

    # 获取所有熔断器状态
    breakers_status = {}
    for purpose, breaker in get_all_breakers().items():
        breakers_status[purpose] = breaker.get_status()

    logger.api_success('/api/ai-queue/status', '获取状态成功')
    return APIResponse.success(data={
        'webhook_queue': webhook_queue.get_status() if webhook_queue else None,
        'rss_queue': rss_queue.get_status() if rss_queue else None,
        'key_pools': key_pools_status,
        'circuit_breakers': breakers_status
    })


@ai_queue_bp.route('/api/ai-queue/key/<purpose>/<key_id>/reset', methods=['POST'])
@handle_api_errors
def reset_key_cooldown(purpose: str, key_id: str):
    """
    重置指定 Key 的冷却状态。

    Args:
        purpose: Key Pool 用途标识（如 'title_parse'）
        key_id: Key 唯一标识

    Returns:
        JSON 响应:
        - 成功: {success: true, message: '...'}
        - 失败: {success: false, message: '...'}
    """
    logger.api_request(f'/api/ai-queue/key/{purpose}/{key_id}/reset', 'POST')

    pool = get_pool(purpose)
    if not pool:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset',
            f'未找到 {purpose} 的 Key Pool'
        )
        return APIResponse.not_found(f'未找到 {purpose} 的 Key Pool')

    if pool.reset_cooldown(key_id):
        logger.api_success(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset',
            f'Key {key_id} 冷却已重置'
        )
        return APIResponse.success(message=f'Key {key_id} 冷却已重置')
    else:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset',
            f'未找到 Key: {key_id}'
        )
        return APIResponse.not_found(f'未找到 Key: {key_id}')


@ai_queue_bp.route('/api/ai-queue/key/<purpose>/<key_id>/enable', methods=['POST'])
@handle_api_errors
def enable_key(purpose: str, key_id: str):
    """
    启用已禁用的 Key。

    当 Key 因为 400/403/404 错误被自动禁用后，
    可以通过此接口手动重新启用。

    Args:
        purpose: Key Pool 用途标识（如 'title_parse'）
        key_id: Key 唯一标识

    Returns:
        JSON 响应:
        - 成功: {success: true, message: '...'}
        - 失败: {success: false, message: '...'}
    """
    logger.api_request(f'/api/ai-queue/key/{purpose}/{key_id}/enable', 'POST')

    pool = get_pool(purpose)
    if not pool:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/enable',
            f'未找到 {purpose} 的 Key Pool'
        )
        return APIResponse.not_found(f'未找到 {purpose} 的 Key Pool')

    if pool.enable_key(key_id):
        logger.api_success(
            f'/api/ai-queue/key/{purpose}/{key_id}/enable',
            f'Key {key_id} 已重新启用'
        )
        return APIResponse.success(message=f'Key {key_id} 已重新启用')
    else:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/enable',
            f'Key {key_id} 未处于禁用状态或不存在'
        )
        return APIResponse.bad_request(f'Key {key_id} 未处于禁用状态或不存在')


@ai_queue_bp.route('/api/ai-queue/key/<purpose>/<key_id>/reset-rpm', methods=['POST'])
@handle_api_errors
def reset_key_rpm(purpose: str, key_id: str):
    """
    重置指定 Key 的 RPM 计数。

    Args:
        purpose: Key Pool 用途标识
        key_id: Key 唯一标识

    Returns:
        JSON 响应
    """
    logger.api_request(f'/api/ai-queue/key/{purpose}/{key_id}/reset-rpm', 'POST')

    pool = get_pool(purpose)
    if not pool:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset-rpm',
            f'未找到 {purpose} 的 Key Pool'
        )
        return APIResponse.not_found(f'未找到 {purpose} 的 Key Pool')

    if pool.reset_rpm(key_id):
        logger.api_success(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset-rpm',
            f'Key {key_id} RPM 已重置'
        )
        return APIResponse.success(message=f'Key {key_id} RPM 已重置')
    else:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset-rpm',
            f'未找到 Key: {key_id}'
        )
        return APIResponse.not_found(f'未找到 Key: {key_id}')


@ai_queue_bp.route('/api/ai-queue/key/<purpose>/<key_id>/reset-rpd', methods=['POST'])
@handle_api_errors
def reset_key_rpd(purpose: str, key_id: str):
    """
    重置指定 Key 的 RPD 计数。

    Args:
        purpose: Key Pool 用途标识
        key_id: Key 唯一标识

    Returns:
        JSON 响应
    """
    logger.api_request(f'/api/ai-queue/key/{purpose}/{key_id}/reset-rpd', 'POST')

    pool = get_pool(purpose)
    if not pool:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset-rpd',
            f'未找到 {purpose} 的 Key Pool'
        )
        return APIResponse.not_found(f'未找到 {purpose} 的 Key Pool')

    if pool.reset_rpd(key_id):
        logger.api_success(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset-rpd',
            f'Key {key_id} RPD 已重置'
        )
        return APIResponse.success(message=f'Key {key_id} RPD 已重置')
    else:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset-rpd',
            f'未找到 Key: {key_id}'
        )
        return APIResponse.not_found(f'未找到 Key: {key_id}')


@ai_queue_bp.route('/api/ai-queue/key/<purpose>/<key_id>/reset-all', methods=['POST'])
@handle_api_errors
def reset_key_all_limits(purpose: str, key_id: str):
    """
    重置指定 Key 的所有限制（冷却、RPM、RPD）。

    Args:
        purpose: Key Pool 用途标识
        key_id: Key 唯一标识

    Returns:
        JSON 响应
    """
    logger.api_request(f'/api/ai-queue/key/{purpose}/{key_id}/reset-all', 'POST')

    pool = get_pool(purpose)
    if not pool:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset-all',
            f'未找到 {purpose} 的 Key Pool'
        )
        return APIResponse.not_found(f'未找到 {purpose} 的 Key Pool')

    if pool.reset_all_limits(key_id):
        logger.api_success(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset-all',
            f'Key {key_id} 所有限制已重置'
        )
        return APIResponse.success(message=f'Key {key_id} 所有限制已重置')
    else:
        logger.api_error_msg(
            f'/api/ai-queue/key/{purpose}/{key_id}/reset-all',
            f'未找到 Key: {key_id}'
        )
        return APIResponse.not_found(f'未找到 Key: {key_id}')


@ai_queue_bp.route('/api/ai-queue/circuit/<purpose>/reset', methods=['POST'])
@handle_api_errors
def reset_circuit_breaker(purpose: str):
    """
    重置指定用途的熔断器。

    Args:
        purpose: 熔断器用途标识

    Returns:
        JSON 响应:
        - 成功: {success: true, message: '...'}
        - 失败: {success: false, message: '...'}
    """
    logger.api_request(f'/api/ai-queue/circuit/{purpose}/reset', 'POST')

    breaker = get_breaker(purpose)
    if not breaker:
        logger.api_error_msg(
            f'/api/ai-queue/circuit/{purpose}/reset',
            f'未找到 {purpose} 的熔断器'
        )
        return APIResponse.not_found(f'未找到 {purpose} 的熔断器')

    breaker.reset()
    logger.api_success(
        f'/api/ai-queue/circuit/{purpose}/reset',
        f'{purpose} 熔断器已重置'
    )
    return APIResponse.success(message=f'{purpose} 熔断器已重置')


@ai_queue_bp.route('/api/ai-queue/queue/<queue_name>/pause', methods=['POST'])
@handle_api_errors
def pause_queue(queue_name: str):
    """
    暂停指定队列的处理。

    暂停后队列仍接收事件，但不处理新事件。
    工作线程继续运行，等待恢复信号。

    Args:
        queue_name: 队列名称 ('webhook' 或 'rss')

    Returns:
        JSON 响应:
        - 成功: {success: true, message: '...'}
        - 失败: {success: false, message: '...'}
    """
    logger.api_request(f'/api/ai-queue/queue/{queue_name}/pause', 'POST')

    queue_worker = _get_queue_worker(queue_name)
    if not queue_worker:
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/pause',
            f'未找到队列: {queue_name}'
        )
        return APIResponse.not_found(f'未找到队列: {queue_name}')

    if queue_worker.is_paused():
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/pause',
            f'队列 {queue_name} 已经处于暂停状态'
        )
        return APIResponse.bad_request(f'队列 {queue_name} 已经处于暂停状态')

    if queue_worker.is_stopped():
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/pause',
            f'队列 {queue_name} 已停止，无法暂停'
        )
        return APIResponse.bad_request(f'队列 {queue_name} 已停止，无法暂停')

    queue_worker.pause()
    logger.api_success(
        f'/api/ai-queue/queue/{queue_name}/pause',
        f'队列 {queue_name} 已暂停'
    )
    return APIResponse.success(message=f'队列 {queue_name} 已暂停')


@ai_queue_bp.route('/api/ai-queue/queue/<queue_name>/resume', methods=['POST'])
@handle_api_errors
def resume_queue(queue_name: str):
    """
    恢复指定队列的处理。

    Args:
        queue_name: 队列名称 ('webhook' 或 'rss')

    Returns:
        JSON 响应:
        - 成功: {success: true, message: '...'}
        - 失败: {success: false, message: '...'}
    """
    logger.api_request(f'/api/ai-queue/queue/{queue_name}/resume', 'POST')

    queue_worker = _get_queue_worker(queue_name)
    if not queue_worker:
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/resume',
            f'未找到队列: {queue_name}'
        )
        return APIResponse.not_found(f'未找到队列: {queue_name}')

    if not queue_worker.is_paused():
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/resume',
            f'队列 {queue_name} 未处于暂停状态'
        )
        return APIResponse.bad_request(f'队列 {queue_name} 未处于暂停状态')

    queue_worker.resume()
    logger.api_success(
        f'/api/ai-queue/queue/{queue_name}/resume',
        f'队列 {queue_name} 已恢复'
    )
    return APIResponse.success(message=f'队列 {queue_name} 已恢复')


@ai_queue_bp.route('/api/ai-queue/queue/<queue_name>/stop', methods=['POST'])
@handle_api_errors
def stop_queue(queue_name: str):
    """
    停止指定队列的工作线程。

    完全停止工作线程，但队列中的事件会被保留。
    使用 start 端点重新启动。

    Args:
        queue_name: 队列名称 ('webhook' 或 'rss')

    Returns:
        JSON 响应:
        - 成功: {success: true, message: '...'}
        - 失败: {success: false, message: '...'}
    """
    logger.api_request(f'/api/ai-queue/queue/{queue_name}/stop', 'POST')

    queue_worker = _get_queue_worker(queue_name)
    if not queue_worker:
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/stop',
            f'未找到队列: {queue_name}'
        )
        return APIResponse.not_found(f'未找到队列: {queue_name}')

    if queue_worker.is_stopped():
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/stop',
            f'队列 {queue_name} 已经处于停止状态'
        )
        return APIResponse.bad_request(f'队列 {queue_name} 已经处于停止状态')

    queue_worker.stop()
    logger.api_success(
        f'/api/ai-queue/queue/{queue_name}/stop',
        f'队列 {queue_name} 已停止'
    )
    return APIResponse.success(message=f'队列 {queue_name} 已停止')


@ai_queue_bp.route('/api/ai-queue/queue/<queue_name>/start', methods=['POST'])
@handle_api_errors
def start_queue(queue_name: str):
    """
    启动指定队列的工作线程。

    如果队列已经在运行，则此操作无效果。

    Args:
        queue_name: 队列名称 ('webhook' 或 'rss')

    Returns:
        JSON 响应:
        - 成功: {success: true, message: '...'}
        - 失败: {success: false, message: '...'}
    """
    logger.api_request(f'/api/ai-queue/queue/{queue_name}/start', 'POST')

    queue_worker = _get_queue_worker(queue_name)
    if not queue_worker:
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/start',
            f'未找到队列: {queue_name}'
        )
        return APIResponse.not_found(f'未找到队列: {queue_name}')

    if queue_worker.is_running():
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/start',
            f'队列 {queue_name} 已经在运行中'
        )
        return APIResponse.bad_request(f'队列 {queue_name} 已经在运行中')

    queue_worker.start()
    logger.api_success(
        f'/api/ai-queue/queue/{queue_name}/start',
        f'队列 {queue_name} 已启动'
    )
    return APIResponse.success(message=f'队列 {queue_name} 已启动')


@ai_queue_bp.route('/api/ai-queue/queue/<queue_name>/clear', methods=['POST'])
@handle_api_errors
def clear_queue(queue_name: str):
    """
    清空指定队列中的所有待处理事件。

    此操作不可恢复。

    Args:
        queue_name: 队列名称 ('webhook' 或 'rss')

    Returns:
        JSON 响应:
        - 成功: {success: true, message: '...', data: {cleared_count: n}}
        - 失败: {success: false, message: '...'}
    """
    logger.api_request(f'/api/ai-queue/queue/{queue_name}/clear', 'POST')

    queue_worker = _get_queue_worker(queue_name)
    if not queue_worker:
        logger.api_error_msg(
            f'/api/ai-queue/queue/{queue_name}/clear',
            f'未找到队列: {queue_name}'
        )
        return APIResponse.not_found(f'未找到队列: {queue_name}')

    cleared_count = queue_worker.clear_queue()
    logger.api_success(
        f'/api/ai-queue/queue/{queue_name}/clear',
        f'已清空 {cleared_count} 个事件'
    )
    return APIResponse.success(
        message=f'已清空 {cleared_count} 个事件',
        data={'cleared_count': cleared_count}
    )


def _get_queue_worker(queue_name: str):
    """
    根据名称获取队列工作者实例。

    Args:
        queue_name: 队列名称 ('webhook' 或 'rss')

    Returns:
        队列工作者实例或 None
    """
    if queue_name == 'webhook':
        return get_webhook_queue()
    elif queue_name == 'rss':
        return get_rss_queue()
    return None
