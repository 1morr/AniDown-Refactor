"""
Web控制器装饰器

提供统一的异常处理、验证等装饰器功能
"""
import functools
import logging
from flask import request
from typing import Callable, List, Any
from .api_response import APIResponse

logger = logging.getLogger(__name__)


def handle_api_errors(f: Callable) -> Callable:
    """
    统一处理API异常的装饰器

    自动捕获常见异常并返回标准化的错误响应：
    - ValueError -> 400 参数错误
    - PermissionError -> 403 权限不足
    - FileNotFoundError -> 404 资源未找到
    - Exception -> 500 服务器错误

    Args:
        f: 被装饰的视图函数

    Returns:
        装饰后的函数

    Example:
        >>> @anime_bp.route('/api/anime/<int:anime_id>')
        >>> @handle_api_errors
        >>> def get_anime(anime_id):
        >>>     anime = repository.get_by_id(anime_id)
        >>>     if not anime:
        >>>         raise FileNotFoundError('动漫不存在')
        >>>     return APIResponse.success(data=anime)
    """
    @functools.wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"⚠️ 参数验证失败 [{request.path}]: {str(e)}")
            return APIResponse.bad_request(f"参数错误: {str(e)}")
        except PermissionError as e:
            logger.warning(f"⚠️ 权限不足 [{request.path}]: {str(e)}")
            return APIResponse.forbidden("权限不足")
        except FileNotFoundError as e:
            logger.error(f"❌ 资源未找到 [{request.path}]: {str(e)}")
            return APIResponse.not_found(str(e))
        except KeyError as e:
            logger.warning(f"⚠️ 缺少必要字段 [{request.path}]: {str(e)}")
            return APIResponse.bad_request(f"缺少必要字段: {str(e)}")
        except Exception as e:
            logger.error(f"❌ API错误 [{request.path}]: {str(e)}", exc_info=True)
            return APIResponse.internal_error(f"服务器错误: {str(e)}")

    return decorated_function


def validate_json(*required_fields: str) -> Callable:
    """
    验证JSON请求体的装饰器

    检查请求是否为JSON格式，并验证必需字段是否存在

    Args:
        *required_fields: 必需的字段名列表

    Returns:
        装饰器函数

    Example:
        >>> @anime_bp.route('/api/anime', methods=['POST'])
        >>> @validate_json('short_title', 'subtitle_group', 'season')
        >>> def create_anime():
        >>>     data = request.get_json()
        >>>     # data中一定包含required_fields
        >>>     return APIResponse.created(data=anime)
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            # 检查是否为JSON请求
            if not request.is_json:
                logger.warning(f"⚠️ 非JSON请求 [{request.path}]")
                return APIResponse.bad_request("请求必须是JSON格式")

            # 获取JSON数据
            data = request.get_json()
            if data is None:
                logger.warning(f"⚠️ JSON解析失败 [{request.path}]")
                return APIResponse.bad_request("无法解析JSON数据")

            # 验证必需字段
            missing = [field for field in required_fields if not data.get(field)]

            if missing:
                logger.warning(
                    f"⚠️ 缺少必要字段 [{request.path}]: {', '.join(missing)}"
                )
                return APIResponse.bad_request(
                    f"缺少必要字段: {', '.join(missing)}"
                )

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_form(*required_fields: str) -> Callable:
    """
    验证表单数据的装饰器

    检查表单中的必需字段是否存在且不为空

    Args:
        *required_fields: 必需的字段名列表

    Returns:
        装饰器函数

    Example:
        >>> @manual_upload_bp.route('/upload', methods=['POST'])
        >>> @validate_form('rss_url', 'short_title')
        >>> def upload():
        >>>     rss_url = request.form.get('rss_url')
        >>>     # rss_url一定存在且不为空
        >>>     return APIResponse.success()
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            # 验证必需字段
            missing = []
            empty = []

            for field in required_fields:
                value = request.form.get(field, '').strip()
                if not value:
                    if field not in request.form:
                        missing.append(field)
                    else:
                        empty.append(field)

            if missing:
                logger.warning(
                    f"⚠️ 缺少表单字段 [{request.path}]: {', '.join(missing)}"
                )
                return APIResponse.bad_request(
                    f"缺少必要字段: {', '.join(missing)}"
                )

            if empty:
                logger.warning(
                    f"⚠️ 表单字段为空 [{request.path}]: {', '.join(empty)}"
                )
                return APIResponse.bad_request(
                    f"以下字段不能为空: {', '.join(empty)}"
                )

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def log_api_call(f: Callable) -> Callable:
    """
    记录API调用的装饰器

    自动记录API的请求和响应信息

    Args:
        f: 被装饰的视图函数

    Returns:
        装饰后的函数

    Example:
        >>> @anime_bp.route('/api/anime')
        >>> @log_api_call
        >>> def get_anime_list():
        >>>     return APIResponse.success(data=anime_list)
    """
    @functools.wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        logger.debug(f"🚀 API请求: {request.method} {request.path}")

        # 记录请求参数
        if request.args:
            logger.debug(f"   查询参数: {dict(request.args)}")
        if request.is_json:
            logger.debug(f"   请求体: {request.get_json()}")

        # 执行函数
        result = f(*args, **kwargs)

        # 记录响应
        if isinstance(result, tuple) and len(result) == 2:
            response, status_code = result
            if 200 <= status_code < 300:
                logger.debug(f"✅ API成功: {request.path} [{status_code}]")
            else:
                logger.warning(f"⚠️ API错误: {request.path} [{status_code}]")
        else:
            logger.debug(f"✅ API完成: {request.path}")

        return result
    return decorated_function


def require_params(*param_names: str) -> Callable:
    """
    验证URL查询参数的装饰器

    检查必需的查询参数是否存在

    Args:
        *param_names: 必需的参数名列表

    Returns:
        装饰器函数

    Example:
        >>> @anime_bp.route('/api/search')
        >>> @require_params('keyword')
        >>> def search():
        >>>     keyword = request.args.get('keyword')
        >>>     # keyword一定存在
        >>>     return APIResponse.success(data=results)
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            missing = [param for param in param_names if not request.args.get(param)]

            if missing:
                logger.warning(
                    f"⚠️ 缺少查询参数 [{request.path}]: {', '.join(missing)}"
                )
                return APIResponse.bad_request(
                    f"缺少必要查询参数: {', '.join(missing)}"
                )

            return f(*args, **kwargs)
        return decorated_function
    return decorator
