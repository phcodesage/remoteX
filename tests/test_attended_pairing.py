from fastapi.testclient import TestClient

from server.app import create_app
from server.config import Settings


def test_attended_pairing_requires_no_user_token(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'attended.sqlite3'}",
        jwt_secret="test-secret-with-at-least-32-bytes-long",
    )
    with TestClient(create_app(settings)) as client:
        registered = client.post(
            "/api/v1/guest/devices/register",
            json={"name": "Remote Mac", "platform": "Darwin", "public_key": "x" * 32},
        )
        assert registered.status_code == 200
        host = registered.json()

        paired = client.post(
            "/api/v1/guest/sessions/pair",
            json={"pairing_code": host["pairing_code"].replace("-", "")},
        )
        assert paired.status_code == 200
        session = paired.json()
        assert session["device_name"] == "Remote Mac"
        assert session["pairing_code"] == host["pairing_code"]
        assert session["signaling_token"]

        current = client.get(
            f"/api/v1/sessions/{session['id']}",
            headers={"X-Session-Token": session["signaling_token"]},
        )
        assert current.status_code == 200

        approved = client.post(
            f"/api/v1/sessions/{session['id']}/approve",
            headers={"X-Device-Token": host["device_token"]},
        )
        assert approved.status_code == 200
        assert client.get(
            f"/api/v1/sessions/{session['id']}",
            headers={"X-Session-Token": session["signaling_token"]},
        ).json()["status"] == "active"


def test_attended_registration_recovers_stale_device_token(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'recovery.sqlite3'}",
        jwt_secret="test-secret-with-at-least-32-bytes-long",
    )
    with TestClient(create_app(settings)) as client:
        first = client.post(
            "/api/v1/guest/devices/register",
            json={"name": "Remote Mac", "platform": "Darwin", "public_key": "y" * 32},
        )
        assert first.status_code == 200
        first_payload = first.json()

        recovered = client.post(
            "/api/v1/guest/devices/register",
            json={"name": "Remote Mac", "platform": "Darwin", "public_key": "y" * 32},
        )
        assert recovered.status_code == 200
        recovered_payload = recovered.json()
        assert recovered_payload["device_id"] == first_payload["device_id"]
        assert recovered_payload["device_token"] != first_payload["device_token"]

        refreshed = client.post(
            "/api/v1/guest/devices/pairing",
            headers={"X-Device-Token": recovered_payload["device_token"]},
        )
        assert refreshed.status_code == 200
