from __future__ import annotations

import asyncio
import json
import queue
import threading
from urllib.parse import quote

import websockets
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer

from common.network import websocket_url
from common.tls import trusted_tls_context


class ViewerRtcWorker(QThread):
    frame_ready = Signal(QImage)
    status_changed = Signal(str)
    error = Signal(str)

    def __init__(self, server_url: str, token: str, session_id: str, ice_servers: list[dict]) -> None:
        super().__init__()
        self.server_url = server_url
        self.token = token
        self.session_id = session_id
        self.ice_servers = ice_servers
        self.commands: queue.Queue[dict | None] = queue.Queue()
        self.stopping = threading.Event()

    def send_control(self, command: dict) -> None:
        self.commands.put(command)

    def stop(self) -> None:
        self.stopping.set()
        self.commands.put(None)
        self.wait(3000)

    def run(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            self.error.emit(str(exc))

    def rtc_configuration(self) -> RTCConfiguration:
        servers = []
        for server in self.ice_servers:
            urls = server.get("urls", [])
            urls = [urls] if isinstance(urls, str) else urls
            servers.append(
                RTCIceServer(
                    urls=urls,
                    username=server.get("username", ""),
                    credential=server.get("credential", ""),
                )
            )
        return RTCConfiguration(iceServers=servers)

    async def _consume_video(self, track) -> None:
        while not self.stopping.is_set():
            frame = await track.recv()
            image = frame.to_ndarray(format="rgb24")
            height, width, _ = image.shape
            qimage = QImage(image.data, width, height, width * 3, QImage.Format_RGB888).copy()
            self.frame_ready.emit(qimage)

    async def _run(self) -> None:
        signal_url = websocket_url(
            self.server_url,
            f"/api/v1/signaling/{quote(self.session_id)}?role=controller&token={quote(self.token)}",
        )
        async with websockets.connect(
            signal_url,
            ssl=trusted_tls_context(signal_url),
            ping_interval=20,
            max_size=8 * 1024 * 1024,
        ) as signal:
            peer = RTCPeerConnection(self.rtc_configuration())
            control = peer.createDataChannel("control", ordered=True)
            peer.createDataChannel("telemetry", ordered=False, maxRetransmits=0)

            @peer.on("track")
            def on_track(track) -> None:
                if track.kind == "video":
                    asyncio.create_task(self._consume_video(track))

            ready = json.loads(await signal.recv())
            if ready.get("type") != "session_ready":
                raise RuntimeError("Signaling session did not become ready")
            offer = await peer.createOffer()
            await peer.setLocalDescription(offer)
            await signal.send(
                json.dumps(
                    {
                        "type": "offer",
                        "session_id": self.session_id,
                        "payload": {
                            "sdp": peer.localDescription.sdp,
                            "type": peer.localDescription.type,
                        },
                    }
                )
            )
            self.status_changed.emit("Connecting…")
            receive_task = asyncio.create_task(signal.recv())
            command_task = asyncio.create_task(asyncio.to_thread(self.commands.get))
            try:
                while not self.stopping.is_set():
                    done, _ = await asyncio.wait(
                        [receive_task, command_task], return_when=asyncio.FIRST_COMPLETED
                    )
                    if receive_task in done:
                        raw = receive_task.result()
                        message = json.loads(raw)
                        message_type = message.get("type")
                        if message_type == "answer":
                            from aiortc import RTCSessionDescription

                            answer = message["payload"]
                            await peer.setRemoteDescription(
                                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
                            )
                            self.status_changed.emit("Connected")
                        elif message_type in {"session_revoked", "session_ended"}:
                            break
                        receive_task = asyncio.create_task(signal.recv())
                    if command_task in done:
                        command = command_task.result()
                        if command is None:
                            break
                        if control.readyState == "open":
                            control.send(json.dumps(command))
                        command_task = asyncio.create_task(asyncio.to_thread(self.commands.get))
            finally:
                receive_task.cancel()
                command_task.cancel()
                await peer.close()
