from __future__ import annotations

import asyncio

import av
import pytest
from aiortc import RTCPeerConnection, VideoStreamTrack


class OneFrameTrack(VideoStreamTrack):
    kind = "video"

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frame = av.VideoFrame(width=2, height=2, format="rgb24")
        frame.pts, frame.time_base = pts, time_base
        return frame


@pytest.mark.asyncio
async def test_local_offer_answer_data_channel_and_video() -> None:
    controller = RTCPeerConnection()
    agent = RTCPeerConnection()
    received_message = asyncio.Event()
    received_frame = asyncio.Event()
    channel = controller.createDataChannel("control")

    @agent.on("datachannel")
    def on_datachannel(remote) -> None:
        remote.on("message", lambda _: received_message.set())

    @agent.on("track")
    def on_track(track) -> None:
        async def consume() -> None:
            await track.recv()
            received_frame.set()

        asyncio.create_task(consume())

    controller.addTrack(OneFrameTrack())
    offer = await controller.createOffer()
    await controller.setLocalDescription(offer)
    await agent.setRemoteDescription(controller.localDescription)
    answer = await agent.createAnswer()
    await agent.setLocalDescription(answer)
    await controller.setRemoteDescription(agent.localDescription)

    for _ in range(100):
        if channel.readyState == "open":
            break
        await asyncio.sleep(0.05)
    assert channel.readyState == "open"
    channel.send('{"type":"mouse_move","x":1,"y":1}')
    await asyncio.wait_for(received_message.wait(), 5)
    await asyncio.wait_for(received_frame.wait(), 5)
    await controller.close()
    await agent.close()

