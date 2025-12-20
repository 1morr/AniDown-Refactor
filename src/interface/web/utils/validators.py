"""
输入验证工具

提供灵活的数据验证功能
"""
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ValidationRule:
    """
    验证规则

    Attributes:
        required: 是否必填
        min_length: 最小长度
        max_length: 最大长度
        pattern: 正则表达式模式
        choices: 允许的值列表
        min_value: 最小值（用于数字）
        max_value: 最大值（用于数字）
        custom_validator: 自定义验证函数

    Example:
        >>> rule = ValidationRule(
        ...     required=True,
        ...     min_length=2,
        ...     max_length=100,
        ...     pattern=r'^[a-zA-Z0-9_]+$'
        ... )
    """
    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    choices: Optional[List[Any]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    custom_validator: Optional[callable] = None


class RequestValidator:
    """请求数据验证器"""

    @staticmethod
    def validate(
        data: Dict[str, Any],
        rules: Dict[str, ValidationRule]
    ) -> Optional[str]:
        """
        验证数据

        Args:
            data: 待验证的数据字典
            rules: 验证规则字典，键为字段名，值为ValidationRule

        Returns:
            None if valid, error message if invalid

        Example:
            >>> data = {'username': 'john', 'age': 25}
            >>> rules = {
            ...     'username': ValidationRule(required=True, min_length=3),
            ...     'age': ValidationRule(min_value=18, max_value=100)
            ... }
            >>> error = RequestValidator.validate(data, rules)
            >>> if error:
            ...     return APIResponse.bad_request(error)
        """
        for field, rule in rules.items():
            value = data.get(field)

            # 必填验证
            if rule.required and (value is None or value == ''):
                return f"字段 '{field}' 不能为空"

            # 如果值为None且非必填，跳过后续验证
            if value is None:
                continue

            # 字符串验证
            if isinstance(value, str):
                # 长度验证
                if rule.min_length is not None and len(value) < rule.min_length:
                    return f"字段 '{field}' 长度不能小于 {rule.min_length}"

                if rule.max_length is not None and len(value) > rule.max_length:
                    return f"字段 '{field}' 长度不能大于 {rule.max_length}"

                # 正则表达式验证
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

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        验证URL格式

        Args:
            url: URL字符串

        Returns:
            True if valid, False otherwise

        Example:
            >>> RequestValidator.validate_url('https://example.com/rss')
            True
            >>> RequestValidator.validate_url('not a url')
            False
        """
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        return bool(url_pattern.match(url))

    @staticmethod
    def validate_email(email: str) -> bool:
        """
        验证邮箱格式

        Args:
            email: 邮箱字符串

        Returns:
            True if valid, False otherwise

        Example:
            >>> RequestValidator.validate_email('user@example.com')
            True
        """
        email_pattern = re.compile(
            r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        )
        return bool(email_pattern.match(email))

    @staticmethod
    def sanitize_string(text: str, max_length: Optional[int] = None) -> str:
        """
        清理字符串（去除前后空格，限制长度）

        Args:
            text: 待清理的字符串
            max_length: 最大长度

        Returns:
            清理后的字符串

        Example:
            >>> RequestValidator.sanitize_string('  hello  ', max_length=3)
            'hel'
        """
        cleaned = text.strip()
        if max_length and len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        return cleaned

    @staticmethod
    def validate_season(season: Any) -> Optional[str]:
        """
        验证季数

        Args:
            season: 季数（可以是字符串或整数）

        Returns:
            None if valid, error message if invalid

        Example:
            >>> RequestValidator.validate_season(1)
            None
            >>> RequestValidator.validate_season(-1)
            '季数必须是正整数'
        """
        try:
            season_int = int(season)
            if season_int <= 0:
                return "季数必须是正整数"
            if season_int > 100:
                return "季数不能超过100"
            return None
        except (ValueError, TypeError):
            return "季数必须是有效的整数"

    @staticmethod
    def validate_category(category: str) -> Optional[str]:
        """
        验证分类

        Args:
            category: 分类名称

        Returns:
            None if valid, error message if invalid

        Example:
            >>> RequestValidator.validate_category('tv')
            None
            >>> RequestValidator.validate_category('invalid')
            "分类必须是 'tv' 或 'movie'"
        """
        valid_categories = ['tv', 'movie']
        if category not in valid_categories:
            return f"分类必须是 {valid_categories} 之一"
        return None

    @staticmethod
    def validate_media_type(media_type: str) -> Optional[str]:
        """
        验证媒体类型

        Args:
            media_type: 媒体类型

        Returns:
            None if valid, error message if invalid

        Example:
            >>> RequestValidator.validate_media_type('anime')
            None
            >>> RequestValidator.validate_media_type('invalid')
            "媒体类型必须是 'anime' 或 'live_action'"
        """
        valid_types = ['anime', 'live_action']
        if media_type not in valid_types:
            return f"媒体类型必须是 {valid_types} 之一"
        return None


class FormDataExtractor:
    """表单数据提取器，提供便捷的数据提取和转换方法"""

    @staticmethod
    def get_string(
        data: Dict[str, Any],
        key: str,
        default: str = '',
        strip: bool = True
    ) -> str:
        """
        获取字符串值

        Args:
            data: 数据字典
            key: 键名
            default: 默认值
            strip: 是否去除前后空格

        Returns:
            字符串值

        Example:
            >>> data = {'name': '  john  '}
            >>> FormDataExtractor.get_string(data, 'name')
            'john'
        """
        value = data.get(key, default)
        if strip and isinstance(value, str):
            value = value.strip()
        return value

    @staticmethod
    def get_int(
        data: Dict[str, Any],
        key: str,
        default: int = 0,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None
    ) -> int:
        """
        获取整数值

        Args:
            data: 数据字典
            key: 键名
            default: 默认值
            min_value: 最小值限制
            max_value: 最大值限制

        Returns:
            整数值

        Raises:
            ValueError: 如果值无法转换为整数或超出范围

        Example:
            >>> data = {'page': '1'}
            >>> FormDataExtractor.get_int(data, 'page', min_value=1)
            1
        """
        try:
            value = int(data.get(key, default))
            if min_value is not None and value < min_value:
                raise ValueError(f"{key} 不能小于 {min_value}")
            if max_value is not None and value > max_value:
                raise ValueError(f"{key} 不能大于 {max_value}")
            return value
        except (ValueError, TypeError) as e:
            raise ValueError(f"{key} 必须是有效的整数") from e

    @staticmethod
    def get_bool(data: Dict[str, Any], key: str, default: bool = False) -> bool:
        """
        获取布尔值

        支持多种格式：'true', 'false', '1', '0', True, False

        Args:
            data: 数据字典
            key: 键名
            default: 默认值

        Returns:
            布尔值

        Example:
            >>> data = {'enabled': 'true'}
            >>> FormDataExtractor.get_bool(data, 'enabled')
            True
        """
        value = data.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value)

    @staticmethod
    def get_list(
        data: Dict[str, Any],
        key: str,
        default: Optional[List] = None,
        separator: str = ','
    ) -> List[str]:
        """
        获取列表值

        Args:
            data: 数据字典
            key: 键名
            default: 默认值
            separator: 分隔符

        Returns:
            列表

        Example:
            >>> data = {'tags': 'action,drama,comedy'}
            >>> FormDataExtractor.get_list(data, 'tags')
            ['action', 'drama', 'comedy']
        """
        if default is None:
            default = []

        value = data.get(key)
        if not value:
            return default

        if isinstance(value, list):
            return value

        if isinstance(value, str):
            return [item.strip() for item in value.split(separator) if item.strip()]

        return default
