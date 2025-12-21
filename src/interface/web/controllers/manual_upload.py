"""
手动上传控制器

处理 torrent 文件和磁力链接的手动上传
"""
from flask import Blueprint, render_template, request
from dependency_injector.wiring import inject, Provide
import threading

from src.core.config import config
from src.container import Container
from src.services.download_manager import DownloadManager
from src.infrastructure.repositories.history_repository import HistoryRepository
from src.interface.web.utils import (
    APIResponse,
    handle_api_errors,
    validate_json,
    RequestValidator,
    ValidationRule,
    WebLogger
)

manual_upload_bp = Blueprint('manual_upload', __name__)
logger = WebLogger(__name__)


@manual_upload_bp.route('/manual_upload')
def manual_upload_page():
    """手動上傳torrent/磁力鏈頁面"""
    return render_template('manual_upload.html', config=config)


@manual_upload_bp.route('/api/manual_upload_history')
@inject
@handle_api_errors
def get_manual_upload_history_api(
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """API: 获取手动上传历史记录"""
    try:
        limit = int(request.args.get('limit', 20))
    except ValueError:
        return APIResponse.bad_request("limit必须是整数")

    if limit < 1 or limit > 100:
        return APIResponse.bad_request("limit必须在1-100之间")

    logger.api_request(f"获取手动上传历史 - limit:{limit}")

    history = history_repo.get_manual_upload_history(limit)

    logger.api_success('/api/manual_upload_history', f"返回 {len(history)} 条记录")
    return APIResponse.success(history=history)


@manual_upload_bp.route('/api/submit_upload', methods=['POST'])
@inject
@handle_api_errors
@validate_json()
def submit_manual_upload(
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """處理手動上傳請求"""
    data = request.get_json()

    # 验证必填字段
    upload_type = data.get('upload_type', 'torrent')
    anime_title = data.get('anime_title', '').strip()

    # 设置默认值
    if 'season' not in data:
        data['season'] = 1
    if 'category' not in data:
        data['category'] = 'tv'
    if 'media_type' not in data:
        data['media_type'] = 'anime'

    season = data.get('season', 1)
    category = data.get('category', 'tv')
    media_type = data.get('media_type', 'anime')
    requires_tvdb = data.get('requires_tvdb', False)
    tvdb_id = data.get('tvdb_id', None)

    # 验证 upload_type
    if upload_type not in ['torrent', 'magnet']:
        return APIResponse.bad_request("upload_type必须是'torrent'或'magnet'")

    # 根据类型验证特定字段
    if upload_type == 'torrent':
        torrent_file = data.get('torrent_file')
        if not torrent_file:
            return APIResponse.bad_request('請選擇要上傳的torrent文件')
    elif upload_type == 'magnet':
        magnet_link = data.get('magnet_link', '').strip()
        if not magnet_link:
            return APIResponse.bad_request('請輸入磁力鏈接')
        if not magnet_link.startswith('magnet:'):
            return APIResponse.bad_request('無效的磁力鏈接格式')

    if not anime_title:
        return APIResponse.bad_request('請輸入動漫名稱')

    # 验证其他字段
    validation_rules = {
        'season': ValidationRule(required=True, min_value=1, max_value=100),
        'category': ValidationRule(required=True, choices=['tv', 'movie']),
        'media_type': ValidationRule(required=True, choices=['anime', 'live_action'])
    }

    error = RequestValidator.validate(data, validation_rules)
    if error:
        return APIResponse.bad_request(error)

    logger.api_request(
        f"手动上传 - 类型:{upload_type}, 标题:{anime_title}, "
        f"季数:{season}, 分类:{category}, TVDB:{requires_tvdb}, TVDB_ID:{tvdb_id}"
    )

    # 在后台线程中处理上传
    def process_background():
        try:
            logger.processing_start(f"手动上传处理: {anime_title}")
            download_manager.process_manual_upload(data)
            logger.processing_success("手动上传处理完成")
        except Exception as e:
            logger.processing_error("手动上传处理", e)

    thread = threading.Thread(target=process_background, daemon=True)
    thread.start()

    logger.api_success('/api/submit_upload', '手动上传处理已启动')
    return APIResponse.success(message='手動上傳處理已啟動')
