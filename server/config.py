from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="REMOTE_")

    server_url: str = "http://127.0.0.1:8000"
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = "sqlite:///./remote_support.sqlite3"
    jwt_secret: str = "development-only-change-me-please-rotate"
    jwt_ttl_minutes: int = 30
    pairing_ttl_minutes: int = 10
    local_auth_enabled: bool = False
    stun_urls: str = "stun:stun.cloudflare.com:3478"
    turn_urls: str = ""
    turn_username: str = ""
    turn_credential: str = ""
    cloudflare_turn_key_id: str = ""
    cloudflare_turn_api_token: str = ""
    cloudflare_turn_ttl_seconds: int = 3600

    def ice_servers(self) -> list[dict[str, object]]:
        servers: list[dict[str, object]] = []
        stun = [item.strip() for item in self.stun_urls.split(",") if item.strip()]
        if stun:
            servers.append({"urls": stun})
        turn = [item.strip() for item in self.turn_urls.split(",") if item.strip()]
        if turn:
            entry: dict[str, object] = {"urls": turn}
            if self.turn_username:
                entry["username"] = self.turn_username
            if self.turn_credential:
                entry["credential"] = self.turn_credential
            servers.append(entry)
        return servers


@lru_cache
def get_settings() -> Settings:
    return Settings()
