"""
Flask 应用工厂

创建和配置 Flask 应用实例
"""
from flask import Flask, request
from flask.json.provider import DefaultJSONProvider
from datetime import datetime, timezone
from src.container import Container
from src.core.config import config
from src.core.utils.timezone_utils import format_datetime_iso

# 导入蓝图
from src.interface.web.controllers.dashboard import dashboard_bp


class CustomJSONProvider(DefaultJSONProvider):
    """自定义JSON序列化器，确保datetime对象以UTC ISO格式返回"""

    def default(self, obj):
        if isinstance(obj, datetime):
            # 如果datetime没有时区信息，假设它是UTC
            if obj.tzinfo is None:
                obj = obj.replace(tzinfo=timezone.utc)
            # 返回ISO 8601格式的字符串，包含时区信息
            return obj.isoformat()
        return super().default(obj)


def create_app(container: Container) -> Flask:
    """
    创建 Flask 应用

    Args:
        container: 依赖注入容器

    Returns:
        配置完成的 Flask 应用实例
    """
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    # 配置自定义JSON序列化器
    app.json = CustomJSONProvider(app)

    # 配置
    app.secret_key = 'anime_downloader_webui_secret_key'  # 建议从配置读取

    # 关联容器
    app.container = container

    # 注册蓝图
    app.register_blueprint(dashboard_bp)

    # 注入依赖到蓝图
    container.wire(modules=[
        "src.interface.web.controllers.dashboard",
    ])

    # 注册 Jinja2 过滤器 - 统一的时间格式化
    @app.template_filter('format_datetime')
    def format_datetime_filter(value, format_type='full'):
        """
        Jinja2 过滤器：格式化 datetime 对象为 ISO 8601 字符串
        前端 JavaScript (TimezoneUtils) 会自动转换为用户本地时区

        用法示例：
            {{ download.download_time | format_datetime }}
            {{ download.download_time | format_datetime('date') }}
        """
        if value is None:
            return None

        # 使用统一的时间工具格式化为 ISO 8601
        return format_datetime_iso(value)

    # 添加静态文件缓存策略
    @app.after_request
    def add_cache_headers(response):
        """为静态资源添加浏览器缓存头"""
        if 'static' in request.path:
            # 静态文件缓存1天 (86400秒)
            response.cache_control.max_age = 86400
            response.cache_control.public = True
            # 添加 ETag 支持
            response.add_etag()
        return response

    return app
