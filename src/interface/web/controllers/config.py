"""
配置管理控制器

处理应用程序配置的管理和更新
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
import json

from src.core.config import config, RSSFeed, OpenAIConfig
from src.interface.web.utils import (
    APIResponse,
    handle_api_errors,
    WebLogger
)

config_bp = Blueprint('config', __name__)
logger = WebLogger(__name__)


@config_bp.route('/config')
def config_page():
    """配置管理页面"""
    return render_template('config.html', config=config)


@config_bp.route('/config/update', methods=['POST'])
@handle_api_errors
def update_config():
    """更新配置"""
    # 获取表单数据
    data = request.form
    is_ajax = request.headers.get('Content-Type', '').startswith('multipart/form-data')

    logger.api_request("更新配置")

    # RSS 配置 - 支持新的结构
    if 'rss_feeds' in data:
        try:
            rss_feeds_data = json.loads(data['rss_feeds'])
            rss_feeds = []
            for feed_data in rss_feeds_data:
                if isinstance(feed_data, str):
                    # 向后兼容：纯字符串 URL
                    rss_feeds.append(feed_data)
                else:
                    # 新格式：包含 url, blocked_keywords, blocked_regex
                    rss_feeds.append(RSSFeed(**feed_data))
            config.set('rss.fixed_urls', rss_feeds)
        except json.JSONDecodeError:
            # 如果不是 JSON，尝试旧格式（换行分隔的 URL）
            urls = [url.strip() for url in data['rss_feeds'].split('\n') if url.strip()]
            config.set('rss.fixed_urls', urls)

    if 'rss_interval' in data:
        try:
            interval = int(data['rss_interval'])
            if interval < 1:
                return _handle_config_error(is_ajax, 'RSS检查间隔必须大于0')
            config.set('rss.check_interval', interval)
        except ValueError:
            return _handle_config_error(is_ajax, 'RSS检查间隔必须是整数')

    # qBittorrent 配置
    if 'qb_url' in data:
        config.set('qbittorrent.url', data['qb_url'])

    if 'qb_username' in data:
        config.set('qbittorrent.username', data['qb_username'])

    if 'qb_password' in data:
        config.set('qbittorrent.password', data['qb_password'])

    if 'qb_download_path' in data:
        config.set('qbittorrent.base_download_path', data['qb_download_path'])

    if 'qb_anime_folder' in data:
        config.set('qbittorrent.anime_folder_name', data['qb_anime_folder'])

    if 'qb_liveaction_folder' in data:
        config.set('qbittorrent.live_action_folder_name', data['qb_liveaction_folder'])

    if 'qb_tv_folder' in data:
        config.set('qbittorrent.tv_folder_name', data['qb_tv_folder'])

    if 'qb_movie_folder' in data:
        config.set('qbittorrent.movie_folder_name', data['qb_movie_folder'])

    if 'qb_category' in data:
        config.set('qbittorrent.category', data['qb_category'])

    # Discord 配置
    config.set('discord.enabled', data.get('discord_enabled') == 'on')

    if 'discord_rss_webhook' in data:
        config.set('discord.rss_webhook_url', data['discord_rss_webhook'])

    if 'discord_hardlink_webhook' in data:
        config.set('discord.hardlink_webhook_url', data['discord_hardlink_webhook'])

    # OpenAI - 标题解析配置
    if 'openai_title_parse_key' in data:
        config.set('openai.title_parse.api_key', data['openai_title_parse_key'])

    if 'openai_title_parse_model' in data:
        config.set(
            'openai.title_parse.model',
            data['openai_title_parse_model'] or 'gpt-4'
        )

    if 'openai_title_parse_base_url' in data:
        config.set(
            'openai.title_parse.base_url',
            data['openai_title_parse_base_url'] or 'https://api.openai.com/v1'
        )

    if 'openai_title_parse_extra_body' in data:
        extra_body = data['openai_title_parse_extra_body'].strip()
        # 验证JSON格式（如果不为空）
        if extra_body:
            try:
                json.loads(extra_body)
                config.set('openai.title_parse.extra_body', extra_body)
            except json.JSONDecodeError:
                return _handle_config_error(
                    is_ajax,
                    '标题解析 Extra Body 必须是合法的 JSON 格式'
                )
        else:
            config.set('openai.title_parse.extra_body', '')

    # OpenAI - 标题解析 Key Pool
    if 'openai_title_parse_pool' in data:
        try:
            pool_data = json.loads(data['openai_title_parse_pool'] or '[]')
            pool_entries = []
            for item in pool_data:
                if isinstance(item, dict) and (item.get('api_key') or '').strip():
                    pool_entries.append(OpenAIConfig.APIKeyEntry(**item))
            config.set('openai.title_parse.api_key_pool', pool_entries)
        except Exception as e:
            return _handle_config_error(
                is_ajax,
                f'标题解析 Key Pool 配置解析失败: {e}'
            )

    # OpenAI - 多文件重命名配置
    if 'openai_multi_rename_key' in data:
        config.set('openai.multi_file_rename.api_key', data['openai_multi_rename_key'])

    if 'openai_multi_rename_model' in data:
        config.set(
            'openai.multi_file_rename.model',
            data['openai_multi_rename_model'] or 'gpt-4'
        )

    if 'openai_multi_rename_base_url' in data:
        config.set(
            'openai.multi_file_rename.base_url',
            data['openai_multi_rename_base_url'] or 'https://api.openai.com/v1'
        )

    if 'openai_multi_rename_extra_body' in data:
        extra_body = data['openai_multi_rename_extra_body'].strip()
        # 验证JSON格式（如果不为空）
        if extra_body:
            try:
                json.loads(extra_body)
                config.set('openai.multi_file_rename.extra_body', extra_body)
            except json.JSONDecodeError:
                return _handle_config_error(
                    is_ajax,
                    '多文件重命名 Extra Body 必须是合法的 JSON 格式'
                )
        else:
            config.set('openai.multi_file_rename.extra_body', '')

    # OpenAI - 多文件重命名 Key Pool
    if 'openai_multi_rename_pool' in data:
        try:
            pool_data = json.loads(data['openai_multi_rename_pool'] or '[]')
            pool_entries = []
            for item in pool_data:
                if isinstance(item, dict) and (item.get('api_key') or '').strip():
                    pool_entries.append(OpenAIConfig.APIKeyEntry(**item))
            config.set('openai.multi_file_rename.api_key_pool', pool_entries)
        except Exception as e:
            return _handle_config_error(
                is_ajax,
                f'多文件重命名 Key Pool 配置解析失败: {e}'
            )

    if 'openai_title_parse_retries' in data:
        try:
            retries = int(data['openai_title_parse_retries'])
            if retries < 0:
                return _handle_config_error(is_ajax, 'OpenAI重试次数不能为负数')
            config.set('openai.title_parse_retries', retries)
        except ValueError:
            return _handle_config_error(is_ajax, 'OpenAI重试次数必须是整数')

    # AI 处理配置
    if 'ai_max_batch_size' in data:
        try:
            batch_size = int(data['ai_max_batch_size'])
            if batch_size < 1:
                return _handle_config_error(is_ajax, 'AI批处理大小必须大于0')
            config.set('ai_processing.max_batch_size', batch_size)
        except ValueError:
            return _handle_config_error(is_ajax, 'AI批处理大小必须是整数')

    if 'ai_batch_processing_retries' in data:
        try:
            retries = int(data['ai_batch_processing_retries'])
            if retries < 0:
                return _handle_config_error(is_ajax, 'AI批处理重试次数不能为负数')
            config.set('ai_processing.batch_processing_retries', retries)
        except ValueError:
            return _handle_config_error(is_ajax, 'AI批处理重试次数必须是整数')

    # 路径配置
    if 'link_target_path' in data:
        config.set('link_target_path', data['link_target_path'])

    if 'movie_link_target_path' in data:
        config.set('movie_link_target_path', data['movie_link_target_path'])

    if 'live_action_tv_target_path' in data:
        config.set('live_action_tv_target_path', data['live_action_tv_target_path'])

    if 'live_action_movie_target_path' in data:
        config.set('live_action_movie_target_path', data['live_action_movie_target_path'])

    # 命名一致性配置
    config.set('use_consistent_naming_tv', data.get('use_consistent_naming_tv') == 'on')
    config.set('use_consistent_naming_movie', data.get('use_consistent_naming_movie') == 'on')

    # WebUI 配置
    if 'webui_port' in data:
        try:
            port = int(data['webui_port'])
            if port < 1 or port > 65535:
                return _handle_config_error(is_ajax, 'WebUI端口必须在1-65535之间')
            config.set('webui.port', port)
        except ValueError:
            return _handle_config_error(is_ajax, 'WebUI端口必须是整数')

    # 路径转换配置
    config.set('path_conversion.enabled', data.get('path_conversion_enabled') == 'on')

    if 'path_conversion_source_base' in data:
        config.set('path_conversion.source_base_path', data['path_conversion_source_base'])

    if 'path_conversion_target_base' in data:
        config.set('path_conversion.target_base_path', data['path_conversion_target_base'])

    # Webhook 配置
    if 'webhook_port' in data:
        try:
            port = int(data['webhook_port'])
            if port < 1 or port > 65535:
                return _handle_config_error(is_ajax, 'Webhook端口必须在1-65535之间')
            config.set('webhook.port', port)
        except ValueError:
            return _handle_config_error(is_ajax, 'Webhook端口必须是整数')

    # TVDB 配置 (只保存 API Key，启用开关已移至手动上传页面)
    if 'tvdb_api_key' in data:
        config.set('tvdb.api_key', data['tvdb_api_key'])

    # 保持 max_data_length 的默认值
    if not config.get('tvdb.max_data_length'):
        config.set('tvdb.max_data_length', 10000)

    # 保存配置
    config.save_config()

    logger.api_success('/config/update', '配置已保存成功')

    # 检查请求是否为 AJAX
    if is_ajax:
        # AJAX 请求，返回 JSON
        return APIResponse.success(message='配置已保存成功')
    else:
        # 普通表单提交，使用 flash 和重定向
        flash('配置已保存成功', 'success')
        return redirect(url_for('config.config_page'))


def _handle_config_error(is_ajax: bool, message: str):
    """统一处理配置错误"""
    logger.api_error_msg('/config/update', message)
    if is_ajax:
        return APIResponse.bad_request(message)
    else:
        flash(f'保存配置失败: {message}', 'error')
        return redirect(url_for('config.config_page'))
