from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PUBLIC_SERVER_URL = "https://remotex.chat-x.site"
DEFAULT_HOST_PORT = 8080


@dataclass
class AppPreferences:
    """Per-computer UI settings shared by the viewer and embedded agent."""

    server_url: str = DEFAULT_PUBLIC_SERVER_URL
    host_mode: bool = False
    host_port: int = DEFAULT_HOST_PORT

    @property
    def effective_server_url(self) -> str:
        if self.host_mode:
            return f"http://127.0.0.1:{self.host_port}"
        return normalize_server_url(self.server_url)


def normalize_server_url(value: str) -> str:
    return value.strip().rstrip("/")


def preferences_path() -> Path:
    override = os.getenv("REMOTEX_SETTINGS_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return Path("~/.python-remote/preferences.json").expanduser()


def _is_loopback(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _default_preferences() -> AppPreferences:
    env_url = os.getenv("REMOTE_SERVER_URL", "").strip()
    autostart = os.getenv("REMOTE_AUTOSTART_SERVER", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    host_mode = bool(env_url and _is_loopback(env_url) and autostart)
    public_url = DEFAULT_PUBLIC_SERVER_URL if not env_url or _is_loopback(env_url) else env_url
    try:
        port = int(os.getenv("REMOTE_PORT", str(DEFAULT_HOST_PORT)))
    except ValueError:
        port = DEFAULT_HOST_PORT
    return AppPreferences(server_url=normalize_server_url(public_url), host_mode=host_mode, host_port=port)


def load_preferences() -> AppPreferences:
    path = preferences_path()
    if not path.exists():
        return _default_preferences()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        server_url = normalize_server_url(str(payload.get("server_url", DEFAULT_PUBLIC_SERVER_URL)))
        host_mode = bool(payload.get("host_mode", False))
        host_port = int(payload.get("host_port", DEFAULT_HOST_PORT))
        if not 1024 <= host_port <= 65535:
            raise ValueError("host port out of range")
        return AppPreferences(server_url=server_url, host_mode=host_mode, host_port=host_port)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return _default_preferences()


def save_preferences(preferences: AppPreferences) -> None:
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(preferences), indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
