from server.config import Settings


def test_cloudflare_turn_configuration_is_published_as_ice_servers() -> None:
    settings = Settings(
        stun_urls="stun:stun.cloudflare.com:3478",
        turn_urls="turn:turn.example.com:3478,turns:turn.example.com:5349",
        turn_username="temporary-user",
        turn_credential="temporary-secret",
    )
    servers = settings.ice_servers()
    assert servers[0]["urls"] == ["stun:stun.cloudflare.com:3478"]
    assert servers[1]["urls"] == ["turn:turn.example.com:3478", "turns:turn.example.com:5349"]
    assert servers[1]["username"] == "temporary-user"

