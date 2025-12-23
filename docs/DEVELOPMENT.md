# 開發指南

本文檔說明 AniDown 的項目結構、開發環境設置和測試方法。

---

## 目錄

- [目錄結構](#目錄結構)
- [開發環境設置](#開發環境設置)
- [測試](#測試)
- [代碼檢查](#代碼檢查)
- [代碼風格](#代碼風格)

---

## 目錄結構

```
AniDown/
├── src/
│   ├── core/                    # 核心層
│   │   ├── domain/              # 領域模型
│   │   ├── interfaces/          # 接口定義
│   │   ├── utils/               # 工具類
│   │   ├── config.py            # 配置管理
│   │   └── exceptions.py        # 異常定義
│   │
│   ├── infrastructure/          # 基礎設施層
│   │   ├── ai/                  # AI 組件
│   │   │   ├── api_client.py    # OpenAI 客戶端
│   │   │   ├── key_pool.py      # Key 池管理
│   │   │   ├── circuit_breaker.py # 熔斷器
│   │   │   ├── title_parser.py  # 標題解析器
│   │   │   └── file_renamer.py  # 文件重命名器
│   │   ├── database/            # 數據庫
│   │   ├── downloader/          # 下載器適配
│   │   ├── metadata/            # 元數據服務
│   │   ├── notification/        # 通知服務
│   │   └── repositories/        # 數據倉儲
│   │
│   ├── services/                # 服務層
│   │   ├── queue/               # 隊列處理
│   │   ├── file/                # 文件服務
│   │   ├── rename/              # 重命名服務
│   │   ├── download_manager.py  # 下載管理器
│   │   └── rss_service.py       # RSS 服務
│   │
│   ├── interface/               # 接口層
│   │   ├── web/                 # Web UI
│   │   └── webhook/             # Webhook 處理
│   │
│   ├── container.py             # 依賴注入容器
│   └── main.py                  # 應用入口
│
├── tests/                       # 測試目錄
│   ├── unit/                    # 單元測試
│   └── integration/             # 集成測試
│
├── qb-webhook/                  # qBittorrent Webhook 工具
├── config.json.example          # 配置範例
├── docker-compose.yml           # Docker 編排
├── Dockerfile                   # Docker 鏡像
├── requirements.txt             # Python 依賴
└── README.md
```

### 各層職責

| 層級 | 目錄 | 職責 |
|------|------|------|
| Core | `src/core/` | 領域模型、接口定義、異常、配置 |
| Infrastructure | `src/infrastructure/` | 外部服務適配、數據持久化 |
| Services | `src/services/` | 業務邏輯、隊列處理 |
| Interface | `src/interface/` | Web UI、Webhook、CLI |

---

## 開發環境設置

### 1. 克隆項目

```bash
git clone https://github.com/your-repo/anidown.git
cd anidown
```

### 2. 創建虛擬環境

```bash
# 創建虛擬環境
python -m venv venv

# 激活（Linux/macOS）
source venv/bin/activate

# 激活（Windows）
.\venv\Scripts\Activate.ps1
```

### 3. 安裝依賴

```bash
pip install -r requirements.txt

# 安裝開發依賴（如果有）
pip install -r requirements-dev.txt
```

### 4. 配置

```bash
cp config.json.example config.json
# 編輯 config.json
```

---

## 測試

### 運行所有測試

```bash
pytest tests/
```

### 運行單元測試

```bash
pytest -m unit
```

### 運行集成測試

```bash
pytest -m integration
```

### 運行特定測試文件

```bash
pytest tests/unit/test_key_pool.py
```

### 運行特定測試函數

```bash
pytest tests/unit/test_key_pool.py::TestKeyPool::test_reserve_returns_key
```

### 測試覆蓋率

```bash
pytest --cov=src --cov-report=term-missing
```

### 跳過需要外部服務的測試

```bash
# 跳過需要 AI API 的測試
pytest -m "not requires_ai"

# 跳過需要 qBittorrent 的測試
pytest -m "not requires_qbit"
```

### 測試標記（Markers）

| 標記 | 說明 |
|------|------|
| `@pytest.mark.unit` | 快速單元測試，無外部依賴 |
| `@pytest.mark.integration` | 集成測試，可能需要外部服務 |
| `@pytest.mark.slow` | 慢速測試（API 調用、大數據處理） |
| `@pytest.mark.requires_qbit` | 需要 qBittorrent 連接 |
| `@pytest.mark.requires_ai` | 需要 OpenAI API |
| `@pytest.mark.requires_discord` | 需要 Discord Webhook |
| `@pytest.mark.requires_tvdb` | 需要 TVDB API |

---

## 代碼檢查

### Ruff

```bash
# 檢查代碼
ruff check src/

# 自動修復
ruff check src/ --fix

# 格式化
ruff format src/
```

---

## 代碼風格

項目遵循 `CODE_STYLE.md` 中定義的代碼風格。

### 主要規則

| 規則 | 說明 |
|------|------|
| PEP 8 | 遵循 Python PEP 8 規範 |
| 單引號 | 字符串使用單引號 |
| 行長度 | 最大 100 字符 |
| 類型註解 | 所有函數必須有類型註解 |
| Docstring | 使用 Google 風格 docstring |
| 接口命名 | 接口使用 `I` 前綴（如 `IAnimeRepository`） |

### 日誌 Emoji 指示符

| Emoji | 含義 |
|-------|------|
| 🚀 | 啟動 / 開始 |
| ✅ | 成功 |
| ❌ | 錯誤 |
| ⚠️ | 警告 |
| 🔄 | 處理中 |

### 示例

```python
from typing import Optional, List
from src.core.interfaces import IAnimeRepository

def get_anime_by_id(anime_id: int) -> Optional[Anime]:
    '''根據 ID 獲取動漫信息。

    Args:
        anime_id: 動漫 ID

    Returns:
        動漫對象，如果不存在則返回 None
    '''
    logger.info(f'🔄 正在獲取動漫 ID: {anime_id}')
    try:
        anime = repo.get(anime_id)
        logger.info(f'✅ 成功獲取動漫: {anime.title}')
        return anime
    except Exception as e:
        logger.error(f'❌ 獲取動漫失敗: {e}')
        return None
```

---

## 相關文檔

- [返回主文檔](../README.md)
- [系統架構](ARCHITECTURE.md)
- [配置說明](CONFIGURATION.md)
