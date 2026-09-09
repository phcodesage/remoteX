from __future__ import annotations

import httpx

from server.config import Settings


async def get_ice_servers(settings: Settings) -> list[dict]:
    """Return static ICE config or generate short-lived Cloudflare TURN credentials."""
    if settings.cloudflare_turn_key_id and settings.cloudflare_turn_api_token:
        url = (
            "https://rtc.live.cloudflare.com/v1/turn/keys/"
            f"{settings.cloudflare_turn_key_id}/credentials/generate-ice-servers"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.cloudflare_turn_api_token}"},
                json={"ttl": settings.cloudflare_turn_ttl_seconds},
            )
            response.raise_for_status()
            payload = response.json()
        return payload.get("iceServers", [])
    return settings.ice_servers()

