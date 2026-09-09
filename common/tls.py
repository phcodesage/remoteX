from __future__ import annotations

import ssl
from urllib.parse import urlparse

import certifi


def trusted_tls_context(url: str) -> ssl.SSLContext | None:
    """Use certifi's CA bundle for HTTPS/WSS on macOS and other Python builds.

    Some Python installations do not have the operating system CA roots wired
    into ``ssl.create_default_context``. Cloudflare certificates are publicly
    trusted, so certifi provides the same verification without disabling TLS.
    Plain HTTP/WS development URLs do not need an SSL context.
    """
    if urlparse(url).scheme.lower() not in {"https", "wss"}:
        return None
    return ssl.create_default_context(cafile=certifi.where())
