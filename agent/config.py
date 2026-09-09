from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="REMOTE_")

    server_url: str = "https://remotex.chat-x.site"
    owner_token: str = ""
    device_name: str = "Remote computer"
    device_data_dir: str = "~/.python-remote"
    heartbeat_seconds: int = 20


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
