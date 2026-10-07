#!/usr/bin/env python3
"""
Laya Universal Service Controller (Linux & macOS)
Zero-dependency controller for upstream laya-serve on loopback 127.0.0.1:5292.
Supports balanced memory profiles, dynamic model eviction, and .env configuration.
Adheres to Zero-Trust Architecture: Native stdlib, loopback binding, fail-closed probes.
"""

import argparse
import contextlib
import http.client
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time

BASE_DIR = os.path.expanduser("~/.cache/laya")
PID_FILE = os.path.join(BASE_DIR, "laya_serve.pid")
LOG_FILE = os.path.join(BASE_DIR, "laya_serve.log")
HIBERNATE_SENTINEL = os.path.join(BASE_DIR, "hibernated")

try:
    os.makedirs(BASE_DIR, mode=0o700, exist_ok=True)
except OSError as err:
    logging.debug("Directory init: %s", err)


def load_env_file() -> dict[str, str]:
    """Parse key=value pairs from .env without external dependencies."""
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.expanduser("~/.config/laya/.env"),
        os.path.expanduser("~/.cache/laya/.env"),
    ]
    env_vars: dict[str, str] = {}
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            env_vars[k] = v
                break
            except OSError:
                continue
    return env_vars


ENV_CONFIG = load_env_file()

# Profiles: balanced (default 1-2 models, LRU evict), performance (all 3 in RAM), eco (1 model)
PROFILES = {
    "balanced": {
        "LAYA_MODELS": "multilingual,english",
        "LAYA_MAX_LOADED": "2",
        "LAYA_IDLE_UNLOAD_SECONDS": "300",
        "LAYA_PRELOAD": "1",
    },
    "performance": {
        "LAYA_MODELS": "english,multilingual,typed-decisions",
        "LAYA_MAX_LOADED": "3",
        "LAYA_IDLE_UNLOAD_SECONDS": "0",
        "LAYA_PRELOAD": "1",
    },
    "eco": {
        "LAYA_MODELS": "multilingual",
        "LAYA_MAX_LOADED": "1",
        "LAYA_IDLE_UNLOAD_SECONDS": "120",
        "LAYA_PRELOAD": "1",
    },
}

ACTIVE_PROFILE = os.environ.get("LAYA_PROFILE") or ENV_CONFIG.get("LAYA_PROFILE", "balanced")
PROFILE_DEFAULTS = PROFILES.get(ACTIVE_PROFILE, PROFILES["balanced"])

HOST = os.environ.get("LAYA_HOST") or ENV_CONFIG.get("LAYA_HOST", "127.0.0.1")
PORT = int(os.environ.get("LAYA_PORT") or ENV_CONFIG.get("LAYA_PORT", "5292"))
BASE_URL = f"http://{HOST}:{PORT}"


def ensure_reclaimer_hook() -> str:
    """Deploy native OS memory reclaimer (Darwin pressure relief & Linux malloc_trim)."""
    lib_dir = os.path.join(BASE_DIR, "lib")
    try:
        os.makedirs(lib_dir, exist_ok=True)
    except OSError as err:
        logging.debug("lib_dir init: %s", err)
    target = os.path.join(lib_dir, "sitecustomize.py")
    hook_code = '''import gc
import os
import sys

BASE_DIR = os.path.expanduser("~/.cache/laya")
HIBERNATE_SENTINEL = os.path.join(BASE_DIR, "hibernated")
PID_FILE = os.path.join(BASE_DIR, "laya_serve.pid")

def release_os_memory():
    gc.collect()
    try:
        import torch
        if hasattr(torch, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    if sys.platform == "darwin":
        try:
            import ctypes
            ctypes.CDLL("libSystem.B.dylib").malloc_zone_pressure_relief(None, 0)
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

try:
    from laya import router
    orig_evict = router.Router._evict_locked
    orig_unload = router.Router.unload

    def patched_evict(self):
        res = orig_evict(self)
        release_os_memory()
        return res

    def patched_unload(self, name=None):
        res = orig_unload(self, name=name)
        release_os_memory()

        # If all models unloaded (idle reaper), trigger clean auto-hibernation to achieve 0.0 MB RAM!
        auto_hib = os.environ.get("LAYA_AUTO_HIBERNATE", "1")
        if auto_hib == "1" and name is None:
            try:
                if os.path.exists(PID_FILE):
                    os.remove(PID_FILE)
                with open(HIBERNATE_SENTINEL, "w") as f:
                    f.write(str(os.getpid()))
                sys.stdout.write("[+] Idle timeout reached: Auto-hibernating laya-serve to 0.0 MB RAM.\\n")
                sys.stdout.flush()
            except Exception:
                pass
            os._exit(0)

        return res

    router.Router._evict_locked = patched_evict
    router.Router.unload = patched_unload
except Exception:
    pass
'''
    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(hook_code)
    except OSError as err:
        logging.debug("hook write: %s", err)
    return lib_dir


def get_resolved_env() -> dict[str, str]:
    """Merge profile defaults with explicit env and .env overrides."""
    env = os.environ.copy()
    env["LAYA_HOST"] = HOST
    env["LAYA_PORT"] = str(PORT)

    lib_dir = ensure_reclaimer_hook()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{lib_dir}:{existing_pp}" if existing_pp else lib_dir

    for k, v in PROFILE_DEFAULTS.items():
        val = os.environ.get(k) or ENV_CONFIG.get(k) or v
        env[k] = str(val)

    return env


def check_health(timeout: float = 1.0) -> dict | None:
    try:
        conn = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
        conn.request("GET", "/health", headers={"User-Agent": "LayaCtl/1.0"})
        resp = conn.getresponse()
        if resp.status == 200:
            data = resp.read().decode("utf-8")
            conn.close()
            return json.loads(data)
        conn.close()
    except (OSError, ValueError, TimeoutError, http.client.HTTPException):
        return None
    return None


def get_running_pid() -> int | None:
    if not os.path.exists(PID_FILE):
        return None
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        with contextlib.suppress(OSError):
            os.remove(PID_FILE)
        return None


def get_rss_mb(pid: int) -> float | None:
    """Read process resident set size (RSS) in MB using native OS command."""
    try:
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)]).decode().strip()
        return int(out) / 1024.0
    except Exception:
        return None


def service_setup() -> None:
    """Convenience installer for upstream laya[serve,mcp]."""
    print("[*] Setting up upstream laya with serve and mcp extras...")
    if shutil.which("uv"):
        cmd = ["uv", "tool", "install", "--force", "laya[serve,mcp]"]
        print(f"[*] Running: {' '.join(cmd)}")
        res = subprocess.run(cmd, check=False)
        if res.returncode == 0:
            print("[+] Successfully installed laya via uv tool.")
            return

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "laya[serve,mcp]"]
    print(f"[*] Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, check=False)
    if res.returncode == 0:
        print("[+] Successfully installed laya via pip.")
    else:
        print("[-] Failed to install laya. Please install manually: uv tool install 'laya[serve,mcp]'")
        sys.exit(1)


def service_start(foreground: bool = False) -> None:
    if os.path.exists(HIBERNATE_SENTINEL):
        try:
            os.remove(HIBERNATE_SENTINEL)
        except OSError as err:
            logging.debug("clean sentinel: %s", err)

    existing_pid = get_running_pid()
    health = check_health()
    if existing_pid and health:
        print(f"[-] laya-serve is already running (PID: {existing_pid}, Device: {health.get('device')}).")
        return

    env = get_resolved_env()
    preload_models = env.get("LAYA_MODELS", "(all)")
    max_resident = env.get("LAYA_MAX_LOADED", "2")
    idle_unload = env.get("LAYA_IDLE_UNLOAD_SECONDS", "0")

    print(f"[*] Profile: '{ACTIVE_PROFILE}' | Preload: [{preload_models}] | Max Resident: {max_resident} | Idle Unload: {idle_unload}s")

    if foreground:
        print(f"[*] Starting laya-serve on {BASE_URL} in foreground...")
        with contextlib.suppress(KeyboardInterrupt):
            subprocess.run(["laya-serve"], env=env, check=False)
        return

    try:
        log_fd = open(LOG_FILE, "a", encoding="utf-8")  # noqa: SIM115
        if sys.platform == "darwin":
            with contextlib.suppress(Exception):
                subprocess.run(["chflags", "uappnd", LOG_FILE], check=False)
    except OSError as e:
        print(f"[-] Failed to open log file: {e}")
        sys.exit(1)

    print(f"[*] Spawning laya-serve daemon on {BASE_URL}...")
    try:
        proc = subprocess.Popen(
            ["laya-serve"],
            env=env,
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as e:
        print(f"[-] Failed to spawn process: {e}")
        sys.exit(1)

    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
    except OSError as e:
        print(f"[!] Warning: failed to write PID file: {e}")

    print(f"[+] Process spawned (PID: {proc.pid}). Waiting for models on {HOST}:{PORT}...")
    for _ in range(60):
        time.sleep(0.5)
        h = check_health(timeout=1.0)
        if h and h.get("status") == "ok":
            loaded_models = ", ".join(h.get("loaded", []))
            print(f"[+] laya-serve is READY on {BASE_URL} (Device: {h.get('device')}, Loaded: [{loaded_models}]).")
            return

    print("[!] Warning: Server started but /health was slow to respond. Check ~/.cache/laya/laya_serve.log.")


def service_stop() -> None:
    if os.path.exists(HIBERNATE_SENTINEL):
        try:
            os.remove(HIBERNATE_SENTINEL)
        except OSError as err:
            logging.debug("clean sentinel: %s", err)

    pid = get_running_pid()
    if not pid:
        health = check_health()
        if health:
            print("[!] laya-serve is answering but PID file missing. Stop manually via kill/pkill.")
        else:
            print("[-] laya-serve is not running.")
        return

    print(f"[*] Terminating laya-serve (PID: {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.2)
            try:
                os.kill(pid, 0)
            except OSError:
                break
        print("[+] laya-serve stopped successfully.")
    except OSError as e:
        print(f"[-] Error stopping PID {pid}: {e}")
    finally:
        if os.path.exists(PID_FILE):
            with contextlib.suppress(OSError):
                os.remove(PID_FILE)


def service_status() -> None:
    pid = get_running_pid()
    health = check_health()
    if health and health.get("status") == "ok":
        loaded = ", ".join(health.get("loaded", [])) or "none (lazy)"
        device = health.get("device", "unknown")
        pid_str = f"PID: {pid}" if pid else "PID: external"
        mem_str = ""
        if pid:
            rss = get_rss_mb(pid)
            if rss:
                mem_str = f" | RAM: {rss:.1f} MB ({rss / 1024:.2f} GB)"
        print(f"[+] laya-serve is HEALTHY ({pid_str}{mem_str}) on {BASE_URL}")
        print(f"    Profile: {ACTIVE_PROFILE} | Device: {device} | Resident Models: [{loaded}]")
    elif os.path.exists(HIBERNATE_SENTINEL):
        print(f"[-] laya-serve is HIBERNATED (0.0 MB RAM) on {BASE_URL}")
        print(f"    Profile: {ACTIVE_PROFILE} | Auto-wake ready on next tool call")
    else:
        print(f"[-] laya-serve is NOT running on {BASE_URL}.")
        sys.exit(1)


def service_logs(lines: int = 30, follow: bool = False) -> None:
    if not os.path.exists(LOG_FILE):
        print(f"[-] No log file found at {LOG_FILE}")
        return

    if follow:
        print(f"[*] Following {LOG_FILE} (Ctrl+C to stop)...")
        with contextlib.suppress(KeyboardInterrupt):
            subprocess.run(["tail", "-n", str(lines), "-f", LOG_FILE], check=False)
    else:
        try:
            out = subprocess.check_output(["tail", "-n", str(lines), LOG_FILE]).decode("utf-8", errors="replace")
            print(out, end="")
        except Exception:
            try:
                with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                    content = f.readlines()
                    print("".join(content[-lines:]), end="")
            except OSError as err:
                print(f"[-] Error reading log file: {err}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Laya Universal Service Controller")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "setup", "logs"], help="Service action")
    parser.add_argument("-n", "--lines", type=int, default=30, help="Number of log lines to show (default: 30)")
    parser.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    parser.add_argument("--profile", choices=["balanced", "performance", "eco"], help="Override profile (balanced|performance|eco)")
    parser.add_argument("--foreground", action="store_true", help="Run in foreground")
    args = parser.parse_args()

    global ACTIVE_PROFILE, PROFILE_DEFAULTS
    if args.profile:
        ACTIVE_PROFILE = args.profile
        PROFILE_DEFAULTS = PROFILES.get(ACTIVE_PROFILE, PROFILES["balanced"])

    if args.action == "setup":
        service_setup()
    elif args.action == "start":
        service_start(foreground=args.foreground)
    elif args.action == "stop":
        service_stop()
    elif args.action == "restart":
        service_stop()
        time.sleep(1)
        service_start(foreground=args.foreground)
    elif args.action == "status":
        service_status()
    elif args.action == "logs":
        service_logs(lines=args.lines, follow=args.follow)


if __name__ == "__main__":
    main()
