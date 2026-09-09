from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@dataclass
class DeviceIdentity:
    private_key: Ed25519PrivateKey

    @property
    def public_key_b64(self) -> str:
        public = self.private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return base64.b64encode(public).decode("ascii")

    @classmethod
    def load_or_create(cls, path: Path) -> "DeviceIdentity":
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            payload = json.loads(path.read_text())
            raw = base64.b64decode(payload["private_key"])
            return cls(Ed25519PrivateKey.from_private_bytes(raw))
        identity = cls(Ed25519PrivateKey.generate())
        raw = identity.private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        path.write_text(json.dumps({"private_key": base64.b64encode(raw).decode("ascii")}))
        path.chmod(0o600)
        return identity


@dataclass
class DeviceCredentials:
    device_id: str
    device_token: str

    @classmethod
    def load(cls, path: Path) -> "DeviceCredentials | None":
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        return cls(device_id=payload["device_id"], device_token=payload["device_token"])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"device_id": self.device_id, "device_token": self.device_token}))
        path.chmod(0o600)

