from __future__ import annotations

import json
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.crypto import sha256_hex
from common.models import SessionStatus, SignalType, iso
from common.protocol import DeviceHeartbeat, DeviceRegistration, SessionCreate, SignalEnvelope
from server.auth import (
    bearer,
    current_user,
    decode_user_token,
    decode_signaling_token,
    hash_password,
    issue_signaling_token,
    issue_user_token,
    verify_password,
)
from server.config import Settings, get_settings
from server.database import (
    AuditEvent,
    Device,
    PairingCode,
    RemoteSession,
    User,
    ensure_utc,
    get_db,
    initialize_database,
    make_session_factory,
    utcnow,
)
from server.ice import get_ice_servers
from server.websocket_manager import WebSocketManager


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class PairingClaim(BaseModel):
    pairing_code: str = Field(min_length=7, max_length=7)


class SessionResponse(BaseModel):
    id: str
    device_id: str
    device_name: str | None = None
    status: str
    pairing_code: str | None = None
    signaling_token: str | None = None
    expires_at: str


ATTENDED_USER_EMAIL = "attended@remotex.local"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        initialize_database(settings)
        yield

    app = FastAPI(title="Python Remote Control", version="0.1.0", lifespan=lifespan)
    manager = WebSocketManager()
    app.state.settings = settings
    app.state.manager = manager

    def app_get_db():
        db = make_session_factory(settings)()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = app_get_db

    def app_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        db: Session = Depends(app_get_db),
    ) -> User:
        if not credentials:
            raise HTTPException(status_code=401, detail="Bearer token required")
        return decode_user_token(credentials.credentials, settings, db)

    app.dependency_overrides[current_user] = app_current_user

    def audit(
        db: Session,
        event_type: str,
        session_id: str | None = None,
        actor_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        db.add(
            AuditEvent(
                session_id=session_id,
                actor_id=actor_id,
                event_type=event_type,
                metadata_json=json.dumps(metadata or {}),
            )
        )

    def get_owned_device(db: Session, device_id: str, user_id: str) -> Device:
        device = db.scalar(select(Device).where(Device.id == device_id, Device.user_id == user_id))
        if not device or device.revoked_at:
            raise HTTPException(status_code=404, detail="Device not found")
        return device

    def get_device_by_token(db: Session, token: str) -> Device:
        device = db.scalar(select(Device).where(Device.device_token_hash == sha256_hex(token)))
        if not device or device.revoked_at:
            raise HTTPException(status_code=401, detail="Invalid device token")
        return device

    def get_attended_user(db: Session) -> User:
        """Return the internal owner for the no-account attended-support mode.

        This is deliberately not exposed as a login identity. It keeps the
        existing database shape compatible while authorization is provided by
        a one-time pairing code and the host's explicit approval.
        """
        user = db.scalar(select(User).where(User.email == ATTENDED_USER_EMAIL))
        if user:
            return user
        user = User(email=ATTENDED_USER_EMAIL, password_hash=hash_password(secrets.token_urlsafe(32)))
        db.add(user)
        db.flush()
        return user

    def create_pairing_code(db: Session, device: Device) -> tuple[str, PairingCode]:
        now = utcnow()
        for old_code in db.scalars(
            select(PairingCode).where(PairingCode.device_id == device.id, PairingCode.used_at.is_(None))
        ).all():
            old_code.used_at = now
        plain_code = f"{secrets.randbelow(1000):03d}-{secrets.randbelow(1000):03d}"
        pairing = PairingCode(
            device_id=device.id,
            code_hash=sha256_hex(plain_code),
            expires_at=now + timedelta(minutes=settings.pairing_ttl_minutes),
        )
        db.add(pairing)
        return plain_code, pairing

    def get_session_or_404(db: Session, session_id: str) -> RemoteSession:
        remote_session = db.get(RemoteSession, session_id)
        if not remote_session:
            raise HTTPException(status_code=404, detail="Session not found")
        if ensure_utc(remote_session.expires_at) < utcnow() and remote_session.status not in {
            SessionStatus.ENDED,
            SessionStatus.REVOKED,
        }:
            remote_session.status = SessionStatus.EXPIRED
            db.commit()
        return remote_session

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/config/ice")
    async def ice_config() -> dict:
        return {"ice_servers": await get_ice_servers(settings)}

    @app.post("/api/v1/auth/register", response_model=AuthResponse)
    def register(payload: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
        email = payload.email.strip().lower()
        if "@" not in email:
            raise HTTPException(status_code=422, detail="A valid email is required")
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(status_code=409, detail="Email is already registered")
        user = User(email=email, password_hash=hash_password(payload.password))
        db.add(user)
        db.commit()
        db.refresh(user)
        return AuthResponse(access_token=issue_user_token(user, settings), user_id=user.id)

    @app.post("/api/v1/auth/login", response_model=AuthResponse)
    def login(payload: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
        user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
        if not user or user.disabled_at or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        return AuthResponse(access_token=issue_user_token(user, settings), user_id=user.id)

    @app.post("/api/v1/auth/local", response_model=AuthResponse)
    def local_auth(request: Request, db: Session = Depends(get_db)) -> AuthResponse:
        """Prototype-only auth for a localhost desktop session.

        This is intentionally disabled by default and refuses non-loopback
        requests. Internet/shared deployments must use normal account tokens.
        """
        client_host = request.client.host if request.client else ""
        if not settings.local_auth_enabled or client_host not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(status_code=403, detail="Local auth is disabled")
        email = "local@remotex.local"
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            user = User(email=email, password_hash=hash_password(secrets.token_urlsafe(32)))
            db.add(user)
            db.commit()
            db.refresh(user)
        return AuthResponse(access_token=issue_user_token(user, settings), user_id=user.id)

    @app.post("/api/v1/guest/devices/register")
    def register_attended_device(
        payload: DeviceRegistration,
        db: Session = Depends(get_db),
    ) -> dict:
        """Register a host for attended support without a user account.

        Registration alone cannot start a control session. The controller
        still needs a short-lived pairing code, and the host must approve the
        incoming request locally.
        """
        user = get_attended_user(db)
        device_token = secrets.token_urlsafe(32)
        device = Device(
            user_id=user.id,
            name=payload.name,
            platform=payload.platform,
            public_key=payload.public_key,
            device_token_hash=sha256_hex(device_token),
            last_seen_at=utcnow(),
        )
        db.add(device)
        db.flush()
        pairing_code, pairing = create_pairing_code(db, device)
        db.commit()
        return {
            "device_id": device.id,
            "device_token": device_token,
            "name": device.name,
            "pairing_code": pairing_code,
            "pairing_expires_at": iso(pairing.expires_at),
        }

    @app.post("/api/v1/guest/devices/pairing")
    def new_attended_pairing_code(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
        token = request.headers.get("X-Device-Token")
        if not token:
            raise HTTPException(status_code=401, detail="Device registration is required")
        device = get_device_by_token(db, token)
        pairing_code, pairing = create_pairing_code(db, device)
        db.commit()
        return {"pairing_code": pairing_code, "expires_at": iso(pairing.expires_at) or ""}

    @app.post("/api/v1/devices/register")
    def register_device(
        payload: DeviceRegistration,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        device_token = secrets.token_urlsafe(32)
        device = Device(
            user_id=user.id,
            name=payload.name,
            platform=payload.platform,
            public_key=payload.public_key,
            device_token_hash=sha256_hex(device_token),
            last_seen_at=utcnow(),
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        return {"device_id": device.id, "device_token": device_token, "name": device.name}

    @app.get("/api/v1/devices")
    def list_devices(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
        devices = db.scalars(
            select(Device)
            .where(Device.user_id == user.id, Device.revoked_at.is_(None))
            .order_by(Device.name)
        ).all()
        return [
            {
                "id": device.id,
                "name": device.name,
                "platform": device.platform,
                "online": manager.agent_online(device.id),
                "last_seen_at": iso(device.last_seen_at),
            }
            for device in devices
        ]

    @app.post("/api/v1/devices/heartbeat")
    def device_heartbeat(
        payload: DeviceHeartbeat,
        request: Request,
        db: Session = Depends(get_db),
    ) -> dict[str, str]:
        token = request.headers.get("X-Device-Token")
        if not token:
            raise HTTPException(status_code=401, detail="X-Device-Token required")
        device = get_device_by_token(db, token)
        device.last_seen_at = utcnow()
        db.commit()
        return {"status": payload.status}

    @app.delete("/api/v1/devices/{device_id}")
    async def revoke_device(
        device_id: str,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> dict[str, str]:
        device = get_owned_device(db, device_id, user.id)
        device.revoked_at = utcnow()
        for remote_session in db.scalars(
            select(RemoteSession).where(
                RemoteSession.device_id == device.id,
                RemoteSession.status == SessionStatus.ACTIVE,
            )
        ).all():
            remote_session.status = SessionStatus.REVOKED
            remote_session.ended_at = utcnow()
            await manager.forward(
                remote_session.id,
                "controller",
                {"type": SignalType.SESSION_REVOKED, "session_id": remote_session.id, "payload": {}},
            )
        db.commit()
        return {"status": "revoked"}

    @app.post("/api/v1/sessions", response_model=SessionResponse)
    async def create_session(
        payload: SessionCreate,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> SessionResponse:
        device = get_owned_device(db, payload.device_id, user.id)
        pairing_code = f"{secrets.randbelow(1000):03d}-{secrets.randbelow(1000):03d}"
        remote_session = RemoteSession(
            device_id=device.id,
            controller_user_id=user.id,
            status=(
                SessionStatus.AWAITING_APPROVAL
                if manager.agent_online(device.id)
                else SessionStatus.PENDING
            ),
            pairing_hash=sha256_hex(pairing_code),
            expires_at=utcnow() + timedelta(seconds=payload.expires_in_seconds),
        )
        db.add(remote_session)
        db.flush()
        audit(db, "session_created", remote_session.id, user.id, {"device_id": device.id})
        db.commit()
        await manager.send_to_agent(
            device.id,
            {
                "type": "session_request",
                "session_id": remote_session.id,
                "payload": {
                    "pairing_code": pairing_code,
                    "controller": user.email,
                    "agent_signal_token": issue_signaling_token(device.id, remote_session.id, "agent", settings),
                    "expires_at": iso(remote_session.expires_at),
                },
            },
        )
        return SessionResponse(
            id=remote_session.id,
            device_id=device.id,
            status=remote_session.status,
            pairing_code=pairing_code,
            signaling_token=issue_signaling_token(user.id, remote_session.id, "controller", settings),
            expires_at=iso(remote_session.expires_at) or "",
        )

    @app.post("/api/v1/sessions/pair", response_model=SessionResponse)
    def claim_pairing_code(
        payload: PairingClaim,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> SessionResponse:
        remote_session = db.scalar(
            select(RemoteSession).where(
                RemoteSession.pairing_hash == sha256_hex(payload.pairing_code),
                RemoteSession.status.in_([SessionStatus.PENDING, SessionStatus.AWAITING_APPROVAL]),
            )
        )
        if not remote_session or ensure_utc(remote_session.expires_at) < utcnow():
            raise HTTPException(status_code=404, detail="Pairing code is invalid or expired")
        device = db.get(Device, remote_session.device_id)
        # Pairing is one-time: replace the stored digest after a successful claim.
        remote_session.pairing_hash = sha256_hex(secrets.token_urlsafe(32))
        remote_session.controller_user_id = user.id
        audit(db, "pairing_claimed", remote_session.id, user.id)
        db.commit()
        return SessionResponse(
            id=remote_session.id,
            device_id=remote_session.device_id,
            device_name=device.name,
            status=remote_session.status,
            signaling_token=issue_signaling_token(user.id, remote_session.id, "controller", settings),
            expires_at=iso(remote_session.expires_at) or "",
        )

    @app.post("/api/v1/guest/sessions/pair", response_model=SessionResponse)
    async def claim_attended_pairing_code(
        payload: PairingClaim,
        db: Session = Depends(get_db),
    ) -> SessionResponse:
        pairing = db.scalar(
            select(PairingCode).where(
                PairingCode.code_hash == sha256_hex(payload.pairing_code),
                PairingCode.used_at.is_(None),
            )
        )
        if not pairing or ensure_utc(pairing.expires_at) < utcnow():
            raise HTTPException(status_code=404, detail="Pairing code is invalid or expired")
        device = db.get(Device, pairing.device_id)
        if not device or device.revoked_at:
            raise HTTPException(status_code=404, detail="Remote device is unavailable")

        pairing.used_at = utcnow()
        controller = get_attended_user(db)
        remote_session = RemoteSession(
            device_id=device.id,
            controller_user_id=controller.id,
            status=(
                SessionStatus.AWAITING_APPROVAL
                if manager.agent_online(device.id)
                else SessionStatus.PENDING
            ),
            pairing_hash=sha256_hex(secrets.token_urlsafe(32)),
            expires_at=utcnow() + timedelta(seconds=600),
        )
        db.add(remote_session)
        db.flush()
        audit(db, "attended_session_created", remote_session.id, None, {"device_id": device.id})
        db.commit()
        await manager.send_to_agent(
            device.id,
            {
                "type": "session_request",
                "session_id": remote_session.id,
                "payload": {
                    "pairing_code": payload.pairing_code,
                    "controller": "RemoteX controller",
                    "agent_signal_token": issue_signaling_token(device.id, remote_session.id, "agent", settings),
                    "expires_at": iso(remote_session.expires_at),
                },
            },
        )
        return SessionResponse(
            id=remote_session.id,
            device_id=device.id,
            device_name=device.name,
            status=remote_session.status,
            signaling_token=issue_signaling_token(controller.id, remote_session.id, "controller", settings),
            expires_at=iso(remote_session.expires_at) or "",
        )

    @app.post("/api/v1/sessions/{session_id}/approve")
    async def approve_session(session_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
        token = request.headers.get("X-Device-Token")
        if not token:
            raise HTTPException(status_code=401, detail="X-Device-Token required")
        device = get_device_by_token(db, token)
        remote_session = get_session_or_404(db, session_id)
        if remote_session.device_id != device.id:
            raise HTTPException(status_code=403, detail="Session access denied")
        remote_session.status = SessionStatus.ACTIVE
        remote_session.approved_at = utcnow()
        audit(db, "session_approved", session_id, device.id)
        db.commit()
        await manager.forward(session_id, "agent", {"type": SignalType.SESSION_APPROVED, "session_id": session_id, "payload": {}})
        return {"status": "approved"}

    @app.post("/api/v1/sessions/{session_id}/reject")
    async def reject_session(session_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
        token = request.headers.get("X-Device-Token")
        if not token:
            raise HTTPException(status_code=401, detail="X-Device-Token required")
        device = get_device_by_token(db, token)
        remote_session = get_session_or_404(db, session_id)
        if remote_session.device_id != device.id:
            raise HTTPException(status_code=403, detail="Session access denied")
        remote_session.status = SessionStatus.REJECTED
        remote_session.ended_at = utcnow()
        audit(db, "session_rejected", session_id, device.id)
        db.commit()
        await manager.forward(session_id, "agent", {"type": SignalType.SESSION_REJECTED, "session_id": session_id, "payload": {}})
        return {"status": "rejected"}

    def authorize_controller_session(request: Request, session_id: str, db: Session) -> RemoteSession:
        remote_session = get_session_or_404(db, session_id)
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            user = decode_user_token(authorization[7:].strip(), settings, db)
            if remote_session.controller_user_id != user.id:
                raise HTTPException(status_code=403, detail="Session access denied")
            return remote_session
        session_token = request.headers.get("X-Session-Token")
        if not session_token:
            raise HTTPException(status_code=401, detail="Session is not authorized")
        subject = decode_signaling_token(session_token, session_id, "controller", settings)
        if subject != remote_session.controller_user_id:
            raise HTTPException(status_code=403, detail="Session access denied")
        return remote_session

    @app.get("/api/v1/sessions/{session_id}", response_model=SessionResponse)
    def get_session(session_id: str, request: Request, db: Session = Depends(get_db)) -> SessionResponse:
        remote_session = authorize_controller_session(request, session_id, db)
        device = db.get(Device, remote_session.device_id)
        return SessionResponse(
            id=remote_session.id,
            device_id=remote_session.device_id,
            device_name=device.name,
            status=remote_session.status,
            expires_at=iso(remote_session.expires_at) or "",
        )

    @app.post("/api/v1/sessions/{session_id}/revoke")
    async def revoke_session(
        session_id: str,
        request: Request,
        db: Session = Depends(get_db),
    ) -> dict[str, str]:
        remote_session = authorize_controller_session(request, session_id, db)
        remote_session.status = SessionStatus.REVOKED
        remote_session.ended_at = utcnow()
        audit(db, "session_revoked", session_id, remote_session.controller_user_id)
        db.commit()
        message = {"type": SignalType.SESSION_REVOKED, "session_id": session_id, "payload": {}}
        await manager.forward(session_id, "controller", message)
        await manager.send_to_agent(remote_session.device_id, message)
        return {"status": "revoked"}

    @app.websocket("/api/v1/agent/connect")
    async def agent_connect(websocket: WebSocket, device_token: str) -> None:
        await websocket.accept()
        db = make_session_factory(settings)()
        device_id: str | None = None
        try:
            device = get_device_by_token(db, device_token)
            device_id = device.id
            await manager.set_agent(device.id, websocket)
            device.last_seen_at = utcnow()
            db.commit()
            pending = db.scalars(
                select(RemoteSession).where(
                    RemoteSession.device_id == device.id,
                    RemoteSession.status.in_([SessionStatus.PENDING, SessionStatus.AWAITING_APPROVAL]),
                )
            ).all()
            for remote_session in pending:
                await websocket.send_json(
                    {
                        "type": "session_request",
                        "session_id": remote_session.id,
                        "payload": {
                            "expires_at": iso(remote_session.expires_at),
                            "agent_signal_token": issue_signaling_token(device.id, remote_session.id, "agent", settings),
                        },
                    }
                )
            while True:
                message = SignalEnvelope.model_validate(await websocket.receive_json())
                remote_session = db.get(RemoteSession, message.session_id)
                if message.type == SignalType.HEARTBEAT:
                    device.last_seen_at = utcnow()
                    db.commit()
                elif message.type == SignalType.SESSION_APPROVED:
                    if not remote_session or remote_session.device_id != device.id:
                        continue
                    remote_session.status = SessionStatus.ACTIVE
                    remote_session.approved_at = utcnow()
                    audit(db, "session_approved", remote_session.id, device.id)
                    db.commit()
                    await manager.forward(remote_session.id, "agent", message.model_dump(mode="json"))
                elif message.type == SignalType.SESSION_REJECTED:
                    if not remote_session or remote_session.device_id != device.id:
                        continue
                    remote_session.status = SessionStatus.REJECTED
                    remote_session.ended_at = utcnow()
                    audit(db, "session_rejected", remote_session.id, device.id)
                    db.commit()
                    await manager.forward(remote_session.id, "agent", message.model_dump(mode="json"))
                elif message.type == SignalType.SESSION_ENDED:
                    if remote_session and remote_session.device_id == device.id:
                        remote_session.status = SessionStatus.ENDED
                        remote_session.ended_at = utcnow()
                        db.commit()
                        await manager.forward(remote_session.id, "agent", message.model_dump(mode="json"))
        except (WebSocketDisconnect, HTTPException):
            pass
        finally:
            if device_id:
                await manager.remove_agent(device_id, websocket)
            db.close()

    @app.websocket("/api/v1/signaling/{session_id}")
    async def signaling(websocket: WebSocket, session_id: str, role: str, token: str) -> None:
        db = make_session_factory(settings)()
        try:
            remote_session = get_session_or_404(db, session_id)
            if role == "controller":
                subject = decode_signaling_token(token, session_id, role, settings)
                if subject != remote_session.controller_user_id:
                    raise HTTPException(status_code=403, detail="Session access denied")
            elif role == "agent":
                subject = decode_signaling_token(token, session_id, role, settings)
                if subject != remote_session.device_id:
                    raise HTTPException(status_code=403, detail="Session access denied")
            else:
                raise HTTPException(status_code=400, detail="Invalid signaling role")
            await websocket.accept()
            await manager.add_session(session_id, role, websocket)
            while True:
                message = SignalEnvelope.model_validate(await websocket.receive_json())
                if message.session_id == session_id:
                    await manager.forward(session_id, role, message.model_dump(mode="json"))
        except (WebSocketDisconnect, HTTPException):
            pass
        finally:
            await manager.remove_session(session_id, role, websocket)
            db.close()

    return app


def run_server() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


app = create_app()
