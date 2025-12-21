#!/bin/bash
set -eo pipefail

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日誌函數
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    if [ "${DEBUG}" = "true" ]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

# 設置時區
setup_timezone() {
    if [ -n "${TZ}" ]; then
        if [ -f "/usr/share/zoneinfo/${TZ}" ]; then
            log_info "設置時區為: ${TZ}"
            ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime
            echo "${TZ}" > /etc/timezone
        else
            log_warn "找不到時區文件: ${TZ}，使用默認時區"
        fi
    fi
}

# 檢查並創建必要的目錄
create_directories() {
    log_info "創建必要的目錄..."

    directories=(
        "/data/db"
        "/data/config"
        "/data/logs"
        "/data/ai_logs"
        "/storage/downloads/AniDown"
        "/storage/library/TV Shows"
        "/storage/library/Movies"
    )

    for dir in "${directories[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log_debug "創建目錄: $dir"
        fi
    done

    # 設置權限 (如果作為 root 運行)
    if [ "$(id -u)" = "0" ]; then
        chmod 755 /data/db /data/config /data/logs /data/ai_logs
        chmod 755 /storage
    fi

    log_info "目錄創建完成"
}

# 初始化配置文件
init_config() {
    local config_file="/data/config/config.json"
    local config_example="/app/config.json.example"

    if [ ! -f "$config_file" ]; then
        log_info "創建默認配置文件..."

        if [ -f "$config_example" ]; then
            cp "$config_example" "$config_file"
            log_info "從範例文件複製配置: $config_file"
        else
            log_error "找不到配置範例文件: $config_example"
            exit 1
        fi
    else
        log_info "配置文件已存在: $config_file"
    fi

    # 設置配置文件路徑環境變數
    export CONFIG_PATH="$config_file"
}

# 等待 qBittorrent 服務啟動
wait_for_qbittorrent() {
    local qb_url="${ANIDOWN_QBITTORRENT__URL:-http://qbittorrent:8080}"
    local max_attempts=30
    local attempt=1

    # 如果是 localhost，可能不需要等待，或者服務在容器外
    if [[ "$qb_url" == *"localhost"* ]] || [[ "$qb_url" == *"127.0.0.1"* ]]; then
         log_debug "qBittorrent 配置為本地地址，跳過連接檢查"
         return 0
    fi

    log_info "等待 qBittorrent 服務啟動 (${qb_url})..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s --connect-timeout 5 "$qb_url" > /dev/null 2>&1; then
            log_info "qBittorrent 服務已就緒"
            return 0
        fi

        if [ $((attempt % 5)) -eq 0 ]; then
            log_debug "嘗試 $attempt/$max_attempts: qBittorrent 尚未就緒"
        fi

        sleep 2
        attempt=$((attempt + 1))
    done

    log_warn "qBittorrent 服務在 $((max_attempts * 2)) 秒內未就緒，應用程序將繼續啟動，但可能會遇到連接錯誤。"
}

# 檢查必要的環境變數
check_environment() {
    log_info "檢查環境配置..."

    # 檢查 OpenAI API Key（如果需要 AI 功能）
    if [ -z "${ANIDOWN_OPENAI__API_KEY}" ]; then
        log_warn "未設置 OPENAI_API_KEY，AI 功能將不可用"
    fi

    # 檢查 Discord Webhook（如果啟用）
    if [ "${DISCORD_ENABLED}" = "true" ]; then
        if [ -z "${DISCORD_RSS_WEBHOOK_URL}" ] && [ -z "${DISCORD_HARDLINK_WEBHOOK_URL}" ]; then
            log_warn "Discord 已啟用但未設置 Webhook URL"
        fi
    fi

    log_info "環境檢查完成"
}

# 顯示啟動信息
show_startup_info() {
    log_info "=========================================="
    log_info "🚀 AniDown 動漫下載管理器"
    log_info "=========================================="
    log_info "Web UI: http://localhost:${WEBUI_PORT:-8081}"
    log_info "Webhook: http://localhost:${WEBHOOK_PORT:-5678}"
    if [ -n "${TZ}" ]; then
        log_info "時區: ${TZ}"
    fi
    log_info "Debug 模式: ${DEBUG:-false}"
    log_info "配置文件: ${CONFIG_PATH:-/data/config/config.json}"
    log_info "數據庫: ${DB_PATH:-/data/db/anime_downloader.db}"
    log_info "=========================================="
}

# 主函數
main() {
    log_info "啟動 AniDown 容器..."

    # 設置時區
    setup_timezone

    # 創建目錄
    create_directories

    # 初始化配置
    init_config

    # 檢查環境
    check_environment

    # 嘗試連接 qBittorrent (非阻塞)
    wait_for_qbittorrent &

    # 顯示啟動信息
    show_startup_info

    # 執行傳入的命令
    log_info "執行命令: $*"
    exec "$@"
}

# 信號處理
trap 'log_info "接收到停止信號，正在關閉..."; exit 0' SIGTERM SIGINT

# 執行主函數
main "$@"
