from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SignalEnvelope(BaseModel):
    type: str
    session_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DeviceRegistration(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(min_length=1, max_length=80)
    public_key: str = Field(min_length=20, max_length=5000)


class DeviceHeartbeat(BaseModel):
    status: Literal["online", "idle"] = "online"


class SessionCreate(BaseModel):
    device_id: str
    expires_in_seconds: int = Field(default=600, ge=60, le=3600)


class InputCommand(BaseModel):
    type: Literal["mouse_move", "mouse_button", "mouse_scroll", "key", "hotkey"]
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)
    button: str | None = None
    pressed: bool | None = None
    key: str | None = None
    keys: list[str] | None = None
    delta: int | None = None

