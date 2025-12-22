"""
Configuration module.

Contains Pydantic-based configuration classes for the AniDown application.
"""

import os
import json
from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


class RSSFeed(BaseModel):
    """单个 RSS Feed 配置"""

    url: str
    blocked_keywords: str = ''  # 换行分隔的屏蔽词列表
    blocked_regex: str = ''  # 换行分隔的正则表达式列表
    media_type: str = 'anime'  # anime: 动漫, live_action: 真人


class RSSConfig(BaseModel):
    """RSS 配置"""

    model_config = ConfigDict(validate_assignment=True)

    fixed_urls: List[Union[str, RSSFeed]] = []  # 兼容旧格式和新格式
    check_interval: int = Field(default=3600, ge=60)

    @field_validator('fixed_urls', mode='before')
    @classmethod
    def convert_to_rssfeed(cls, v):
        """将字典格式转换为 RSSFeed 对象"""
        if not isinstance(v, list):
            return v

        result = []
        for item in v:
            if isinstance(item, dict):
                result.append(RSSFeed(**item))
            elif isinstance(item, str):
                result.append(RSSFeed(url=item))
            else:
                result.append(item)
        return result

    def get_feeds(self) -> List[RSSFeed]:
        """获取 RSS Feed 列表，统一转换为 RSSFeed 对象"""
        feeds = []
        for item in self.fixed_urls:
            if isinstance(item, str):
                # 旧格式：纯字符串 URL，转换为 RSSFeed 对象
                feeds.append(RSSFeed(url=item))
            elif isinstance(item, dict):
                # 字典格式，转换为 RSSFeed 对象
                feeds.append(RSSFeed(**item))
            elif isinstance(item, RSSFeed):
                # 已经是 RSSFeed 对象
                feeds.append(item)
        return feeds


class DiscordConfig(BaseModel):
    """Discord 通知配置"""

    enabled: bool = False
    rss_webhook_url: Optional[str] = ''
    hardlink_webhook_url: Optional[str] = ''


class QBitTorrentConfig(BaseModel):
    """qBittorrent 配置"""

    url: str = 'http://localhost:8080'
    username: str = ''
    password: str = ''
    base_download_path: str = '/downloads/AniDown/'
    category: str = 'AniDown'
    anime_folder_name: str = 'Anime'
    live_action_folder_name: str = 'LiveAction'
    tv_folder_name: str = 'TV'
    movie_folder_name: str = 'Movies'


class LanguagePriorityConfig(BaseModel):
    """语言优先级配置"""

    name: str  # 语言名称: 中文, English, 日本語, Romaji 等


class OpenAIConfig(BaseModel):
    """AI/LLM 配置（按任务区分）"""

    class APIKeyEntry(BaseModel):
        """单个 API Key 配置（用于 Key Pool）"""

        name: str = ''
        api_key: str = ''
        # 0 表示不限制（向后兼容：旧配置未提供限额）
        rpm: int = Field(default=0, ge=0)  # Requests Per Minute
        rpd: int = Field(default=0, ge=0)  # Requests Per Day
        enabled: bool = True

    class TaskConfig(BaseModel):
        """任务特定的 AI 配置"""

        api_key: str = ''
        api_key_pool: List['OpenAIConfig.APIKeyEntry'] = Field(default_factory=list)
        base_url: str = 'https://api.openai.com/v1'
        model: str = 'gpt-4'
        extra_body: str = ''  # JSON格式的额外参数
        timeout: int = Field(default=180, ge=10, le=600)  # API 超时时间（秒）

    class RateLimitConfig(BaseModel):
        """Key Pool 限流/冷却/熔断参数"""

        # 连续错误超过阈值后打开熔断
        max_consecutive_errors: int = Field(default=5, ge=1, le=1000)
        # 基础冷却秒数
        key_cooldown_seconds: int = Field(default=30, ge=0, le=3600)
        # 熔断打开后的暂停时间
        circuit_breaker_cooldown_seconds: int = Field(default=900, ge=0, le=86400)
        # 指数退避最大上限
        max_backoff_seconds: int = Field(default=300, ge=0, le=3600)

    # 标题解析
    title_parse: TaskConfig = Field(default_factory=TaskConfig)
    # 多文件重命名
    multi_file_rename: TaskConfig = Field(default_factory=TaskConfig)
    # 字幕匹配（不在配置页面显示，只能手动修改config.json，默认fallback到multi_file_rename）
    subtitle_match: TaskConfig = Field(default_factory=TaskConfig)

    # 标题解析重试次数
    title_parse_retries: int = Field(default=3, ge=0, le=10)

    # Key Pool 限流/熔断配置
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)

    # 语言优先级配置（用于标题解析时选择首选语言）
    language_priorities: List[LanguagePriorityConfig] = Field(
        default_factory=lambda: [
            LanguagePriorityConfig(name='中文'),
            LanguagePriorityConfig(name='English'),
            LanguagePriorityConfig(name='日本語'),
            LanguagePriorityConfig(name='Romaji'),
        ]
    )


class AIProcessingConfig(BaseModel):
    """AI 处理配置"""

    max_batch_size: int = Field(default=30, gt=0, le=100)
    batch_processing_retries: int = Field(default=2, ge=0)


class WebhookConfig(BaseModel):
    """Webhook 配置"""

    host: str = '0.0.0.0'
    port: int = Field(default=5678, ge=1, le=65535)


class WebUIConfig(BaseModel):
    """Web UI 配置"""

    host: str = '0.0.0.0'
    port: int = Field(default=8081, ge=1, le=65535)


class PathConversionConfig(BaseModel):
    """路径转换配置"""

    enabled: bool = False
    source_base_path: str = '/downloads/AniDown/'
    target_base_path: str = '/path/to/target/'


class TVDBConfig(BaseModel):
    """TVDB 配置"""

    enabled: bool = False
    api_key: str = ''
    max_data_length: int = 10000


class AppConfig(BaseSettings):
    """主应用配置"""

    rss: RSSConfig = Field(default_factory=RSSConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    qbittorrent: QBitTorrentConfig = Field(default_factory=QBitTorrentConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    ai_processing: AIProcessingConfig = Field(default_factory=AIProcessingConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    webui: WebUIConfig = Field(default_factory=WebUIConfig)
    path_conversion: PathConversionConfig = Field(default_factory=PathConversionConfig)
    tvdb: TVDBConfig = Field(default_factory=TVDBConfig)

    # 动漫硬链接路径
    link_target_path: str = '/library/TV Shows'
    movie_link_target_path: str = '/library/Movies'
    # 真人硬链接路径
    live_action_tv_target_path: str = '/library/LiveAction/TV Shows'
    live_action_movie_target_path: str = '/library/LiveAction/Movies'
    use_consistent_naming_tv: bool = False
    use_consistent_naming_movie: bool = False

    model_config = ConfigDict(
        env_prefix='ANIDOWN_',
        env_nested_delimiter='__'
    )

    def get(self, key: str, default=None):
        """获取配置值，支持点分隔的嵌套键"""
        try:
            keys = key.split('.')
            value = self
            for k in keys:
                if hasattr(value, k):
                    value = getattr(value, k)
                else:
                    return default
            return value
        except Exception:
            return default

    def set(self, key: str, value) -> bool:
        """设置配置值，支持点分隔的嵌套键"""
        try:
            keys = key.split('.')
            if len(keys) == 1:
                # 直接设置顶级属性
                setattr(self, keys[0], value)
            else:
                # 设置嵌套属性
                obj = self
                for k in keys[:-1]:
                    if hasattr(obj, k):
                        obj = getattr(obj, k)
                    else:
                        return False
                setattr(obj, keys[-1], value)
            return True
        except Exception:
            return False

    def save_config(self, config_path: str = None):
        """保存配置的别名方法"""
        self.save(config_path)

    @classmethod
    def load(cls, config_path: str = None) -> 'AppConfig':
        """加载配置"""
        if config_path is None:
            config_path = os.getenv('CONFIG_PATH', 'config.json')

        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            return cls(**config_data)

        # 如果配置文件不存在，创建默认配置并保存
        config_instance = cls()
        config_instance.save(config_path)
        return config_instance

    def save(self, config_path: str = None):
        """保存配置"""
        if config_path is None:
            config_path = os.getenv('CONFIG_PATH', 'config.json')

        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(self.model_dump_json(indent=2))


# 全局配置实例
config = AppConfig.load()
