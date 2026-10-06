# laya-ctl

**Zero-dependency daemon controller for [`laya-serve`](https://github.com/NandhaKishorM/laya) on Linux and Apple Silicon macOS.**

`laya-serve` runs in foreground by default. `laya-ctl` wraps it into a clean, background-managed local daemon with PID tracking, memory profiling, hardware device discovery (MPS, CUDA, CPU), readiness probes, and graceful shutdowns.

---

## Installation

### Option 1: Direct Executable (Zero Dependencies)
Download or link the executable directly into your `PATH`:

```bash
curl -fsSL https://raw.githubusercontent.com/r1cc4rd0m4zz4/laya-ctl/main/bin/laya-ctl -o /usr/local/bin/laya-ctl
chmod +x /usr/local/bin/laya-ctl
```

### Option 2: via `uv` / `pipx`
```bash
uv tool install git+https://github.com/r1cc4rd0m4zz4/laya-ctl.git
# or
pipx install git+https://github.com/r1cc4rd0m4zz4/laya-ctl.git
```

---

## Quick Start

```bash
# Setup upstream laya with serve and mcp extras (via uv or pip)
laya-ctl setup

# Start the background daemon on 127.0.0.1:5292 (default: balanced profile)
laya-ctl start

# Check status, active PID, RSS memory, device (MPS/CUDA/CPU), and resident models
laya-ctl status

# Graceful restart
laya-ctl restart

# Stop the daemon
laya-ctl stop
```

---

## Memory Profiles & Dynamic Eviction

Three memory profiles balance resident RAM against model switch latency:

| Profile | Preload Models | Max Resident | Idle Unload | Typical RSS Memory |
| :--- | :--- | :--- | :--- | :--- |
| **`balanced`** *(Default)* | `multilingual,english` | **2** | **300s** (5 min) | **~1.2 - 1.9 GB** (loads `typed-decisions` on demand, evicts LRU checkpoint, unloads on idle) |
| **`performance`** | `english,multilingual,typed-decisions` | **3** | **Disabled (0s)** | **~2.2 GB** (all 3 models permanently in RAM, zero switch latency) |
| **`eco`** | `multilingual` | **1** | **120s** (2 min) | **~0.9 - 1.2 GB** (single resident model, recommended for 8-16 GB laptops) |

### Switching Profiles

- **CLI Flag**:
  ```bash
  laya-ctl restart --profile performance
  laya-ctl restart --profile balanced
  laya-ctl restart --profile eco
  ```

- **Environment Variable**:
  ```bash
  LAYA_PROFILE=performance laya-ctl restart
  ```

- **Persistent Configuration via `.env`**:
  Copy `.env.example` to `~/.config/laya/.env`:
  ```bash
  cp .env.example ~/.config/laya/.env
  ```

---

## Service Autostart & Integration Examples

Ready-to-use production examples are provided under [`examples/`](examples/):

- **macOS LaunchAgent**: [`examples/launchd/com.user.laya.plist`](examples/launchd/com.user.laya.plist)  
  Autostart on login via `launchctl load ~/Library/LaunchAgents/com.user.laya.plist`.

- **Linux systemd user unit**: [`examples/systemd/laya.service`](examples/systemd/laya.service)  
  Autostart on boot via `systemctl --user enable --now laya`.

- **Zero-Dependency Python Client**: [`examples/python_client.py`](examples/python_client.py)  
  Minimal stdlib client demonstrating how to query TypeSafe Jev `/v1/systemone` directly.

- **Curl Query Script**: [`examples/curl_query.sh`](examples/curl_query.sh)  
  One-liner CLI example querying safety and risk classification.

---

## Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `LAYA_PROFILE` | `balanced` | Memory preset: `balanced`, `performance`, or `eco` |
| `LAYA_HOST` | `127.0.0.1` | Loopback socket interface |
| `LAYA_PORT` | `5292` | TCP listening port |
| `LAYA_DEVICE` | `auto` | PyTorch device preference (`mps`, `cuda`, `cpu`) |
| `LAYA_MAX_LOADED` | `2` (in balanced) | Maximum checkpoints resident in RAM simultaneously |
| `LAYA_IDLE_UNLOAD_SECONDS` | `300` | Inactivity seconds before resident models are evicted |

PID and log files are stored in `~/.cache/laya/`:
- PID file: `~/.cache/laya/laya_serve.pid`
- Log file: `~/.cache/laya/laya_serve.log`

---

## License

MIT
