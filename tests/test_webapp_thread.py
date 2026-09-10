"""
Tests for WebAppThreadManager.from_config() — the env-gated TLS decision for
the Wi-Fi upload portal. No real Uvicorn socket is opened (the server is
constructed but never run), so this stays offline like the rest of the suite.

TLS is enabled only when WIFI_TLS_CERTFILE and WIFI_TLS_KEYFILE both point at
files that exist on disk; anything else falls back to plain HTTP so a
zero-setup `make run-sim` still serves the portal.
"""
from managers.webapp_thread import WebAppThreadManager, wifi_portal_url


def _write(path, text="x"):
    path.write_text(text)
    return str(path)


class TestFromConfig:
    def test_tls_enabled_when_cert_and_key_exist(self, tmp_path, monkeypatch):
        certfile = _write(tmp_path / "cert.pem")
        keyfile = _write(tmp_path / "key.pem")
        monkeypatch.setenv("WIFI_TLS_CERTFILE", certfile)
        monkeypatch.setenv("WIFI_TLS_KEYFILE", keyfile)

        manager = WebAppThreadManager.from_config()

        assert manager.tls_enabled is True
        assert manager.server.config.ssl_certfile == certfile
        assert manager.server.config.ssl_keyfile == keyfile

    def test_plain_http_when_cert_missing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("WIFI_TLS_CERTFILE", str(tmp_path / "nope-cert.pem"))
        monkeypatch.setenv("WIFI_TLS_KEYFILE", str(tmp_path / "nope-key.pem"))

        manager = WebAppThreadManager.from_config()

        assert manager.tls_enabled is False
        assert manager.server.config.ssl_certfile is None
        assert "plain HTTP" in capsys.readouterr().out

    def test_plain_http_when_only_key_present(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WIFI_TLS_CERTFILE", str(tmp_path / "missing-cert.pem"))
        monkeypatch.setenv("WIFI_TLS_KEYFILE", _write(tmp_path / "key.pem"))

        manager = WebAppThreadManager.from_config()

        assert manager.tls_enabled is False

    def test_default_paths_used_when_env_unset(self, tmp_path, monkeypatch):
        # Unset both keys: from_config() falls back to the documented default
        # paths (certs/cert.pem, certs/key.pem). Those don't exist under a
        # fresh tmp cwd, so TLS stays off — no crash, no env required.
        monkeypatch.delenv("WIFI_TLS_CERTFILE", raising=False)
        monkeypatch.delenv("WIFI_TLS_KEYFILE", raising=False)
        monkeypatch.chdir(tmp_path)

        manager = WebAppThreadManager.from_config()

        assert manager.tls_enabled is False


class TestWifiPortalUrl:
    def test_explicit_tls_flag_wins_over_files(self, tmp_path, monkeypatch):
        # tls= is the running server's actual state; it must not be second-guessed
        # against the filesystem (the two could disagree if a cert is added/removed
        # after boot).
        monkeypatch.setenv("WIFI_TLS_CERTFILE", str(tmp_path / "absent.pem"))
        monkeypatch.setenv("WIFI_TLS_KEYFILE", str(tmp_path / "absent.pem"))
        assert wifi_portal_url(host="10.0.0.5", tls=True) == "https://10.0.0.5:8000/upload"
        assert wifi_portal_url(host="10.0.0.5", tls=False) == "http://10.0.0.5:8000/upload"

    def test_scheme_inferred_from_files_when_flag_omitted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WIFI_TLS_CERTFILE", _write(tmp_path / "cert.pem"))
        monkeypatch.setenv("WIFI_TLS_KEYFILE", _write(tmp_path / "key.pem"))
        assert wifi_portal_url(host="10.0.0.5") == "https://10.0.0.5:8000/upload"

        monkeypatch.setenv("WIFI_TLS_CERTFILE", str(tmp_path / "gone.pem"))
        assert wifi_portal_url(host="10.0.0.5") == "http://10.0.0.5:8000/upload"

    def test_resolves_a_host_when_none_given(self, tmp_path, monkeypatch):
        url = wifi_portal_url(tls=False)
        assert url.startswith("http://") and url.endswith(":8000/upload")
