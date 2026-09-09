#!/usr/bin/env python3
"""Single entry point for the server, agent, viewer, and diagnostics."""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import threading
import time
from urllib.parse import urlparse
from urllib.request import urlopen
from pathlib import Path

from common.preferences import load_preferences

VERSION = "0.1.0"


def _healthy(url: str) -> bool:
    try:
        with urlopen(url.rstrip("/") + "/healthz", timeout=0.5) as response:
            return response.status == 200
    except Exception:
        return False


def ensure_local_server() -> None:
    """Start FastAPI automatically for the default single-command local app."""
    from server.config import get_settings

    settings = get_settings()
    preferences = load_preferences()
    if not preferences.host_mode:
        return
    parsed = urlparse(preferences.effective_server_url)
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if parsed.hostname not in local_hosts:
        return
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    if _healthy(base_url):
        return

    import uvicorn
    from server.app import create_app

    host = "127.0.0.1" if parsed.hostname in {"localhost", "127.0.0.1"} else "::1"
    host_settings = settings.model_copy(
        update={
            "server_url": preferences.effective_server_url,
            "host": host,
            "port": preferences.host_port,
            "local_auth_enabled": True,
        }
    )
    thread = threading.Thread(
        target=lambda: uvicorn.run(
            create_app(host_settings), host=host, port=preferences.host_port, log_level="warning"
        ),
        name="remotex-server",
        daemon=True,
    )
    thread.start()
    for _ in range(50):
        if _healthy(base_url):
            return
        time.sleep(0.1)
    print(f"Warning: local server did not become ready at {base_url}")


def doctor() -> int:
    print(f"python-remote {VERSION}")
    print(f"Python: {platform.python_version()} ({platform.system()})")
    required = {
        "fastapi": "server",
        "uvicorn": "server",
        "aiortc": "WebRTC",
        "av": "WebRTC video",
        "mss": "screen capture",
        "pyautogui": "input control",
        "PySide6": "viewer UI",
        "cryptography": "device identity",
        "sqlalchemy": "database",
        "argon2": "password hashing",
        "websockets": "signaling client",
    }
    missing = []
    for module, purpose in required.items():
        installed = importlib.util.find_spec(module) is not None
        print(f"  [{'OK' if installed else 'MISSING':7}] {module:14} {purpose}")
        if not installed:
            missing.append(module)
    env_file = Path(".env")
    print(f"  [{'OK' if env_file.exists() else 'INFO':7}] .env            {'found' if env_file.exists() else 'copy .env.example for local configuration'}")
    print("  [INFO  ] macOS permissions: Screen Recording and Accessibility")
    try:
        from server.config import get_settings

        settings = get_settings()
        cloudflare_ready = bool(settings.cloudflare_turn_key_id and settings.cloudflare_turn_api_token)
        print(f"  [{'OK' if cloudflare_ready else 'INFO':7}] Cloudflare TURN {'configured' if cloudflare_ready else 'not configured'}")
    except Exception:
        print("  [INFO  ] Cloudflare TURN configuration unavailable")
    return 1 if missing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Python remote-support system")
    parser.add_argument("role", nargs="?", choices=["desktop", "server", "agent", "viewer", "doctor", "version"])
    args = parser.parse_args()
    role = args.role or "desktop"
    if role == "version":
        print(VERSION)
        return 0
    if role == "doctor":
        return doctor()
    if role == "server":
        from server.app import run_server
        run_server()
        return 0
    if role in {"desktop", "agent", "viewer"}:
        from viewer.main import run_unified
        run_unified()
        return 0
    if role == "viewer":
        from viewer.main import run_viewer
        run_viewer()
        return 0
    parser.error(f"unknown role: {role}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
