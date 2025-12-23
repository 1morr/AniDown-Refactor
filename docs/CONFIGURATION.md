# 配置說明

本文檔詳細說明 AniDown 的所有配置選項。

---

## 目錄

- [完整配置結構](#完整配置結構)
- [RSS 配置](#rss-配置)
- [qBittorrent 配置](#qbittorrent-配置)
- [OpenAI / AI 配置](#openai--ai-配置)
  - [Key Pool 配置](#key-pool-配置)
  - [任務配置](#任務配置)
  - [速率限制配置](#速率限制配置)
  - [語言優先級](#語言優先級)
- [Discord 通知配置](#discord-通知配置)
- [媒體庫路徑配置](#媒體庫路徑配置)
- [TVDB 配置](#tvdb-配置)
- [路徑轉換配置](#路徑轉換配置)
- [服務端口配置](#服務端口配置)
- [AI 批處理配置](#ai-批處理配置)

---

## 完整配置結構

`config.json` 的完整結構：

```json
{
  "rss": {
    "fixed_urls": [],
    "check_interval": 3600
  },
  "discord": {
    "enabled": false,
    "rss_webhook_url": "",
    "hardlink_webhook_url": ""
  },
  "qbittorrent": {
    "url": "http://qbittorrent:8080",
    "username": "admin",
    "password": "adminadmin",
    "base_download_path": "/storage/downloads/AniDown/",
    "category": "AniDown",
    "anime_folder_name": "Anime",
    "live_action_folder_name": "LiveAction",
    "tv_folder_name": "TV",
    "movie_folder_name": "Movies"
  },
  "openai": {
    "key_pools": [...],
    "title_parse": {...},
    "multi_file_rename": {...},
    "subtitle_match": {...},
    "title_parse_retries": 3,
    "subtitle_match_retries": 3,
    "rate_limits": {...},
    "language_priorities": [...]
  },
  "ai_processing": {
    "max_batch_size": 30,
    "batch_processing_retries": 2
  },
  "webhook": { "host": "0.0.0.0", "port": 5678 },
  "webui": { "host": "0.0.0.0", "port": 8081 },
  "path_conversion": {...},
  "tvdb": { "api_key": "", "max_data_length": 10000 },
  "link_target_path": "/storage/library/TV Shows",
  "movie_link_target_path": "/storage/library/Movies",
  "live_action_tv_target_path": "/storage/library/LiveAction/TV Shows",
  "live_action_movie_target_path": "/storage/library/LiveAction/Movies",
  "use_consistent_naming_tv": false,
  "use_consistent_naming_movie": false
}
```

---

## RSS 配置

```json
{
  "rss": {
    "fixed_urls": [
      "https://mikanani.me/RSS/Bangumi?bangumiId=xxx"
    ],
    "check_interval": 3600
  }
}
```

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `fixed_urls` | array | RSS 訂閱 URL 列表 | `[]` |
| `check_interval` | number | 檢查間隔（秒） | `3600` |

---

## qBittorrent 配置

```json
{
  "qbittorrent": {
    "url": "http://qbittorrent:8080",
    "username": "admin",
    "password": "adminadmin",
    "base_download_path": "/storage/downloads/AniDown/",
    "category": "AniDown",
    "anime_folder_name": "Anime",
    "live_action_folder_name": "LiveAction",
    "tv_folder_name": "TV",
    "movie_folder_name": "Movies"
  }
}
```

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `url` | string | qBittorrent WebAPI 地址 | `http://localhost:8080` |
| `username` | string | 登錄用戶名 | `admin` |
| `password` | string | 登錄密碼 | - |
| `base_download_path` | string | 下載基礎路徑 | - |
| `category` | string | qBittorrent 分類名稱 | `AniDown` |
| `anime_folder_name` | string | 動漫子目錄名稱 | `Anime` |
| `live_action_folder_name` | string | 真人劇子目錄名稱 | `LiveAction` |
| `tv_folder_name` | string | TV 劇集子目錄名稱 | `TV` |
| `movie_folder_name` | string | 電影子目錄名稱 | `Movies` |

---

## OpenAI / AI 配置

### Key Pool 配置

支持多個 API Key 輪換使用，配置 RPM/RPD 限制：

```json
{
  "openai": {
    "key_pools": [
      {
        "name": "MyPool",
        "base_url": "https://api.openai.com/v1",
        "api_keys": [
          {
            "name": "Key 1",
            "api_key": "sk-xxx",
            "rpm": 60,
            "rpd": 1000,
            "enabled": true
          },
          {
            "name": "Key 2",
            "api_key": "sk-yyy",
            "rpm": 60,
            "rpd": 1000,
            "enabled": true
          }
        ]
      }
    ]
  }
}
```

#### Pool 配置

| 字段 | 類型 | 說明 |
|------|------|------|
| `name` | string | Pool 名稱，用於任務引用 |
| `base_url` | string | API 基礎 URL |
| `api_keys` | array | API Key 列表 |

#### API Key 配置

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `name` | string | Key 名稱（用於識別） | - |
| `api_key` | string | API Key | - |
| `rpm` | number | 每分鐘請求限制 | `60` |
| `rpd` | number | 每日請求限制 | `1000` |
| `enabled` | boolean | 是否啟用此 Key | `true` |

---

### 任務配置

每個 AI 任務可以使用 Key Pool 或獨立 API Key：

```json
{
  "openai": {
    "title_parse": {
      "pool_name": "MyPool",
      "api_key": "",
      "base_url": "https://api.openai.com/v1",
      "model": "gpt-4",
      "extra_body": "",
      "timeout": 180
    },
    "multi_file_rename": {
      "pool_name": "MyPool",
      "api_key": "",
      "base_url": "https://api.openai.com/v1",
      "model": "gpt-4",
      "extra_body": "",
      "timeout": 360
    },
    "subtitle_match": {
      "pool_name": "MyPool",
      "api_key": "",
      "base_url": "https://api.openai.com/v1",
      "model": "gpt-4",
      "extra_body": "",
      "timeout": 180
    }
  }
}
```

#### 任務類型

| 任務 | 說明 |
|------|------|
| `title_parse` | RSS 標題解析 |
| `multi_file_rename` | 批量文件重命名 |
| `subtitle_match` | 字幕匹配 |

#### 任務配置字段

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `pool_name` | string | 使用的 Key Pool 名稱（優先） | - |
| `api_key` | string | 獨立 API Key（pool_name 為空時使用） | - |
| `base_url` | string | API 基礎 URL | `https://api.openai.com/v1` |
| `model` | string | 使用的模型 | `gpt-4` |
| `extra_body` | string | 額外請求參數（JSON 字符串） | - |
| `timeout` | number | 請求超時（秒） | `180` |

> **注意**: 如果設置了 `pool_name`，則使用 Key Pool；否則使用獨立的 `api_key`。

---

### 速率限制配置

```json
{
  "openai": {
    "title_parse_retries": 3,
    "subtitle_match_retries": 3,
    "rate_limits": {
      "max_consecutive_errors": 5,
      "key_cooldown_seconds": 30,
      "circuit_breaker_cooldown_seconds": 900,
      "max_backoff_seconds": 300
    }
  }
}
```

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `title_parse_retries` | number | 標題解析重試次數 | `3` |
| `subtitle_match_retries` | number | 字幕匹配重試次數 | `3` |
| `rate_limits.max_consecutive_errors` | number | 最大連續錯誤次數 | `5` |
| `rate_limits.key_cooldown_seconds` | number | Key 冷卻時間（秒） | `30` |
| `rate_limits.circuit_breaker_cooldown_seconds` | number | 熔斷器冷卻時間（秒） | `900` |
| `rate_limits.max_backoff_seconds` | number | 最大退避時間（秒） | `300` |

---

### 語言優先級

用於 AI 解析時選擇動漫名稱的語言優先順序：

```json
{
  "openai": {
    "language_priorities": [
      { "name": "中文" },
      { "name": "English" },
      { "name": "日本語" },
      { "name": "Romaji" }
    ]
  }
}
```

---

## Discord 通知配置

```json
{
  "discord": {
    "enabled": true,
    "rss_webhook_url": "https://discord.com/api/webhooks/xxx/yyy",
    "hardlink_webhook_url": "https://discord.com/api/webhooks/xxx/yyy"
  }
}
```

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `enabled` | boolean | 是否啟用 Discord 通知 | `false` |
| `rss_webhook_url` | string | RSS 新番通知 Webhook URL | - |
| `hardlink_webhook_url` | string | 硬鏈接完成通知 Webhook URL | - |

---

## 媒體庫路徑配置

```json
{
  "link_target_path": "/storage/library/TV Shows",
  "movie_link_target_path": "/storage/library/Movies",
  "live_action_tv_target_path": "/storage/library/LiveAction/TV Shows",
  "live_action_movie_target_path": "/storage/library/LiveAction/Movies",
  "use_consistent_naming_tv": false,
  "use_consistent_naming_movie": false
}
```

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `link_target_path` | string | 動漫 TV 媒體庫路徑 | - |
| `movie_link_target_path` | string | 動漫電影媒體庫路徑 | - |
| `live_action_tv_target_path` | string | 真人劇 TV 媒體庫路徑 | - |
| `live_action_movie_target_path` | string | 真人電影媒體庫路徑 | - |
| `use_consistent_naming_tv` | boolean | TV 使用統一命名格式 | `false` |
| `use_consistent_naming_movie` | boolean | 電影使用統一命名格式 | `false` |

---

## TVDB 配置

```json
{
  "tvdb": {
    "api_key": "your-tvdb-api-key",
    "max_data_length": 10000
  }
}
```

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `api_key` | string | TVDB API Key | - |
| `max_data_length` | number | 最大數據長度 | `10000` |

---

## 路徑轉換配置

用於 qBittorrent 與 AniDown 容器路徑不一致時的路徑映射：

```json
{
  "path_conversion": {
    "enabled": false,
    "source_base_path": "/downloads/AniDown/",
    "target_base_path": "/storage/downloads/AniDown/"
  }
}
```

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `enabled` | boolean | 是否啟用路徑轉換 | `false` |
| `source_base_path` | string | 源路徑前綴（qBittorrent 看到的路徑） | - |
| `target_base_path` | string | 目標路徑前綴（AniDown 看到的路徑） | - |

---

## 服務端口配置

```json
{
  "webhook": {
    "host": "0.0.0.0",
    "port": 5678
  },
  "webui": {
    "host": "0.0.0.0",
    "port": 8081
  }
}
```

| 服務 | 字段 | 類型 | 說明 | 默認值 |
|------|------|------|------|--------|
| Webhook | `host` | string | 監聽地址 | `0.0.0.0` |
| | `port` | number | 監聽端口 | `5678` |
| Web UI | `host` | string | 監聽地址 | `0.0.0.0` |
| | `port` | number | 監聯端口 | `8081` |

---

## AI 批處理配置

```json
{
  "ai_processing": {
    "max_batch_size": 30,
    "batch_processing_retries": 2
  }
}
```

| 字段 | 類型 | 說明 | 默認值 |
|------|------|------|--------|
| `max_batch_size` | number | 單次批處理最大文件數 | `30` |
| `batch_processing_retries` | number | 批處理重試次數 | `2` |

---

## 相關文檔

- [返回主文檔](../README.md)
- [安裝指南](INSTALLATION.md)
- [系統架構](ARCHITECTURE.md)
- [qBittorrent Webhook 配置](QBITTORRENT_WEBHOOK.md)
