from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class WebSocketManager:
    """In-memory presence/signaling for the single-server MVP.

    Redis-backed presence can replace this class when deploying multiple
    FastAPI instances.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.agent_connections: dict[str, WebSocket] = {}
        self.session_connections: dict[str, dict[str, WebSocket]] = defaultdict(dict)

    async def set_agent(self, device_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self.agent_connections[device_id] = websocket

    async def remove_agent(self, device_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if self.agent_connections.get(device_id) is websocket:
                self.agent_connections.pop(device_id, None)

    async def send_to_agent(self, device_id: str, message: dict) -> bool:
        websocket = self.agent_connections.get(device_id)
        if not websocket:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            return False

    async def add_session(self, session_id: str, role: str, websocket: WebSocket) -> None:
        async with self._lock:
            self.session_connections[session_id][role] = websocket
            peers = list(self.session_connections[session_id].values())
            if len(peers) == 2:
                message = {"type": "session_ready", "session_id": session_id, "payload": {}}
                for peer in peers:
                    await peer.send_json(message)

    async def remove_session(self, session_id: str, role: str, websocket: WebSocket) -> None:
        async with self._lock:
            if self.session_connections.get(session_id, {}).get(role) is websocket:
                self.session_connections[session_id].pop(role, None)
            if not self.session_connections.get(session_id):
                self.session_connections.pop(session_id, None)

    async def forward(self, session_id: str, from_role: str, message: dict) -> bool:
        target_role = "agent" if from_role == "controller" else "controller"
        websocket = self.session_connections.get(session_id, {}).get(target_role)
        if not websocket:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            return False

    def agent_online(self, device_id: str) -> bool:
        return device_id in self.agent_connections
