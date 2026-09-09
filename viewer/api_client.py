from __future__ import annotations

import httpx


class ApiError(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""
        self.user_id = ""

    def _request(self, method: str, path: str, **kwargs):
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = httpx.request(method, self.base_url + path, headers=headers, timeout=15, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"Server unavailable: {exc}") from exc
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ApiError(str(detail))
        return response

    def authenticate(self, email: str, password: str, register: bool = False) -> None:
        response = self._request(
            "POST",
            "/api/v1/auth/register" if register else "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        payload = response.json()
        self.token, self.user_id = payload["access_token"], payload["user_id"]

    def local_authenticate(self) -> None:
        response = self._request("POST", "/api/v1/auth/local")
        payload = response.json()
        self.token, self.user_id = payload["access_token"], payload["user_id"]

    def devices(self) -> list[dict]:
        return self._request("GET", "/api/v1/devices").json()

    def create_session(self, device_id: str) -> dict:
        return self._request("POST", "/api/v1/sessions", json={"device_id": device_id}).json()

    def claim_pairing(self, pairing_code: str) -> dict:
        return self._request("POST", "/api/v1/sessions/pair", json={"pairing_code": pairing_code}).json()

    def session(self, session_id: str) -> dict:
        return self._request("GET", f"/api/v1/sessions/{session_id}").json()

    def revoke_session(self, session_id: str) -> None:
        self._request("POST", f"/api/v1/sessions/{session_id}/revoke")

    def ice_servers(self) -> list[dict]:
        return self._request("GET", "/api/v1/config/ice").json().get("ice_servers", [])
