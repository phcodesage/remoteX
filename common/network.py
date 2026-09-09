from __future__ import annotations


def websocket_url(server_url: str, path: str) -> str:
    if server_url.startswith("https://"):
        return "wss://" + server_url.removeprefix("https://") + path
    return "ws://" + server_url.removeprefix("http://") + path

