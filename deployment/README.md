# Deployment notes

Run FastAPI behind HTTPS/WSS, for example with Caddy and Cloudflare Tunnel:

```text
https://control.example.com  →  Cloudflare Tunnel  →  127.0.0.1:8000
```

Set `REMOTE_SERVER_URL=https://control.example.com` on both the agent and viewer.

Configure Cloudflare Realtime TURN with `REMOTE_CLOUDFLARE_TURN_KEY_ID` and `REMOTE_CLOUDFLARE_TURN_API_TOKEN`. FastAPI uses the private API token to request short-lived ICE credentials and exposes only the resulting `iceServers` at `/api/v1/config/ice`.

For a static local setup, populate `REMOTE_TURN_URLS`, `REMOTE_TURN_USERNAME`, and `REMOTE_TURN_CREDENTIAL` instead.

Cloudflare Tunnel is not a TURN relay. Keep the HTTPS/WSS route and the WebRTC ICE/TURN route conceptually separate. If the Cloudflare product/account in use does not provide TURN credentials, use a compatible managed TURN service or deploy coturn, then keep the same environment-variable interface.
