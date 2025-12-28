# Phase 4 总结：统一依赖注入模式

## 概述

Phase 4 完成了代码清理工作流程的最后阶段，统一了项目的依赖注入模式，消除了全局单例变量和工厂函数。

## 清理前状态

项目同时存在三种依赖管理模式：

1. **dependency-injector Container** (主要方式)
   - 大多数服务通过 `src/container.py` 配置
   
2. **全局单例变量**
   - `_xxx_service: XxxService | None = None`
   
3. **工厂函数**
   - `def get_xxx_service() -> XxxService`

## 清理内容

### 1. 移除的全局单例和工厂函数

| 文件 | 单例变量 | 工厂函数 | 全局实例 |
|------|----------|----------|----------|
| `ai_debug_service.py` | `_ai_debug_service` | `get_ai_debug_service()` | `ai_debug_service` |
| `anime_service.py` | `_anime_service` | `get_anime_service()` | - |
| `filter_service.py` | `_filter_service` | `get_filter_service()` | - |
| `log_rotation_service.py` | `_log_rotation_service` | `get_log_rotation_service()` |

**注意**: `LogRotationService` 未在 Container 中注册，因为日志轮换在模块导入时就需要执行（早于 Container 初始化）。在 `main.py` 中直接实例化。 - |
| `metadata_service.py` | `_metadata_service` | `get_metadata_service()` | - |

### 2. AI 适配器依赖注入重构

将 `ai_debug_service` 从全局变量改为构造函数注入：

**修改前**：
```python
from src.services.ai_debug_service import ai_debug_service

class AITitleParser:
    def __init__(self, key_pool, circuit_breaker, api_client=None, max_retries=3):
        # ...

    def parse(self, title):
        if ai_debug_service.enabled:
            ai_debug_service.log_ai_interaction(...)
```

**修改后**：
```python
from src.services.ai_debug_service import AIDebugService

class AITitleParser:
    def __init__(
        self,
        key_pool,
        circuit_breaker,
        api_client=None,
        max_retries=3,
        ai_debug_service: AIDebugService | None = None
    ):
        self._ai_debug_service = ai_debug_service

    def parse(self, title):
        if self._ai_debug_service and self._ai_debug_service.enabled:
            self._ai_debug_service.log_ai_interaction(...)
```

### 3. Container 配置更新

```python
# AI Debug Service 移至 AI 组件之前定义
ai_debug_service = providers.Singleton(AIDebugService)

# 各 AI 适配器注入 ai_debug_service
title_parser = providers.Singleton(
    AITitleParser,
    key_pool=title_parse_pool,
    circuit_breaker=title_parse_breaker,
    api_client=title_parse_api_client,
    ai_debug_service=ai_debug_service
)

file_renamer = providers.Singleton(
    AIFileRenamer,
    key_pool=rename_pool,
    circuit_breaker=rename_breaker,
    api_client=rename_api_client,
    ai_debug_service=ai_debug_service
)

subtitle_matcher = providers.Singleton(
    AISubtitleMatcher,
    key_pool=subtitle_match_pool,
    circuit_breaker=subtitle_match_breaker,
    api_client=subtitle_match_api_client,
    ai_debug_service=ai_debug_service
)
```

### 4. 外部引用更新

| 文件 | 修改内容 |
|------|----------|
| `src/main.py` | `ai_debug_service.enable()` → `container.ai_debug_service().enable()` |
| `src/interface/web/controllers/ai_test.py` | 使用延迟导入辅助函数避免循环导入 |
| `src/services/__init__.py` | 移除工厂函数导出 |

## 清理后状态

### 统一的依赖获取方式

```python
# 推荐方式：通过 Container 获取服务
from src.container import container

service = container.ai_debug_service()
service = container.anime_service()
service = container.filter_service()
service = container.metadata_service()
service = container.log_rotation_service()

# Flask 控制器中的依赖注入
from dependency_injector.wiring import inject, Provide
from src.container import Container

@inject
def handler(service: SomeService = Provide[Container.some_service]):
    pass
```

### 服务导出

`src/services/__init__.py` 只导出服务类，不再导出工厂函数：

```python
__all__ = [
    # 服务类
    'FilterService',
    'MetadataService',
    'AnimeService',
    'AIDebugService',
    'LogRotationService',
    # ...
]
```

## 验证结果

- ✅ `ruff check src/` - 无新增 lint 错误
- ✅ `pytest tests/` - 261 passed, 1 skipped
- ✅ `python -m src.main --test` - 所有验证通过

## 架构改进

1. **一致性** - 所有服务现在都通过 Container 获取
2. **可测试性** - 依赖可以在测试中轻松替换
3. **可追踪性** - 所有依赖关系在 `container.py` 中集中配置
4. **无全局状态** - 消除了模块级别的可变全局状态

## 整体清理工作流程完成

| Phase | 描述 | 状态 |
|-------|------|------|
| Phase 1 | 删除未使用代码 | ✅ 完成 |
| Phase 2 | 合并重复服务 | ✅ 完成 |
| Phase 3 | 整合 Discord 通知器 | ✅ 完成 |
| Phase 4 | 统一依赖注入模式 | ✅ 完成 |

## 代码统计

| 指标 | 变化 |
|------|------|
| 移除的全局单例变量 | 5 |
| 移除的工厂函数 | 5 |
| 更新的 AI 适配器 | 3 |
| 更新的控制器/入口文件 | 2 |
