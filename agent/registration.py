from __future__ import annotations

import platform
from pathlib import Path

import httpx

from agent.config import AgentSettings
from agent.device_identity import DeviceCredentials, DeviceIdentity


class AgentRegistration:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        data_dir = Path(settings.device_data_dir).expanduser()
        self.identity_path = data_dir / "identity.json"
        self.credentials_path = data_dir / "credentials.json"

    async def ensure_registered(self, owner_token: str | None = None) -> tuple[DeviceIdentity, DeviceCredentials]:
        identity = DeviceIdentity.load_or_create(self.identity_path)
        credentials = DeviceCredentials.load(self.credentials_path)
        owner_token = owner_token or self.settings.owner_token
        if credentials:
            # A saved device token is account-bound. The unified UI can switch
            # local profiles, so verify the saved device belongs to the current
            # controller before reusing it.
            if owner_token:
                async with httpx.AsyncClient(base_url=self.settings.server_url, timeout=15) as client:
                    response = await client.get(
                        "/api/v1/devices",
                        headers={"Authorization": f"Bearer {owner_token}"},
                    )
                    response.raise_for_status()
                    owned_ids = {device["id"] for device in response.json()}
                if credentials.device_id in owned_ids:
                    return identity, credentials
                credentials = None
            else:
                return identity, credentials
        if not owner_token:
            raise RuntimeError(
                "This device is not enrolled. Set REMOTE_ACCESS_TOKEN or REMOTE_OWNER_TOKEN for first enrollment."
            )
        async with httpx.AsyncClient(base_url=self.settings.server_url, timeout=15) as client:
            response = await client.post(
                "/api/v1/devices/register",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={
                    "name": self.settings.device_name,
                    "platform": f"{platform.system()} {platform.release()}",
                    "public_key": identity.public_key_b64,
                },
            )
            response.raise_for_status()
            payload = response.json()
        credentials = DeviceCredentials(payload["device_id"], payload["device_token"])
        credentials.save(self.credentials_path)
        print(f"Registered device {payload['name']} ({credentials.device_id})")
        return identity, credentials
