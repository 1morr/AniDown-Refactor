# qBittorrent Webhook 配置

本文檔說明如何配置 qBittorrent 與 AniDown 的 Webhook 整合。

---

## 目錄

- [概述](#概述)
- [編譯 Webhook 工具](#編譯-webhook-工具)
- [配置 Webhook URL](#配置-webhook-url)
- [配置 qBittorrent](#配置-qbittorrent)
- [參數說明](#參數說明)
- [故障排除](#故障排除)

---

## 概述

AniDown 提供了專用的 Webhook 發送工具（`qb-webhook`），用於在種子下載完成時通知 AniDown 進行後續處理。

支持兩種版本：
- **Go 編譯版本**：性能更好，推薦使用
- **Python 腳本版本**：無需編譯，開箱即用

---

## 編譯 Webhook 工具

### 前置需求

- [Go 1.21+](https://go.dev/dl/)

### 編譯命令

```powershell
# 進入 qb-webhook 目錄
cd qb-webhook

# Windows
go build -o qb-webhook.exe

# Linux (或在 Windows 上交叉編譯)
$env:GOOS = "linux"; $env:GOARCH = "amd64"; go build -o qb-webhook-linux

# macOS
go build -o qb-webhook && chmod +x qb-webhook
```

### 編譯輸出

| 平台 | 輸出文件 |
|------|---------|
| Windows | `qb-webhook.exe` |
| Linux | `qb-webhook-linux` 或 `qb-webhook` |
| macOS | `qb-webhook` |

---

## 配置 Webhook URL

在 `qb-webhook` 目錄下創建 `config.json`：

```json
{
  "webhook_url": "http://localhost:5678/webhook/qbit",
  "log_file": "webhook.log",
  "retries": 3,
  "timeout": 10
}
```

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `webhook_url` | string | AniDown Webhook 接收地址 | `http://localhost:5678/webhook/qbit` |
| `log_file` | string | 日誌文件名 | `webhook.log` |
| `retries` | number | 請求重試次數 | `3` |
| `timeout` | number | 請求超時（秒） | `10` |

### Docker 環境

如果 AniDown 運行在 Docker 中：

```json
{
  "webhook_url": "http://anidown:5678/webhook/qbit"
}
```

或使用宿主機 IP：

```json
{
  "webhook_url": "http://192.168.1.100:5678/webhook/qbit"
}
```

---

## 配置 qBittorrent

在 qBittorrent 中配置「Torrent 完成時運行外部程序」：

**路徑**: qBittorrent → 選項 → 下載 → 「Torrent 完成時運行外部程序」

### Windows (Go 版本)

```
"C:\path\to\qb-webhook.exe" --name "%N" --category "%L" --tags "%G" --content-path "%F" --root-path "%R" --save-path "%D" --file-count "%C" --size "%Z" --tracker "%T" --hash-v1 "%I" --hash-v2 "%J" --id "%K"
```

### Windows (Python 版本)

```
python "C:\path\to\webhook_sender.py" --name "%N" --category "%L" --tags "%G" --content-path "%F" --root-path "%R" --save-path "%D" --file-count "%C" --size "%Z" --tracker "%T" --hash-v1 "%I" --hash-v2 "%J" --id "%K"
```

### Linux / macOS / Docker

```
/path/to/qb-webhook --name "%N" --category "%L" --tags "%G" --content-path "%F" --root-path "%R" --save-path "%D" --file-count "%C" --size "%Z" --tracker "%T" --hash-v1 "%I" --hash-v2 "%J" --id "%K"
```

---

## 參數說明

| 參數 | qBit 變量 | 說明 | 示例 |
|------|-----------|------|------|
| `--name` | `%N` | Torrent 名稱 | `[字幕組] 動漫名稱 - 01 [1080p].mkv` |
| `--category` | `%L` | 分類 | `AniDown` |
| `--tags` | `%G` | 標籤 | `anime,new` |
| `--content-path` | `%F` | 內容路徑（文件或目錄完整路徑） | `/downloads/AniDown/Anime/...` |
| `--root-path` | `%R` | 根路徑（種子的根目錄） | `/downloads/AniDown/Anime/動漫名稱` |
| `--save-path` | `%D` | 保存路徑 | `/downloads/AniDown/Anime/` |
| `--file-count` | `%C` | 文件數量 | `5` |
| `--size` | `%Z` | 大小（字節） | `1073741824` |
| `--tracker` | `%T` | Tracker URL | `http://tracker.example.com` |
| `--hash-v1` | `%I` | v1 Hash | `abc123...` |
| `--hash-v2` | `%J` | v2 Hash | `def456...` |
| `--id` | `%K` | Torrent ID | `12345` |

---

## 故障排除

### Webhook 未發送

1. **檢查日誌文件**

   查看 `qb-webhook` 同級目錄下的 `webhook.log` 文件：

   ```bash
   cat webhook.log
   ```

2. **手動測試 Webhook**

   使用 curl 測試 AniDown Webhook 端點：

   ```bash
   curl -X POST http://localhost:5678/webhook/qbit \
     -H "Content-Type: application/json" \
     -d '{"name": "test", "category": "AniDown"}'
   ```

3. **檢查網絡連接**

   確保 qBittorrent 可以訪問 AniDown 的 Webhook 端口。

### 常見錯誤

| 錯誤 | 可能原因 | 解決方案 |
|------|---------|---------|
| Connection refused | AniDown 未運行或端口錯誤 | 確認 AniDown 正在運行，檢查端口配置 |
| Timeout | 網絡延遲或防火牆 | 增加 timeout 值，檢查防火牆規則 |
| 404 Not Found | URL 路徑錯誤 | 確認 URL 為 `/webhook/qbit` |
| 分類不匹配 | Webhook 僅處理特定分類 | 確保種子分類為 `AniDown` |

### 權限問題

**Windows**: 確保 qBittorrent 有權限執行 `qb-webhook.exe`

**Linux/macOS**: 確保執行權限：
```bash
chmod +x /path/to/qb-webhook
```

### Docker 特殊情況

如果 qBittorrent 和 AniDown 都在 Docker 中：

1. 確保兩個容器在同一 Docker 網絡
2. 使用容器名稱作為主機名：`http://anidown:5678/webhook/qbit`
3. 或使用 Docker 橋接網絡的網關 IP

---

## 相關文檔

- [返回主文檔](../README.md)
- [配置說明](CONFIGURATION.md)
- [安裝指南](INSTALLATION.md)
