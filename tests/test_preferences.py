from common.preferences import AppPreferences, load_preferences, save_preferences


def test_host_preferences_use_local_port(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REMOTEX_SETTINGS_FILE", str(tmp_path / "preferences.json"))
    preferences = AppPreferences(
        server_url="https://remotex.chat-x.site/",
        host_mode=True,
        host_port=8080,
    )
    save_preferences(preferences)
    loaded = load_preferences()
    assert loaded.server_url == "https://remotex.chat-x.site"
    assert loaded.effective_server_url == "http://127.0.0.1:8080"


def test_remote_preferences_use_tunnel(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REMOTEX_SETTINGS_FILE", str(tmp_path / "preferences.json"))
    save_preferences(AppPreferences(server_url="https://control.example.com", host_mode=False))
    assert load_preferences().effective_server_url == "https://control.example.com"


def test_env_can_enable_host_before_ui_starts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REMOTEX_SETTINGS_FILE", str(tmp_path / "preferences.json"))
    monkeypatch.setenv("REMOTE_HOST_MODE", "true")
    monkeypatch.setenv("REMOTE_HOST_PORT", "8080")
    assert load_preferences().effective_server_url == "http://127.0.0.1:8080"
