"""
Tests for scripts/setup_hotspot.py — the .env-driven hotspot setup (ADR 0007,
issue #29). Everything here runs offline: files are rendered and written under
a tmp "root", and no command is ever run.

What only the Pi can show (hostapd on a real radio, ap_isolate, phones) is out
of scope; tests/hotspot_container/ checks the firewall and dnsmasq for real
inside a Linux container.
"""
import datetime
import importlib.util
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import get_config

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "setup_hotspot.py"
_spec = importlib.util.spec_from_file_location("setup_hotspot", _SCRIPT)
hs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hs)

HOTSPOT_KEYS = [
    "KIOSK_ID", "WIFI_HOTSPOT_ENABLED", "WIFI_HOTSPOT_INTERFACE", "WIFI_HOTSPOT_SSID",
    "WIFI_HOTSPOT_COUNTRY", "WIFI_HOTSPOT_CHANNEL", "WIFI_HOTSPOT_ADDRESS",
    "PORTAL_HOSTNAME", "WIFI_PORTAL_PORT", "ADMIN_DASHBOARD_PORT",
]


def _config(**overrides):
    values = dict(
        wifi_hotspot_enabled=True,
        wifi_hotspot_interface="wlan0",
        wifi_hotspot_ssid="AIO-SPARK",
        wifi_hotspot_country="PH",
        wifi_hotspot_channel=6,
        wifi_hotspot_address="10.3.141.1/24",
        portal_hostname="print.aio-spark.example",
        wifi_portal_port=8000,
        admin_dashboard_port=8100,
        kiosk_id="kiosk-01",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _settings(**overrides):
    return hs.HotspotSettings.from_config(_config(**overrides))


def _lines(text):
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


def _runs(actions):
    return [a.argv for a in actions if isinstance(a, hs.Run)]


def _writes(actions):
    return {a.path for a in actions if isinstance(a, hs.Write)}


class TestSettings:
    def test_defaults_from_real_config_are_valid(self, monkeypatch):
        for key in HOTSPOT_KEYS:
            monkeypatch.delenv(key, raising=False)

        s = hs.HotspotSettings.from_config(get_config())

        assert s.enabled is False  # unset means off: never switch a radio on by accident
        assert s.interface == "wlan0"
        assert str(s.address) == "10.3.141.1/24"
        assert s.portal_port == 8000
        assert s.portal_hostname == "print.aio-spark.example"

    def test_env_values_reach_settings(self, monkeypatch):
        monkeypatch.setenv("WIFI_HOTSPOT_ENABLED", "true")
        monkeypatch.setenv("WIFI_HOTSPOT_ADDRESS", "192.168.77.1/24")
        monkeypatch.setenv("WIFI_HOTSPOT_COUNTRY", "ph")
        monkeypatch.setenv("WIFI_PORTAL_PORT", "8443")

        s = hs.HotspotSettings.from_config(get_config())

        assert s.enabled is True
        assert str(s.address.ip) == "192.168.77.1"
        assert s.country == "PH"
        assert s.portal_port == 8443

    @pytest.mark.parametrize("overrides, fragment", [
        (dict(wifi_hotspot_address="nonsense"), "WIFI_HOTSPOT_ADDRESS"),
        (dict(wifi_hotspot_address="8.8.8.1/24"), "private"),
        (dict(wifi_hotspot_address="10.3.141.5/24"), "first host"),
        (dict(wifi_hotspot_address="10.3.141.1/30"), "/16 to /29"),
        (dict(wifi_hotspot_ssid=""), "WIFI_HOTSPOT_SSID"),
        (dict(wifi_hotspot_ssid="x" * 33), "WIFI_HOTSPOT_SSID"),
        (dict(wifi_hotspot_ssid="bad\nssid"), "WIFI_HOTSPOT_SSID"),
        (dict(wifi_hotspot_country="PHL"), "WIFI_HOTSPOT_COUNTRY"),
        (dict(wifi_hotspot_channel=36), "WIFI_HOTSPOT_CHANNEL"),
        (dict(wifi_hotspot_interface="wlan0; rm -rf /"), "WIFI_HOTSPOT_INTERFACE"),
        (dict(portal_hostname="not a host"), "PORTAL_HOSTNAME"),
        (dict(wifi_portal_port=22), "SSH"),
        (dict(wifi_portal_port=8100), "Admin Dashboard"),
        (dict(kiosk_id="Kiosk One"), "KIOSK_ID"),
    ])
    def test_rejects_bad_values(self, overrides, fragment):
        with pytest.raises(hs.SettingsError, match=fragment):
            _settings(**overrides)

    def test_reports_every_problem_at_once(self):
        with pytest.raises(hs.SettingsError) as exc:
            _settings(wifi_hotspot_channel=99, wifi_portal_port=8100, wifi_hotspot_country="x")
        message = str(exc.value)
        assert "CHANNEL" in message and "PORTAL_PORT" in message and "COUNTRY" in message

    def test_blank_kiosk_id_is_allowed(self):
        assert _settings(kiosk_id="").kiosk_id == ""

    def test_dhcp_range_skips_the_pi(self):
        start, end = _settings().dhcp_range
        assert (str(start), str(end)) == ("10.3.141.2", "10.3.141.254")


class TestHostapd:
    def test_open_network_with_client_isolation(self):
        lines = _lines(hs.render_hostapd(_settings()))
        assert "ap_isolate=1" in lines
        assert "interface=wlan0" in lines
        assert "country_code=PH" in lines
        assert "channel=6" in lines
        assert not any(line.startswith(("wpa", "rsn_", "wep_")) for line in lines)

    def test_ssid_with_quotes_stays_one_value(self):
        text = hs.render_hostapd(_settings(wifi_hotspot_ssid='Joe\'s "Print"'))
        assert 'ssid2=P"Joe\'s \\"Print\\""' in text

    def test_marked_as_managed(self):
        assert hs.MARKER in hs.render_hostapd(_settings())


class TestDnsmasq:
    def test_answers_portal_name_and_nothing_upstream(self):
        lines = _lines(hs.render_dnsmasq(_settings()))
        assert "host-record=print.aio-spark.example,10.3.141.1" in lines
        assert "no-resolv" in lines
        assert not any(line.startswith("server=") for line in lines)

    def test_serves_only_the_hotspot_interface(self):
        lines = _lines(hs.render_dnsmasq(_settings(wifi_hotspot_interface="wlan1")))
        assert "interface=wlan1" in lines
        assert "except-interface=lo" in lines

    def test_dhcp_range_and_options(self):
        lines = _lines(hs.render_dnsmasq(_settings(wifi_hotspot_address="192.168.50.1/26")))
        assert "dhcp-range=192.168.50.2,192.168.50.62,255.255.255.192,1h" in lines
        assert "dhcp-option=option:dns-server,192.168.50.1" in lines


class TestFirewall:
    def test_allows_only_dhcp_dns_and_portal(self):
        text = hs.render_firewall(_settings(wifi_portal_port=8443))
        accepts = [line for line in _lines(text) if "dport" in line and "accept" in line]
        ports = sorted(line.split("dport")[1].split()[0] for line in accepts)
        assert ports == ["53", "53", "67", "8443"]
        assert "8100" not in text and "dport 22" not in text

    def test_drops_everything_else_on_the_hotspot_only(self):
        lines = _lines(hs.render_firewall(_settings()))
        assert 'iifname != "wlan0" accept' in lines
        assert any(line.startswith("counter drop") for line in lines)

    def test_no_forwarding_in_either_direction(self):
        lines = _lines(hs.render_firewall(_settings()))
        assert any(line.startswith('iifname "wlan0" counter drop') for line in lines)
        assert any(line.startswith('oifname "wlan0" counter drop') for line in lines)

    def test_only_touches_its_own_table(self):
        text = hs.render_firewall(_settings())
        assert "flush ruleset" not in text
        assert "delete table inet ssp_hotspot" in text


class TestPlanEnabled:
    def test_writes_every_hotspot_file(self, tmp_path):
        actions = hs.plan(_settings(), tmp_path)
        assert _writes(actions) == set(hs.HOTSPOT_FILES) | {hs.FIREWALL_NFT, hs.FIREWALL_UNIT}

    def test_installs_unmasks_then_enables(self, tmp_path):
        runs = _runs(hs.plan(_settings(), tmp_path))
        install = runs.index(("apt-get", "install", "-y", "--no-install-recommends", "hostapd", "dnsmasq", "nftables"))
        unmask = runs.index(("systemctl", "unmask", "hostapd.service"))
        enable = runs.index(("systemctl", "enable", "hostapd.service"))
        assert install < unmask < enable

    def test_firewall_is_up_before_the_hotspot_starts(self, tmp_path):
        runs = _runs(hs.plan(_settings(), tmp_path))
        firewall = runs.index(("systemctl", "restart", "ssp-hotspot-firewall.service"))
        assert firewall < runs.index(("systemctl", "restart", "hostapd.service"))
        assert firewall < runs.index(("systemctl", "restart", "dnsmasq.service"))

    def test_foreign_file_is_backed_up_before_being_replaced(self, tmp_path):
        foreign = tmp_path / hs.HOSTAPD_CONF
        foreign.parent.mkdir(parents=True)
        foreign.write_text("interface=wlan0\nwpa=2\n")

        actions = hs.plan(_settings(), tmp_path)

        backup = actions.index(hs.Backup(hs.HOSTAPD_CONF))
        write = next(i for i, a in enumerate(actions) if isinstance(a, hs.Write) and a.path == hs.HOSTAPD_CONF)
        assert backup < write

    def test_own_file_is_not_backed_up(self, tmp_path):
        own = tmp_path / hs.HOSTAPD_CONF
        own.parent.mkdir(parents=True)
        own.write_text(hs.render_hostapd(_settings()))

        assert hs.Backup(hs.HOSTAPD_CONF) not in hs.plan(_settings(), tmp_path)


class TestPlanDisabled:
    def test_disables_hotspot_but_keeps_firewall(self, tmp_path):
        actions = hs.plan(_settings(wifi_hotspot_enabled=False), tmp_path)
        runs = _runs(actions)

        assert _writes(actions) == {hs.FIREWALL_NFT, hs.FIREWALL_UNIT}
        assert ("systemctl", "disable", "--now", "hostapd.service") in runs
        assert ("systemctl", "disable", "--now", "dnsmasq.service") in runs
        assert ("systemctl", "restart", "ssp-hotspot-firewall.service") in runs
        assert not any(argv[:2] == ("systemctl", "enable") and "hostapd" in argv[-1] for argv in runs)

    def test_removes_hotspot_files_left_from_an_earlier_run(self, tmp_path):
        hs.apply(hs.plan(_settings(), tmp_path), tmp_path, run_commands=False)

        actions = hs.plan(_settings(wifi_hotspot_enabled=False), tmp_path)
        hs.apply(actions, tmp_path, run_commands=False)

        for path in hs.HOTSPOT_FILES:
            assert not (tmp_path / path).exists(), path
        assert (tmp_path / hs.FIREWALL_NFT).exists()


class TestRaspapCleanup:
    def _raspap_root(self, root):
        (root / "etc/raspap").mkdir(parents=True)
        dnsmasq_d = root / "etc/dnsmasq.d"
        dnsmasq_d.mkdir(parents=True)
        (dnsmasq_d / "090_raspap.conf").write_text("interface=wlan0\n")
        (dnsmasq_d / "090_wlan0.conf").write_text("dhcp-range=10.3.141.50,10.3.141.254\n")
        (dnsmasq_d / "README").write_text("unrelated\n")
        return root

    def test_nothing_to_clean_on_a_fresh_pi(self, tmp_path):
        actions = hs.plan(_settings(), tmp_path)
        assert not any("raspapd" in " ".join(argv) for argv in _runs(actions))

    def test_stops_raspap_and_moves_its_dnsmasq_files_aside(self, tmp_path):
        root = self._raspap_root(tmp_path)
        actions = hs.plan(_settings(), root, installed=lambda names: ["nodogsplash"])
        runs = _runs(actions)

        assert ("systemctl", "disable", "--now", "raspapd.service") in runs
        assert ("systemctl", "disable", "--now", "nodogsplash.service") in runs
        assert ("apt-get", "purge", "-y", "nodogsplash") in runs
        assert hs.Backup("etc/dnsmasq.d/090_raspap.conf") in actions
        assert hs.Backup("etc/dnsmasq.d/090_wlan0.conf") in actions
        assert hs.Backup("etc/dnsmasq.d/README") not in actions

    def test_cleanup_happens_before_the_new_hotspot_starts(self, tmp_path):
        root = self._raspap_root(tmp_path)
        runs = _runs(hs.plan(_settings(), root))
        assert runs.index(("systemctl", "disable", "--now", "raspapd.service")) < runs.index(
            ("systemctl", "restart", "hostapd.service"))

    def test_no_purge_when_packages_are_not_installed(self, tmp_path):
        root = self._raspap_root(tmp_path)
        runs = _runs(hs.plan(_settings(), root, installed=lambda names: []))
        assert not any(argv[:2] == ("apt-get", "purge") for argv in runs)


class TestApply:
    NOW = datetime.datetime(2026, 10, 7, 12, 0, 0)

    def test_writes_files_and_skips_commands_under_a_staging_root(self, tmp_path, capsys):
        hs.apply(hs.plan(_settings(), tmp_path), tmp_path, run_commands=False)

        assert hs.is_managed(tmp_path / hs.HOSTAPD_CONF)
        assert (tmp_path / hs.FIREWALL_NFT).read_text() == hs.render_firewall(_settings())
        assert "[skip] run     systemctl restart hostapd.service" in capsys.readouterr().out

    def test_dry_run_changes_nothing(self, tmp_path):
        hs.apply(hs.plan(_settings(), tmp_path), tmp_path, dry_run=True)
        assert list(tmp_path.iterdir()) == []

    def test_backup_moves_file_under_timestamped_dir(self, tmp_path):
        foreign = tmp_path / "etc/dnsmasq.d/090_raspap.conf"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("raspap\n")

        hs.apply([hs.Backup("etc/dnsmasq.d/090_raspap.conf")], tmp_path, now=self.NOW)

        assert not foreign.exists()
        moved = tmp_path / hs.BACKUP_DIR / "20261007-120000/etc/dnsmasq.d/090_raspap.conf"
        assert moved.read_text() == "raspap\n"

    def test_remove_leaves_files_it_did_not_write(self, tmp_path):
        foreign = tmp_path / hs.HOSTAPD_CONF
        foreign.parent.mkdir(parents=True)
        foreign.write_text("someone else's\n")

        hs.apply([hs.Remove(hs.HOSTAPD_CONF)], tmp_path)

        assert foreign.exists()


class TestMain:
    def test_staging_run_end_to_end(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # restored after the test; main() chdirs to the repo
        monkeypatch.setenv("WIFI_HOTSPOT_ENABLED", "true")
        monkeypatch.setenv("WIFI_HOTSPOT_SSID", "AIO-SPARK-TEST")
        monkeypatch.setenv("KIOSK_ID", "kiosk-01")
        stage = tmp_path / "stage"

        assert hs.main(["--root", str(stage)]) == 0

        assert "ssid2=P\"AIO-SPARK-TEST\"" in (stage / hs.HOSTAPD_CONF).read_text()

    def test_bad_env_exits_with_every_problem(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("WIFI_HOTSPOT_CHANNEL", "99")
        monkeypatch.setenv("WIFI_PORTAL_PORT", "22")

        assert hs.main(["--root", str(tmp_path / "stage")]) == 2

        err = capsys.readouterr().err
        assert "WIFI_HOTSPOT_CHANNEL" in err and "WIFI_PORTAL_PORT" in err
        assert not (tmp_path / "stage").exists()


def test_settings_are_immutable():
    s = _settings()
    assert replace(s, channel=11).channel == 11
    with pytest.raises(Exception):
        s.channel = 11
