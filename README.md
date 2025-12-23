# AniDown

<p align="center">
  <strong>AI-Driven Anime Download Manager</strong>
</p>

<p align="center">
  自動下載、智能重命名、整理動漫到 Plex/Jellyfin 媒體庫
</p>

---

## 目錄

- [功能特點](#功能特點)
- [環境需求](#環境需求)
- [快速開始](#快速開始)
- [端口說明](#端口說明)
- [詳細文檔](#詳細文檔)
- [License](#license)

---

## 功能特點

- **RSS 訂閱監控** - 自動解析 RSS 訂閱源，發現新番劇集
- **AI 智能解析** - 使用 GPT 模型解析標題，提取動漫名稱、集數、字幕組等信息
- **自動重命名** - 將下載的文件重命名為 Plex/Jellyfin 標準格式
- **硬鏈接整理** - 使用硬鏈接將文件整理到媒體庫，不佔用額外空間
- **Discord 通知** - 下載完成、處理進度等狀態通過 Discord Webhook 推送
- **Web UI** - 直觀的網頁管理界面
- **多 API Key 支持** - API Key 池管理，支持 RPM/RPD 限制和自動輪換

---

## 環境需求

### 必需組件

| 組件 | 版本要求 | 說明 |
|------|---------|------|
| **Python** | 3.11+ | 運行環境 |
| **qBittorrent** | 4.4+ | 下載客戶端，需啟用 WebAPI |
| **OpenAI API** | - | OpenAI或其他兼容的API |

### 可選組件

| 組件 | 說明 |
|------|------|
| **Docker** | 容器化部署 |
| **Discord Webhook** | 通知推送 |
| **TVDB API** | 獲取動漫元數據 |

---

## 快速開始

### 方法一：Docker 部署（推薦）

```bash
# 1. 克隆項目
git clone https://github.com/your-repo/anidown.git
cd anidown

# 2. 複製配置
cp .env.example .env
mkdir -p data/config
cp config.json.example data/config/config.json

# 3. 編輯配置文件
# 編輯 .env 和 data/config/config.json

# 4. 啟動
docker-compose up -d
```

> 詳細說明請參閱 [安裝指南 - Docker 部署](docs/INSTALLATION.md#方法一docker-部署推薦)

### 方法二：Windows 本地運行

```powershell
# 1. 創建虛擬環境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 配置
Copy-Item config.json.example config.json
# 編輯 config.json

# 4. 運行
python -m src.main
```

> 詳細說明請參閱 [安裝指南 - Windows 本地運行](docs/INSTALLATION.md#方法二windows-本地運行虛擬環境)

---

## 端口說明

| 端口 | 服務 | 說明 |
|------|------|------|
| 8081 | Web UI | 管理界面 |
| 5678 | Webhook | qBittorrent 回調 |

訪問 `http://localhost:8081` 即可使用 Web UI。

---

## 詳細文檔

| 文檔 | 說明 |
|------|------|
| [系統架構](docs/ARCHITECTURE.md) | 系統架構圖、工作流程、隊列機制、AI Key Pool 機制 |
| [安裝指南](docs/INSTALLATION.md) | Docker 部署、Windows 本地運行、常見問題 |
| [配置說明](docs/CONFIGURATION.md) | 完整配置參考：RSS、qBittorrent、OpenAI、Discord 等 |
| [qBittorrent Webhook](docs/QBITTORRENT_WEBHOOK.md) | Webhook 工具編譯、配置、故障排除 |
| [CLI 命令](docs/CLI.md) | 命令行使用指南 |
| [開發指南](docs/DEVELOPMENT.md) | 目錄結構、測試、代碼檢查 |

---

## License

[GPLv3 License](LICENSE)
