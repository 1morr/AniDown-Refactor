"""
配置热重载服务模块。

在配置保存后重新初始化各个组件，使配置立即生效。
"""

import logging
from typing import Dict, List, Optional, Tuple

from dependency_injector import providers

logger = logging.getLogger(__name__)


class ConfigReloader:
    """
    配置热重载服务。

    负责在配置变更后重新初始化相关组件，
    使大多数配置无需重启即可生效。

    需要重启才能生效的配置：
    - WebUI 端口
    - Webhook 端口
    """

    # 需要重启才能生效的配置项
    RESTART_REQUIRED_KEYS = [
        'webui.port',
        'webhook.port',
    ]

    def __init__(self):
        self._old_config_snapshot: Dict = {}

    def snapshot_config(self) -> None:
        """保存当前配置快照（用于检测变更）"""
        from src.core.config import config

        self._old_config_snapshot = {
            'webui_port': config.webui.port,
            'webhook_port': config.webhook.port,
        }

    def check_restart_required(self) -> Tuple[bool, List[str]]:
        """
        检查是否需要重启。

        Returns:
            (需要重启, 变更的配置项列表)
        """
        from src.core.config import config

        changed_items = []

        if self._old_config_snapshot.get('webui_port') != config.webui.port:
            changed_items.append('WebUI 端口')

        if self._old_config_snapshot.get('webhook_port') != config.webhook.port:
            changed_items.append('Webhook 端口')

        return len(changed_items) > 0, changed_items

    def reload_all(self) -> Dict[str, bool]:
        """
        重新加载所有可热重载的配置。

        Returns:
            各组件重载结果 {组件名: 是否成功}
        """
        results = {}

        # 1. 重载 Key Pools 和 Circuit Breakers
        results['key_pools'] = self._reload_key_pools()

        # 2. 重载 Discord Webhook
        results['discord'] = self._reload_discord()

        # 3. 重载 qBittorrent Adapter
        results['qbittorrent'] = self._reload_qbittorrent()

        # 4. 重载 TVDB Adapter
        results['tvdb'] = self._reload_tvdb()

        # 5. 重载 AI 客户端（timeout 等）
        results['ai_clients'] = self._reload_ai_clients()

        # 6. 重载 Path Builder
        results['path_builder'] = self._reload_path_builder()

        # 记录结果
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        logger.info(f'🔄 配置热重载完成: {success_count}/{total_count} 组件成功')

        return results

    def _reload_key_pools(self) -> bool:
        """重载 Key Pools 和 Circuit Breakers"""
        try:
            from src.core.config import config
            from src.container import container
            from src.infrastructure.ai.key_pool import (
                KeyPool, KeySpec,
                register_pool, register_named_pool, bind_purpose_to_pool,
                get_named_pool, clear_all_registries
            )
            from src.infrastructure.ai.circuit_breaker import (
                CircuitBreaker,
                register_breaker, register_named_breaker, get_named_breaker,
                clear_all_breaker_registries
            )

            # 清空现有注册表
            clear_all_registries()
            clear_all_breaker_registries()

            # Phase 1: 创建命名 Key Pools
            for pool_def in config.openai.key_pools:
                pool_name = pool_def.name
                if not pool_name:
                    continue

                pool = KeyPool(purpose=f'pool:{pool_name}')
                breaker = CircuitBreaker(purpose=f'pool:{pool_name}')

                keys = []
                for idx, key_entry in enumerate(pool_def.api_keys):
                    if key_entry.enabled and key_entry.api_key:
                        keys.append(KeySpec(
                            key_id=f'{pool_name}_key_{idx}',
                            name=key_entry.name or f'Key {idx + 1}',
                            api_key=key_entry.api_key,
                            base_url=pool_def.base_url,
                            rpm_limit=key_entry.rpm,
                            rpd_limit=key_entry.rpd,
                            enabled=True,
                            extra_body=''
                        ))

                if keys:
                    pool.configure(keys)
                    register_named_pool(pool, pool_name)
                    register_named_breaker(breaker, pool_name)
                    pool.restore_counts_from_db()
                    logger.debug(f'🔑 重载命名 Key Pool "{pool_name}": {len(keys)} 个 Key')

            # Phase 2: 为每个任务绑定池或创建独立池
            task_configs = [
                ('title_parse', config.openai.title_parse,
                 container.title_parse_pool, container.title_parse_breaker),
                ('multi_file_rename', config.openai.multi_file_rename,
                 container.rename_pool, container.rename_breaker),
                ('subtitle_match', config.openai.subtitle_match,
                 container.subtitle_match_pool, container.subtitle_match_breaker),
            ]

            for purpose, task_config, pool_provider, breaker_provider in task_configs:
                if task_config.pool_name:
                    named_pool = get_named_pool(task_config.pool_name)
                    named_breaker = get_named_breaker(task_config.pool_name)

                    if named_pool and named_breaker:
                        pool_provider.override(providers.Object(named_pool))
                        breaker_provider.override(providers.Object(named_breaker))
                        bind_purpose_to_pool(purpose, task_config.pool_name)
                        register_pool(named_pool)
                        register_breaker(named_breaker)
                        logger.debug(f'🔗 任务 {purpose} 重新绑定 Pool "{task_config.pool_name}"')
                elif task_config.api_key:
                    # 重置 provider 并重新创建
                    pool_provider.reset()
                    breaker_provider.reset()

                    pool = pool_provider()
                    breaker = breaker_provider()

                    keys = [KeySpec(
                        key_id=f'{purpose}_key_0',
                        name='Primary Key',
                        api_key=task_config.api_key,
                        base_url=task_config.base_url,
                        rpm_limit=0,
                        rpd_limit=0,
                        enabled=True,
                        extra_body=task_config.extra_body
                    )]

                    pool.configure(keys)
                    register_pool(pool)
                    register_breaker(breaker)
                    pool.restore_counts_from_db()
                    logger.debug(f'🔑 任务 {purpose} 重载独立配置')

            # Phase 3: 更新已存在的 AI 服务实例的内部引用
            # 由于 Singleton 模式，服务实例已创建并持有旧的 pool/breaker 引用
            # 需要直接更新这些实例的内部属性
            self._update_ai_service_references()

            logger.info('✅ Key Pools 热重载完成')
            return True
        except Exception as e:
            logger.error(f'❌ Key Pools 热重载失败: {e}', exc_info=True)
            return False

    def _update_ai_service_references(self) -> None:
        """
        更新已存在的 AI 服务实例的内部引用。

        由于使用 Singleton 模式，AI 服务在启动时创建并持有
        key_pool 和 circuit_breaker 的引用。热重载后需要
        直接更新这些实例的内部属性以指向新的 pool/breaker。

        同时更新依赖这些 AI 服务的上层服务的引用。
        """
        from src.container import container

        try:
            # 获取新的 pool 和 breaker 实例
            new_title_parse_pool = container.title_parse_pool()
            new_title_parse_breaker = container.title_parse_breaker()
            new_rename_pool = container.rename_pool()
            new_rename_breaker = container.rename_breaker()
            new_subtitle_match_pool = container.subtitle_match_pool()
            new_subtitle_match_breaker = container.subtitle_match_breaker()

            # 更新 title_parser 的引用
            title_parser = container.title_parser()
            title_parser._key_pool = new_title_parse_pool
            title_parser._circuit_breaker = new_title_parse_breaker
            logger.debug('🔄 更新 title_parser 的 pool/breaker 引用')

            # 更新 file_renamer 的引用
            file_renamer = container.file_renamer()
            file_renamer._key_pool = new_rename_pool
            file_renamer._circuit_breaker = new_rename_breaker
            logger.debug('🔄 更新 file_renamer 的 pool/breaker 引用')

            # 更新 subtitle_matcher 的引用
            subtitle_matcher = container.subtitle_matcher()
            subtitle_matcher._key_pool = new_subtitle_match_pool
            subtitle_matcher._circuit_breaker = new_subtitle_match_breaker
            logger.debug('🔄 更新 subtitle_matcher 的 pool/breaker 引用')

            # 更新依赖 AI 服务的上层服务的引用
            # download_manager 持有 title_parser 和 file_renamer 引用
            download_manager = container.download_manager()
            download_manager._title_parser = title_parser
            download_manager._file_renamer = file_renamer
            logger.debug('🔄 更新 download_manager 的 AI 服务引用')

            # rename_service 持有 file_renamer 引用
            rename_service = container.rename_service()
            rename_service._ai_file_renamer = file_renamer
            logger.debug('🔄 更新 rename_service 的 file_renamer 引用')

            # subtitle_service 持有 subtitle_matcher 引用
            subtitle_service = container.subtitle_service()
            subtitle_service._subtitle_matcher = subtitle_matcher
            logger.debug('🔄 更新 subtitle_service 的 subtitle_matcher 引用')

        except Exception as e:
            logger.warning(f'⚠️ 更新 AI 服务引用时出错: {e}')

    def _reload_discord(self) -> bool:
        """重载 Discord Webhook 配置"""
        try:
            from src.core.config import config
            from src.container import container

            discord_client = container.discord_webhook()

            webhooks = {}
            if config.discord.rss_webhook_url:
                webhooks['rss'] = config.discord.rss_webhook_url
            if config.discord.hardlink_webhook_url:
                webhooks['hardlink'] = config.discord.hardlink_webhook_url
                webhooks['download'] = config.discord.hardlink_webhook_url

            discord_client.configure(
                webhooks=webhooks,
                enabled=config.discord.enabled
            )

            if config.discord.enabled:
                logger.info(f'✅ Discord 热重载完成: {list(webhooks.keys())}')
            else:
                logger.info('✅ Discord 热重载完成 (已禁用)')

            return True
        except Exception as e:
            logger.error(f'❌ Discord 热重载失败: {e}', exc_info=True)
            return False

    def _reload_qbittorrent(self) -> bool:
        """重载 qBittorrent 配置"""
        try:
            from src.core.config import config
            from src.container import container

            qb_client = container.qb_client()

            # 更新配置
            qb_client.base_url = config.qbittorrent.url.rstrip('/')
            qb_client.username = config.qbittorrent.username
            qb_client.password = config.qbittorrent.password

            # 清除现有登录状态，强制重新登录
            qb_client.cookies = None
            qb_client.session.cookies.clear()

            # 尝试重新登录
            if qb_client.login():
                logger.info('✅ qBittorrent 热重载完成')
                return True
            else:
                logger.warning('⚠️ qBittorrent 热重载完成 (登录失败，可能未配置)')
                return True  # 配置已更新，只是登录失败

        except Exception as e:
            logger.error(f'❌ qBittorrent 热重载失败: {e}', exc_info=True)
            return False

    def _reload_tvdb(self) -> bool:
        """重载 TVDB 配置"""
        try:
            from src.core.config import config
            from src.container import container

            tvdb_client = container.tvdb_client()

            # 更新 API Key
            tvdb_client._api_key = config.tvdb.api_key
            tvdb_client._token = None  # 清除现有 token

            # 如果有 API Key，尝试重新登录
            if tvdb_client.is_enabled:
                if tvdb_client.login():
                    logger.info('✅ TVDB 热重载完成')
                else:
                    logger.warning('⚠️ TVDB 热重载完成 (登录失败)')
            else:
                logger.info('✅ TVDB 热重载完成 (未启用)')

            return True
        except Exception as e:
            logger.error(f'❌ TVDB 热重载失败: {e}', exc_info=True)
            return False

    def _reload_ai_clients(self) -> bool:
        """重载 AI 客户端配置（超时时间等）"""
        try:
            from src.core.config import config
            from src.container import container
            from src.infrastructure.ai.api_client import OpenAIClient

            # 重置并重新创建 API 客户端
            container.title_parse_api_client.override(
                providers.Singleton(
                    OpenAIClient,
                    timeout=config.openai.title_parse.timeout
                )
            )

            container.rename_api_client.override(
                providers.Singleton(
                    OpenAIClient,
                    timeout=config.openai.multi_file_rename.timeout
                )
            )

            # 字幕匹配客户端
            subtitle_timeout = (
                config.openai.subtitle_match.timeout
                if config.openai.subtitle_match.api_key or config.openai.subtitle_match.pool_name
                else config.openai.multi_file_rename.timeout
            )
            container.subtitle_match_api_client.override(
                providers.Singleton(
                    OpenAIClient,
                    timeout=subtitle_timeout
                )
            )

            # 获取新的 API 客户端实例
            new_title_parse_client = container.title_parse_api_client()
            new_rename_client = container.rename_api_client()
            new_subtitle_match_client = container.subtitle_match_api_client()

            # 更新 AI 服务的 api_client 引用
            title_parser = container.title_parser()
            title_parser._api_client = new_title_parse_client
            logger.debug('🔄 更新 title_parser 的 api_client 引用')

            file_renamer = container.file_renamer()
            file_renamer._api_client = new_rename_client
            logger.debug('🔄 更新 file_renamer 的 api_client 引用')

            subtitle_matcher = container.subtitle_matcher()
            subtitle_matcher._api_client = new_subtitle_match_client
            logger.debug('🔄 更新 subtitle_matcher 的 api_client 引用')

            logger.info('✅ AI 客户端热重载完成')
            return True
        except Exception as e:
            logger.error(f'❌ AI 客户端热重载失败: {e}', exc_info=True)
            return False

    def _reload_path_builder(self) -> bool:
        """重载 PathBuilder 配置"""
        try:
            from src.core.config import config
            from src.container import container
            from src.services.file.path_builder import PathBuilder

            # 重置并重新创建 PathBuilder
            container.path_builder.override(
                providers.Singleton(
                    PathBuilder,
                    download_root=config.qbittorrent.base_download_path,
                    library_root=config.link_target_path
                )
            )

            # 获取新的 PathBuilder 实例
            new_path_builder = container.path_builder()

            # 更新已存在服务实例的引用
            # hardlink_service 持有 path_builder 引用
            hardlink_service = container.hardlink_service()
            hardlink_service._path_builder = new_path_builder
            logger.debug('🔄 更新 hardlink_service 的 path_builder 引用')

            # download_manager 持有 path_builder 引用
            download_manager = container.download_manager()
            download_manager._path_builder = new_path_builder
            logger.debug('🔄 更新 download_manager 的 path_builder 引用')

            logger.info('✅ PathBuilder 热重载完成')
            return True
        except Exception as e:
            logger.error(f'❌ PathBuilder 热重载失败: {e}', exc_info=True)
            return False


# 全局单例
config_reloader = ConfigReloader()


def reload_config() -> Tuple[Dict[str, bool], bool, List[str]]:
    """
    执行配置热重载。

    Returns:
        (重载结果, 是否需要重启, 需要重启的配置项)
    """
    restart_required, restart_items = config_reloader.check_restart_required()
    results = config_reloader.reload_all()

    return results, restart_required, restart_items
