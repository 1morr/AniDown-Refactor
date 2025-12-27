"""
配置管理控制器

处理应用程序配置的管理和更新
"""
import json
import os

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.core.config import AppConfig, LanguagePriorityConfig, OpenAIConfig, RSSFeed, config
from src.interface.web.utils import APIResponse, WebLogger, handle_api_errors
from src.services.config_reloader import config_reloader, reload_config

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

    # 保存配置快照（用于检测端口变更）
    config_reloader.snapshot_config()

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

    # 独立 Key Pools 配置
    if 'key_pools' in data:
        try:
            pools_data = json.loads(data['key_pools'] or '[]')
            key_pools = []
            for pool_data in pools_data:
                if isinstance(pool_data, dict) and pool_data.get('name'):
                    # 转换 api_keys 为 KeyPoolEntry 对象
                    api_keys = []
                    for key_data in pool_data.get('api_keys', []):
                        if isinstance(key_data, dict) and key_data.get('api_key'):
                            api_keys.append(OpenAIConfig.KeyPoolEntry(
                                name=key_data.get('name', ''),
                                api_key=key_data.get('api_key', ''),
                                rpm=int(key_data.get('rpm', 0)),
                                rpd=int(key_data.get('rpd', 0)),
                                enabled=bool(key_data.get('enabled', True))
                            ))
                    key_pools.append(OpenAIConfig.KeyPoolDefinition(
                        name=pool_data['name'],
                        base_url=pool_data.get('base_url', 'https://api.openai.com/v1'),
                        model=pool_data.get('model', 'gpt-4'),
                        api_keys=api_keys
                    ))
            config.set('openai.key_pools', key_pools)
        except Exception as e:
            return _handle_config_error(
                is_ajax,
                f'Key Pools 配置解析失败: {e}'
            )

    # 标题解析 Pool 选择
    if 'title_parse_pool_name' in data:
        config.set('openai.title_parse.pool_name', data['title_parse_pool_name'])

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

    # OpenAI - 标题解析超时时间
    if 'openai_title_parse_timeout' in data:
        try:
            timeout = int(data['openai_title_parse_timeout'])
            if timeout < 10 or timeout > 600:
                return _handle_config_error(
                    is_ajax,
                    '标题解析 API 超时时间必须在 10-600 秒之间'
                )
            config.set('openai.title_parse.timeout', timeout)
        except ValueError:
            return _handle_config_error(is_ajax, '标题解析 API 超时时间必须是整数')

    # 语言优先级配置
    if 'language_priorities' in data:
        try:
            priorities_data = json.loads(data['language_priorities'] or '[]')
            priorities = []
            for item in priorities_data:
                if isinstance(item, dict) and item.get('name'):
                    priorities.append(LanguagePriorityConfig(name=item['name']))
                elif isinstance(item, str) and item.strip():
                    priorities.append(LanguagePriorityConfig(name=item.strip()))
            if priorities:
                config.set('openai.language_priorities', priorities)
        except Exception as e:
            return _handle_config_error(
                is_ajax,
                f'语言优先级配置解析失败: {e}'
            )

    # 多文件重命名 Pool 选择
    if 'multi_file_rename_pool_name' in data:
        config.set('openai.multi_file_rename.pool_name', data['multi_file_rename_pool_name'])

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

    # OpenAI - 多文件重命名超时时间
    if 'openai_multi_rename_timeout' in data:
        try:
            timeout = int(data['openai_multi_rename_timeout'])
            if timeout < 10 or timeout > 600:
                return _handle_config_error(
                    is_ajax,
                    '多文件重命名 API 超时时间必须在 10-600 秒之间'
                )
            config.set('openai.multi_file_rename.timeout', timeout)
        except ValueError:
            return _handle_config_error(is_ajax, '多文件重命名 API 超时时间必须是整数')

    # 字幕匹配 Pool 选择
    if 'subtitle_match_pool_name' in data:
        config.set('openai.subtitle_match.pool_name', data['subtitle_match_pool_name'])

    # OpenAI - 字幕匹配配置
    if 'openai_subtitle_match_key' in data:
        config.set('openai.subtitle_match.api_key', data['openai_subtitle_match_key'])

    if 'openai_subtitle_match_model' in data:
        config.set(
            'openai.subtitle_match.model',
            data['openai_subtitle_match_model'] or 'gpt-4'
        )

    if 'openai_subtitle_match_base_url' in data:
        config.set(
            'openai.subtitle_match.base_url',
            data['openai_subtitle_match_base_url'] or 'https://api.openai.com/v1'
        )

    if 'openai_subtitle_match_extra_body' in data:
        extra_body = data['openai_subtitle_match_extra_body'].strip()
        # 验证JSON格式（如果不为空）
        if extra_body:
            try:
                json.loads(extra_body)
                config.set('openai.subtitle_match.extra_body', extra_body)
            except json.JSONDecodeError:
                return _handle_config_error(
                    is_ajax,
                    '字幕匹配 Extra Body 必须是合法的 JSON 格式'
                )
        else:
            config.set('openai.subtitle_match.extra_body', '')

    # OpenAI - 字幕匹配超时时间
    if 'openai_subtitle_match_timeout' in data:
        try:
            timeout = int(data['openai_subtitle_match_timeout'])
            if timeout < 10 or timeout > 600:
                return _handle_config_error(
                    is_ajax,
                    '字幕匹配 API 超时时间必须在 10-600 秒之间'
                )
            config.set('openai.subtitle_match.timeout', timeout)
        except ValueError:
            return _handle_config_error(is_ajax, '字幕匹配 API 超时时间必须是整数')

    # OpenAI - 字幕匹配重试次数
    if 'openai_subtitle_match_retries' in data:
        try:
            retries = int(data['openai_subtitle_match_retries'])
            if retries < 0:
                return _handle_config_error(is_ajax, '字幕匹配重试次数不能为负数')
            config.set('openai.subtitle_match.retries', retries)
        except ValueError:
            return _handle_config_error(is_ajax, '字幕匹配重试次数必须是整数')

    if 'openai_title_parse_retries' in data:
        try:
            retries = int(data['openai_title_parse_retries'])
            if retries < 0:
                return _handle_config_error(is_ajax, 'OpenAI重试次数不能为负数')
            config.set('openai.title_parse.retries', retries)
        except ValueError:
            return _handle_config_error(is_ajax, 'OpenAI重试次数必须是整数')

    # 多文件重命名批处理配置
    if 'ai_max_batch_size' in data:
        try:
            batch_size = int(data['ai_max_batch_size'])
            if batch_size < 1:
                return _handle_config_error(is_ajax, 'AI批处理大小必须大于0')
            config.set('openai.multi_file_rename.max_batch_size', batch_size)
        except ValueError:
            return _handle_config_error(is_ajax, 'AI批处理大小必须是整数')

    if 'ai_batch_processing_retries' in data:
        try:
            retries = int(data['ai_batch_processing_retries'])
            if retries < 0:
                return _handle_config_error(is_ajax, 'AI批处理重试次数不能为负数')
            config.set('openai.multi_file_rename.batch_processing_retries', retries)
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

    # 执行配置热重载
    reload_results, restart_required, restart_items = reload_config()

    # 统计热重载结果
    success_count = sum(1 for v in reload_results.values() if v)
    total_count = len(reload_results)

    # 构建消息
    if restart_required:
        restart_msg = f'以下配置需要重启程序才能生效: {", ".join(restart_items)}'
        if success_count == total_count:
            message = f'配置已保存并重新加载成功。{restart_msg}'
        else:
            message = f'配置已保存，部分组件重新加载失败 ({success_count}/{total_count})。{restart_msg}'
    else:
        if success_count == total_count:
            message = '配置已保存并实时生效'
        else:
            failed_components = [k for k, v in reload_results.items() if not v]
            message = f'配置已保存，部分组件重新加载失败: {", ".join(failed_components)}'

    logger.api_success('/config/update', message)

    # 检查请求是否为 AJAX
    if is_ajax:
        # AJAX 请求，返回 JSON
        return APIResponse.success(
            message=message,
            data={
                'reload_results': reload_results,
                'restart_required': restart_required,
                'restart_items': restart_items
            }
        )
    else:
        # 普通表单提交，使用 flash 和重定向
        flash(message, 'success' if success_count == total_count else 'warning')
        return redirect(url_for('config.config_page'))


def _handle_config_error(is_ajax: bool, message: str):
    """统一处理配置错误"""
    logger.api_error_msg('/config/update', message)
    if is_ajax:
        return APIResponse.bad_request(message)
    else:
        flash(f'保存配置失败: {message}', 'error')
        return redirect(url_for('config.config_page'))


@config_bp.route('/config/reload', methods=['POST'])
@handle_api_errors
def reload_config_from_file():
    """从 config.json 重新加载配置"""
    global config

    logger.api_request('从文件重新加载配置')

    config_path = os.getenv('CONFIG_PATH', 'config.json')

    if not os.path.exists(config_path):
        logger.api_error_msg('/config/reload', f'配置文件不存在: {config_path}')
        return APIResponse.bad_request(f'配置文件不存在: {config_path}')

    try:
        # 从文件加载新配置
        new_config = AppConfig.load(config_path)

        # 更新全局配置对象的所有属性
        for field_name in new_config.model_fields:
            setattr(config, field_name, getattr(new_config, field_name))

        # 执行配置热重载
        reload_results, restart_required, restart_items = reload_config()

        message = '配置已从文件重新加载'
        if restart_required:
            message += f'，以下配置需要重启程序才能生效: {", ".join(restart_items)}'

        logger.api_success('/config/reload', message)

        return APIResponse.success(
            message=message,
            data={
                'reload_results': reload_results,
                'restart_required': restart_required,
                'restart_items': restart_items
            }
        )
    except Exception as e:
        logger.api_error_msg('/config/reload', f'加载配置文件失败: {e}')
        return APIResponse.bad_request(f'加载配置文件失败: {e}')


@config_bp.route('/config/defaults', methods=['GET'])
@handle_api_errors
def get_default_config():
    """获取默认配置值"""
    logger.api_request('获取默认配置')

    try:
        # 创建一个新的默认配置实例
        default_config = AppConfig()

        # 构建返回的默认值字典
        defaults = {
            # RSS 配置
            'rss_interval': default_config.rss.check_interval,

            # qBittorrent 配置
            'qb_url': default_config.qbittorrent.url,
            'qb_username': default_config.qbittorrent.username,
            'qb_password': default_config.qbittorrent.password,
            'qb_path': default_config.qbittorrent.base_download_path,
            'qb_category': default_config.qbittorrent.category,
            'qb_anime_folder': default_config.qbittorrent.anime_folder_name,
            'qb_liveaction_folder': default_config.qbittorrent.live_action_folder_name,
            'qb_tv_folder': default_config.qbittorrent.tv_folder_name,
            'qb_movie_folder': default_config.qbittorrent.movie_folder_name,

            # Discord 配置
            'discord_enabled': default_config.discord.enabled,
            'discord_rss_webhook': default_config.discord.rss_webhook_url or '',
            'discord_hardlink_webhook': default_config.discord.hardlink_webhook_url or '',

            # AI 配置 - 标题解析
            'ai_title_parse_base_url': default_config.openai.title_parse.base_url,
            'ai_title_parse_api_key': default_config.openai.title_parse.api_key,
            'ai_title_parse_model': default_config.openai.title_parse.model,
            'ai_title_parse_timeout': default_config.openai.title_parse.timeout,
            'ai_title_parse_retries': default_config.openai.title_parse.retries,
            'ai_title_parse_extra_body': default_config.openai.title_parse.extra_body,
            'title_parse_pool_name': default_config.openai.title_parse.pool_name,

            # AI 配置 - 多文件重命名
            'ai_multi_rename_base_url': default_config.openai.multi_file_rename.base_url,
            'ai_multi_rename_api_key': default_config.openai.multi_file_rename.api_key,
            'ai_multi_rename_model': default_config.openai.multi_file_rename.model,
            'ai_multi_rename_timeout': default_config.openai.multi_file_rename.timeout,
            'ai_multi_rename_extra_body': default_config.openai.multi_file_rename.extra_body,
            'ai_max_batch_size': default_config.openai.multi_file_rename.max_batch_size,
            'ai_batch_processing_retries': (
                default_config.openai.multi_file_rename.batch_processing_retries
            ),
            'multi_file_rename_pool_name': default_config.openai.multi_file_rename.pool_name,

            # AI 配置 - 字幕匹配
            'ai_subtitle_match_base_url': default_config.openai.subtitle_match.base_url,
            'ai_subtitle_match_api_key': default_config.openai.subtitle_match.api_key,
            'ai_subtitle_match_model': default_config.openai.subtitle_match.model,
            'ai_subtitle_match_timeout': default_config.openai.subtitle_match.timeout,
            'ai_subtitle_match_retries': default_config.openai.subtitle_match.retries,
            'ai_subtitle_match_extra_body': default_config.openai.subtitle_match.extra_body,
            'subtitle_match_pool_name': default_config.openai.subtitle_match.pool_name,

            # 语言优先级
            'language_priorities': [
                lp.name for lp in default_config.openai.language_priorities
            ],

            # 路径配置
            'link_target_path': default_config.link_target_path,
            'movie_link_target_path': default_config.movie_link_target_path,
            'live_action_tv_target_path': default_config.live_action_tv_target_path,
            'live_action_movie_target_path': default_config.live_action_movie_target_path,

            # 命名一致性
            'use_consistent_naming_tv': default_config.use_consistent_naming_tv,
            'use_consistent_naming_movie': default_config.use_consistent_naming_movie,

            # 路径转换
            'path_conversion_enabled': default_config.path_conversion.enabled,
            'path_conversion_source_base': default_config.path_conversion.source_base_path,
            'path_conversion_target_base': default_config.path_conversion.target_base_path,

            # 端口配置
            'webui_port': default_config.webui.port,
            'webhook_port': default_config.webhook.port,

            # TVDB
            'tvdb_api_key': default_config.tvdb.api_key,
        }

        logger.api_success('/config/defaults', '获取默认配置成功')
        return APIResponse.success(data=defaults)

    except Exception as e:
        logger.api_error_msg('/config/defaults', f'获取默认配置失败: {e}')
        return APIResponse.bad_request(f'获取默认配置失败: {e}')
