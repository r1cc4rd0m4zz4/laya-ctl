#!/usr/bin/env python3
"""
Laya Universal Service Controller (Linux & macOS)
Zero-dependency controller for upstream laya-serve on loopback 127.0.0.1:5292.
Adheres to AGENTS.md: Native stdlib, zero-trust loopback binding, fail-closed probes.
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

HOST = os.environ.get("LAYA_HOST", "127.0.0.1")
PORT = int(os.environ.get("LAYA_PORT", "5292"))
BASE_URL = f"http://{HOST}:{PORT}"
BASE_DIR = os.path.expanduser("~/.cache/laya")
PID_FILE = os.path.join(BASE_DIR, "laya_serve.pid")
LOG_FILE = os.path.join(BASE_DIR, "laya_serve.log")

try:
    os.makedirs(BASE_DIR, mode=0o700, exist_ok=True)
except OSError as err:
    logging.debug("Directory init: %s", err)


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


def service_setup() -> None:
    """Install upstream laya[serve,mcp] via uv tool or pip."""
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
    existing_pid = get_running_pid()
    health = check_health()
    if existing_pid and health:
        print(f"[-] laya-serve is already running (PID: {existing_pid}, Device: {health.get('device')}).")
        return

    env = os.environ.copy()
    env["LAYA_HOST"] = HOST
    env["LAYA_PORT"] = str(PORT)
    env["LAYA_PRELOAD"] = "1"

    if foreground:
        print(f"[*] Starting laya-serve on {BASE_URL} in foreground...")
        with contextlib.suppress(KeyboardInterrupt):
            subprocess.run(["laya-serve"], env=env, check=False)
        return

    try:
        log_fd = open(LOG_FILE, "a", encoding="utf-8")  # noqa: SIM115
    except OSError as e:
        print(f"[-] Failed to open log file: {e}")
        sys.exit(1)

    print(f"[*] Spawning laya-serve on {BASE_URL}...")
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

    print(f"[+] Process spawned (PID: {proc.pid}). Waiting for model preload on {HOST}:{PORT}...")
    for _ in range(60):
        time.sleep(0.5)
        h = check_health(timeout=1.0)
        if h and h.get("status") == "ok":
            print(f"[+] laya-serve is READY on {BASE_URL} (Device: {h.get('device')}, Models: {len(h.get('loaded', []))}).")
            return

    print("[!] Warning: Server started but /health was slow to respond. Check ~/.cache/laya/laya_serve.log.")


def service_stop() -> None:
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
        loaded = ", ".join(health.get("loaded", []))
        device = health.get("device", "unknown")
        pid_str = f"PID: {pid}" if pid else "PID: external"
        print(f"[+] laya-serve is HEALTHY ({pid_str}) on {BASE_URL} | Device: {device} | Models: [{loaded}]")
    else:
        print(f"[-] laya-serve is NOT running or unresponsive on {BASE_URL}.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Laya Service Controller")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "setup"], help="Service action")
    parser.add_argument("--foreground", action="store_true", help="Run in foreground")
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
