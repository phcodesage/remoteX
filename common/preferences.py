from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

DEFAULT_PUBLIC_SERVER_URL = "https://remotex.chat-x.site"


@dataclass
class AppPreferences:
    """Per-computer UI settings shared by the viewer and agent."""

    server_url: str = DEFAULT_PUBLIC_SERVER_URL
    access_token: str = ""

    @property
    def effective_server_url(self) -> str:
        return normalize_server_url(self.server_url)


def normalize_server_url(value: str) -> str:
    return value.strip().rstrip("/")


def preferences_path() -> Path:
    override = os.getenv("REMOTEX_SETTINGS_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return Path("~/.python-remote/preferences.json").expanduser()


def configured_value(name: str) -> str | None:
    direct = os.getenv(name)
    if direct is not None:
        return direct
    values = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    value = values.get(name)
    return str(value) if value is not None else None


def _default_preferences() -> AppPreferences:
    env_url = (configured_value("REMOTE_SERVER_URL") or "").strip()
    parsed = urlparse(env_url)
    public_url = (
        DEFAULT_PUBLIC_SERVER_URL
        if not env_url or parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        else env_url
    )
    access_token = configured_value("REMOTE_ACCESS_TOKEN") or configured_value("REMOTE_OWNER_TOKEN") or ""
    return AppPreferences(server_url=normalize_server_url(public_url), access_token=access_token.strip())


def load_preferences() -> AppPreferences:
    path = preferences_path()
    if not path.exists():
        return _default_preferences()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        server_url = normalize_server_url(str(payload.get("server_url", DEFAULT_PUBLIC_SERVER_URL)))
        access_token = str(payload.get("access_token", "")).strip()
        if not access_token:
            access_token = (
                configured_value("REMOTE_ACCESS_TOKEN") or configured_value("REMOTE_OWNER_TOKEN") or ""
            ).strip()
        return AppPreferences(server_url=server_url, access_token=access_token)
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
