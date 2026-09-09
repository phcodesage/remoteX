from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

import websockets
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer

from common.network import websocket_url
from agent.input_controller import InputController
from agent.screen_track import MssScreenTrack


class AgentRtcSession:
    def __init__(self, server_url: str, signal_token: str, session_id: str, ice_servers: list[dict]) -> None:
        self.server_url = server_url
        self.signal_token = signal_token
        self.session_id = session_id
        self.ice_servers = ice_servers
        self.input = InputController()
        self.peer: RTCPeerConnection | None = None
        self.track: MssScreenTrack | None = None

    def rtc_configuration(self) -> RTCConfiguration:
        servers = []
        for server in self.ice_servers:
            urls = server.get("urls", [])
            if isinstance(urls, str):
                urls = [urls]
            servers.append(
                RTCIceServer(
                    urls=urls,
                    username=server.get("username", ""),
                    credential=server.get("credential", ""),
                )
            )
        return RTCConfiguration(iceServers=servers)

    async def run(self) -> None:
        signal_url = websocket_url(
            self.server_url,
            f"/api/v1/signaling/{quote(self.session_id)}?role=agent&token={quote(self.signal_token)}",
        )
        async with websockets.connect(signal_url, ping_interval=20, max_size=8 * 1024 * 1024) as signal:
            self.peer = RTCPeerConnection(self.rtc_configuration())
            self.track = MssScreenTrack()
            self.peer.addTrack(self.track)

            @self.peer.on("datachannel")
            def on_datachannel(channel) -> None:
                if channel.label == "control":
                    channel.on("message", self.input.handle)

            try:
                async for raw in signal:
                    message = json.loads(raw)
                    message_type = message.get("type")
                    if message_type == "offer":
                        from aiortc import RTCSessionDescription

                        offer = message["payload"]
                        await self.peer.setRemoteDescription(
                            RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
                        )
                        answer = await self.peer.createAnswer()
                        await self.peer.setLocalDescription(answer)
                        await signal.send(
                            json.dumps(
                                {
                                    "type": "answer",
                                    "session_id": self.session_id,
                                    "payload": {
                                        "sdp": self.peer.localDescription.sdp,
                                        "type": self.peer.localDescription.type,
                                    },
                                }
                            )
                        )
                    elif message_type == "ice_candidate":
                        # Trickle ICE can be added once deployments need it. The
                        # initial SDP currently contains gathered candidates.
                        continue
                    elif message_type in {"session_revoked", "session_ended"}:
                        break
            finally:
                if self.track:
                    self.track.close()
                await self.peer.close()
