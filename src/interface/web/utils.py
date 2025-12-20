"""
Web 接口工具模块。

提供 API 响应格式化、日志记录和装饰器。
"""

import logging
import functools
from typing import Any, Dict, Optional, List

from flask import jsonify, Response


logger = logging.getLogger(__name__)


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
        data: Optional[Any] = None,
        message: Optional[str] = None,
        code: int = 200
    ) -> Response:
        """
        构建统一的响应格式。

        Args:
            success: 操作是否成功
            data: 响应数据
            message: 响应消息
            code: HTTP 状态码

        Returns:
            Flask Response 对象
        """
        response_body = {'success': success}

        if data is not None:
            response_body['data'] = data

        if message is not None:
            response_body['message'] = message

        response = jsonify(response_body)
        response.status_code = code
        return response

    @classmethod
    def success(
        cls,
        data: Optional[Any] = None,
        message: Optional[str] = None
    ) -> Response:
        """
        成功响应。

        Args:
            data: 响应数据
            message: 成功消息

        Returns:
            200 OK 响应
        """
        return cls._make_response(
            success=True,
            data=data,
            message=message,
            code=200
        )

    @classmethod
    def created(
        cls,
        data: Optional[Any] = None,
        message: Optional[str] = None
    ) -> Response:
        """
        资源创建成功响应。

        Args:
            data: 创建的资源数据
            message: 成功消息

        Returns:
            201 Created 响应
        """
        return cls._make_response(
            success=True,
            data=data,
            message=message,
            code=201
        )

    @classmethod
    def error(
        cls,
        message: str,
        code: int = 500
    ) -> Response:
        """
        错误响应。

        Args:
            message: 错误消息
            code: HTTP 状态码（默认 500）

        Returns:
            错误响应
        """
        return cls._make_response(
            success=False,
            message=message,
            code=code
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
