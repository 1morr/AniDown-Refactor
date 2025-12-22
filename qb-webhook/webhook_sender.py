#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

def load_config(config_path=None):
    config = {
        "webhook_url": "",
        "log_file": "webhook_py.log",
        "retries": 3,
        "timeout": 10,
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "qBittorrent-Webhook-Sender-Py/1.0"
        }
    }

    # 1. Load from file
    if not config_path:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(exe_dir, "config.json")

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"Warning: Failed to load config file: {e}")

    # 2. Env var overrides
    if os.environ.get("WEBHOOK_URL"):
        config["webhook_url"] = os.environ.get("WEBHOOK_URL")

    return config

def log_message(config, message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)
    
    log_file = config.get("log_file")
    if log_file:
        # Handle relative paths by making them absolute relative to the script directory
        if not os.path.isabs(log_file):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            log_file = os.path.join(script_dir, log_file)

        try:
            with open(log_file, "a", encoding='utf-8') as f:
                f.write(log_line + "\n")
        except PermissionError:
            # Fallback to temp directory if permission denied
            import tempfile
            temp_log = os.path.join(tempfile.gettempdir(), "qb-webhook.log")
            try:
                with open(temp_log, "a", encoding='utf-8') as f:
                    f.write(log_line + "\n")
                if level == "FATAL" or "Starting" in message:
                    print(f"Warning: Permission denied for {log_file}, logging to {temp_log}")
            except Exception:
                pass # Give up on file logging
        except Exception as e:
            print(f"Error writing to log file: {e}")

def send_webhook(config, payload):
    url = config["webhook_url"]
    if not url:
        raise ValueError("Webhook URL not configured")

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    
    for k, v in config.get("headers", {}).items():
        req.add_header(k, v)

    retries = config.get("retries", 3)
    timeout = config.get("timeout", 10)
    last_error = None

    for i in range(retries + 1):
        if i > 0:
            time.sleep(2)
            log_message(config, f"Retry {i}/{retries}...", "INFO")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode('utf-8')
                if 200 <= response.status < 300:
                    log_message(config, f"Success: {response.status} - {body}", "INFO")
                    return
                else:
                    last_error = f"Server returned status {response.status}: {body}"
                    log_message(config, f"Request failed: {last_error}", "ERROR")
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8') if e.fp else ""
            last_error = f"HTTP Error {e.code}: {e.reason} - {body}"
            log_message(config, f"Request failed: {last_error}", "ERROR")
        except urllib.error.URLError as e:
            last_error = f"URL Error: {e.reason}"
            log_message(config, f"Request failed: {last_error}", "ERROR")
        except Exception as e:
            last_error = str(e)
            log_message(config, f"Request failed: {last_error}", "ERROR")

    raise Exception(f"Failed after {retries} retries. Last error: {last_error}")

def main():
    parser = argparse.ArgumentParser(description="qBittorrent Webhook Sender")
    parser.add_argument("--name", default="", help="Torrent name (%N)")
    parser.add_argument("--category", default="", help="Category (%L)")
    parser.add_argument("--tags", default="", help="Tags (%G)")
    parser.add_argument("--content-path", default="", help="Content path (%F)")
    parser.add_argument("--root-path", default="", help="Root path (%R)")
    parser.add_argument("--save-path", default="", help="Save path (%D)")
    parser.add_argument("--file-count", type=int, default=0, help="File count (%C)")
    parser.add_argument("--size", type=int, default=0, help="Torrent size (%Z)")
    parser.add_argument("--tracker", default="", help="Tracker (%T)")
    parser.add_argument("--hash-v1", default="", help="Info Hash v1 (%I)")
    parser.add_argument("--hash-v2", default="", help="Info Hash v2 (%J)")
    parser.add_argument("--id", default="", help="Torrent ID (%K)")
    parser.add_argument("--config", default=None, help="Config file path")

    args = parser.parse_args()
    config = load_config(args.config)

    log_message(config, "Starting webhook sender (Python)...")

    if not config["webhook_url"]:
        log_message(config, "Error: Webhook URL missing", "FATAL")
        sys.exit(1)

    # Logic to handle Hash field (force v1 hash if available)
    # Priority: hash_v1 > torrent_id > hash_v2
    hash_val = ""
    if args.hash_v1:
        hash_val = args.hash_v1
    elif args.id:
        hash_val = args.id
    elif args.hash_v2:
        hash_val = args.hash_v2

    # Ensure legacy TorrentID is set
    torrent_id = args.id if args.id else hash_val

    payload = {
        "torrent_name": args.name,
        "category": args.category,
        "tags": args.tags,
        "content_path": args.content_path,
        "root_path": args.root_path,
        "save_path": args.save_path,
        "file_count": args.file_count,
        "torrent_size": args.size,
        "tracker": args.tracker,
        "info_hash_v1": args.hash_v1,
        "info_hash_v2": args.hash_v2,
        "torrent_id": torrent_id,
        "hash": hash_val,
        "event_type": "torrent_finished",
        "timestamp": int(time.time())
    }

    log_message(config, f"Processing torrent: {args.name} (Hash: {hash_val})")

    try:
        send_webhook(config, payload)
        log_message(config, "Webhook sent successfully.")
    except Exception as e:
        log_message(config, f"Fatal Error: {e}", "FATAL")
        sys.exit(1)

if __name__ == "__main__":
    main()
