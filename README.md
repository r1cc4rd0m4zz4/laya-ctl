# laya-ctl

**Zero-dependency daemon controller for [`laya-serve`](https://github.com/NandhaKishorM/laya) on Linux and Apple Silicon macOS.**

`laya-serve` runs in foreground by default. `laya-ctl` wraps it into a clean, background-managed local daemon with PID tracking, hardware device discovery (MPS, CUDA, CPU), readiness probes, and graceful shutdowns.

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

## Usage

```bash
# Setup upstream laya with serve and mcp extras (via uv or pip)
laya-ctl setup

# Start the background daemon on 127.0.0.1:5292
laya-ctl start

# Check status, active PID, device (MPS/CUDA/CPU), and loaded models
laya-ctl status

# Graceful restart
laya-ctl restart

# Stop the daemon
laya-ctl stop
```

---

## Configuration

Control binding and ports with environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `LAYA_HOST` | `127.0.0.1` | Loopback socket interface |
| `LAYA_PORT` | `5292` | TCP listening port |
| `LAYA_PRELOAD` | `1` | Preload models into unified memory at startup |

Logs and PID files are stored in `~/.cache/laya/`:
- PID file: `~/.cache/laya/laya_serve.pid`
- Log file: `~/.cache/laya/laya_serve.log`

---

## License

MIT
