# 安裝指南

本文檔詳細說明 AniDown 的安裝和部署方式。

---

## 目錄

- [方法一：Docker 部署（推薦）](#方法一docker-部署推薦)
- [方法二：Windows 本地運行（虛擬環境）](#方法二windows-本地運行虛擬環境)
- [Windows 常見問題](#windows-常見問題)

---

## 方法一：Docker 部署（推薦）

Docker 部署是最簡單的方式，適合 Linux/macOS/Windows 用戶。

### 1. 克隆項目

```bash
git clone https://github.com/your-repo/anidown.git
cd anidown
```

### 2. 複製並編輯環境配置

```bash
# Linux/macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

編輯 `.env` 文件，配置時區和路徑：

```ini
# 時區設置
TZ=Asia/Taipei

# 端口配置
WEBUI_PORT=8081
WEBHOOK_PORT=5678

# 數據目錄 (可使用絕對路徑)
HOST_DB_PATH=./data/db
HOST_CONFIG_PATH=./data/config
HOST_LOG_PATH=./data/logs
HOST_AI_LOG_PATH=./data/ai_logs
HOST_STORAGE_PATH=./storage
```

### 3. 創建配置文件

```bash
# 創建配置目錄
mkdir -p data/config

# 複製配置範例
cp config.json.example data/config/config.json
```

編輯 `data/config/config.json`，填入 OpenAI API Key 和 qBittorrent 連接信息。

> 詳細配置說明請參閱 [配置說明](CONFIGURATION.md)

### 4. 啟動服務

#### 使用 Docker Compose（推薦）

```bash
# 構建並啟動
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 停止服務
docker-compose down
```

#### 使用 Docker Run（無需 Docker Compose）

如果你不想使用 Docker Compose，可以使用以下 `docker run` 命令：

**第一步：構建鏡像（可選）**

如果你想使用本地構建的鏡像，而非 Docker Hub 上的預構建鏡像：

```bash
docker build -t 1mor/anidown:latest .
```

**第二步：運行容器**

Linux/macOS:
```bash
docker run -d \
  --name anidown \
  --restart unless-stopped \
  -p 8081:8081 \
  -p 5678:5678 \
  -v ./data/db:/data/db \
  -v ./data/config:/data/config \
  -v ./data/logs:/data/logs \
  -v ./data/ai_logs:/data/ai_logs \
  -v ./storage:/storage \
  -e TZ=Asia/Taipei \
  -e DEBUG=false \
  -e CONFIG_PATH=/data/config/config.json \
  -e DB_PATH=/data/db/anime_downloader.db \
  -e LOG_PATH=/data/logs \
  -e AI_LOG_PATH=/data/ai_logs \
  -e ANIDOWN_WEBUI__HOST=0.0.0.0 \
  -e ANIDOWN_WEBUI__PORT=8081 \
  -e ANIDOWN_WEBHOOK__HOST=0.0.0.0 \
  -e ANIDOWN_WEBHOOK__PORT=5678 \
  1mor/anidown:latest
```

Windows PowerShell:
```powershell
docker run -d `
  --name anidown `
  --restart unless-stopped `
  -p 8081:8081 `
  -p 5678:5678 `
  -v ${PWD}/data/db:/data/db `
  -v ${PWD}/data/config:/data/config `
  -v ${PWD}/data/logs:/data/logs `
  -v ${PWD}/data/ai_logs:/data/ai_logs `
  -v ${PWD}/storage:/storage `
  -e TZ=Asia/Taipei `
  -e DEBUG=false `
  -e CONFIG_PATH=/data/config/config.json `
  -e DB_PATH=/data/db/anime_downloader.db `
  -e LOG_PATH=/data/logs `
  -e AI_LOG_PATH=/data/ai_logs `
  -e ANIDOWN_WEBUI__HOST=0.0.0.0 `
  -e ANIDOWN_WEBUI__PORT=8081 `
  -e ANIDOWN_WEBHOOK__HOST=0.0.0.0 `
  -e ANIDOWN_WEBHOOK__PORT=5678 `
  1mor/anidown:latest
```

**常用管理命令**

```bash
# 查看日誌
docker logs -f anidown

# 停止容器
docker stop anidown

# 啟動容器
docker start anidown

# 刪除容器
docker rm anidown

# 進入容器 shell
docker exec -it anidown /bin/sh
```

### 5. 訪問 Web UI

打開瀏覽器訪問 `http://localhost:8081`

### Docker 目錄結構

```
./
├── data/
│   ├── config/          # 配置文件 (config.json)
│   ├── db/              # SQLite 數據庫
│   ├── logs/            # 應用日誌
│   └── ai_logs/         # AI 調試日誌
└── storage/
    ├── Downloads/AniDown/    # qBittorrent 下載目錄
    │   ├── Anime/
    │   │   ├── TV/
    │   │   └── Movies/
    │   └── LiveAction/
    │       ├── TV/
    │       └── Movies/
    └── Library/              # Plex/Jellyfin 媒體庫
        ├── Anime/
        │   ├── TV/
        │   └── Movies/
        └── LiveAction/
            ├── TV/
            └── Movies/
```

> **重要**: `Downloads` 和 `Library` 必須在同一文件系統（同一掛載點）以支持硬鏈接。

---

## 方法二：Windows 本地運行（虛擬環境）

在 Windows 上運行需要使用 Python 虛擬環境來隔離依賴。

### 前置需求

- **Python 3.11+**: [下載 Python](https://www.python.org/downloads/)
- **qBittorrent 4.4+**: 需啟用 WebAPI
- **Git** (可選): 用於克隆項目

### 1. 克隆或下載項目

```powershell
# 使用 Git
git clone https://github.com/your-repo/anidown.git
cd anidown

# 或下載 ZIP 解壓後進入目錄
```

### 2. 創建虛擬環境

```powershell
# 創建虛擬環境
python -m venv venv

# 激活虛擬環境
.\venv\Scripts\Activate.ps1

# 如果遇到執行策略錯誤，先運行：
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

激活後，命令行提示符前會顯示 `(venv)`。

### 3. 安裝依賴

```powershell
# 確保 pip 是最新版本
python -m pip install --upgrade pip

# 安裝項目依賴
pip install -r requirements.txt
```

### 4. 配置文件

```powershell
# 複製配置範例
Copy-Item config.json.example config.json
```

編輯 `config.json`，配置以下關鍵項：

```json
{
  "qbittorrent": {
    "url": "http://localhost:8080",
    "username": "admin",
    "password": "your-password",
    "base_download_path": "D:/Downloads/AniDown/"
  },
  "openai": {
    "key_pools": [
      {
        "name": "MyPool",
        "base_url": "https://api.openai.com/v1",
        "api_keys": [
          {
            "name": "Key 1",
            "api_key": "sk-your-api-key",
            "rpm": 60,
            "rpd": 1000,
            "enabled": true
          }
        ]
      }
    ],
    "title_parse": {
      "pool_name": "MyPool",
      "model": "gpt-4"
    },
    "multi_file_rename": {
      "pool_name": "MyPool"
    }
  },
  "link_target_path": "D:/Media/TV Shows",
  "movie_link_target_path": "D:/Media/Movies"
}
```

> **Windows 路徑注意**: 使用正斜杠 `/` 或雙反斜杠 `\\`，例如 `D:/Downloads` 或 `D:\\Downloads`

> 詳細配置說明請參閱 [配置說明](CONFIGURATION.md)

### 5. 運行應用

```powershell
# 確保虛擬環境已激活 (命令行顯示 (venv))
.\venv\Scripts\Activate.ps1

# 運行驗證測試
python -m src.main --test

# 正常啟動
python -m src.main

# Debug 模式
python -m src.main --debug
```

### 6. 訪問 Web UI

打開瀏覽器訪問 `http://localhost:8081`

### 創建快捷啟動腳本 (可選)

創建 `start.bat` 文件：

```batch
@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python -m src.main
pause
```

或創建 `start.ps1` (PowerShell):

```powershell
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& ".\venv\Scripts\Activate.ps1"
python -m src.main
```

### 設置開機自啟 (可選)

1. 按 `Win + R`，輸入 `shell:startup`
2. 將 `start.bat` 的快捷方式放入此目錄

---

## Windows 常見問題

### Q: 執行 PowerShell 腳本報錯「無法加載文件...因為在此系統上禁止運行腳本」

```powershell
# 以管理員身份運行 PowerShell，執行：
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Q: pip install 報錯或速度慢

```powershell
# 使用國內鏡像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q: 虛擬環境每次都要手動激活

創建啟動腳本 (如上所述) 或使用 VS Code 自動激活。

### Q: Windows 硬鏈接失敗

- 確保下載目錄和媒體庫在**同一分區**（如都在 D: 盤）
- 確保運行 AniDown 的用戶有足夠權限

### Q: Python 找不到模組

確保虛擬環境已激活，命令行提示符前應顯示 `(venv)`。

### Q: qBittorrent 連接失敗

1. 確保 qBittorrent WebUI 已啟用：選項 → Web UI → 啟用 Web 用戶界面
2. 檢查端口是否正確（默認 8080）
3. 檢查用戶名密碼是否正確

---

## 相關文檔

- [返回主文檔](../README.md)
- [配置說明](CONFIGURATION.md)
- [系統架構](ARCHITECTURE.md)
- [qBittorrent Webhook 配置](QBITTORRENT_WEBHOOK.md)
