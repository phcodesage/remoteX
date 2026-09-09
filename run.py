#!/usr/bin/env python3
"""Single entry point for the server, agent, viewer, and diagnostics."""

from __future__ import annotations

import argparse
import importlib.util
import platform
from pathlib import Path

VERSION = "0.1.0"


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
    parser.add_argument(
        "role",
        nargs="?",
        choices=["desktop", "server", "backend", "agent", "viewer", "doctor", "version"],
    )
    args = parser.parse_args()
    role = args.role or "desktop"
    if role == "version":
        print(VERSION)
        return 0
    if role == "doctor":
        return doctor()
    if role in {"server", "backend"}:
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
