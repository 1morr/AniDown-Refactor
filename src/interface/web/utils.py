"""
Web 接口工具模块。

提供 API 响应格式化、日志记录和装饰器。
"""

import functools
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flask import Response, jsonify, request

logger = logging.getLogger(__name__)


@dataclass
class ValidationRule:
    """
    验证规则。

    Attributes:
        required: 是否必填
        min_length: 最小长度
        max_length: 最大长度
        pattern: 正则表达式模式
        choices: 允许的值列表
        min_value: 最小值（用于数字）
        max_value: 最大值（用于数字）
        custom_validator: 自定义验证函数
    """

    required: bool = False
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    choices: list[Any] | None = None
    min_value: float | None = None
    max_value: float | None = None
    custom_validator: Callable | None = None


class RequestValidator:
    """请求数据验证器。"""

    @staticmethod
    def validate(
        data: dict[str, Any],
        rules: dict[str, ValidationRule]
    ) -> str | None:
        """
        验证数据。

        Args:
            data: 待验证的数据字典
            rules: 验证规则字典，键为字段名，值为 ValidationRule

        Returns:
            None if valid, error message if invalid
        """
        for field, rule in rules.items():
            value = data.get(field)

            # 必填验证
            if rule.required and (value is None or value == ''):
                return f"字段 '{field}' 不能为空"

            # 如果值为 None 且非必填，跳过后续验证
            if value is None:
                continue

            # 字符串验证
            if isinstance(value, str):
                if rule.min_length is not None and len(value) < rule.min_length:
                    return f"字段 '{field}' 长度不能小于 {rule.min_length}"

                if rule.max_length is not None and len(value) > rule.max_length:
                    return f"字段 '{field}' 长度不能大于 {rule.max_length}"

                if rule.pattern and not re.match(rule.pattern, value):
                    return f"字段 '{field}' 格式不正确"

            # 数值验证
            if isinstance(value, (int, float)):
                if rule.min_value is not None and value < rule.min_value:
                    return f"字段 '{field}' 的值不能小于 {rule.min_value}"

                if rule.max_value is not None and value > rule.max_value:
                    return f"字段 '{field}' 的值不能大于 {rule.max_value}"

            # 选项验证
            if rule.choices is not None and value not in rule.choices:
                return f"字段 '{field}' 的值必须是 {rule.choices} 之一"

            # 自定义验证
            if rule.custom_validator:
                try:
                    is_valid = rule.custom_validator(value)
                    if not is_valid:
                        return f"字段 '{field}' 验证失败"
                except Exception as e:
                    return f"字段 '{field}' 验证失败: {str(e)}"

        return None


class APIResponse:
    """
    统一 API 响应格式。

    所有 API 端点应使用此类返回响应，确保前端处理的一致性。

    Example:
        >>> return APIResponse.success(data={'id': 1})
        >>> return APIResponse.error('Invalid input')
        >>> return APIResponse.not_found('Anime not found')
    """

    @staticmethod
    def _make_response(
        success: bool,
        data: Any | None = None,
        message: str | None = None,
        code: int = 200,
        **kwargs: Any
    ) -> Response:
        """
        构建统一的响应格式。

        Args:
            success: 操作是否成功
            data: 响应数据
            message: 响应消息
            code: HTTP 状态码
            **kwargs: 其他需要添加到响应中的字段

        Returns:
            Flask Response 对象
        """
        response_body: dict[str, Any] = {'success': success}

        if data is not None:
            response_body['data'] = data

        if message is not None:
            response_body['message'] = message

        # 添加额外的字段（排除已处理的保留字段）
        for key, value in kwargs.items():
            if key not in ('success', 'data', 'message', 'code'):
                response_body[key] = value

        response = jsonify(response_body)
        response.status_code = code
        return response

    @classmethod
    def success(
        cls,
        data: Any | None = None,
        message: str | None = None,
        **kwargs: Any
    ) -> Response:
        """
        成功响应。

        Args:
            data: 响应数据
            message: 成功消息
            **kwargs: 其他需要添加到响应中的字段

        Returns:
            200 OK 响应

        Example:
            >>> return APIResponse.success(data={'id': 1}, message='创建成功')
            >>> return APIResponse.success(anime_list=[...], total=100)
        """
        # 过滤掉保留字段，避免冲突
        filtered_kwargs = {
            k: v for k, v in kwargs.items()
            if k not in ('success', 'data', 'message', 'code')
        }
        return cls._make_response(
            success=True,
            data=data,
            message=message,
            code=200,
            **filtered_kwargs
        )

    @classmethod
    def created(
        cls,
        data: Any | None = None,
        message: str | None = None,
        **kwargs: Any
    ) -> Response:
        """
        资源创建成功响应。

        Args:
            data: 创建的资源数据
            message: 成功消息
            **kwargs: 其他需要添加到响应中的字段

        Returns:
            201 Created 响应
        """
        return cls._make_response(
            success=True,
            data=data,
            message=message,
            code=201,
            **kwargs
        )

    @classmethod
    def error(
        cls,
        message: str,
        code: int = 500,
        **kwargs: Any
    ) -> Response:
        """
        错误响应。

        Args:
            message: 错误消息
            code: HTTP 状态码（默认 500）
            **kwargs: 其他需要添加到响应中的字段

        Returns:
            错误响应
        """
        return cls._make_response(
            success=False,
            message=message,
            code=code,
            **kwargs
        )

    @classmethod
    def bad_request(cls, message: str) -> Response:
        """
        请求参数错误响应。

        Args:
            message: 错误消息

        Returns:
            400 Bad Request 响应
        """
        return cls._make_response(
            success=False,
            message=message,
            code=400
        )

    @classmethod
    def not_found(cls, message: str) -> Response:
        """
        资源未找到响应。

        Args:
            message: 错误消息

        Returns:
            404 Not Found 响应
        """
        return cls._make_response(
            success=False,
            message=message,
            code=404
        )

    @classmethod
    def unauthorized(cls, message: str = '未授权') -> Response:
        """
        未授权响应。

        Args:
            message: 错误消息

        Returns:
            401 Unauthorized 响应
        """
        return cls._make_response(
            success=False,
            message=message,
            code=401
        )

    @classmethod
    def forbidden(cls, message: str = '禁止访问') -> Response:
        """
        禁止访问响应。

        Args:
            message: 错误消息

        Returns:
            403 Forbidden 响应
        """
        return cls._make_response(
            success=False,
            message=message,
            code=403
        )

    @classmethod
    def conflict(cls, message: str) -> Response:
        """
        资源冲突响应。

        Args:
            message: 错误消息

        Returns:
            409 Conflict 响应
        """
        return cls._make_response(
            success=False,
            message=message,
            code=409
        )


def handle_api_errors(f):
    """
    API 错误处理装饰器。

    捕获函数执行中的异常，返回标准化的错误响应。

    Example:
        >>> @app.route('/api/test')
        >>> @handle_api_errors
        >>> def test():
        >>>     raise ValueError('Test error')
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f'⚠️ 请求参数错误: {e}')
            return APIResponse.bad_request(str(e))
        except KeyError as e:
            logger.warning(f'⚠️ 缺少必需参数: {e}')
            return APIResponse.bad_request(f'缺少必需参数: {e}')
        except Exception as e:
            logger.exception(f'❌ API 处理失败: {e}')
            return APIResponse.error(f'服务器内部错误: {str(e)}')
    return decorated_function


class WebLogger:
    """
    Web 控制器日志工具。

    提供标准化的 API 请求/响应日志记录。

    Example:
        >>> logger = WebLogger(__name__)
        >>> logger.api_request('GET /api/anime/1')
        >>> logger.api_success('/api/anime/1', '获取成功')
    """

    def __init__(self, name: str):
        """
        初始化日志工具。

        Args:
            name: 日志记录器名称（通常使用 __name__）
        """
        self._logger = logging.getLogger(name)

    def api_request(self, endpoint: str, method: str = 'GET') -> None:
        """
        记录 API 请求。

        Args:
            endpoint: API 端点
            method: HTTP 方法
        """
        self._logger.debug(f'📥 {method} {endpoint}')

    def api_success(self, endpoint: str, message: str = '成功') -> None:
        """
        记录 API 成功响应。

        Args:
            endpoint: API 端点
            message: 成功消息
        """
        self._logger.info(f'✅ {endpoint}: {message}')

    def api_error_msg(self, endpoint: str, message: str) -> None:
        """
        记录 API 错误响应。

        Args:
            endpoint: API 端点
            message: 错误消息
        """
        self._logger.warning(f'❌ {endpoint}: {message}')

    def api_error(self, endpoint: str, error: Exception) -> None:
        """
        记录 API 异常。

        Args:
            endpoint: API 端点
            error: 异常对象
        """
        self._logger.error(f'❌ {endpoint}: {error}')

    def db_query(self, query_type: str, details: str = '') -> None:
        """
        数据库查询日志。

        Args:
            query_type: 查询类型
            details: 查询详情
        """
        if details:
            self._logger.debug(f'💾 数据库查询: {query_type} - {details}')
        else:
            self._logger.debug(f'💾 数据库查询: {query_type}')

    def db_error(self, operation: str, error: Exception) -> None:
        """
        数据库错误日志。

        Args:
            operation: 操作类型
            error: 异常对象
        """
        self._logger.error(f'❌ 数据库错误: {operation} - {str(error)}', exc_info=True)

    def db_update(self, resource: str, details: str) -> None:
        """
        数据库更新日志。

        Args:
            resource: 资源名称
            details: 更新详情
        """
        self._logger.info(f'💾 数据库更新: {resource} - {details}')

    def processing_start(self, task: str) -> None:
        """
        记录处理任务开始。

        Args:
            task: 任务描述
        """
        self._logger.info(f'🔄 开始处理: {task}')

    def processing_success(self, message: str, details: str = '') -> None:
        """
        记录处理成功。

        Args:
            message: 成功消息
            details: 可选的补充信息
        """
        if details:
            self._logger.info(f'✅ {message} - {details}')
        else:
            self._logger.info(f'✅ {message}')

    def processing_error(self, task: str, error: Exception) -> None:
        """
        记录处理任务错误。

        Args:
            task: 任务描述
            error: 异常对象
        """
        self._logger.error(f'❌ 处理失败: {task} - {str(error)}', exc_info=True)

    def error(self, message: str, error: Exception | None = None) -> None:
        """
        记录错误信息。

        Args:
            message: 错误描述
            error: 异常对象（可选）
        """
        if error:
            self._logger.error(f'❌ 错误: {message} - {str(error)}', exc_info=True)
        else:
            self._logger.error(f'❌ 错误: {message}')

    def warning(self, message: str) -> None:
        """
        记录警告信息。

        Args:
            message: 警告内容
        """
        self._logger.warning(f'⚠️ 警告: {message}')


def validate_json(*required_fields: str) -> Callable:
    """
    验证 JSON 请求体的装饰器。

    检查请求是否为 JSON 格式，并验证必需字段是否存在。

    Args:
        *required_fields: 必需的字段名列表

    Returns:
        装饰器函数

    Example:
        >>> @anime_bp.route('/api/anime', methods=['POST'])
        >>> @validate_json('short_title', 'subtitle_group', 'season')
        >>> def create_anime():
        >>>     data = request.get_json()
        >>>     return APIResponse.created(data=anime)
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            # 检查是否为 JSON 请求
            if not request.is_json:
                logger.warning(f'⚠️ 非JSON请求 [{request.path}]')
                return APIResponse.bad_request('请求必须是JSON格式')

            # 获取 JSON 数据
            data = request.get_json()
            if data is None:
                logger.warning(f'⚠️ JSON解析失败 [{request.path}]')
                return APIResponse.bad_request('无法解析JSON数据')

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
