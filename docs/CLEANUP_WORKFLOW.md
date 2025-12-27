# AniDown 代码清理工作流程

**基于**: CODE_ANALYSIS_REPORT.md
**创建日期**: 2025-12-28
**目标**: 系统性清理冗余代码，统一重复实现，优化架构

---

## 概览

| Phase | 名称 | 优先级 | 预计删除代码 | 风险等级 |
|-------|------|--------|-------------|----------|
| 1 | 删除死代码文件 | 🔴 高 | ~800 行 | 低 |
| 2 | 统一路径构建逻辑 | 🔴 高 | ~110 行 | 中 |
| 3 | 清理未使用的代码片段 | 🟠 中 | ~50 行 | 低 |
| 4 | 待确认服务处理 | 🟡 低 | ~200 行 | 低 |

**总计**: 删除约 1160+ 行冗余代码

---

## Phase 1: 删除死代码文件 🔴

**风险等级**: 低 (这些文件从未被导入)
**预计时间**: 15 分钟

### 1.1 删除未使用的处理器类

这些类已完整实现，但从未被实例化。`DownloadManager` 自己实现了相同功能。

```bash
# 待删除文件
src/services/download/rss_processor.py           # ~300 行
src/services/download/torrent_completion_handler.py  # ~200 行
```

**验证步骤**:
```bash
# 确认没有导入
grep -r "from src.services.download.rss_processor" src/
grep -r "from src.services.download.torrent_completion_handler" src/
grep -r "RSSProcessor" src/ --include="*.py"
grep -r "TorrentCompletionHandler" src/ --include="*.py"
```

- [ ] 运行验证命令确认无引用
- [ ] 删除 `src/services/download/rss_processor.py`
- [ ] 删除 `src/services/download/torrent_completion_handler.py`
- [ ] 运行测试: `pytest tests/`
- [ ] 运行应用验证: `python -m src.main --test`

### 1.2 删除未使用的 utils 文件夹

所有控制器使用 `src/interface/web/utils.py`，而不是 `utils/` 文件夹。

```bash
# 待删除文件夹
src/interface/web/utils/                         # 整个文件夹 ~300 行
  ├── api_response.py
  ├── decorators.py
  ├── logger.py
  ├── validators.py
  └── __init__.py (如果存在)
```

**验证步骤**:
```bash
# 确认没有从 utils/ 导入
grep -r "from src.interface.web.utils." src/
grep -r "from src.interface.web.utils import" src/ | grep -v "utils.py"
```

- [ ] 运行验证命令确认无引用
- [ ] 删除整个 `src/interface/web/utils/` 文件夹
- [ ] 运行测试: `pytest tests/`
- [ ] 启动应用验证 Web UI 正常

### Phase 1 完成检查
- [ ] 所有死代码文件已删除
- [ ] 测试通过: `pytest tests/`
- [ ] 应用验证通过: `python -m src.main --test`
- [ ] Web UI 正常访问

---

## Phase 2: 统一路径构建逻辑 🔴

**风险等级**: 中 (需要修改多个服务的构造函数和方法调用)
**预计时间**: 45 分钟

### 2.1 修改 container.py - 注入 PathBuilder

**文件**: `src/container.py`

```python
# 修改 AnimeService 注入
anime_service = providers.Singleton(
    AnimeService,
    anime_repo=anime_repo,
    download_repo=download_repo,
    download_client=qb_client,
    path_builder=path_builder  # ← 添加
)

# 修改 AnimeDetailService 注入
anime_detail_service = providers.Singleton(
    AnimeDetailService,
    anime_repo=anime_repo,
    download_repo=download_repo,
    download_client=qb_client,
    path_builder=path_builder  # ← 添加
)

# 修改 RenameService 注入 (如果还没有)
rename_service = providers.Singleton(
    RenameService,
    file_classifier=file_classifier,
    filename_formatter=filename_formatter,
    anime_repo=anime_repo,
    ai_file_renamer=file_renamer,
    path_builder=path_builder  # ← 添加
)
```

- [ ] 修改 `container.py` 中的 `anime_service` 定义
- [ ] 修改 `container.py` 中的 `anime_detail_service` 定义
- [ ] 修改 `container.py` 中的 `rename_service` 定义

### 2.2 修改 AnimeService

**文件**: `src/services/anime_service.py`

**Step 1**: 修改构造函数
```python
from src.services.file.path_builder import PathBuilder

class AnimeService:
    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        download_client: IDownloadClient,
        path_builder: PathBuilder  # ← 添加
    ):
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._download_client = download_client
        self._path_builder = path_builder  # ← 添加
```

**Step 2**: 删除重复方法
```python
# 删除这些方法 (~50 行):
# - _sanitize_title()
# - _get_original_folder_path()
# - _get_hardlink_folder_path()
```

**Step 3**: 更新调用点
```python
# 原来:
path = self._get_original_folder_path(title, media_type, category)

# 改为:
path = self._path_builder.build_download_path(title, season, category, media_type)
```

```python
# 原来:
path = self._get_hardlink_folder_path(title, media_type, category)

# 改为:
path = self._path_builder.build_library_path(title, media_type, category)
```

- [ ] 修改 `AnimeService.__init__()` 添加 `path_builder` 参数
- [ ] 查找 `_get_original_folder_path` 的所有调用点并替换
- [ ] 查找 `_get_hardlink_folder_path` 的所有调用点并替换
- [ ] 删除 `_sanitize_title()` 方法
- [ ] 删除 `_get_original_folder_path()` 方法
- [ ] 删除 `_get_hardlink_folder_path()` 方法

### 2.3 修改 AnimeDetailService

**文件**: `src/services/anime_detail_service.py`

**Step 1**: 修改构造函数
```python
from src.services.file.path_builder import PathBuilder

class AnimeDetailService:
    def __init__(
        self,
        anime_repo: IAnimeRepository,
        download_repo: IDownloadRepository,
        download_client: IDownloadClient,
        path_builder: PathBuilder  # ← 添加
    ):
        self._anime_repo = anime_repo
        self._download_repo = download_repo
        self._download_client = download_client
        self._path_builder = path_builder  # ← 添加
```

**Step 2**: 删除重复方法
```python
# 删除这些方法 (~40 行):
# - _sanitize_title()
# - _build_auto_target_path()
```

**Step 3**: 更新调用点
```python
# 原来:
path = self._build_auto_target_path(anime_info)

# 改为:
path = self._path_builder.build_target_directory(
    anime_title=anime_info.get('short_title') or anime_info.get('original_title'),
    media_type=anime_info.get('media_type', 'anime'),
    category=anime_info.get('category', 'tv')
)
```

- [ ] 修改 `AnimeDetailService.__init__()` 添加 `path_builder` 参数
- [ ] 查找 `_build_auto_target_path` 的所有调用点并替换
- [ ] 删除 `_sanitize_title()` 方法
- [ ] 删除 `_build_auto_target_path()` 方法

### 2.4 修改 RenameService

**文件**: `src/services/rename/rename_service.py`

**Step 1**: 修改构造函数 (如果还没有 path_builder)
```python
from src.services.file.path_builder import PathBuilder

class RenameService:
    def __init__(
        self,
        file_classifier: FileClassifier,
        filename_formatter: FilenameFormatter,
        anime_repo: IAnimeRepository,
        ai_file_renamer: IFileRenamer,
        path_builder: PathBuilder  # ← 添加
    ):
        # ...
        self._path_builder = path_builder
```

**Step 2**: 删除或替换 `_sanitize_filename()`
```python
# 删除 _sanitize_filename() 方法 (~20 行)
# 所有调用改为:
self._path_builder._sanitize_filename(name)
```

- [ ] 检查 `RenameService.__init__()` 是否已有 `path_builder`
- [ ] 如果没有，添加 `path_builder` 参数
- [ ] 查找所有 `self._sanitize_filename` 调用并替换
- [ ] 删除 `_sanitize_filename()` 方法

### 2.5 修改控制器调用

**文件**: `src/interface/web/controllers/anime_detail.py`

检查是否直接调用了 `_sanitize_title`:
```python
# 如果有类似这样的代码:
sanitized_title = anime_detail_service._sanitize_title(anime_title)

# 改为:
# 方案1: 通过服务获取 (推荐)
target_path = anime_detail_service.get_target_path(anime_info)

# 方案2: 直接使用 path_builder
from src.container import container
path_builder = container.path_builder()
sanitized_title = path_builder._sanitize_filename(anime_title)
```

- [ ] 检查 `anime_detail.py` 是否直接调用 `_sanitize_title`
- [ ] 如果有，修改为使用 `path_builder`

### Phase 2 完成检查
- [ ] 所有服务已注入 `path_builder`
- [ ] 所有重复的 `_sanitize_title` 方法已删除
- [ ] 所有调用点已更新
- [ ] 测试通过: `pytest tests/`
- [ ] 应用验证通过: `python -m src.main --test`
- [ ] Web UI 动漫列表、详情页正常
- [ ] 硬链接创建功能正常

---

## Phase 3: 清理未使用的代码片段 🟠

**风险等级**: 低 (只删除未使用的类定义)
**预计时间**: 10 分钟

### 3.1 清理未使用的异常类

**文件**: `src/core/exceptions.py`

```python
# 删除这些类:
class RSSParseError(AniDownError):
    """RSS 解析错误"""
    pass

class ConfigValidationError(AniDownError):
    """配置验证错误"""
    pass

class RecordNotFoundError(AniDownError):
    """记录未找到错误"""
    pass
```

**验证步骤**:
```bash
grep -r "RSSParseError" src/ --include="*.py"
grep -r "ConfigValidationError" src/ --include="*.py"
grep -r "RecordNotFoundError" src/ --include="*.py"
```

- [ ] 验证这些异常类没有被使用
- [ ] 删除 `RSSParseError` 类
- [ ] 删除 `ConfigValidationError` 类
- [ ] 删除 `RecordNotFoundError` 类

### 3.2 清理未使用的值对象

**文件**: `src/core/domain/value_objects.py`

```python
# 删除 FilePath 类 (~30 行)
@dataclass(frozen=True)
class FilePath:
    """文件路径值对象"""
    path: str
    # ...
```

**验证步骤**:
```bash
grep -r "FilePath" src/ --include="*.py" | grep -v "value_objects.py"
```

- [ ] 验证 `FilePath` 没有被使用
- [ ] 删除 `FilePath` 类

### Phase 3 完成检查
- [ ] 未使用的异常类已删除
- [ ] 未使用的值对象已删除
- [ ] 测试通过: `pytest tests/`
- [ ] 代码风格检查: `ruff check src/`

---

## Phase 4: 待确认服务处理 🟡

**风险等级**: 低
**预计时间**: 15 分钟

### 4.1 评估 ai_debug_service

**文件**: `src/services/ai_debug_service.py`

**当前状态**: 注册到容器但从未通过 `container.ai_debug_service()` 获取

**检查**:
```bash
grep -r "ai_debug_service" src/ --include="*.py"
grep -r "AIDebugService" src/ --include="*.py"
```

**决策**:
- [ ] 如果有使用计划 → 保留
- [ ] 如果确定不需要 → 删除文件并从 `container.py` 移除注册

### 4.2 评估 log_rotation_service

**文件**: `src/services/log_rotation_service.py`

**当前状态**: 注册到容器但从未通过 `container.log_rotation_service()` 获取

**检查**:
```bash
grep -r "log_rotation_service" src/ --include="*.py"
grep -r "LogRotationService" src/ --include="*.py"
```

**决策**:
- [ ] 如果有使用计划 → 保留
- [ ] 如果确定不需要 → 删除文件并从 `container.py` 移除注册

### Phase 4 完成检查
- [ ] 已评估所有待确认服务
- [ ] 做出保留/删除决策
- [ ] 测试通过: `pytest tests/`

---

## 最终验证

完成所有 Phase 后，执行以下验证:

### 功能验证
```bash
# 1. 代码风格检查
ruff check src/

# 2. 运行所有测试
pytest tests/

# 3. 应用启动验证
python -m src.main --test

# 4. 完整功能测试
python -m src.main
# 手动测试:
# - RSS 订阅添加
# - 手动上传
# - 动漫列表查看
# - 动漫详情查看
# - 硬链接创建
```

### 代码统计
```bash
# 验证代码行数减少
find src -name "*.py" | xargs wc -l
```

### 完成清单
- [ ] Phase 1 完成: 死代码文件已删除
- [ ] Phase 2 完成: 路径构建逻辑已统一
- [ ] Phase 3 完成: 未使用代码片段已清理
- [ ] Phase 4 完成: 待确认服务已处理
- [ ] 所有测试通过
- [ ] 应用功能正常
- [ ] 代码风格检查通过

---

## 回滚计划

如果出现问题，可以使用 git 回滚:

```bash
# 查看提交历史
git log --oneline -10

# 回滚到指定提交
git reset --hard <commit-hash>

# 或者回滚单个文件
git checkout <commit-hash> -- <file-path>
```

**建议**: 每完成一个 Phase 就创建一个提交:
```bash
git add .
git commit -m "cleanup: Phase N - 描述"
```

---

*工作流程生成: Claude Code*
