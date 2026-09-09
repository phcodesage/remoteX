from __future__ import annotations

import asyncio
import time

import av
import mss
import numpy as np
from aiortc import VideoStreamTrack


class MssScreenTrack(VideoStreamTrack):
    """Captures the primary display at a bounded frame rate."""

    kind = "video"

    def __init__(self, monitor: int = 1, fps: int = 15, max_width: int = 1280) -> None:
        super().__init__()
        self.monitor = monitor
        self.frame_interval = 1 / max(fps, 1)
        self.max_width = max_width
        self._next_frame = time.monotonic()
        self._sct = mss.mss()

    async def recv(self) -> av.VideoFrame:
        now = time.monotonic()
        delay = self._next_frame - now
        if delay > 0:
            await asyncio.sleep(delay)
        self._next_frame = max(self._next_frame + self.frame_interval, time.monotonic())
        shot = await asyncio.to_thread(self._sct.grab, self._sct.monitors[self.monitor])
        image = np.asarray(shot)
        image = image[:, :, :3][:, :, ::-1]  # BGRA -> RGB
        if image.shape[1] > self.max_width:
            ratio = self.max_width / image.shape[1]
            height = max(1, int(image.shape[0] * ratio))
            image = np.asarray(av.VideoFrame.from_ndarray(image, format="rgb24").reformat(width=self.max_width, height=height).to_ndarray(format="rgb24"))
        frame = av.VideoFrame.from_ndarray(image, format="rgb24")
        frame.pts, frame.time_base = await self.next_timestamp()
        return frame

    def close(self) -> None:
        self._sct.close()

