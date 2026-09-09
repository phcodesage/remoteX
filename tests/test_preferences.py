from common.preferences import AppPreferences, load_preferences, save_preferences


def test_preferences_normalize_server_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REMOTEX_SETTINGS_FILE", str(tmp_path / "preferences.json"))
    preferences = AppPreferences(
        server_url="https://remotex.chat-x.site/",
    )
    save_preferences(preferences)
    loaded = load_preferences()
    assert loaded.server_url == "https://remotex.chat-x.site"
    assert loaded.effective_server_url == "https://remotex.chat-x.site"


def test_remote_preferences_use_tunnel(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REMOTEX_SETTINGS_FILE", str(tmp_path / "preferences.json"))
    save_preferences(AppPreferences(server_url="https://control.example.com"))
    assert load_preferences().effective_server_url == "https://control.example.com"


def test_default_server_url_uses_tunnel(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REMOTEX_SETTINGS_FILE", str(tmp_path / "preferences.json"))
    monkeypatch.delenv("REMOTE_SERVER_URL", raising=False)
    assert load_preferences().effective_server_url == "https://remotex.chat-x.site"
