"""
统一的API响应工具类

提供标准化的API响应格式，确保前后端接口一致性
"""
from flask import jsonify
from typing import Any, Optional, Dict, List, Tuple


class APIResponse:
    """标准化API响应格式"""

    @staticmethod
    def success(
        data: Any = None,
        message: str = "操作成功",
        **kwargs
    ) -> Tuple[Any, int]:
        """
        成功响应

        Args:
            data: 响应数据
            message: 成功消息
            **kwargs: 其他需要添加到响应中的字段

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.success(data={'id': 1}, message='创建成功')
            >>> return APIResponse.success(anime_list=[...], total=100)
        """
        response = {
            "success": True,
            "message": message
        }
        if data is not None:
            response["data"] = data
        response.update(kwargs)
        return jsonify(response), 200

    @staticmethod
    def error(
        message: str,
        code: int = 500,
        **kwargs
    ) -> Tuple[Any, int]:
        """
        错误响应

        Args:
            message: 错误消息
            code: HTTP状态码（400=客户端错误, 404=未找到, 500=服务器错误）
            **kwargs: 其他需要添加到响应中的字段

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.error('参数错误', code=400)
            >>> return APIResponse.error('资源不存在', code=404)
        """
        response = {
            "success": False,
            "error": message
        }
        response.update(kwargs)
        return jsonify(response), code

    @staticmethod
    def paginated(
        data: List[Any],
        total: int,
        page: int,
        per_page: int,
        **kwargs
    ) -> Tuple[Any, int]:
        """
        分页响应

        Args:
            data: 当前页数据列表
            total: 总记录数
            page: 当前页码
            per_page: 每页记录数
            **kwargs: 其他需要添加到响应中的字段

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.paginated(
            ...     data=anime_list,
            ...     total=100,
            ...     page=1,
            ...     per_page=20
            ... )
        """
        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

        return APIResponse.success(
            data=data,
            pagination={
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "current_page": page,
                "total_count": total
            },
            **kwargs
        )

    @staticmethod
    def created(
        data: Any = None,
        message: str = "创建成功",
        **kwargs
    ) -> Tuple[Any, int]:
        """
        创建成功响应 (HTTP 201)

        Args:
            data: 创建的资源数据
            message: 成功消息
            **kwargs: 其他需要添加到响应中的字段

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.created(data={'id': 1, 'name': '新动漫'})
        """
        response = {
            "success": True,
            "message": message
        }
        if data is not None:
            response["data"] = data
        response.update(kwargs)
        return jsonify(response), 201

    @staticmethod
    def accepted(
        message: str = "请求已接受，正在处理",
        **kwargs
    ) -> Tuple[Any, int]:
        """
        请求已接受响应 (HTTP 202)

        用于异步操作，表示请求已接受但尚未完成

        Args:
            message: 提示消息
            **kwargs: 其他需要添加到响应中的字段

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.accepted(message='RSS处理已开始，请稍后查看结果')
        """
        response = {
            "success": True,
            "message": message
        }
        response.update(kwargs)
        return jsonify(response), 202

    @staticmethod
    def no_content() -> Tuple[str, int]:
        """
        无内容响应 (HTTP 204)

        用于删除等操作成功但无需返回数据的场景

        Returns:
            ('', 状态码)

        Example:
            >>> return APIResponse.no_content()
        """
        return '', 204

    @staticmethod
    def bad_request(message: str = "请求参数错误") -> Tuple[Any, int]:
        """
        错误的请求响应 (HTTP 400)

        Args:
            message: 错误消息

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.bad_request('RSS URL不能为空')
        """
        return APIResponse.error(message, code=400)

    @staticmethod
    def unauthorized(message: str = "未授权") -> Tuple[Any, int]:
        """
        未授权响应 (HTTP 401)

        Args:
            message: 错误消息

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.unauthorized('请先登录')
        """
        return APIResponse.error(message, code=401)

    @staticmethod
    def forbidden(message: str = "权限不足") -> Tuple[Any, int]:
        """
        禁止访问响应 (HTTP 403)

        Args:
            message: 错误消息

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.forbidden('无权删除此资源')
        """
        return APIResponse.error(message, code=403)

    @staticmethod
    def not_found(message: str = "资源不存在") -> Tuple[Any, int]:
        """
        未找到响应 (HTTP 404)

        Args:
            message: 错误消息

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.not_found('动漫不存在')
        """
        return APIResponse.error(message, code=404)

    @staticmethod
    def conflict(message: str = "资源冲突") -> Tuple[Any, int]:
        """
        冲突响应 (HTTP 409)

        用于资源已存在等冲突场景

        Args:
            message: 错误消息

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.conflict('该动漫已存在')
        """
        return APIResponse.error(message, code=409)

    @staticmethod
    def internal_error(message: str = "服务器内部错误") -> Tuple[Any, int]:
        """
        服务器内部错误响应 (HTTP 500)

        Args:
            message: 错误消息

        Returns:
            (响应对象, 状态码)

        Example:
            >>> return APIResponse.internal_error('数据库连接失败')
        """
        return APIResponse.error(message, code=500)
