from __future__ import annotations

import httpx
import re

from common.tls import trusted_tls_context


class ApiError(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""
        self.user_id = ""
        self.session_tokens: dict[str, str] = {}

    def _request(self, method: str, path: str, **kwargs):
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = httpx.request(
                method,
                self.base_url + path,
                headers=headers,
                timeout=15,
                verify=trusted_tls_context(self.base_url),
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ApiError(f"Server unavailable: {exc}") from exc
        if response.is_error:
            content_type = response.headers.get("content-type", "")
            if response.status_code in {502, 503, 504} and "text/html" in content_type:
                detail = (
                    f"The control server returned HTTP {response.status_code} at {self.base_url}. "
                    "Cloudflare reached the domain, but the tunnel cannot reach its origin. "
                    "On the host computer, run `python3 run.py backend` and verify that "
                    "the tunnel forwards to http://127.0.0.1:8080."
                )
            else:
                try:
                    detail = response.json().get("detail", response.text)
                except ValueError:
                    detail = response.text[:500] or f"HTTP {response.status_code}"
            if isinstance(detail, list):
                messages = [item.get("msg") for item in detail if isinstance(item, dict) and item.get("msg")]
                detail = messages[0] if messages else "The request was invalid"
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
        digits = re.sub(r"\D", "", pairing_code)
        if len(digits) == 6:
            pairing_code = f"{digits[:3]}-{digits[3:]}"
        session = self._request(
            "POST", "/api/v1/guest/sessions/pair", json={"pairing_code": pairing_code}
        ).json()
        if session.get("signaling_token"):
            self.session_tokens[session["id"]] = session["signaling_token"]
        return session

    def session(self, session_id: str) -> dict:
        headers = {}
        if session_id in self.session_tokens:
            headers["X-Session-Token"] = self.session_tokens[session_id]
        return self._request("GET", f"/api/v1/sessions/{session_id}", headers=headers).json()

    def revoke_session(self, session_id: str) -> None:
        headers = {}
        if session_id in self.session_tokens:
            headers["X-Session-Token"] = self.session_tokens[session_id]
        self._request("POST", f"/api/v1/sessions/{session_id}/revoke", headers=headers)

    def ice_servers(self) -> list[dict]:
        return self._request("GET", "/api/v1/config/ice").json().get("ice_servers", [])
