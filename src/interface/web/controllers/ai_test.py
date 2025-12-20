"""
AI 测试工具控制器

提供 AI 提示词测试和调试功能
"""
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response, stream_with_context
)
from dependency_injector.wiring import inject, Provide
import json
from datetime import datetime

from src.core.config import config
from src.container import Container
from src.infrastructure.ai.prompts import (
    TITLE_PARSE_SYSTEM_PROMPT,
    MULTI_FILE_RENAME_WITH_TVDB_PROMPT,
    MULTI_FILE_RENAME_STANDARD_PROMPT
)
from src.services.rss_service import RSSService
from src.services.metadata_service import MetadataService
from src.services.ai_debug_service import ai_debug_service
from src.infrastructure.metadata.tvdb_adapter import TVDBAdapter
from src.interface.web.utils import (
    APIResponse,
    handle_api_errors,
    validate_json,
    WebLogger
)

ai_test_bp = Blueprint('ai_test', __name__)
logger = WebLogger(__name__)


@ai_test_bp.route('/ai_test')
def ai_test_page():
    """AI测试页面"""
    try:
        # 从 prompts.py 获取默认的系统提示词
        default_system_prompt = TITLE_PARSE_SYSTEM_PROMPT

        return render_template(
            'ai_test.html',
            config=config,
            system_prompt=default_system_prompt,
            multi_file_tvdb_prompt=MULTI_FILE_RENAME_WITH_TVDB_PROMPT,
            multi_file_standard_prompt=MULTI_FILE_RENAME_STANDARD_PROMPT
        )

    except Exception as e:
        logger.api_error_msg('/ai_test', f'访问AI测试页面失败: {str(e)}')
        flash(f'访问AI测试页面失败: {str(e)}', 'error')
        return redirect(url_for('dashboard.dashboard'))


@ai_test_bp.route('/ai_test/process', methods=['POST'])
@inject
@handle_api_errors
@validate_json()
def process_ai_test(
    rss_service: RSSService = Provide[Container.rss_service]
):
    """处理AI测试请求 (非流式)"""
    import requests as http_requests

    data = request.get_json()

    prompt_template = (data.get('prompt_template') or 'title_parse').strip()
    purpose = (
        'multi_file_rename' if prompt_template.startswith('multi_file')
        else 'title_parse'
    )
    cfg_prefix = (
        'openai.multi_file_rename' if purpose == 'multi_file_rename'
        else 'openai.title_parse'
    )

    input_type = (data.get('input_type') or 'rss').strip()
    ai_model = (data.get('model') or config.get(f'{cfg_prefix}.model', 'gpt-4')).strip()
    base_url = (data.get('base_url') or '').strip() or None
    api_key = (
        (data.get('api_key') or '').strip() or
        config.get(f'{cfg_prefix}.api_key', '')
    )
    system_prompt = (data.get('system_prompt') or '').strip()
    content = (data.get('content') or '').strip()
    enable_logging = data.get('enable_logging', True)

    # 获取新增参数
    temperature = data.get('temperature')
    if temperature is not None:
        try:
            temperature = float(temperature)
        except (ValueError, TypeError):
            temperature = None

    extra_body_str = data.get('extra_body')
    extra_body = None
    if extra_body_str:
        try:
            if isinstance(extra_body_str, str):
                extra_body = json.loads(extra_body_str)
            elif isinstance(extra_body_str, dict):
                extra_body = extra_body_str
        except json.JSONDecodeError:
            return APIResponse.bad_request('Extra Body 必须是合法的 JSON 格式')

    # 验证输入类型
    if input_type not in ['rss', 'manual']:
        return APIResponse.bad_request("input_type必须是'rss'或'manual'")

    if not system_prompt:
        return APIResponse.bad_request('请输入系统提示词')

    if not content:
        return APIResponse.bad_request('请输入内容')

    logger.api_request(
        f"AI测试 - 模板:{prompt_template}, 模式:{input_type}, 模型:{ai_model}"
    )

    titles = []
    rss_items = []

    # 根据输入模式处理
    if input_type == 'rss':
        logger.processing_start(f"解析RSS: {content}")
        rss_items = rss_service.parse_rss_feed(content)

        if not rss_items:
            return APIResponse.bad_request('无法解析RSS feed或feed为空')

        titles = [item.get('title', '') for item in rss_items if item.get('title')]
        if not titles:
            return APIResponse.bad_request('RSS feed中没有找到有效的标题')

        logger.processing_success(f"解析RSS成功，找到 {len(titles)} 个标题")

    else:  # manual
        titles = [line.strip() for line in content.split('\n') if line.strip()]
        if not titles:
            return APIResponse.bad_request('请输入至少一个有效的动漫标题')

        logger.processing_start(f"手动模式处理 {len(titles)} 个标题")

    # 获取实际使用的 base_url
    actual_base_url = (
        base_url or
        config.get(f'{cfg_prefix}.base_url', 'https://api.openai.com/v1')
    ).rstrip('/')

    # 构建用户消息
    user_message = "\n".join(titles[:5])  # 限制最多5个标题
    total_tokens = 0
    results = []

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": ai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        }

        if temperature is not None:
            payload["temperature"] = temperature

        if extra_body:
            # 避免覆盖关键参数
            for k in ['model', 'messages', 'temperature', 'stream']:
                if k in extra_body:
                    del extra_body[k]
            payload.update(extra_body)

        response = http_requests.post(
            f"{actual_base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            return APIResponse.error(
                f"API请求失败: {response.status_code} - {response.text}"
            )

        result = response.json()
        ai_content = result['choices'][0]['message']['content'].strip()
        total_tokens = result.get('usage', {}).get('total_tokens', 0)

        # 尝试解析JSON响应
        try:
            import re
            # 清理markdown代码块
            if ai_content.startswith('```json'):
                ai_content = ai_content[7:]
            if ai_content.startswith('```'):
                ai_content = ai_content[3:]
            if ai_content.endswith('```'):
                ai_content = ai_content[:-3]
            ai_content = ai_content.strip()

            parsed_result = json.loads(ai_content)
            results = [{
                'title': user_message,
                'result': parsed_result,
                'status': 'success'
            }]
        except json.JSONDecodeError:
            # 如果不是JSON，直接返回原始文本
            results = [{
                'title': user_message,
                'result': ai_content,
                'status': 'success'
            }]

    except http_requests.exceptions.Timeout:
        return APIResponse.error("请求超时，请检查网络连接或稍后重试")
    except http_requests.exceptions.ConnectionError:
        return APIResponse.error("连接失败，请检查API地址是否正确")
    except Exception as e:
        logger.processing_error("AI API调用", e)
        results = [{
            'title': user_message,
            'error': str(e),
            'status': 'error'
        }]

    # 记录到AI debug日志
    if enable_logging:
        try:
            was_enabled = ai_debug_service.enabled
            ai_debug_service.enable()

            ai_debug_service.log_ai_interaction(
                system_prompt=system_prompt,
                user_prompt=f"输入模式: {input_type}\n内容:\n{user_message}",
                ai_response={'results': results},
                model=ai_model,
                context={
                    'test_type': 'ai_test_page',
                    'input_type': input_type,
                    'base_url': actual_base_url,
                    'titles_count': len(titles),
                    'processed_count': len(results),
                    'total_tokens': total_tokens,
                    'timestamp': datetime.now().isoformat()
                }
            )

            if not was_enabled:
                ai_debug_service.disable()

        except Exception as log_error:
            logger.api_error_msg(
                '/ai_test/process',
                f'日志记录失败: {str(log_error)}'
            )

    logger.api_success(
        '/ai_test/process',
        f"处理完成 - 成功:{sum(1 for r in results if r['status'] == 'success')}/{len(results)}"
    )

    return APIResponse.success(
        results=results,
        titles_count=len(titles),
        processed_count=len(results),
        input_type=input_type,
        model=ai_model,
        tokens=total_tokens,
        message=f'成功处理 {len(results)} 个标题'
    )


@ai_test_bp.route('/ai_test/process_stream', methods=['POST'])
@inject
def process_ai_test_stream(
    rss_service: RSSService = Provide[Container.rss_service]
):
    """处理AI测试请求 (流式传输)"""
    import requests as http_requests

    try:
        data = request.get_json()

        prompt_template = (data.get('prompt_template') or 'title_parse').strip()
        anime_title = (data.get('anime_title') or '').strip()
        purpose = (
            'multi_file_rename'
            if (prompt_template.startswith('multi_file') or anime_title)
            else 'title_parse'
        )
        cfg_prefix = (
            'openai.multi_file_rename' if purpose == 'multi_file_rename'
            else 'openai.title_parse'
        )

        input_type = (data.get('input_type') or 'rss').strip()
        ai_model = (
            data.get('model') or
            config.get(f'{cfg_prefix}.model', 'gpt-4')
        ).strip()
        base_url = (
            (data.get('base_url') or '').strip() or
            config.get(f'{cfg_prefix}.base_url', 'https://api.openai.com/v1')
        ).rstrip('/')
        custom_api_key = (data.get('api_key') or '').strip() or None
        system_prompt = (data.get('system_prompt') or '').strip()
        content = (data.get('content') or '').strip()
        enable_logging = data.get('enable_logging', True)

        # 获取新增参数
        temperature = data.get('temperature')
        if temperature is not None:
            try:
                temperature = float(temperature)
            except (ValueError, TypeError):
                temperature = None

        extra_body_str = data.get('extra_body')
        extra_body = None
        if extra_body_str:
            try:
                if isinstance(extra_body_str, str):
                    extra_body = json.loads(extra_body_str)
                elif isinstance(extra_body_str, dict):
                    extra_body = extra_body_str
            except json.JSONDecodeError:
                return Response(
                    f'data: {json.dumps({"type": "error", "error": "Extra Body 必须是合法的 JSON 格式"})}\n\n',
                    mimetype='text/event-stream'
                )

        # 新增参数
        anime_type = (data.get('anime_type') or 'tv').strip()
        tvdb_id = (data.get('tvdb_id') or '').strip()

        # 验证输入
        if input_type not in ['rss', 'manual']:
            return Response(
                f'data: {json.dumps({"type": "error", "error": "input_type必须是rss或manual"})}\n\n',
                mimetype='text/event-stream'
            )

        if not system_prompt:
            return Response(
                f'data: {json.dumps({"type": "error", "error": "请输入系统提示词"})}\n\n',
                mimetype='text/event-stream'
            )

        if not content:
            return Response(
                f'data: {json.dumps({"type": "error", "error": "请输入内容"})}\n\n',
                mimetype='text/event-stream'
            )

        logger.api_request(
            f"AI测试(流式) - 模板:{prompt_template}, 模式:{input_type}, 模型:{ai_model}"
        )

        # 解析输入内容
        titles = []
        if input_type == 'rss':
            rss_items = rss_service.parse_rss_feed(content)
            if not rss_items:
                return Response(
                    f'data: {json.dumps({"type": "error", "error": "无法解析RSS feed或feed为空"})}\n\n',
                    mimetype='text/event-stream'
                )
            titles = [
                item.get('title', '') for item in rss_items
                if item.get('title')
            ]
        else:
            titles = [line.strip() for line in content.split('\n') if line.strip()]

        if not titles:
            return Response(
                f'data: {json.dumps({"type": "error", "error": "没有找到有效的标题"})}\n\n',
                mimetype='text/event-stream'
            )

        # 获取API密钥
        api_key = custom_api_key or config.get(f'{cfg_prefix}.api_key', '')
        if not api_key:
            return Response(
                f'data: {json.dumps({"type": "error", "error": "API密钥未配置"})}\n\n',
                mimetype='text/event-stream'
            )

        def generate():
            """流式生成响应"""
            full_response = ""
            full_thinking = ""
            total_tokens = 0

            try:
                # 构建用户消息
                if anime_title:
                    # 尝试获取TVDB信息
                    tvdb_data = None
                    if tvdb_id:
                        try:
                            metadata_service = MetadataService(TVDBAdapter())
                            tvdb_data = metadata_service.get_tvdb_data_by_id(
                                int(tvdb_id), ignore_enabled_check=True
                            )
                        except Exception as e:
                            logger.error(f"获取TVDB数据失败: {e}")

                    user_data = {
                        "files": titles,
                        "category": anime_type,
                        "tvdb_info": tvdb_data,
                        "anime_title": anime_title
                    }
                    user_message = json.dumps(user_data, ensure_ascii=False)
                else:
                    user_message = "\n".join(titles[:5])

                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }

                payload = {
                    "model": ai_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "stream": True,
                    "stream_options": {"include_usage": True}
                }

                if temperature is not None:
                    payload["temperature"] = temperature

                if extra_body:
                    for k in ['model', 'messages', 'stream', 'stream_options']:
                        if k in extra_body:
                            del extra_body[k]

                    if 'temperature' in extra_body and temperature is not None:
                        del extra_body['temperature']

                    payload.update(extra_body)

                response = http_requests.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=120
                )

                if response.status_code != 200:
                    error_msg = f"API请求失败: {response.status_code} - {response.text}"
                    yield f'data: {json.dumps({"type": "error", "error": error_msg})}\n\n'
                    return

                for line in response.iter_lines():
                    if line:
                        line_text = line.decode('utf-8')
                        if line_text.startswith('data: '):
                            data_content = line_text[6:]

                            if data_content == '[DONE]':
                                break

                            try:
                                chunk = json.loads(data_content)

                                if 'choices' in chunk and len(chunk['choices']) > 0:
                                    choice = chunk['choices'][0]
                                    delta = choice.get('delta', {})

                                    if 'reasoning_content' in delta and delta['reasoning_content']:
                                        thinking_text = delta['reasoning_content']
                                        full_thinking += thinking_text
                                        yield f'data: {json.dumps({"type": "thinking", "content": thinking_text})}\n\n'

                                    if 'content' in delta and delta['content']:
                                        content_text = delta['content']
                                        full_response += content_text
                                        yield f'data: {json.dumps({"type": "content", "content": content_text})}\n\n'

                                    if choice.get('finish_reason'):
                                        break

                                if 'usage' in chunk and chunk['usage']:
                                    total_tokens = chunk['usage'].get('total_tokens', 0)

                            except json.JSONDecodeError:
                                continue

                if total_tokens == 0 and (full_response or full_thinking):
                    total_chars = (
                        len(full_response) + len(full_thinking) +
                        len(system_prompt) + len(user_message)
                    )
                    total_tokens = max(1, total_chars // 2)

                yield f'data: {json.dumps({"type": "done", "tokens": total_tokens})}\n\n'
                yield 'data: [DONE]\n\n'

                if enable_logging:
                    try:
                        was_enabled = ai_debug_service.enabled
                        ai_debug_service.enable()

                        ai_debug_service.log_ai_interaction(
                            system_prompt=system_prompt,
                            user_prompt=f"输入模式: {input_type}\n标题列表:\n{user_message}",
                            ai_response={
                                'thinking_process': full_thinking,
                                'final_response': full_response,
                                'streaming': True
                            },
                            model=ai_model,
                            context={
                                'test_type': 'ai_test_page_streaming',
                                'input_type': input_type,
                                'base_url': base_url,
                                'titles_count': len(titles),
                                'total_tokens': total_tokens,
                                'timestamp': datetime.now().isoformat()
                            }
                        )

                        if not was_enabled:
                            ai_debug_service.disable()

                    except Exception as log_error:
                        logger.api_error_msg(
                            '/ai_test/process_stream',
                            f'日志记录失败: {str(log_error)}'
                        )

            except http_requests.exceptions.Timeout:
                error_msg = "请求超时，请检查网络连接或稍后重试"
                logger.api_error_msg('/ai_test/process_stream', '流式处理超时')
                yield f'data: {json.dumps({"type": "error", "error": error_msg})}\n\n'

            except http_requests.exceptions.ConnectionError:
                error_msg = "连接失败，请检查API地址是否正确"
                logger.api_error_msg('/ai_test/process_stream', '流式处理连接失败')
                yield f'data: {json.dumps({"type": "error", "error": error_msg})}\n\n'

            except Exception as e:
                error_msg = str(e)
                logger.api_error_msg(
                    '/ai_test/process_stream',
                    f'流式处理失败: {error_msg}'
                )

                if enable_logging:
                    try:
                        was_enabled = ai_debug_service.enabled
                        ai_debug_service.enable()

                        ai_debug_service.log_ai_interaction(
                            system_prompt=system_prompt,
                            user_prompt=f"输入模式: {input_type}\n内容: {content[:500]}...",
                            ai_response=None,
                            model=ai_model,
                            context={
                                'test_type': 'ai_test_page_streaming',
                                'input_type': input_type,
                                'base_url': base_url,
                                'timestamp': datetime.now().isoformat()
                            },
                            error=error_msg
                        )

                        if not was_enabled:
                            ai_debug_service.disable()

                    except Exception:
                        pass

                yield f'data: {json.dumps({"type": "error", "error": error_msg})}\n\n'

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        logger.api_error_msg('/ai_test/process_stream', f'请求处理失败: {str(e)}')
        return Response(
            f'data: {json.dumps({"type": "error", "error": str(e)})}\n\n',
            mimetype='text/event-stream'
        )


@ai_test_bp.route('/ai_test/prompts', methods=['GET'])
def get_available_prompts():
    """获取可用的提示词模板列表"""
    try:
        prompts = {
            'title_parse': {
                'name': '标题解析 (Title Parse)',
                'description': '解析动漫文件名，提取标题、字幕组、集数等信息',
                'prompt': TITLE_PARSE_SYSTEM_PROMPT
            },
            'multi_file_tvdb': {
                'name': '多文件重命名 - TVDB版',
                'description': '使用TVDB数据辅助进行多文件重命名',
                'prompt': MULTI_FILE_RENAME_WITH_TVDB_PROMPT
            },
            'multi_file_standard': {
                'name': '多文件重命名 - 标准版',
                'description': '不使用TVDB数据的标准多文件重命名',
                'prompt': MULTI_FILE_RENAME_STANDARD_PROMPT
            }
        }

        return APIResponse.success(prompts=prompts)

    except Exception as e:
        logger.api_error_msg('/ai_test/prompts', f'获取提示词列表失败: {str(e)}')
        return APIResponse.error(f'获取提示词列表失败: {str(e)}')


@ai_test_bp.route('/ai_test/models', methods=['GET'])
def get_available_models():
    """获取可用的模型列表"""
    try:
        models = [
            {'id': 'deepseek-chat', 'name': 'DeepSeek Chat', 'provider': 'DeepSeek'},
            {'id': 'deepseek-reasoner', 'name': 'DeepSeek Reasoner', 'provider': 'DeepSeek'},
            {'id': 'gpt-4', 'name': 'GPT-4', 'provider': 'OpenAI'},
            {'id': 'gpt-4-turbo', 'name': 'GPT-4 Turbo', 'provider': 'OpenAI'},
            {'id': 'gpt-4o', 'name': 'GPT-4o', 'provider': 'OpenAI'},
            {'id': 'gpt-4o-mini', 'name': 'GPT-4o Mini', 'provider': 'OpenAI'},
            {'id': 'gpt-3.5-turbo', 'name': 'GPT-3.5 Turbo', 'provider': 'OpenAI'},
            {'id': 'claude-3-opus', 'name': 'Claude 3 Opus', 'provider': 'Anthropic'},
            {'id': 'claude-3-sonnet', 'name': 'Claude 3 Sonnet', 'provider': 'Anthropic'},
            {'id': 'claude-3-haiku', 'name': 'Claude 3 Haiku', 'provider': 'Anthropic'},
        ]

        default_model = config.get('openai.title_parse.model', 'gpt-4')

        return APIResponse.success(models=models, default=default_model)

    except Exception as e:
        logger.api_error_msg('/ai_test/models', f'获取模型列表失败: {str(e)}')
        return APIResponse.error(f'获取模型列表失败: {str(e)}')


@ai_test_bp.route('/ai_test/logs', methods=['GET'])
def get_ai_test_logs():
    """获取AI测试日志列表"""
    try:
        count = request.args.get('count', 10, type=int)
        logs = ai_debug_service.get_latest_logs(count)

        log_list = []
        for log_path in logs:
            log_data = ai_debug_service.read_log(log_path)
            if log_data:
                log_list.append({
                    'path': log_path,
                    'timestamp': log_data.get('timestamp'),
                    'model': log_data.get('model'),
                    'has_error': log_data.get('error') is not None
                })

        return APIResponse.success(logs=log_list)

    except Exception as e:
        logger.api_error_msg('/ai_test/logs', f'获取日志列表失败: {str(e)}')
        return APIResponse.error(f'获取日志列表失败: {str(e)}')


@ai_test_bp.route('/ai_test/logs/<path:log_file>', methods=['GET'])
def get_ai_test_log_detail(log_file):
    """获取单个AI测试日志详情"""
    try:
        log_data = ai_debug_service.read_log(log_file)

        if log_data:
            return APIResponse.success(log=log_data)
        else:
            return APIResponse.not_found('日志文件不存在')

    except Exception as e:
        logger.api_error_msg(
            f'/ai_test/logs/{log_file}',
            f'获取日志详情失败: {str(e)}'
        )
        return APIResponse.error(f'获取日志详情失败: {str(e)}')
