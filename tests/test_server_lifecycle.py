from __future__ import annotations

from fastapi.testclient import TestClient

from server.app import create_app
from server.config import Settings


def test_auth_device_pairing_and_approval(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'remote.sqlite3'}",
        jwt_secret="test-secret-with-at-least-32-bytes-long",
    )
    with TestClient(create_app(settings)) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "smoke@example.com", "password": "password-123"},
        )
        assert registered.status_code == 200
        auth = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        device_response = client.post(
            "/api/v1/devices/register",
            headers=auth,
            json={"name": "Test Mac", "platform": "Darwin", "public_key": "x" * 32},
        )
        assert device_response.status_code == 200
        device = device_response.json()

        session_response = client.post(
            "/api/v1/sessions", headers=auth, json={"device_id": device["device_id"]}
        )
        assert session_response.status_code == 200
        session = session_response.json()
        assert session["status"] == "pending"

        claimed = client.post(
            "/api/v1/sessions/pair",
            headers=auth,
            json={"pairing_code": session["pairing_code"]},
        )
        assert claimed.status_code == 200

        approved = client.post(
            f"/api/v1/sessions/{session['id']}/approve",
            headers={"X-Device-Token": device["device_token"]},
        )
        assert approved.status_code == 200
        current = client.get(f"/api/v1/sessions/{session['id']}", headers=auth)
        assert current.json()["status"] == "active"

