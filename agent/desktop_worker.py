from __future__ import annotations

import asyncio
import json
import queue
import threading
from urllib.parse import quote

import httpx
import websockets
from PySide6.QtCore import QThread, Signal

from agent.agent_rtc import AgentRtcSession
from agent.config import AgentSettings
from agent.registration import AgentRegistration
from common.models import SignalType
from common.network import websocket_url
from common.tls import trusted_tls_context


class AgentWorker(QThread):
    """Runs the remote-side connection behind the unified desktop UI."""

    session_request = Signal(str, str, str)  # session_id, controller, pairing_code
    device_ready = Signal(str)
    pairing_code = Signal(str)
    status_changed = Signal(str)
    error = Signal(str)

    def __init__(self, server_url: str, access_token: str, device_name: str) -> None:
        super().__init__()
        self.server_url = server_url
        self.access_token = access_token
        self.device_name = device_name
        self.decisions: queue.Queue[tuple[str, bool] | None] = queue.Queue()
        self.stopping = threading.Event()

    def decide(self, session_id: str, approved: bool) -> None:
        self.decisions.put((session_id, approved))

    def stop(self) -> None:
        self.stopping.set()
        self.decisions.put(None)
        self.wait(5000)

    def run(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            self.error.emit(str(exc))

    async def _run(self) -> None:
        settings = AgentSettings(
            server_url=self.server_url,
            owner_token=self.access_token,
            device_name=self.device_name,
        )
        self.status_changed.emit("Registering this computer…")
        registration = AgentRegistration(settings)
        _, credentials = await registration.ensure_registered(self.access_token)
        self.device_ready.emit(credentials.device_id)
        async with httpx.AsyncClient(
            base_url=self.server_url,
            timeout=15,
            verify=trusted_tls_context(self.server_url),
        ) as client:
            response = await client.get("/api/v1/config/ice")
            response.raise_for_status()
            ice_servers = response.json().get("ice_servers", [])
            pairing = await client.post(
                "/api/v1/guest/devices/pairing",
                headers={"X-Device-Token": credentials.device_token},
            )
            if pairing.status_code == 401 and not self.access_token:
                # Recover automatically when credentials.json belongs to an
                # older server database or a previous installation.
                self.status_changed.emit("Refreshing this computer’s registration…")
                _, credentials = await registration.ensure_registered(force=True)
                self.device_ready.emit(credentials.device_id)
                pairing = await client.post(
                    "/api/v1/guest/devices/pairing",
                    headers={"X-Device-Token": credentials.device_token},
                )
            pairing.raise_for_status()
            self.pairing_code.emit(pairing.json()["pairing_code"])

        agent_url = websocket_url(
            self.server_url,
            f"/api/v1/agent/connect?device_token={quote(credentials.device_token)}",
        )
        while not self.stopping.is_set():
            try:
                async with websockets.connect(
                    agent_url,
                    ssl=trusted_tls_context(agent_url),
                    ping_interval=20,
                    max_size=2 * 1024 * 1024,
                ) as socket:
                    self.status_changed.emit("This computer is online")
                    await self._serve_socket(socket, settings, credentials.device_token, ice_servers)
            except (websockets.exceptions.ConnectionClosed, OSError, httpx.HTTPError) as exc:
                if not self.stopping.is_set():
                    self.status_changed.emit("Reconnecting…")
                    self.error.emit(str(exc))
                    await asyncio.sleep(3)

    async def _serve_socket(self, socket, settings: AgentSettings, device_token: str, ice_servers: list[dict]) -> None:
        pending: dict[str, dict] = {}
        receive_task = asyncio.create_task(socket.recv())
        decision_task = asyncio.create_task(asyncio.to_thread(self.decisions.get))
        try:
            while not self.stopping.is_set():
                done, _ = await asyncio.wait(
                    [receive_task, decision_task], return_when=asyncio.FIRST_COMPLETED
                )
                if receive_task in done:
                    message = json.loads(receive_task.result())
                    if message.get("type") == "session_request":
                        payload = message.get("payload", {})
                        session_id = message["session_id"]
                        pending[session_id] = payload
                        self.session_request.emit(
                            session_id,
                            payload.get("controller", "RemoteX controller"),
                            payload.get("pairing_code", "Verified"),
                        )
                    receive_task = asyncio.create_task(socket.recv())
                if decision_task in done:
                    decision = decision_task.result()
                    if decision is None:
                        break
                    session_id, approved = decision
                    payload = pending.pop(session_id, {})
                    message_type = SignalType.SESSION_APPROVED if approved else SignalType.SESSION_REJECTED
                    await socket.send(
                        json.dumps({"type": message_type, "session_id": session_id, "payload": {}})
                    )
                    if approved:
                        try:
                            await AgentRtcSession(
                                settings.server_url,
                                payload["agent_signal_token"],
                                session_id,
                                ice_servers,
                            ).run()
                        except Exception as exc:
                            self.error.emit(f"Remote session ended: {exc}")
                    decision_task = asyncio.create_task(asyncio.to_thread(self.decisions.get))
        finally:
            receive_task.cancel()
            decision_task.cancel()
