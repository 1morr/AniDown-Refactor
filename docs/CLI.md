# CLI 命令

本文檔說明 AniDown 的命令行使用方式。

---

## 目錄

- [基本用法](#基本用法)
- [啟動選項](#啟動選項)
- [RSS 命令](#rss-命令)
- [磁力鏈接命令](#磁力鏈接命令)
- [種子文件命令](#種子文件命令)
- [使用示例](#使用示例)

---

## 基本用法

```bash
python -m src.main [選項] [命令] [參數]
```

---

## 啟動選項

### 正常啟動（服務器模式）

```bash
python -m src.main
```

啟動完整的 AniDown 服務，包括：
- Web UI (默認端口 8081)
- Webhook Server (默認端口 5678)
- RSS 定時檢查
- 隊列處理器

### Debug 模式

```bash
python -m src.main --debug
```

啟用詳細 AI 日誌，適合調試 AI 解析問題。日誌將輸出到 `ai_logs/` 目錄。

### 驗證測試

```bash
python -m src.main --test
```

運行系統驗證測試，檢查：
- 配置文件是否正確
- 數據庫連接是否正常
- qBittorrent 連接是否正常
- 依賴注入容器是否正確初始化

---

## RSS 命令

手動處理 RSS 訂閱源。

### 語法

```bash
python -m src.main rss <url>
```

### 參數

| 參數 | 說明 |
|------|------|
| `url` | RSS 訂閱 URL |

### 示例

```bash
# 手動處理單個 RSS 源
python -m src.main rss "https://mikanani.me/RSS/Bangumi?bangumiId=xxx"
```

---

## 磁力鏈接命令

手動添加磁力鏈接。

### 語法

```bash
python -m src.main magnet <hash> <title> <group> [選項]
```

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `hash` | 必需 | 磁力鏈接 Hash（infohash） |
| `title` | 必需 | 動漫標題 |
| `group` | 必需 | 字幕組名稱 |

### 選項

| 選項 | 說明 | 默認值 |
|------|------|--------|
| `--season N` | 指定季數 | 自動檢測 |
| `--category tv\|movie` | 指定類型（TV 或電影） | `tv` |

### 示例

```bash
# 添加磁力鏈接（自動檢測季數）
python -m src.main magnet abc123def456 "某動漫名稱 - 01" "字幕組"

# 指定季數
python -m src.main magnet abc123def456 "某動漫名稱 - 01" "字幕組" --season 2

# 添加電影
python -m src.main magnet abc123def456 "某動漫劇場版" "字幕組" --category movie
```

---

## 種子文件命令

手動添加種子文件。

### 語法

```bash
python -m src.main torrent <file> <title> <group> [選項]
```

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `file` | 必需 | 種子文件路徑 |
| `title` | 必需 | 動漫標題 |
| `group` | 必需 | 字幕組名稱 |

### 選項

| 選項 | 說明 | 默認值 |
|------|------|--------|
| `--season N` | 指定季數 | 自動檢測 |
| `--category tv\|movie` | 指定類型（TV 或電影） | `tv` |

### 示例

```bash
# 添加種子文件
python -m src.main torrent "/path/to/file.torrent" "某動漫名稱 - 01" "字幕組"

# 指定季數
python -m src.main torrent "/path/to/file.torrent" "某動漫名稱 - 01" "字幕組" --season 2

# 添加電影
python -m src.main torrent "/path/to/movie.torrent" "某動漫劇場版" "字幕組" --category movie
```

---

## 使用示例

### 日常使用

```bash
# 啟動服務
python -m src.main

# 後台運行（Linux/macOS）
nohup python -m src.main > anidown.log 2>&1 &

# 後台運行（Windows，使用 start）
start /b python -m src.main > anidown.log 2>&1
```

### 調試和測試

```bash
# 運行驗證測試
python -m src.main --test

# 啟用 Debug 模式
python -m src.main --debug
```

### 手動添加下載

```bash
# 從 RSS 添加
python -m src.main rss "https://mikanani.me/RSS/Bangumi?bangumiId=3143"

# 從磁力鏈接添加
python -m src.main magnet "1234567890abcdef" "葬送的芙莉蓮 - 15" "桜都字幕組" --season 1

# 從種子文件添加
python -m src.main torrent "./downloads/frieren-15.torrent" "葬送的芙莉蓮 - 15" "桜都字幕組"
```

---

## 相關文檔

- [返回主文檔](../README.md)
- [配置說明](CONFIGURATION.md)
- [安裝指南](INSTALLATION.md)
