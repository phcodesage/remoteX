from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

import httpx
import websockets

from agent.agent_rtc import AgentRtcSession, websocket_url
from agent.config import get_agent_settings
from agent.permissions import ask_for_approval
from agent.registration import AgentRegistration
from common.tls import trusted_tls_context


async def run_agent_async() -> None:
    settings = get_agent_settings()
    _, credentials = await AgentRegistration(settings).ensure_registered()
    ice_config = {"ice_servers": []}
    async with httpx.AsyncClient(
        base_url=settings.server_url,
        timeout=15,
        verify=trusted_tls_context(settings.server_url),
    ) as client:
        response = await client.get("/api/v1/config/ice")
        response.raise_for_status()
        ice_config = response.json()
        pairing = await client.post(
            "/api/v1/guest/devices/pairing",
            headers={"X-Device-Token": credentials.device_token},
        )
        if pairing.status_code == 401:
            _, credentials = await AgentRegistration(settings).ensure_registered(force=True)
            pairing = await client.post(
                "/api/v1/guest/devices/pairing",
                headers={"X-Device-Token": credentials.device_token},
            )
        pairing.raise_for_status()
        print(f"Pairing code: {pairing.json()['pairing_code']}")

    agent_url = websocket_url(
        settings.server_url,
        f"/api/v1/agent/connect?device_token={quote(credentials.device_token)}",
    )
    print(f"Agent online as {settings.device_name}. Press Ctrl-C to stop.")
    while True:
        try:
            async with websockets.connect(
                agent_url,
                ssl=trusted_tls_context(agent_url),
                ping_interval=20,
                max_size=2 * 1024 * 1024,
            ) as socket:
                async for raw in socket:
                    message = json.loads(raw)
                    if message.get("type") != "session_request":
                        continue
                    payload = message.get("payload", {})
                    approved = await ask_for_approval(
                        payload.get("controller", ""), payload.get("pairing_code", "")
                    )
                    response_type = "session_approved" if approved else "session_rejected"
                    session_id = message["session_id"]
                    try:
                        async with httpx.AsyncClient(
                            base_url=settings.server_url,
                            timeout=15,
                            verify=trusted_tls_context(settings.server_url),
                        ) as client:
                            response = await client.post(
                                f"/api/v1/sessions/{session_id}/{'approve' if approved else 'reject'}",
                                headers={"X-Device-Token": credentials.device_token},
                            )
                            response.raise_for_status()
                    except httpx.HTTPError:
                        await socket.send(
                            json.dumps({"type": response_type, "session_id": session_id, "payload": {}})
                        )
                    if approved:
                        try:
                            await AgentRtcSession(
                                settings.server_url,
                                payload["agent_signal_token"],
                                session_id,
                                ice_config["ice_servers"],
                            ).run()
                        except Exception as exc:
                            print(f"WebRTC session ended: {exc}")
        except (websockets.exceptions.ConnectionClosed, OSError, httpx.HTTPError) as exc:
            print(f"Agent connection lost ({exc}); retrying in 3 seconds.")
            await asyncio.sleep(3)


def run_agent() -> None:
    try:
        asyncio.run(run_agent_async())
    except KeyboardInterrupt:
        print("\nAgent stopped.")
