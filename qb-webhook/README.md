# qBittorrent Webhook Sender

这是一个跨平台的 Webhook 发送工具，专为 qBittorrent 设计。它不依赖 Docker 或 Python 环境，编译后为一个独立的可执行文件。

## 功能特性

- 🚀 **零依赖**：编译后为独立二进制文件，无需安装任何运行时。
- 💻 **跨平台**：支持 Windows, Linux, macOS。
- 🔧 **配置灵活**：支持配置文件 (`config.json`) 或环境变量 (`WEBHOOK_URL`)。
- 🛡️ **健壮性**：内置重试机制，自动处理特殊字符，详细的日志记录。
- 🔑 **Hash 处理**：强制优先使用 v1 Hash，确保与数据库记录一致。

## 编译指南

你需要安装 [Go 语言环境](https://go.dev/dl/) (1.21 或更高版本)。

### Windows
```powershell
cd qb-webhook
go build -o qb-webhook.exe
```

### Linux / Docker (交叉编译)
如果你在 Windows 上开发，但需要部署到 Docker (通常是 Linux) 环境，请使用以下命令编译 Linux 版本：

```powershell
cd qb-webhook
$env:GOOS = "linux"; $env:GOARCH = "amd64"; go build -o qb-webhook-linux
```

### macOS
```bash
cd qb-webhook
go build -o qb-webhook
chmod +x qb-webhook
```

## 选项二：Python 脚本（无需编译）

如果你不想安装 Go，可以直接使用 Python 版本（需要系统安装 Python 3）。

```bash
python3 webhook_sender.py --name "%N" ...
```

## qBittorrent 配置

在 qBittorrent 的 "下载完成时运行外部程序" 中填入以下命令（请根据实际路径修改）：

### Windows (Go 版本)
```
"C:\path\to\qb-webhook.exe" --name "%N" --category "%L" --tags "%G" --content-path "%F" --root-path "%R" --save-path "%D" --file-count "%C" --size "%Z" --tracker "%T" --hash-v1 "%I" --hash-v2 "%J" --id "%K"
```

### Windows (Python 版本)
```
python "C:\path\to\webhook_sender.py" --name "%N" --category "%L" --tags "%G" --content-path "%F" --root-path "%R" --save-path "%D" --file-count "%C" --size "%Z" --tracker "%T" --hash-v1 "%I" --hash-v2 "%J" --id "%K"
```

### Linux / macOS (Go 版本)
```
/path/to/qb-webhook --name "%N" --category "%L" --tags "%G" --content-path "%F" --root-path "%R" --save-path "%D" --file-count "%C" --size "%Z" --tracker "%T" --hash-v1 "%I" --hash-v2 "%J" --id "%K"
```

## 配置文件 (config.json)

将此文件放在可执行文件同级目录下：

```json
{
  "webhook_url": "http://your-server:5000/webhook/qbit",
  "log_file": "webhook.log",
  "retries": 3,
  "timeout": 10,
  "headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer optional-token"
  }
}
```

或者使用环境变量：
`WEBHOOK_URL=http://your-server:5000/webhook/qbit`

## 故障排除

如果 Webhook 未发送，请检查同级目录下的 `webhook.log` 文件。常见问题包括：
1. Webhook URL 配置错误。
2. 目标服务器不可达。
3. 权限不足（无法写入日志文件）。
