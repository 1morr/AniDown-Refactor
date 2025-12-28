"""
下载管理控制器

处理下载列表、状态检查、硬链接管理等功能
"""
from dependency_injector.wiring import Provide, inject
from flask import Blueprint, render_template, request

from src.container import Container
from src.infrastructure.repositories.download_repository import DownloadRepository
from src.infrastructure.repositories.history_repository import HistoryRepository
from src.interface.web.utils import (
    APIResponse,
    WebLogger,
    handle_api_errors,
    validate_json,
)
from src.services.download_manager import DownloadManager
from src.services.file.file_service import FileService
from src.services.queue.webhook_queue import WebhookPayload

logger = WebLogger(__name__)
downloads_bp = Blueprint('downloads', __name__)


@downloads_bp.route('/downloads')
def downloads_page():
    """下载管理页面"""
    return render_template('downloads.html')


@downloads_bp.route('/download-history')
def download_history_page():
    """下载历史页面"""
    return render_template('download_history.html')


@downloads_bp.route('/api/downloads')
@inject
@handle_api_errors
def api_get_downloads(
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """获取下载记录的API"""
    # 验证查询参数
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except ValueError:
        return APIResponse.bad_request('页码和每页数量必须是整数')

    if page < 1 or per_page < 1:
        return APIResponse.bad_request('页码和每页数量必须大于0')
    if per_page > 100:
        return APIResponse.bad_request('每页最多100条记录')

    search = request.args.get('search', '').strip()
    sort_column = request.args.get('sort_column', 'download_time')
    sort_order = request.args.get('sort_order', 'desc')
    status_filter = request.args.get('status_filter', '').strip()
    season_filter = request.args.get('season_filter', '').strip()
    media_type_filter = request.args.get('media_type_filter', '').strip()
    hardlink_filter = request.args.get('hardlink_filter', '').strip()
    group_by = request.args.get('group_by', '').strip()
    viewing_group = request.args.get('viewing_group', '').strip()

    logger.api_request(f'获取下载列表 - 页码:{page}, 搜索:{search}, 分组:{group_by}')

    # 如果是分组查询且没有指定查看特定分组，返回分组统计
    if group_by and not viewing_group:
        result = download_manager.get_downloads_grouped(
            group_by=group_by,
            search=search,
            status_filter=status_filter,
            season_filter=season_filter,
            media_type_filter=media_type_filter,
            hardlink_filter=hardlink_filter
        )
    else:
        result = download_manager.get_downloads_paginated(
            page=page,
            per_page=per_page,
            search=search,
            sort_column=sort_column,
            sort_order=sort_order,
            status_filter=status_filter,
            season_filter=season_filter,
            media_type_filter=media_type_filter,
            hardlink_filter=hardlink_filter,
            group_by=group_by,
            viewing_group=viewing_group
        )

    logger.api_success('/api/downloads')
    # 解包result字典，避免双重嵌套
    if isinstance(result, dict):
        return APIResponse.success(**result)
    return APIResponse.success(data=result)


@downloads_bp.route('/api/downloads/<hash_id>/check', methods=['POST'])
@inject
@handle_api_errors
def api_check_torrent(
    hash_id: str,
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """检查单个torrent状态"""
    if not hash_id or len(hash_id) != 40:
        return APIResponse.bad_request('无效的torrent哈希值')

    logger.api_request(f'检查torrent状态 - hash:{hash_id}')

    result = download_manager.check_torrent_status(hash_id)

    if result.get('success'):
        logger.api_success(f'/api/downloads/{hash_id}/check')
        return APIResponse.success(data=result)
    else:
        return APIResponse.internal_error(result.get('error', '检查失败'))


@downloads_bp.route('/api/downloads/check-all', methods=['POST'])
@inject
@handle_api_errors
def api_check_all_torrents(
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """批量检查所有torrent状态"""
    logger.api_request('批量检查所有torrent状态')

    result = download_manager.check_all_torrents()

    if result.get('success'):
        logger.api_success(
            '/api/downloads/check-all',
            f"检查了 {result.get('total_checked', 0)} 个"
        )
        # 重新格式化返回数据以匹配前端期望
        return APIResponse.success(
            checked=result.get('total_checked', 0),
            updated=result.get('updated_count', 0),
            status_changed=[]  # 可以在这里添加状态变化的详细信息
        )
    else:
        return APIResponse.internal_error(result.get('error', '批量检查失败'))


@downloads_bp.route('/api/downloads/redownload', methods=['POST'])
@inject
@handle_api_errors
@validate_json('hash_id')
def api_redownload_from_history(
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """从删除历史中重新下载"""
    data = request.get_json()
    hash_id = data.get('hash_id')
    download_directory = data.get('download_directory')

    if not hash_id or len(hash_id) != 40:
        return APIResponse.bad_request('无效的torrent哈希值')

    logger.api_request(f'重新下载 - hash:{hash_id}')

    if download_manager.redownload_from_history(hash_id, download_directory):
        logger.api_success('/api/downloads/redownload')
        return APIResponse.success(message='已重新添加到下载队列')
    else:
        return APIResponse.internal_error('重新下载失败')


@downloads_bp.route('/api/downloads/<hash_id>/delete', methods=['POST'])
@inject
@handle_api_errors
@validate_json()
def api_delete_download(
    hash_id: str,
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """删除下载项目"""
    if not hash_id or len(hash_id) != 40:
        return APIResponse.bad_request('无效的torrent哈希值')

    data = request.get_json()
    delete_files = data.get('delete_files', False)
    delete_hardlinks = data.get('delete_hardlinks', False)

    if not isinstance(delete_files, bool):
        return APIResponse.bad_request('delete_files必须是布尔值')
    if not isinstance(delete_hardlinks, bool):
        return APIResponse.bad_request('delete_hardlinks必须是布尔值')

    logger.api_request(
        f'删除下载 - hash:{hash_id}, '
        f'删除文件:{delete_files}, 删除硬链接:{delete_hardlinks}'
    )

    result = download_manager.delete_download(hash_id, delete_files, delete_hardlinks)

    if result.get('success'):
        logger.api_success(f'/api/downloads/{hash_id}/delete')
        return APIResponse.success(data=result)
    else:
        return APIResponse.internal_error(result.get('error', '删除失败'))


@downloads_bp.route('/api/download-history')
@inject
@handle_api_errors
def api_get_download_history(
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """获取下载历史记录的API"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except ValueError:
        return APIResponse.bad_request('页码和每页数量必须是整数')

    if page < 1 or per_page < 1:
        return APIResponse.bad_request('页码和每页数量必须大于0')
    if per_page > 100:
        return APIResponse.bad_request('每页最多100条记录')

    search = request.args.get('search', '').strip()
    sort_column = request.args.get('sort_column', 'deleted_at')
    sort_order = request.args.get('sort_order', 'desc')

    logger.api_request(f'获取下载历史 - 页码:{page}')

    result = history_repo.get_download_history_paginated(
        page=page,
        per_page=per_page,
        search=search,
        sort_column=sort_column,
        sort_order=sort_order
    )

    logger.api_success('/api/download-history')
    # 解包result字典，避免双重嵌套
    if isinstance(result, dict):
        return APIResponse.success(**result)
    return APIResponse.success(data=result)


@downloads_bp.route('/api/downloads/<hash_id>/files')
@inject
@handle_api_errors
def api_get_torrent_files(
    hash_id: str,
    qb_client=Provide[Container.qb_client]
):
    """獲取種子文件列表（从qBittorrent获取，数据库获取硬链接信息）"""
    if not hash_id or len(hash_id) != 40:
        return APIResponse.bad_request('无效的torrent哈希值')

    logger.api_request(f'获取torrent文件列表 - hash:{hash_id}')

    from src.infrastructure.database.models import Hardlink
    from src.infrastructure.database.session import db_manager

    # 从qBittorrent获取torrent信息
    torrent_info = qb_client.get_torrent_info(hash_id)
    if not torrent_info:
        logger.api_error_msg(
            f'/api/downloads/{hash_id}/files',
            '无法从qBittorrent获取torrent信息'
        )
        return APIResponse.not_found('无法从qBittorrent获取torrent信息，请确认torrent存在')

    # 从qBittorrent获取文件列表
    torrent_files = qb_client.get_torrent_files(hash_id)
    if not torrent_files:
        logger.api_error_msg(
            f'/api/downloads/{hash_id}/files',
            '无法从qBittorrent获取文件列表'
        )
        return APIResponse.not_found('无法从qBittorrent获取文件列表')

    # 从数据库获取已有的硬链接信息
    with db_manager.session() as session:
        hardlinks = session.query(Hardlink).filter_by(torrent_hash=hash_id).all()

        logger.db_query('硬链接查询', f'找到 {len(hardlinks)} 个硬链接记录')

        # 建立原始文件路径到硬链接信息的映射
        # 支持多种路径格式的匹配
        hardlink_map = {}
        for h in hardlinks:
            original_path = h.original_file_path

            # 存储完整路径（原样）
            hardlink_map[original_path] = {
                'id': h.id,
                'hardlink_path': h.hardlink_path
            }

            # 规范化路径（统一使用正斜杠）
            normalized_path = original_path.replace('\\', '/')
            hardlink_map[normalized_path] = {
                'id': h.id,
                'hardlink_path': h.hardlink_path
            }

            # 提取文件名（最后一部分）
            file_name_only = original_path.split('/')[-1].split('\\')[-1]
            if file_name_only not in hardlink_map:  # 避免文件名冲突
                hardlink_map[file_name_only] = {
                    'id': h.id,
                    'hardlink_path': h.hardlink_path
                }

            # 如果路径包含save_path，提取相对路径
            save_path = torrent_info.get('save_path', '')
            if save_path:
                # 尝试从完整路径中提取相对部分
                for separator in ['/', '\\']:
                    if save_path in original_path:
                        relative = original_path.split(save_path)[-1].lstrip('/').lstrip('\\')
                        if relative:
                            hardlink_map[relative] = {
                                'id': h.id,
                                'hardlink_path': h.hardlink_path
                            }
                            # 同时存储规范化版本
                            hardlink_map[relative.replace('\\', '/')] = {
                                'id': h.id,
                                'hardlink_path': h.hardlink_path
                            }
                            break

            # 提取torrent名称后的相对路径
            torrent_name = torrent_info.get('name', '')
            if torrent_name and torrent_name in original_path:
                relative = original_path.split(torrent_name)[-1].lstrip('/').lstrip('\\')
                if relative:
                    hardlink_map[relative] = {
                        'id': h.id,
                        'hardlink_path': h.hardlink_path
                    }
                    hardlink_map[relative.replace('\\', '/')] = {
                        'id': h.id,
                        'hardlink_path': h.hardlink_path
                    }

    # 处理文件列表
    files_data = []
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')
    subtitle_extensions = ('.srt', '.ass', '.ssa', '.vtt', '.sub')

    for file_info in torrent_files:
        file_name = file_info.get('name', '')
        file_size = file_info.get('size', 0)

        # 判断文件类型
        if file_name.lower().endswith(video_extensions):
            file_type = 'video'
        elif file_name.lower().endswith(subtitle_extensions):
            file_type = 'subtitle'
        else:
            file_type = 'other'

        # 检查是否有硬链接 - 尝试多种路径格式
        hardlink_info = None

        # 1. 直接匹配原始路径
        hardlink_info = hardlink_map.get(file_name)

        # 2. 尝试规范化路径
        if not hardlink_info:
            normalized = file_name.replace('\\', '/')
            hardlink_info = hardlink_map.get(normalized)

        # 3. 尝试完整路径（save_path + file_name）
        if not hardlink_info:
            full_path = f"{torrent_info.get('save_path', '')}/{file_name}"
            full_path = full_path.replace('//', '/').replace('\\', '/')
            hardlink_info = hardlink_map.get(full_path)

        # 4. 尝试只用文件名匹配
        if not hardlink_info:
            file_name_only = file_name.split('/')[-1].split('\\')[-1]
            hardlink_info = hardlink_map.get(file_name_only)

        # 5. 尝试 torrent名称/文件名
        if not hardlink_info:
            with_torrent_name = f"{torrent_info.get('name', '')}/{file_name}"
            with_torrent_name = with_torrent_name.replace('//', '/').replace('\\', '/')
            hardlink_info = hardlink_map.get(with_torrent_name)

        files_data.append({
            'name': file_name.split('/')[-1],  # 只保留文件名
            'relative_path': file_name,  # 完整的相对路径
            'size': file_size,
            'type': file_type,
            'has_hardlink': hardlink_info is not None,
            'hardlink_info': hardlink_info
        })

    # 构建返回的torrent信息
    result_torrent_info = {
        'name': torrent_info.get('name', ''),
        'save_path': torrent_info.get('save_path', ''),
        'size': torrent_info.get('size', 0),
        'progress': torrent_info.get('progress', 0.0)
    }

    logger.api_success(
        f'/api/downloads/{hash_id}/files',
        f'返回 {len(files_data)} 个文件'
    )

    return APIResponse.success(
        torrent_info=result_torrent_info,
        files=files_data
    )


@downloads_bp.route('/api/downloads/<hash_id>/hardlinks', methods=['POST'])
@inject
@handle_api_errors
@validate_json('files')
def api_create_hardlinks(
    hash_id: str,
    file_service: FileService = Provide[Container.file_service],
    download_repo: DownloadRepository = Provide[Container.download_repo]
):
    """創建硬鏈接（优化版，减少对qBittorrent的依赖）"""
    if not hash_id or len(hash_id) != 40:
        return APIResponse.bad_request('无效的torrent哈希值')

    data = request.get_json()
    files = data.get('files', [])
    target_path = data.get('target_path', '').strip()

    if not files:
        return APIResponse.bad_request('未選擇文件')

    logger.api_request(f'创建硬链接 - hash:{hash_id}, 文件数:{len(files)}')

    # 獲取下載信息
    download_info = download_repo.get_download_status_by_hash(hash_id)
    if not download_info:
        return APIResponse.not_found('未找到下載記錄')

    # 構建目標目錄
    import os

    from src.core.config import config

    anime_title = download_info['anime_title'] or 'Unknown'
    base_target_path = config.link_target_path

    if target_path:
        target_directory = f'{base_target_path}/{anime_title}/{target_path.lstrip("/")}'
    else:
        target_directory = f'{base_target_path}/{anime_title}'

    # 確保目標目錄存在
    os.makedirs(target_directory, mode=0o775, exist_ok=True)

    created_links = []
    failed_links = []

    # 获取下载目录（从数据库记录中获取，避免调用qBittorrent）
    download_directory = download_info.get('download_directory', '')

    for file_data in files:
        try:
            relative_path = file_data.get('relative_path', '')
            custom_name = file_data.get('custom_name', '').strip()

            # 構建源文件路徑（使用数据库中的下载目录）
            if download_directory:
                source_path = f'{download_directory}/{relative_path}'
            else:
                source_path = relative_path

            # 確定目標文件名
            if custom_name:
                target_filename = custom_name
            else:
                target_filename = relative_path.split('/')[-1]

            target_file_path = f'{target_directory}/{target_filename}'

            # 創建硬鏈接
            if file_service.create_hardlink(
                source_path=source_path,
                target_path=target_file_path,
                anime_id=download_info.get('anime_id'),
                torrent_hash=hash_id
            ):
                created_links.append({
                    'file': relative_path,
                    'target': target_file_path
                })
            else:
                failed_links.append({
                    'file': relative_path,
                    'reason': '硬鏈接創建失敗'
                })

        except Exception as e:
            failed_links.append({
                'file': file_data.get('relative_path', 'unknown'),
                'reason': str(e)
            })

    logger.api_success(
        f'/api/downloads/{hash_id}/hardlinks',
        f'创建 {len(created_links)} 个硬链接, {len(failed_links)} 个失败'
    )

    return APIResponse.success(
        created_links=created_links,
        failed_links=failed_links,
        target_directory=target_directory
    )


@downloads_bp.route('/api/hardlinks/<int:hardlink_id>', methods=['DELETE'])
@inject
@handle_api_errors
def api_delete_hardlink(
    hardlink_id: int,
    file_service: FileService = Provide[Container.file_service]
):
    """刪除硬鏈接"""
    if hardlink_id < 1:
        return APIResponse.bad_request('硬链接ID必须大于0')

    logger.api_request(f'删除硬链接 - ID:{hardlink_id}')

    if file_service.delete_hardlink(hardlink_id):
        logger.api_success(f'/api/hardlinks/{hardlink_id}')
        return APIResponse.success(message='硬鏈接已刪除')
    else:
        return APIResponse.not_found('硬鏈接不存在或刪除失敗')


@downloads_bp.route('/api/hardlinks/<int:hardlink_id>/rename', methods=['POST'])
@inject
@handle_api_errors
@validate_json('new_name')
def api_rename_hardlink(
    hardlink_id: int,
    file_service: FileService = Provide[Container.file_service]
):
    """重命名硬鏈接"""
    if hardlink_id < 1:
        return APIResponse.bad_request('硬链接ID必须大于0')

    data = request.get_json()
    new_name = data.get('new_name', '').strip()

    if not new_name:
        return APIResponse.bad_request('新文件名不能為空')

    logger.api_request(f'重命名硬链接 - ID:{hardlink_id}, 新名称:{new_name}')

    new_path = file_service.rename_hardlink(hardlink_id, new_name)
    if new_path:
        logger.api_success(f'/api/hardlinks/{hardlink_id}/rename')
        return APIResponse.success(
            message='硬鏈接已重命名',
            new_path=new_path
        )
    else:
        return APIResponse.internal_error('重命名失敗')


@downloads_bp.route('/api/downloads/<hash_id>/webhook', methods=['POST'])
@inject
@handle_api_errors
def api_send_webhook(
    hash_id: str,
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """為指定torrent發送webhook（通过队列异步处理）"""
    if not hash_id or len(hash_id) != 40:
        return APIResponse.bad_request('无效的torrent哈希值')

    logger.api_request(f'发送webhook到队列 - hash:{hash_id}')

    # 获取下载记录信息
    download_repo = DownloadRepository()
    download_info = download_repo.get_download_status_by_hash(hash_id)

    # 模擬webhook數據
    payload = WebhookPayload(
        hash_id=hash_id,
        name=(
            download_info.get('original_filename', f'Manual webhook for {hash_id}')
            if download_info else f'Manual webhook for {hash_id}'
        ),
        category='',
        save_path=download_info.get('download_directory', '') if download_info else '',
        extra_data={
            'tags': '',
            'content_path': '',
            'root_path': '',
            'tracker': ''
        }
    )

    # 使用队列处理
    from src.services import webhook_queue as wq

    # 确保队列已初始化
    if wq.webhook_queue_worker is None:
        try:
            from src.infrastructure.notification.discord_adapter import DiscordAdapter
            wq.init_webhook_queue(
                download_manager=download_manager,
                discord_client=DiscordAdapter()
            )
        except Exception as e:
            logger.error(f'初始化 Webhook 队列失败: {e}')
            wq.init_webhook_queue(download_manager=download_manager, discord_client=None)

    # 入队
    evt = wq.webhook_queue_worker.enqueue_event(
        event_type='torrent_finished',
        payload=payload
    )

    logger.api_success(
        f'/api/downloads/{hash_id}/webhook',
        f'已加入队列 queue_id={evt.queue_id}'
    )
    return APIResponse.success(
        message='已加入处理队列',
        queued=True,
        queue_id=evt.queue_id,
        queue_len=wq.webhook_queue_worker.qsize()
    )


@downloads_bp.route('/api/downloads/check-incomplete', methods=['POST'])
@inject
@handle_api_errors
def api_check_incomplete_torrents(
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """檢查未完成的torrents"""
    logger.api_request('检查未完成的torrents')

    download_repo = DownloadRepository()

    # 獲取所有未完成的下載
    incomplete_downloads = download_repo.get_incomplete_downloads()

    checked = 0
    updated = 0
    status_changed = []

    for download in incomplete_downloads:
        result = download_manager.check_torrent_status(download['hash_id'])
        if result.get('success'):
            checked += 1
            if result.get('status') == 'completed':
                updated += 1
                status_changed.append({
                    'hash_id': download['hash_id'],
                    'title': download['anime_title'] or download['original_filename']
                })

    logger.api_success(
        '/api/downloads/check-incomplete',
        f'检查了 {checked} 个, 更新了 {updated} 个'
    )

    return APIResponse.success(
        checked=checked,
        updated=updated,
        status_changed=status_changed
    )


@downloads_bp.route('/api/downloads/webhook-batch', methods=['POST'])
@inject
@handle_api_errors
def api_send_webhook_batch(
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """批量發送webhook給已完成但沒有硬鏈接的torrents（通过队列异步处理）"""
    logger.api_request('批量发送webhook到队列')

    from src.services import webhook_queue as wq

    download_repo = DownloadRepository()

    # 獲取已完成但沒有硬鏈接的下載
    completed_downloads = download_repo.get_completed_downloads_without_hardlinks()

    if not completed_downloads:
        return APIResponse.success(
            message='没有需要处理的下载项',
            queued=0,
            queue_len=0
        )

    # 确保队列已初始化
    if wq.webhook_queue_worker is None:
        try:
            from src.infrastructure.notification.discord_adapter import DiscordAdapter
            wq.init_webhook_queue(
                download_manager=download_manager,
                discord_client=DiscordAdapter()
            )
        except Exception as e:
            logger.error(f'初始化 Webhook 队列失败: {e}')
            wq.init_webhook_queue(download_manager=download_manager, discord_client=None)

    queued_count = 0
    queued_items = []

    for download in completed_downloads:
        # 模擬webhook數據
        payload = WebhookPayload(
            hash_id=download['hash_id'],
            name=download['original_filename'],
            category='',
            save_path=download['download_directory'] or '',
            extra_data={
                'tags': '',
                'content_path': '',
                'root_path': '',
                'tracker': ''
            }
        )

        # 入队
        evt = wq.webhook_queue_worker.enqueue_event(
            event_type='torrent_finished',
            payload=payload
        )
        queued_count += 1
        queued_items.append({
            'hash_id': download['hash_id'],
            'title': download['anime_title'] or download['original_filename'],
            'queue_id': evt.queue_id
        })

    logger.api_success(
        '/api/downloads/webhook-batch',
        f'已加入队列 {queued_count} 个'
    )

    return APIResponse.success(
        message=f'已将 {queued_count} 个项目加入处理队列',
        queued=queued_count,
        queue_len=wq.webhook_queue_worker.qsize(),
        items=queued_items
    )


@downloads_bp.route('/api/downloads/group', methods=['POST'])
@inject
@handle_api_errors
@validate_json('group_by', 'group_name')
def api_delete_group(
    download_manager: DownloadManager = Provide[Container.download_manager]
):
    """刪除分組"""
    data = request.get_json()
    group_by = data.get('group_by', '')
    group_name = data.get('group_name', '')
    delete_source = data.get('delete_source', False)
    delete_hardlinks = data.get('delete_hardlinks', False)

    if not group_by or not group_name:
        return APIResponse.bad_request('缺少分組信息')

    logger.api_request(f'删除分组 - {group_by}:{group_name}')

    download_repo = DownloadRepository()

    # 獲取分組中的所有下載項
    downloads = download_repo.get_downloads_by_group(group_by, group_name)

    total_count = len(downloads)
    source_deleted = 0
    source_failed = 0
    hardlinks_deleted = 0
    hardlinks_failed = 0
    torrents_removed = 0
    db_records_deleted = 0

    for download in downloads:
        try:
            if delete_source or delete_hardlinks:
                result = download_manager.delete_download(
                    download['hash_id'],
                    delete_files=delete_source,
                    delete_hardlinks=delete_hardlinks
                )

                if result.get('success'):
                    if delete_source and result.get('deleted_files'):
                        source_deleted += 1
                        torrents_removed += 1
                        if result.get('moved_to_history'):
                            db_records_deleted += 1

                    if delete_hardlinks and result.get('deleted_hardlinks'):
                        hardlinks_deleted += result.get('hardlinks_deleted_count', 0)
                else:
                    if delete_source:
                        source_failed += 1
                    if delete_hardlinks:
                        hardlinks_failed += 1

        except Exception:
            if delete_source:
                source_failed += 1
            if delete_hardlinks:
                hardlinks_failed += 1

    logger.api_success(
        '/api/downloads/group',
        f'删除分组 - 总数:{total_count}, 源文件:{source_deleted}, 硬链接:{hardlinks_deleted}'
    )

    return APIResponse.success(
        result={
            'total_count': total_count,
            'source_deleted': source_deleted,
            'source_failed': source_failed,
            'hardlinks_deleted': hardlinks_deleted,
            'hardlinks_failed': hardlinks_failed,
            'torrents_removed': torrents_removed,
            'db_records_deleted': db_records_deleted
        }
    )


@downloads_bp.route('/api/download-history/clear', methods=['POST'])
@inject
@handle_api_errors
def api_clear_download_history(
    history_repo: HistoryRepository = Provide[Container.history_repo]
):
    """清空下载历史记录"""
    logger.api_request('清空下载历史')

    deleted_count = history_repo.clear_all_download_history()

    logger.api_success('/api/download-history/clear', f'清空了 {deleted_count} 条记录')

    return APIResponse.success(message=f'成功清空 {deleted_count} 条历史记录')
