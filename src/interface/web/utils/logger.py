"""
统一的日志工具

提供Web层标准化的日志记录功能
"""
import logging
from typing import Optional, Any


class WebLogger:
    """
    Web层统一日志记录器

    提供标准化的日志格式和emoji指示器，便于日志分析和监控

    Example:
        >>> logger = WebLogger(__name__)
        >>> logger.api_request('/api/anime', 'GET')
        >>> logger.api_success('/api/anime', '获取动漫列表成功')
        >>> logger.api_error('/api/anime', Exception('数据库错误'))
    """

    def __init__(self, name: str):
        """
        初始化日志记录器

        Args:
            name: 模块名称（通常使用 __name__）
        """
        self.logger = logging.getLogger(name)

    def api_request(self, endpoint: str, method: str = 'GET') -> None:
        """
        记录API请求

        Args:
            endpoint: API端点路径
            method: HTTP方法

        Example:
            >>> logger.api_request('/api/anime/1', 'GET')
        """
        self.logger.debug(f"🚀 API请求: {method} {endpoint}")

    def api_success(self, endpoint: str, message: str = "") -> None:
        """
        记录API成功

        Args:
            endpoint: API端点路径
            message: 成功消息

        Example:
            >>> logger.api_success('/api/anime', '获取列表成功')
        """
        if message:
            self.logger.info(f"✅ API成功: {endpoint} - {message}")
        else:
            self.logger.info(f"✅ API成功: {endpoint}")

    def api_error(self, endpoint: str, error: Exception, include_trace: bool = True) -> None:
        """
        记录API错误

        Args:
            endpoint: API端点路径
            error: 异常对象
            include_trace: 是否包含堆栈跟踪

        Example:
            >>> logger.api_error('/api/anime', ValueError('参数错误'))
        """
        self.logger.error(
            f"❌ API错误: {endpoint} - {str(error)}",
            exc_info=include_trace
        )

    def validation_error(self, field: str, reason: str) -> None:
        """
        记录验证错误

        Args:
            field: 字段名
            reason: 错误原因

        Example:
            >>> logger.validation_error('season', '季数必须是正整数')
        """
        self.logger.warning(f"⚠️ 验证失败: {field} - {reason}")

    def database_query(self, query_type: str, details: str = "") -> None:
        """
        记录数据库查询

        Args:
            query_type: 查询类型（SELECT, INSERT, UPDATE, DELETE等）
            details: 查询详情

        Example:
            >>> logger.database_query('SELECT', '获取动漫列表')
        """
        if details:
            self.logger.debug(f"💾 数据库查询: {query_type} - {details}")
        else:
            self.logger.debug(f"💾 数据库查询: {query_type}")

    def database_error(self, operation: str, error: Exception) -> None:
        """
        记录数据库错误

        Args:
            operation: 操作类型
            error: 异常对象

        Example:
            >>> logger.database_error('INSERT', Exception('插入失败'))
        """
        self.logger.error(f"❌ 数据库错误: {operation} - {str(error)}", exc_info=True)

    def external_api_call(self, service: str, endpoint: str) -> None:
        """
        记录外部API调用

        Args:
            service: 服务名称（如qBittorrent, Discord, TVDB等）
            endpoint: API端点

        Example:
            >>> logger.external_api_call('qBittorrent', '/api/v2/torrents/info')
        """
        self.logger.debug(f"🌐 外部API调用: {service} - {endpoint}")

    def external_api_error(self, service: str, error: Exception) -> None:
        """
        记录外部API错误

        Args:
            service: 服务名称
            error: 异常对象

        Example:
            >>> logger.external_api_error('qBittorrent', Exception('连接超时'))
        """
        self.logger.error(f"❌ 外部API错误: {service} - {str(error)}", exc_info=True)

    def file_operation(self, operation: str, path: str) -> None:
        """
        记录文件操作

        Args:
            operation: 操作类型（读取, 写入, 删除等）
            path: 文件路径

        Example:
            >>> logger.file_operation('创建硬链接', '/path/to/file')
        """
        self.logger.debug(f"📁 文件操作: {operation} - {path}")

    def file_error(self, operation: str, path: str, error: Exception) -> None:
        """
        记录文件操作错误

        Args:
            operation: 操作类型
            path: 文件路径
            error: 异常对象

        Example:
            >>> logger.file_error('删除', '/path/to/file', Exception('文件不存在'))
        """
        self.logger.error(
            f"❌ 文件错误: {operation} - {path} - {str(error)}",
            exc_info=True
        )

    def processing_start(self, task: str) -> None:
        """
        记录处理任务开始

        Args:
            task: 任务描述

        Example:
            >>> logger.processing_start('RSS处理')
        """
        self.logger.info(f"🔄 开始处理: {task}")

    def processing_complete(self, task: str, result: str = "") -> None:
        """
        记录处理任务完成

        Args:
            task: 任务描述
            result: 结果描述

        Example:
            >>> logger.processing_complete('RSS处理', '新增10个订阅项')
        """
        if result:
            self.logger.info(f"✅ 处理完成: {task} - {result}")
        else:
            self.logger.info(f"✅ 处理完成: {task}")

    def processing_success(self, message: str, details: str = "") -> None:
        """
        记录处理成功（向后兼容）

        旧代码中常用 processing_success(message) 记录"处理成功/完成/统计信息"等日志。
        这里保留该方法，避免Web控制器调用时报错。

        Args:
            message: 成功消息
            details: 可选的补充信息

        Example:
            >>> logger.processing_success('RSS处理完成')
            >>> logger.processing_success('解析RSS成功', '找到 10 个标题')
        """
        if details:
            self.logger.info(f"✅ {message} - {details}")
        else:
            self.logger.info(f"✅ {message}")

    def processing_error(self, task: str, error: Exception) -> None:
        """
        记录处理任务错误

        Args:
            task: 任务描述
            error: 异常对象

        Example:
            >>> logger.processing_error('RSS处理', Exception('解析失败'))
        """
        self.logger.error(f"❌ 处理失败: {task} - {str(error)}", exc_info=True)

    def user_action(self, action: str, details: str = "") -> None:
        """
        记录用户操作

        Args:
            action: 操作类型
            details: 操作详情

        Example:
            >>> logger.user_action('删除动漫', 'anime_id=123')
        """
        if details:
            self.logger.info(f"👤 用户操作: {action} - {details}")
        else:
            self.logger.info(f"👤 用户操作: {action}")

    def security_warning(self, issue: str, details: str = "") -> None:
        """
        记录安全警告

        Args:
            issue: 安全问题
            details: 详细信息

        Example:
            >>> logger.security_warning('无效的输入', '检测到XSS尝试')
        """
        if details:
            self.logger.warning(f"🔒 安全警告: {issue} - {details}")
        else:
            self.logger.warning(f"🔒 安全警告: {issue}")

    def debug(self, message: str) -> None:
        """
        记录调试信息

        Args:
            message: 调试消息

        Example:
            >>> logger.debug('当前分页参数: page=1, per_page=20')
        """
        self.logger.debug(f"🔍 调试: {message}")

    def info(self, message: str, emoji: str = "ℹ️") -> None:
        """
        记录普通信息

        Args:
            message: 信息内容
            emoji: emoji图标

        Example:
            >>> logger.info('系统启动完成')
        """
        self.logger.info(f"{emoji} {message}")

    def warning(self, message: str) -> None:
        """
        记录警告信息

        Args:
            message: 警告内容

        Example:
            >>> logger.warning('配置项缺失，使用默认值')
        """
        self.logger.warning(f"⚠️ 警告: {message}")

    def error(self, message: str, error: Optional[Exception] = None) -> None:
        """
        记录错误信息

        Args:
            message: 错误描述
            error: 异常对象（可选）

        Example:
            >>> logger.error('初始化失败', error=Exception('配置错误'))
        """
        if error:
            self.logger.error(f"❌ 错误: {message} - {str(error)}", exc_info=True)
        else:
            self.logger.error(f"❌ 错误: {message}")

    def critical(self, message: str, error: Optional[Exception] = None) -> None:
        """
        记录严重错误

        Args:
            message: 错误描述
            error: 异常对象（可选）

        Example:
            >>> logger.critical('数据库连接失败', error=Exception('无法连接'))
        """
        if error:
            self.logger.critical(f"🚨 严重错误: {message} - {str(error)}", exc_info=True)
        else:
            self.logger.critical(f"🚨 严重错误: {message}")

    # === 别名方法（向后兼容） ===

    def db_query(self, query_type: str, details: str = "") -> None:
        """
        数据库查询日志（别名方法）

        Args:
            query_type: 查询类型
            details: 查询详情

        Example:
            >>> logger.db_query('硬链接查询', '找到10个记录')
        """
        self.database_query(query_type, details)

    def db_error(self, operation: str, error: Exception) -> None:
        """
        数据库错误日志（别名方法）

        Args:
            operation: 操作类型
            error: 异常对象

        Example:
            >>> logger.db_error('保存数据', Exception('插入失败'))
        """
        self.database_error(operation, error)

    def db_update(self, resource: str, details: str) -> None:
        """
        数据库更新日志

        Args:
            resource: 资源名称
            details: 更新详情

        Example:
            >>> logger.db_update('系统状态', 'WebUI: 运行')
        """
        self.logger.info(f"💾 数据库更新: {resource} - {details}")

    def api_error_msg(self, endpoint: str, message: str) -> None:
        """
        API错误消息日志（别名方法）

        Args:
            endpoint: API端点路径
            message: 错误消息

        Example:
            >>> logger.api_error_msg('/api/anime', '动漫不存在')
        """
        self.logger.error(f"❌ API错误: {endpoint} - {message}")
