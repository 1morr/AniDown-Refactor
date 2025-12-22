"""
动漫管理页面控制器 - Anime Management Controller
"""
from flask import Blueprint, render_template, request
from dependency_injector.wiring import inject, Provide

from src.container import Container
from src.services.anime_service import AnimeService
from src.services.subtitle_service import SubtitleService
from src.interface.web.utils import (
    APIResponse,
    handle_api_errors,
    validate_json,
    RequestValidator,
    ValidationRule,
    WebLogger
)

logger = WebLogger(__name__)
anime_bp = Blueprint('anime', __name__)


@anime_bp.route('/anime')
def anime_page():
    """动漫管理页面"""
    return render_template('anime.html')


@anime_bp.route('/api/anime')
@inject
@handle_api_errors
def api_get_anime_list(
    anime_service: AnimeService = Provide[Container.anime_service]
):
    """获取动漫列表API"""
    # 验证查询参数
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except ValueError:
        return APIResponse.bad_request("页码和每页数量必须是整数")

    if page < 1 or per_page < 1:
        return APIResponse.bad_request("页码和每页数量必须大于0")

    if per_page > 100:
        return APIResponse.bad_request("每页最多100条记录")

    search = request.args.get('search', '').strip()
    sort_column = request.args.get('sort_column', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')
    media_type_filter = request.args.get('media_type_filter', '').strip()
    category_filter = request.args.get('category_filter', '').strip()
    tvdb_filter = request.args.get('tvdb_filter', '').strip()
    group_by = request.args.get('group_by', '').strip()
    viewing_group = request.args.get('viewing_group', '').strip()

    # 验证排序参数
    valid_sort_columns = [
        'created_at', 'short_title', 'full_title', 'subtitle_group',
        'season', 'category', 'media_type'
    ]
    if sort_column not in valid_sort_columns:
        return APIResponse.bad_request(f"无效的排序列: {sort_column}")

    if sort_order not in ['asc', 'desc']:
        return APIResponse.bad_request(f"无效的排序方向: {sort_order}")

    logger.api_request(f"获取动漫列表 - 页码:{page}, 搜索:{search}")

    result = anime_service.get_anime_list_paginated(
        page=page,
        per_page=per_page,
        search=search,
        sort_column=sort_column,
        sort_order=sort_order,
        media_type_filter=media_type_filter,
        category_filter=category_filter,
        tvdb_filter=tvdb_filter,
        group_by=group_by,
        viewing_group=viewing_group
    )

    logger.api_success('/api/anime', f"返回 {len(result.get('anime_list', []))} 条记录")
    # 解包result字典，避免双重嵌套
    return APIResponse.success(**result)


@anime_bp.route('/api/anime/<int:anime_id>')
@inject
@handle_api_errors
def api_get_anime_details(
    anime_id: int,
    anime_service: AnimeService = Provide[Container.anime_service]
):
    """获取动漫详情API"""
    if anime_id < 1:
        return APIResponse.bad_request("动漫ID必须大于0")

    logger.api_request(f"获取动漫详情 - ID:{anime_id}")

    result = anime_service.get_anime_details(anime_id)

    if 'error' in result:
        logger.api_error_msg(f'/api/anime/{anime_id}', result['error'])
        return APIResponse.not_found(result['error'])

    logger.api_success(f'/api/anime/{anime_id}')
    # 解包result字典
    if isinstance(result, dict):
        return APIResponse.success(**result)
    return APIResponse.success(data=result)


@anime_bp.route('/api/anime/<int:anime_id>/folders')
@inject
@handle_api_errors
def api_get_anime_folders(
    anime_id: int,
    anime_service: AnimeService = Provide[Container.anime_service]
):
    """获取动漫文件夹路径API（用于删除预览）"""
    if anime_id < 1:
        return APIResponse.bad_request("动漫ID必须大于0")

    logger.api_request(f"获取动漫文件夹 - ID:{anime_id}")

    result = anime_service.get_anime_folders(anime_id)

    if 'error' in result:
        logger.api_error_msg(f'/api/anime/{anime_id}/folders', result['error'])
        return APIResponse.not_found(result['error'])

    logger.api_success(f'/api/anime/{anime_id}/folders')
    # 解包result字典
    if isinstance(result, dict):
        return APIResponse.success(**result)
    return APIResponse.success(data=result)


@anime_bp.route('/api/anime/<int:anime_id>/delete', methods=['POST'])
@inject
@handle_api_errors
@validate_json()
def api_delete_anime(
    anime_id: int,
    anime_service: AnimeService = Provide[Container.anime_service]
):
    """删除动漫API"""
    if anime_id < 1:
        return APIResponse.bad_request("动漫ID必须大于0")

    data = request.get_json()

    # 验证布尔值参数
    delete_original = data.get('delete_original', False)
    delete_hardlinks = data.get('delete_hardlinks', False)
    delete_from_database = data.get('delete_from_database', False)

    if not isinstance(delete_original, bool):
        return APIResponse.bad_request("delete_original必须是布尔值")
    if not isinstance(delete_hardlinks, bool):
        return APIResponse.bad_request("delete_hardlinks必须是布尔值")
    if not isinstance(delete_from_database, bool):
        return APIResponse.bad_request("delete_from_database必须是布尔值")

    logger.api_request(
        f"删除动漫 - ID:{anime_id}, "
        f"原始文件:{delete_original}, 硬链接:{delete_hardlinks}, 数据库:{delete_from_database}"
    )

    result = anime_service.delete_anime_files(
        anime_id=anime_id,
        delete_original=delete_original,
        delete_hardlinks=delete_hardlinks,
        delete_from_database=delete_from_database
    )

    if result.get('success'):
        logger.api_success(f'/api/anime/{anime_id}/delete', result.get('message', '删除成功'))
        return APIResponse.success(
            message=result.get('message', '删除成功'),
            deleted_files=result.get('deleted_files', []),
            deleted_folders=result.get('deleted_folders', [])
        )
    else:
        error_msg = result.get('error', '删除失败')
        logger.api_error_msg(f'/api/anime/{anime_id}/delete', error_msg)
        return APIResponse.internal_error(error_msg)


@anime_bp.route('/api/anime/<int:anime_id>/rebuild-regex', methods=['POST'])
@inject
@handle_api_errors
def api_rebuild_regex(
    anime_id: int,
    anime_service: AnimeService = Provide[Container.anime_service]
):
    """重建正则表达式API"""
    if anime_id < 1:
        return APIResponse.bad_request("动漫ID必须大于0")

    logger.api_request(f"重建正则表达式 - ID:{anime_id}")

    result = anime_service.rebuild_regex_patterns(anime_id)

    if result.get('success'):
        logger.api_success(f'/api/anime/{anime_id}/rebuild-regex', result.get('message'))
        return APIResponse.success(
            message=result.get('message', '重建成功'),
            patterns=result.get('patterns', {})
        )
    else:
        error_msg = result.get('error', '重建失败')
        logger.api_error_msg(f'/api/anime/{anime_id}/rebuild-regex', error_msg)
        return APIResponse.internal_error(error_msg)


@anime_bp.route('/api/anime/<int:anime_id>', methods=['PUT'])
@inject
@handle_api_errors
@validate_json()
def api_update_anime(
    anime_id: int,
    anime_service: AnimeService = Provide[Container.anime_service]
):
    """更新动漫信息API"""
    if anime_id < 1:
        return APIResponse.bad_request("动漫ID必须大于0")

    data = request.get_json()

    # 验证更新数据
    validation_rules = {}

    if 'short_title' in data:
        validation_rules['short_title'] = ValidationRule(
            required=True,
            min_length=1,
            max_length=200
        )

    if 'full_title' in data:
        validation_rules['full_title'] = ValidationRule(
            max_length=500
        )

    if 'season' in data:
        validation_rules['season'] = ValidationRule(
            required=True,
            min_value=1,
            max_value=100
        )

    if 'category' in data:
        validation_rules['category'] = ValidationRule(
            required=True,
            choices=['tv', 'movie']
        )

    if 'media_type' in data:
        validation_rules['media_type'] = ValidationRule(
            required=True,
            choices=['anime', 'live_action']
        )

    # 执行验证
    if validation_rules:
        error = RequestValidator.validate(data, validation_rules)
        if error:
            return APIResponse.bad_request(error)

    logger.api_request(f"更新动漫信息 - ID:{anime_id}, 字段:{list(data.keys())}")

    result = anime_service.update_anime_info(anime_id, data)

    if result.get('success'):
        logger.api_success(f'/api/anime/{anime_id}', '更新成功')
        return APIResponse.success(
            message='更新成功',
            updated_fields=list(data.keys())
        )
    else:
        error_msg = result.get('error', '更新失败')
        logger.api_error_msg(f'/api/anime/{anime_id}', error_msg)
        return APIResponse.internal_error(error_msg)


@anime_bp.route('/api/anime/stats')
@inject
@handle_api_errors
def api_get_anime_stats(
    anime_service: AnimeService = Provide[Container.anime_service]
):
    """获取动漫统计信息API"""
    logger.api_request("获取动漫统计信息")

    total_count = anime_service.count_all()
    type_counts = anime_service.count_by_media_type()

    logger.api_success('/api/anime/stats', f"总数:{total_count}")

    return APIResponse.success(
        total_count=total_count,
        type_counts=type_counts
    )


# =============================================================================
# 字幕管理 API
# =============================================================================


@anime_bp.route('/api/anime/<int:anime_id>/subtitles')
@inject
@handle_api_errors
def api_get_subtitles(
    anime_id: int,
    subtitle_service: SubtitleService = Provide[Container.subtitle_service]
):
    """
    获取动漫字幕列表 API。

    Args:
        anime_id: 动漫ID

    Returns:
        字幕列表和影片列表
    """
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    logger.api_request(f'获取字幕列表 - 动漫ID:{anime_id}')

    result = subtitle_service.get_subtitles_for_anime(anime_id)

    logger.api_success(
        f'/api/anime/{anime_id}/subtitles',
        f'字幕数:{result.get("total_subtitles", 0)}'
    )

    return APIResponse.success(**result)


@anime_bp.route('/api/anime/<int:anime_id>/subtitles/match', methods=['POST'])
@inject
@handle_api_errors
def api_match_subtitles(
    anime_id: int,
    anime_service: AnimeService = Provide[Container.anime_service],
    subtitle_service: SubtitleService = Provide[Container.subtitle_service]
):
    """
    AI 匹配字幕 API。

    上传字幕压缩档，AI 自动匹配影片和字幕。

    Args:
        anime_id: 动漫ID

    Form Data:
        archive: 压缩档文件 (zip, rar, 7z)

    Returns:
        匹配结果
    """
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    # 检查文件上传
    if 'archive' not in request.files:
        return APIResponse.bad_request('请上传字幕压缩档')

    file = request.files['archive']
    if file.filename == '':
        return APIResponse.bad_request('请选择文件')

    # 检查文件扩展名
    allowed_extensions = {'.zip', '.rar', '.7z', '.tar', '.gz'}
    import os
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        return APIResponse.bad_request(
            f'不支持的文件格式: {ext}。支持格式: {", ".join(allowed_extensions)}'
        )

    logger.api_request(f'AI匹配字幕 - 动漫ID:{anime_id}, 文件:{file.filename}')

    # 获取动漫标题（用于 AI 上下文）
    anime_details = anime_service.get_anime_details(anime_id)
    anime_title = anime_details.get('short_title', None)

    # 读取文件内容
    archive_content = file.read()

    # 调用服务处理
    result = subtitle_service.process_subtitle_archive(
        anime_id=anime_id,
        archive_content=archive_content,
        archive_name=file.filename,
        anime_title=anime_title
    )

    if result.get('success'):
        logger.api_success(
            f'/api/anime/{anime_id}/subtitles/match',
            f'匹配成功:{result.get("total_matched", 0)}个'
        )
        return APIResponse.success(**result)
    else:
        error_msg = result.get('error', 'AI匹配失败')
        logger.api_error_msg(f'/api/anime/{anime_id}/subtitles/match', error_msg)
        return APIResponse.internal_error(error_msg)


@anime_bp.route('/api/anime/<int:anime_id>/subtitles/<int:subtitle_id>', methods=['DELETE'])
@inject
@handle_api_errors
def api_delete_subtitle(
    anime_id: int,
    subtitle_id: int,
    subtitle_service: SubtitleService = Provide[Container.subtitle_service]
):
    """
    删除字幕记录 API。

    Args:
        anime_id: 动漫ID
        subtitle_id: 字幕记录ID

    Query Params:
        delete_file: 是否同时删除文件 (默认 true)

    Returns:
        删除结果
    """
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')
    if subtitle_id < 1:
        return APIResponse.bad_request('字幕ID必须大于0')

    # 获取查询参数
    delete_file_str = request.args.get('delete_file', 'true').lower()
    delete_file = delete_file_str in ('true', '1', 'yes')

    logger.api_request(
        f'删除字幕 - 动漫ID:{anime_id}, 字幕ID:{subtitle_id}, 删除文件:{delete_file}'
    )

    result = subtitle_service.delete_subtitle(subtitle_id, delete_file=delete_file)

    if result.get('success'):
        logger.api_success(f'/api/anime/{anime_id}/subtitles/{subtitle_id}', '删除成功')
        return APIResponse.success(message='字幕删除成功', **result)
    else:
        error_msg = result.get('error', '删除失败')
        logger.api_error_msg(f'/api/anime/{anime_id}/subtitles/{subtitle_id}', error_msg)
        return APIResponse.internal_error(error_msg)
