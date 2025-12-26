"""
Anime detail page controller.

Provides routes for anime detail page and related API endpoints.
"""

import os
from flask import Blueprint, render_template, request
from dependency_injector.wiring import inject, Provide

from src.container import Container
from src.core.config import config
from src.services.anime_detail_service import AnimeDetailService
from src.services.anime_service import AnimeService
from src.interface.web.utils import (
    APIResponse,
    handle_api_errors,
    validate_json,
    WebLogger
)

logger = WebLogger(__name__)
anime_detail_bp = Blueprint('anime_detail', __name__)


@anime_detail_bp.route('/anime/<int:anime_id>')
@inject
def anime_detail_page(
    anime_id: int,
    anime_service: AnimeService = Provide[Container.anime_service]
):
    """Anime detail page."""
    # Get basic anime info for initial render
    result = anime_service.get_anime_details(anime_id)
    anime_info = result.get('anime', {}) if result.get('success') else {}

    return render_template(
        'anime_detail.html',
        anime_id=anime_id,
        anime_info=anime_info
    )


@anime_detail_bp.route('/api/anime/<int:anime_id>/torrents')
@inject
@handle_api_errors
def api_get_anime_torrents(
    anime_id: int,
    anime_detail_service: AnimeDetailService = Provide[Container.anime_detail_service]
):
    """Get all torrents with files for an anime."""
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    logger.api_request(f'获取动漫种子列表 - ID:{anime_id}')

    result = anime_detail_service.get_anime_with_torrents(anime_id)

    if not result.get('success'):
        return APIResponse.not_found(result.get('error', '获取失败'))

    logger.api_success(
        f'/api/anime/{anime_id}/torrents',
        f'返回 {len(result.get("torrents", []))} 个种子'
    )

    return APIResponse.success(**result)


@anime_detail_bp.route('/api/anime/<int:anime_id>/check-existing', methods=['POST'])
@inject
@handle_api_errors
@validate_json('files')
def api_check_existing_hardlinks(
    anime_id: int,
    anime_detail_service: AnimeDetailService = Provide[Container.anime_detail_service]
):
    """Check if selected files have existing hardlinks."""
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    data = request.get_json()
    files = data.get('files', [])

    if not files:
        return APIResponse.bad_request('未选择文件')

    logger.api_request(f'检查已存在硬链接 - ID:{anime_id}, 文件数:{len(files)}')

    result = anime_detail_service.check_existing_hardlinks(anime_id, files)

    if not result.get('success'):
        return APIResponse.internal_error(result.get('error', '检查失败'))

    logger.api_success(
        f'/api/anime/{anime_id}/check-existing',
        f'已存在:{len(result.get("existing_files", []))}, 新文件:{len(result.get("new_files", []))}'
    )

    return APIResponse.success(**result)


@anime_detail_bp.route('/api/anime/<int:anime_id>/process-ai', methods=['POST'])
@inject
@handle_api_errors
@validate_json('files')
def api_process_with_ai(
    anime_id: int,
    anime_detail_service: AnimeDetailService = Provide[Container.anime_detail_service]
):
    """Process selected files with AI (like webhook completion)."""
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    data = request.get_json()
    files = data.get('files', [])
    replace_existing = data.get('replace_existing', False)

    if not files:
        return APIResponse.bad_request('未选择文件')

    logger.api_request(
        f'AI处理文件 - ID:{anime_id}, 文件数:{len(files)}, 替换已有:{replace_existing}'
    )

    # Group files by torrent hash for processing
    from collections import defaultdict
    files_by_hash = defaultdict(list)
    for f in files:
        files_by_hash[f.get('hash_id')].append(f.get('relative_path'))

    # If replace_existing, delete existing hardlinks first
    if replace_existing:
        check_result = anime_detail_service.check_existing_hardlinks(anime_id, files)
        if check_result.get('success') and check_result.get('existing_files'):
            hardlink_ids = [f['hardlink_id'] for f in check_result['existing_files']]
            anime_detail_service.delete_hardlinks_for_files(hardlink_ids)

    # Process each torrent
    results = {
        'processed': [],
        'failed': [],
        'skipped': []
    }

    try:
        # Get the download manager from container
        from src.container import container
        download_manager = container.download_manager()

        for hash_id, file_paths in files_by_hash.items():
            try:
                # Process with download manager (like webhook completion)
                completion_result = download_manager.handle_torrent_completed(hash_id)

                if completion_result.get('success'):
                    results['processed'].extend([
                        {'hash_id': hash_id, 'path': p} for p in file_paths
                    ])
                else:
                    results['failed'].append({
                        'hash_id': hash_id,
                        'error': completion_result.get('message', '处理失败')
                    })

            except Exception as e:
                logger.error(f'处理torrent失败 {hash_id[:8]}: {e}')
                results['failed'].append({
                    'hash_id': hash_id,
                    'error': str(e)
                })

    except Exception as e:
        logger.error(f'AI处理失败: {e}')
        return APIResponse.internal_error(f'处理失败: {str(e)}')

    logger.api_success(
        f'/api/anime/{anime_id}/process-ai',
        f'成功:{len(results["processed"])}, 失败:{len(results["failed"])}'
    )

    return APIResponse.success(
        processed=results['processed'],
        failed=results['failed'],
        skipped=results['skipped'],
        total_processed=len(results['processed']),
        total_failed=len(results['failed'])
    )


@anime_detail_bp.route('/api/anime/<int:anime_id>/hardlinks', methods=['POST'])
@inject
@handle_api_errors
@validate_json('files')
def api_create_anime_hardlinks(
    anime_id: int,
    anime_detail_service: AnimeDetailService = Provide[Container.anime_detail_service]
):
    """Create hardlinks for selected files."""
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    data = request.get_json()
    files = data.get('files', [])
    target_path = data.get('target_path', '').strip()

    if not files:
        return APIResponse.bad_request('未选择文件')

    logger.api_request(f'创建硬链接 - ID:{anime_id}, 文件数:{len(files)}')

    from src.infrastructure.database.session import db_manager
    from src.infrastructure.database.models import AnimeInfo, DownloadStatus, Hardlink

    try:
        with db_manager.session() as session:
            # Get anime info for target path
            anime = session.query(AnimeInfo).filter_by(id=anime_id).first()
            if not anime:
                return APIResponse.not_found('动漫不存在')

            anime_title = anime.short_title or anime.original_title
            media_type = anime.media_type or 'anime'
            category = anime.category or 'tv'

            # Build target directory
            if media_type == 'live_action':
                if category == 'movie':
                    base_target = config.live_action_movie_target_path
                else:
                    base_target = config.live_action_tv_target_path
            else:
                if category == 'movie':
                    base_target = config.movie_link_target_path or config.link_target_path
                else:
                    base_target = config.link_target_path

            # Sanitize title
            sanitized_title = anime_detail_service._sanitize_title(anime_title)
            target_directory = os.path.join(base_target, sanitized_title)

            if target_path:
                target_directory = os.path.join(target_directory, target_path.lstrip('/\\'))

            # Create target directory
            os.makedirs(target_directory, mode=0o775, exist_ok=True)

            created_links = []
            failed_links = []

            for file_data in files:
                hash_id = file_data.get('hash_id')
                relative_path = file_data.get('relative_path')
                custom_name = file_data.get('custom_name', '').strip()

                # Get download info
                download = session.query(DownloadStatus).filter_by(hash_id=hash_id).first()
                if not download:
                    failed_links.append({
                        'file': relative_path,
                        'error': '下载记录不存在'
                    })
                    continue

                # Build source path
                download_dir = download.download_directory
                source_path = os.path.join(download_dir, relative_path)

                if not os.path.exists(source_path):
                    failed_links.append({
                        'file': relative_path,
                        'error': '源文件不存在'
                    })
                    continue

                # Determine target filename
                if custom_name:
                    target_filename = custom_name
                else:
                    target_filename = relative_path.split('/')[-1].split('\\')[-1]

                target_file_path = os.path.join(target_directory, target_filename)

                try:
                    # Create hardlink
                    if os.path.exists(target_file_path):
                        os.remove(target_file_path)

                    os.link(source_path, target_file_path)

                    # Get file size
                    file_size = os.path.getsize(source_path)

                    # Save to database
                    hardlink = Hardlink(
                        anime_id=anime_id,
                        original_file_path=source_path,
                        hardlink_path=target_file_path,
                        file_size=file_size,
                        torrent_hash=hash_id
                    )
                    session.add(hardlink)

                    created_links.append({
                        'original': relative_path,
                        'hardlink': target_file_path
                    })

                except OSError as e:
                    logger.error(f'创建硬链接失败: {e}')
                    failed_links.append({
                        'file': relative_path,
                        'error': str(e)
                    })

            session.commit()

        logger.api_success(
            f'/api/anime/{anime_id}/hardlinks',
            f'创建:{len(created_links)}, 失败:{len(failed_links)}'
        )

        return APIResponse.success(
            created=created_links,
            failed=failed_links,
            total_created=len(created_links),
            total_failed=len(failed_links)
        )

    except Exception as e:
        logger.error(f'创建硬链接失败: {e}')
        return APIResponse.internal_error(f'创建硬链接失败: {str(e)}')


@anime_detail_bp.route('/api/anime/<int:anime_id>/hardlinks/delete', methods=['POST'])
@inject
@handle_api_errors
@validate_json('hardlink_ids')
def api_delete_anime_hardlinks(
    anime_id: int,
    anime_detail_service: AnimeDetailService = Provide[Container.anime_detail_service]
):
    """Delete hardlinks for selected files."""
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    data = request.get_json()
    hardlink_ids = data.get('hardlink_ids', [])

    if not hardlink_ids:
        return APIResponse.bad_request('未选择硬链接')

    logger.api_request(f'删除硬链接 - ID:{anime_id}, 数量:{len(hardlink_ids)}')

    result = anime_detail_service.delete_hardlinks_for_files(hardlink_ids)

    if not result.get('success'):
        return APIResponse.internal_error(result.get('error', '删除失败'))

    logger.api_success(
        f'/api/anime/{anime_id}/hardlinks/delete',
        f'删除:{result.get("deleted_count", 0)}'
    )

    return APIResponse.success(**result)


@anime_detail_bp.route('/api/anime/<int:anime_id>/hardlinks/rename', methods=['POST'])
@inject
@handle_api_errors
@validate_json('renames')
def api_rename_anime_hardlinks(
    anime_id: int
):
    """Rename hardlinks for selected files."""
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    data = request.get_json()
    renames = data.get('renames', [])

    if not renames:
        return APIResponse.bad_request('未提供重命名信息')

    logger.api_request(f'重命名硬链接 - ID:{anime_id}, 数量:{len(renames)}')

    from src.infrastructure.database.session import db_manager
    from src.infrastructure.database.models import Hardlink

    renamed = []
    failed = []

    try:
        with db_manager.session() as session:
            for rename_data in renames:
                hardlink_id = rename_data.get('hardlink_id')
                new_name = rename_data.get('new_name', '').strip()

                if not hardlink_id or not new_name:
                    failed.append({
                        'hardlink_id': hardlink_id,
                        'error': '缺少必要参数'
                    })
                    continue

                hardlink = session.query(Hardlink).filter_by(id=hardlink_id).first()
                if not hardlink:
                    failed.append({
                        'hardlink_id': hardlink_id,
                        'error': '硬链接记录不存在'
                    })
                    continue

                old_path = hardlink.hardlink_path
                new_path = os.path.join(os.path.dirname(old_path), new_name)

                try:
                    if os.path.exists(old_path):
                        os.rename(old_path, new_path)
                        hardlink.hardlink_path = new_path
                        renamed.append({
                            'hardlink_id': hardlink_id,
                            'old_path': old_path,
                            'new_path': new_path
                        })
                    else:
                        failed.append({
                            'hardlink_id': hardlink_id,
                            'error': '文件不存在'
                        })

                except OSError as e:
                    failed.append({
                        'hardlink_id': hardlink_id,
                        'error': str(e)
                    })

            session.commit()

        logger.api_success(
            f'/api/anime/{anime_id}/hardlinks/rename',
            f'重命名:{len(renamed)}, 失败:{len(failed)}'
        )

        return APIResponse.success(
            renamed=renamed,
            failed=failed,
            total_renamed=len(renamed),
            total_failed=len(failed)
        )

    except Exception as e:
        logger.error(f'重命名硬链接失败: {e}')
        return APIResponse.internal_error(f'重命名失败: {str(e)}')


@anime_detail_bp.route('/api/anime/<int:anime_id>/ai-rename-preview', methods=['POST'])
@inject
@handle_api_errors
@validate_json('files')
def api_ai_rename_preview(
    anime_id: int,
    anime_detail_service: AnimeDetailService = Provide[Container.anime_detail_service]
):
    """Get AI rename suggestions and compare with existing hardlinks."""
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    data = request.get_json()
    files = data.get('files', [])

    if not files:
        return APIResponse.bad_request('未选择文件')

    logger.api_request(f'获取AI重命名预览 - ID:{anime_id}, 文件数:{len(files)}')

    result = anime_detail_service.get_ai_rename_preview(anime_id, files)

    if not result.get('success'):
        return APIResponse.internal_error(result.get('error', '获取AI预览失败'))

    logger.api_success(
        f'/api/anime/{anime_id}/ai-rename-preview',
        f'预览项目:{result.get("total_count", 0)}, 已有硬链接:{result.get("existing_count", 0)}'
    )

    return APIResponse.success(**result)


@anime_detail_bp.route('/api/anime/<int:anime_id>/apply-ai-renames', methods=['POST'])
@inject
@handle_api_errors
@validate_json('items')
def api_apply_ai_renames(
    anime_id: int,
    anime_detail_service: AnimeDetailService = Provide[Container.anime_detail_service]
):
    """Apply selected AI rename suggestions to create/replace hardlinks."""
    if anime_id < 1:
        return APIResponse.bad_request('动漫ID必须大于0')

    data = request.get_json()
    items = data.get('items', [])
    target_path = data.get('target_path', '')

    if not items:
        return APIResponse.bad_request('未选择要应用的项目')

    if not target_path:
        return APIResponse.bad_request('未指定目标路径')

    logger.api_request(f'应用AI重命名 - ID:{anime_id}, 项目数:{len(items)}')

    result = anime_detail_service.apply_ai_renames(anime_id, items, target_path)

    if not result.get('success'):
        return APIResponse.internal_error(result.get('error', '应用失败'))

    logger.api_success(
        f'/api/anime/{anime_id}/apply-ai-renames',
        f'创建:{result.get("total_created", 0)}, 替换:{result.get("total_replaced", 0)}, 失败:{result.get("total_failed", 0)}'
    )

    return APIResponse.success(**result)
