package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

// Config holds the configuration for the webhook sender
type Config struct {
	WebhookURL string            `json:"webhook_url"`
	Headers    map[string]string `json:"headers"`
	LogFile    string            `json:"log_file"`
	Retries    int               `json:"retries"`
	Timeout    int               `json:"timeout"` // seconds
}

// Payload represents the data sent to the webhook
type Payload struct {
	// Standard qBittorrent parameters
	TorrentName string `json:"torrent_name"`
	Category    string `json:"category"`
	Tags        string `json:"tags"`
	ContentPath string `json:"content_path"`
	RootPath    string `json:"root_path"`
	SavePath    string `json:"save_path"`
	FileCount   int    `json:"file_count"`
	TorrentSize int64  `json:"torrent_size"`
	Tracker     string `json:"tracker"`
	InfoHashV1  string `json:"info_hash_v1"`
	InfoHashV2  string `json:"info_hash_v2"`
	TorrentID   string `json:"torrent_id"`

	// Fields expected by new handler
	Hash      string `json:"hash"`
	EventType string `json:"event_type"`

	// Additional metadata
	Timestamp int64 `json:"timestamp"`
}

var (
	// Command line flags
	name        = flag.String("name", "", "Torrent name (%N)")
	category    = flag.String("category", "", "Category (%L)")
	tags        = flag.String("tags", "", "Tags (%G)")
	contentPath = flag.String("content-path", "", "Content path (%F)")
	rootPath    = flag.String("root-path", "", "Root path (%R)")
	savePath    = flag.String("save-path", "", "Save path (%D)")
	fileCount   = flag.Int("file-count", 0, "File count (%C)")
	size        = flag.Int64("size", 0, "Torrent size in bytes (%Z)")
	tracker     = flag.String("tracker", "", "Current tracker (%T)")
	hashV1      = flag.String("hash-v1", "", "Info Hash v1 (%I)")
	hashV2      = flag.String("hash-v2", "", "Info Hash v2 (%J)")
	id          = flag.String("id", "", "Torrent ID (%K)")
	
	// Config flag
	configFile = flag.String("config", "", "Path to configuration file")
)

func main() {
	flag.Parse()

	// Load configuration
	cfg := loadConfig(*configFile)
	
	// Setup logging
	// Default to stdout if log file cannot be opened
	if cfg.LogFile != "" {
		// Try to open log file in the executable's directory to avoid permission issues in system folders
		logPath := cfg.LogFile
		if !filepath.IsAbs(logPath) {
			ex, err := os.Executable()
			if err == nil {
				logPath = filepath.Join(filepath.Dir(ex), cfg.LogFile)
			}
		}

		f, err := os.OpenFile(logPath, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0666)
		if err != nil {
			// Fallback: try temp directory
			tempLogPath := filepath.Join(os.TempDir(), "qb-webhook.log")
			f, err = os.OpenFile(tempLogPath, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0666)
			if err != nil {
				fmt.Printf("Error opening log file (both configured and temp): %v. Logging to stdout.\n", err)
			} else {
				fmt.Printf("Error opening configured log file: %v. Logging to temp file: %s\n", err, tempLogPath)
				defer f.Close()
				log.SetOutput(f)
			}
		} else {
			defer f.Close()
			log.SetOutput(f)
		}
	}

	log.Println("Starting qb-webhook-sender...")
	
	// Validate Webhook URL
	if cfg.WebhookURL == "" {
		log.Println("Warning: Webhook URL is not configured. Please set WEBHOOK_URL env var or use config file.")
		// We don't exit fatal here to allow debugging arguments even if URL is missing, 
		// but practically it should probably fail.
		// However, user might just want to test arg parsing.
		// But for production, we need a URL.
		log.Fatal("Error: Webhook URL is missing.")
	}

	// Construct payload
	payload := Payload{
		TorrentName: *name,
		Category:    *category,
		Tags:        *tags,
		ContentPath: *contentPath,
		RootPath:    *rootPath,
		SavePath:    *savePath,
		FileCount:   *fileCount,
		TorrentSize: *size,
		Tracker:     *tracker,
		InfoHashV1:  *hashV1,
		InfoHashV2:  *hashV2,
		TorrentID:   *id,
		EventType:   "torrent_finished", // Default event type for "Run external program on completion"
		Timestamp:   time.Now().Unix(),
	}

	// Logic for Hash field: prioritize v1 hash as requested
	// "Please fix and force using v1 hash"
	if payload.InfoHashV1 != "" {
		payload.Hash = payload.InfoHashV1
	} else if payload.TorrentID != "" {
		// If v1 hash is empty, try TorrentID (which might be v1 or v2)
		payload.Hash = payload.TorrentID
	} else if payload.InfoHashV2 != "" {
		payload.Hash = payload.InfoHashV2
	}

	// Ensure TorrentID is also populated if missing (legacy support)
	if payload.TorrentID == "" {
		payload.TorrentID = payload.Hash
	}
	
	log.Printf("Processing torrent: %s (Hash: %s)", payload.TorrentName, payload.Hash)

	if err := sendWebhook(cfg, payload); err != nil {
		log.Fatalf("Failed to send webhook: %v", err)
	}

	log.Println("Webhook sent successfully.")
}

func loadConfig(path string) Config {
	cfg := Config{
		Retries: 3,
		Timeout: 10,
		Headers: map[string]string{
			"Content-Type": "application/json",
			"User-Agent":   "qBittorrent-Webhook-Sender/1.0",
		},
	}

	// 1. Load from file if exists
	// If path is not provided, look for config.json in executable directory
	if path == "" {
		ex, err := os.Executable()
		if err == nil {
			path = filepath.Join(filepath.Dir(ex), "config.json")
		}
	}

	if path != "" {
		if _, err := os.Stat(path); err == nil {
			data, err := os.ReadFile(path)
			if err == nil {
				var fileCfg Config
				if err := json.Unmarshal(data, &fileCfg); err == nil {
					// Merge config
					if fileCfg.WebhookURL != "" { cfg.WebhookURL = fileCfg.WebhookURL }
					if fileCfg.LogFile != "" { cfg.LogFile = fileCfg.LogFile }
					if fileCfg.Retries > 0 { cfg.Retries = fileCfg.Retries }
					if fileCfg.Timeout > 0 { cfg.Timeout = fileCfg.Timeout }
					for k, v := range fileCfg.Headers {
						cfg.Headers[k] = v
					}
				} else {
					log.Printf("Warning: Failed to parse config file: %v", err)
				}
			}
		}
	}

	// 2. Load from Env (overrides file)
	if envURL := os.Getenv("WEBHOOK_URL"); envURL != "" {
		cfg.WebhookURL = envURL
	}

	return cfg
}

func sendWebhook(cfg Config, payload Payload) error {
	jsonData, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("json marshal error: %v", err)
	}

	client := &http.Client{
		Timeout: time.Duration(cfg.Timeout) * time.Second,
	}

	var lastErr error
	for i := 0; i <= cfg.Retries; i++ {
		if i > 0 {
			time.Sleep(2 * time.Second)
			log.Printf("Retry %d/%d...", i, cfg.Retries)
		}

		req, err := http.NewRequest("POST", cfg.WebhookURL, bytes.NewBuffer(jsonData))
		if err != nil {
			return fmt.Errorf("create request error: %v", err)
		}

		for k, v := range cfg.Headers {
			req.Header.Set(k, v)
		}

		resp, err := client.Do(req)
		if err != nil {
			lastErr = err
			log.Printf("Request failed: %v", err)
			continue
		}
		
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			log.Printf("Success: %d - %s", resp.StatusCode, string(body))
			return nil
		}

		lastErr = fmt.Errorf("server returned status %d: %s", resp.StatusCode, string(body))
		log.Printf("Error: %v", lastErr)
	}

	return lastErr
}
