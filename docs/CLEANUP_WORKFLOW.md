# AniDown 代码清理工作流程

基于 `CODE_REVIEW.md` 的分析结果，本文档定义了系统化的代码清理实施计划。

## 工作流程概览

```
Phase 1: 删除未使用代码 (低风险)
    ↓
Phase 2: 合并重复服务 (中等风险)
    ↓
Phase 3: 整合 Discord 通知器 (中等风险)
    ↓
Phase 4: 统一依赖注入模式 (高风险)
```

---

## Phase 1: 删除未使用代码

**风险等级**: 🟢 低  
**预计影响**: 代码更简洁，无功能变化  
**依赖**: 无

### 1.1 删除未使用的异常类

**文件**: `src/core/exceptions.py`

**待删除项目**:
| 异常类 | 行号 | 原因 |
|--------|------|------|
| `AIRateLimitError` | - | 仅导出，无实际使用 |
| `TorrentNotFoundError` | - | 仅导出，无实际使用 |
| `ConfigError` | - | 仅导出，无实际使用 |
| `RSSFetchError` | - | 未使用 |

**步骤**:
- [x] 1.1.1 打开 `src/core/exceptions.py`
- [x] 1.1.2 删除 `AIRateLimitError` 类定义
- [x] 1.1.3 删除 `TorrentNotFoundError` 类定义
- [x] 1.1.4 删除 `ConfigError` 类定义
- [x] 1.1.5 删除 `RSSFetchError` 类定义
- [x] 1.1.6 更新 `__all__` 列表，移除已删除的类
- [x] 1.1.7 搜索全局确认无其他引用

### 1.2 删除空目录

**目录**: `src/services/download/`

**当前状态**:
- 只包含 `__init__.py`
- `__all__ = []` (空导出)

**步骤**:
- [x] 1.2.1 确认目录内容仅有空的 `__init__.py`
- [x] 1.2.2 检查是否有其他文件导入此模块
- [x] 1.2.3 删除整个 `src/services/download/` 目录

### Phase 1 验证 ✅ 已完成

- [x] 运行 `ruff check src/` 确认无语法错误 (预存在的 lint 错误不影响)
- [x] 运行 `pytest tests/` 确认测试通过 (235 passed)
- [x] 运行 `python -m src.main --test` 确认应用启动正常

---

## Phase 2: 合并重复服务

**风险等级**: 🟡 中等  
**预计影响**: 减少文件数量，简化代码结构  
**依赖**: Phase 1 完成

### 2.1 合并 AnimeService 和 AnimeDetailService ✅ 已完成

**当前文件**:
- `src/services/anime_service.py` - AnimeService
- ~~`src/services/anime_detail_service.py`~~ - 已删除

**目标**: 合并为单一 `AnimeService`

**已完成步骤**:
- [x] 2.1.1 分析 AnimeDetailService 所有方法的完整实现
- [x] 2.1.2 分析 AnimeDetailService 的依赖项（与 AnimeService 相同）
- [x] 2.1.3 将 AnimeDetailService 方法迁移到 AnimeService
- [x] 2.1.4 更新 AnimeService 的构造函数（无需修改，依赖相同）
- [x] 2.1.5 更新 `src/container.py` 中的 provider（移除 anime_detail_service）
- [x] 2.1.6 更新 `src/interface/web/controllers/anime_detail.py` 使用 AnimeService
- [x] 2.1.7 删除 `src/services/anime_detail_service.py`
- [x] 2.1.8 更新 `src/services/__init__.py` 导出

### 2.2 合并 HardlinkService 到 FileService ✅ 已完成

**当前文件**:
- `src/services/file_service.py` - FileService
- ~~`src/services/file/hardlink_service.py`~~ - 已删除

**目标**: 统一到 `FileService` (因为不只处理硬链接，还可能操作原文件)

**已完成步骤**:
- [x] 2.2.1 分析 HardlinkService 所有方法的完整实现
- [x] 2.2.2 识别 FileService 和 HardlinkService 的功能重叠
- [x] 2.2.3 将 HardlinkService 方法迁移到 FileService（添加 path_builder 依赖）
- [x] 2.2.4 更新 `src/container.py` 中的 provider（移除 hardlink_service，更新 file_service）
- [x] 2.2.5 更新 DownloadManager 使用 FileService 替代 HardlinkService
- [x] 2.2.6 删除 `src/services/file/hardlink_service.py`
- [x] 2.2.7 更新相关导出（`src/services/__init__.py`, `src/services/file/__init__.py`）
- [x] 2.2.8 更新测试文件中的导入

### Phase 2 验证 ✅ 已完成

- [x] 运行 `ruff check src/` 确认无语法错误
- [x] 运行 `pytest tests/` 确认测试通过 (235 passed)
- [x] 运行 `python -m src.main --test` 确认应用启动正常

---

## Phase 3: 整合 Discord 通知器

**风险等级**: 🟡 中等  
**预计影响**: 减少 5-6 个文件  
**依赖**: Phase 2 完成

### 3.1 分析当前通知器结构

**当前文件** (`src/infrastructure/notification/discord/`):
| 文件 | 类 | 职责 |
|------|-----|------|
| `webhook_client.py` | DiscordWebhookClient | 基础 HTTP 发送 |
| `embed_builder.py` | EmbedBuilder | 构建 Embed 对象 |
| `rss_notifier.py` | RSSNotifier | RSS 相关通知 |
| `download_notifier.py` | DownloadNotifier | 下载相关通知 |
| `hardlink_notifier.py` | HardlinkNotifier | 硬链接相关通知 |
| `error_notifier.py` | ErrorNotifier | 错误通知 |
| `ai_usage_notifier.py` | AIUsageNotifier | AI 使用量通知 |
| `webhook_received_notifier.py` | WebhookReceivedNotifier | Webhook 接收通知 |

### 3.2 设计整合方案

**目标结构**:
```
discord/
├── webhook_client.py      # 保留：基础客户端
├── embed_builder.py       # 保留：Embed 构建器
└── notifier.py            # 新建：统一通知器
```

**新 DiscordNotifier 类设计**:
```python
class DiscordNotifier:
    '''统一 Discord 通知服务'''
    
    # RSS 通知
    def notify_rss_added(...)
    def notify_rss_filtered(...)
    
    # 下载通知
    def notify_download_started(...)
    def notify_download_completed(...)
    def notify_download_error(...)
    
    # 硬链接通知
    def notify_hardlink_created(...)
    def notify_hardlink_deleted(...)
    
    # 错误通知
    def notify_error(...)
    
    # AI 通知
    def notify_ai_usage(...)
    
    # Webhook 通知
    def notify_webhook_received(...)
```

**步骤**:
- [ ] 3.2.1 创建 `notifier.py` 新文件
- [ ] 3.2.2 实现 DiscordNotifier 类，整合所有通知方法
- [ ] 3.2.3 更新 `src/container.py` 使用新的 DiscordNotifier
- [ ] 3.2.4 更新所有引用旧通知器的代码
- [ ] 3.2.5 删除旧的通知器文件:
  - [ ] `rss_notifier.py`
  - [ ] `download_notifier.py`
  - [ ] `hardlink_notifier.py`
  - [ ] `error_notifier.py`
  - [ ] `ai_usage_notifier.py`
  - [ ] `webhook_received_notifier.py`
- [ ] 3.2.6 更新 `__init__.py` 导出

### Phase 3 验证

- [ ] 运行 `ruff check src/` 确认无语法错误
- [ ] 运行 `pytest tests/` 确认测试通过
- [ ] 手动测试各类 Discord 通知是否正常发送

---

## Phase 4: 统一依赖注入模式

**风险等级**: 🔴 高  
**预计影响**: 架构一致性提升  
**依赖**: Phase 3 完成

### 4.1 当前问题

项目同时使用多种依赖管理模式：
1. **dependency-injector Container** - 主要方式
2. **全局单例变量** (`_xxx_service`)
3. **工厂函数** (`get_xxx_service()`)

### 4.2 目标

统一使用 `dependency-injector` Container 模式。

### 4.3 待清理的全局单例

需要搜索并移除的模式：
- `_xxx_service: Optional[XxxService] = None`
- `def get_xxx_service() -> XxxService`
- 直接导入服务类而非通过 Container

**步骤**:
- [ ] 4.3.1 搜索所有全局单例模式 (`_xxx_service`)
- [ ] 4.3.2 搜索所有工厂函数 (`get_xxx_service`)
- [ ] 4.3.3 列出所有受影响的文件
- [ ] 4.3.4 逐个文件更新为使用 Container:
  - [ ] 更新导入语句
  - [ ] 更新服务获取方式
  - [ ] 删除单例变量和工厂函数
- [ ] 4.3.5 确保所有服务都通过 Container 注册
- [ ] 4.3.6 更新文档说明依赖注入用法

### Phase 4 验证

- [ ] 运行 `ruff check src/` 确认无语法错误
- [ ] 运行 `pytest tests/` 确认测试通过
- [ ] 运行 `python -m src.main --test` 确认应用启动正常
- [ ] 全面功能测试

---

## 执行顺序与检查点

```
┌─────────────────────────────────────────────────────────────────┐
│  开始清理工作流程                                                 │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: 删除未使用代码                                         │
│  - 删除 4 个异常类                                                │
│  - 删除空目录 src/services/download/                             │
│  ✓ 检查点: ruff + pytest + --test                               │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2: 合并重复服务                                           │
│  - AnimeService ← AnimeDetailService                            │
│  - FileService ← HardlinkService                                 │
│  ✓ 检查点: ruff + pytest + --test + 功能测试                     │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3: 整合 Discord 通知器                                    │
│  - 7 个通知器 → 1 个统一 DiscordNotifier                         │
│  ✓ 检查点: ruff + pytest + Discord 通知测试                      │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4: 统一依赖注入模式                                        │
│  - 移除全局单例                                                   │
│  - 统一使用 Container                                            │
│  ✓ 检查点: ruff + pytest + --test + 全面功能测试                  │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  完成！更新文档                                                   │
│  - 更新 CLAUDE.md                                                │
│  - 更新 docs/ARCHITECTURE.md                                     │
│  - 创建 CHANGELOG 条目                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 预期成果

### 文件变化统计

| Phase | 删除文件 | 新增文件 | 修改文件 |
|-------|----------|----------|----------|
| 1 | 1 目录 | 0 | 1 |
| 2 | 2 | 0 | 5-8 |
| 3 | 6 | 1 | 5-10 |
| 4 | 0 | 0 | 10-15 |
| **总计** | **8-9** | **1** | **21-34** |

### 代码简化

| 指标 | 清理前 | 清理后 | 变化 |
|------|--------|--------|------|
| 服务文件数 | 19 | 16 | -3 |
| 通知器文件数 | 8 | 3 | -5 |
| 异常类数 | 18 | 14 | -4 |
| 总文件数 | ~67 | ~55 | ~-12 |

---

## 回滚计划

每个 Phase 完成后：
1. 创建 Git 提交
2. 使用有意义的提交信息标记 Phase

如需回滚：
```bash
# 查看提交历史
git log --oneline

# 回滚到特定 Phase
git revert <commit-hash>
```

---

## 注意事项

1. **不要跳过验证步骤** - 每个 Phase 结束后必须运行测试
2. **保持小步提交** - 每个子任务完成后可以单独提交
3. **备份重要文件** - 在删除前确认文件确实无用
4. **测试覆盖** - 如果发现测试不足，先补充测试再重构

---

## 附录：命令参考

```bash
# 代码检查
ruff check src/

# 运行测试
pytest tests/

# 应用测试
python -m src.main --test

# 搜索引用
grep -r "ClassName" src/

# Git 提交
git add .
git commit -m "refactor: Phase N - description"
```
