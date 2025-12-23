"""
手动上传控制器

处理 torrent 文件和磁力链接的手动上传
"""
import base64
import re
import tempfile
import os

from flask import Blueprint, render_template, request
from dependency_injector.wiring import inject, Provide

from src.core.config import config
from src.container import Container
from src.services.download_manager import DownloadManager
from src.infrastructure.repositories.history_repository import HistoryRepository
from src.infrastructure.repositories.download_repository import DownloadRepository
from src.infrastructure.downloader.qbit_adapter import (
    get_torrent_hash_from_file,
    get_torrent_hash_from_magnet
)
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
    download_manager: DownloadManager = Provide[Container.download_manager],
    download_repo: DownloadRepository = Provide[Container.download_repo],
    history_repo: HistoryRepository = Provide[Container.history_repo]
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

    # 根据类型验证特定字段并提取 hash
    hash_id = None
    temp_file_path = None

    if upload_type == 'torrent':
        torrent_file = data.get('torrent_file')
        if not torrent_file:
            return APIResponse.bad_request('請選擇要上傳的torrent文件')

        # 提取 hash 用于重复检查
        try:
            torrent_content = base64.b64decode(torrent_file)
            with tempfile.NamedTemporaryFile(suffix='.torrent', delete=False) as temp_file:
                temp_file.write(torrent_content)
                temp_file_path = temp_file.name
            hash_id = get_torrent_hash_from_file(temp_file_path)
        except Exception as e:
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            logger.processing_error("提取torrent hash失败", e)
            return APIResponse.bad_request(f'無法解析torrent文件: {str(e)}')
        finally:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    elif upload_type == 'magnet':
        magnet_link = data.get('magnet_link', '').strip()
        torrent_hash = data.get('torrent_hash', '').strip().lower()

        if magnet_link:
            # 使用磁力链接
            if not magnet_link.startswith('magnet:'):
                return APIResponse.bad_request('無效的磁力鏈接格式')

            # 提取 hash 用于重复检查
            hash_id = get_torrent_hash_from_magnet(magnet_link)
            if not hash_id:
                return APIResponse.bad_request('無法從磁力鏈接提取hash')
        elif torrent_hash:
            # 使用直接输入的hash
            if not re.match(r'^[a-f0-9]{40}$', torrent_hash):
                return APIResponse.bad_request('無效的Hash格式，請輸入40位十六進制字符')

            hash_id = torrent_hash
            # 构建磁力链接供后续处理使用
            data['magnet_link'] = f'magnet:?xt=urn:btih:{torrent_hash}'
        else:
            return APIResponse.bad_request('請輸入磁力鏈接或 Torrent Hash')

    if not anime_title:
        return APIResponse.bad_request('請輸入動漫名稱')

    if not hash_id:
        return APIResponse.bad_request('無法提取hash，請檢查上傳的內容')

    # 检查 hash 是否已存在于下载列表
    existing_download = download_repo.get_by_hash(hash_id)
    if existing_download:
        anime_name = existing_download.anime_title or existing_download.original_filename
        return APIResponse.bad_request(
            f'該種子已在下載列表中: {anime_name}'
        )

    # 检查 hash 是否已存在于下载历史
    existing_history = history_repo.get_download_history_by_hash(hash_id)
    if existing_history:
        anime_name = existing_history.get('anime_title') or existing_history.get('original_filename')
        return APIResponse.bad_request(
            f'該種子已在下載歷史中: {anime_name}（如需重新下載，請從歷史記錄中操作）'
        )

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
        f"季数:{season}, 分类:{category}, TVDB:{requires_tvdb}, TVDB_ID:{tvdb_id}, "
        f"hash:{hash_id[:8]}..."
    )

    # 同步处理上传，等待结果
    try:
        logger.processing_start(f"手动上传处理: {anime_title}")
        success, error_message = download_manager.process_manual_upload(data)

        if success:
            logger.processing_success("手动上传处理完成")
            logger.api_success('/api/submit_upload', '手动上传处理成功')
            return APIResponse.success(message='手動上傳處理成功')
        else:
            logger.processing_error("手动上传处理", Exception(error_message))
            return APIResponse.error(f'手動上傳失敗: {error_message}', status_code=500)
    except Exception as e:
        logger.processing_error("手动上传处理", e)
        return APIResponse.error(f'手動上傳失敗: {str(e)}', status_code=500)
