"""
Tests for ScannerManager / SimScanner / SaneAirscanScanner — pure logic, no
real hardware, QThread, or subprocess call involved. managers/scanner_thread.py
(the QThread-facing wrapper used by the live scanner screen) is exercised
manually via make run-sim, not unit-tested here.
"""
import os
import subprocess

import fitz
import pytest

from managers.scanner import SaneAirscanScanner, ScannerError, SimScanner
from managers.scanner_manager import ScannerManager


def _manager(tmp_path, page_count=5):
    scanner = SimScanner(str(tmp_path / "sim_pages"), page_count=page_count)
    return ScannerManager(scanner=scanner, dpi=100), scanner


class TestSimScanner:
    def test_seeds_exact_page_count(self, tmp_path):
        sim_dir = tmp_path / "sim_pages"
        SimScanner(str(sim_dir), page_count=4)
        seeded = [f for f in os.listdir(sim_dir) if f.lower().endswith(".png")]
        assert len(seeded) == 4

    def test_cycles_through_canned_pages(self, tmp_path):
        scanner = SimScanner(str(tmp_path / "sim_pages"), page_count=3)
        paths = [scanner.scan_page(dpi=100) for _ in range(6)]
        # Every call returns a fresh path...
        assert len(set(paths)) == 6
        # ...but the underlying content repeats every page_count calls.
        contents = [open(p, "rb").read() for p in paths]
        assert contents[0] == contents[3]
        assert contents[1] == contents[4]
        assert contents[2] == contents[5]

    def test_is_available_always_true(self, tmp_path):
        scanner = SimScanner(str(tmp_path / "sim_pages"))
        assert scanner.is_available() is True


class TestScannerManagerCapture:
    def test_scan_page_auto_starts_session(self, tmp_path):
        manager, _ = _manager(tmp_path)
        result = manager.scan_page()
        assert result["page_number"] == 1
        assert manager.page_count() == 1

    def test_pages_accumulate_in_order(self, tmp_path):
        manager, _ = _manager(tmp_path)
        for expected_number in (1, 2, 3):
            result = manager.scan_page()
            assert result["page_number"] == expected_number
        assert manager.page_count() == 3

    def test_rescan_last_replaces_last_page(self, tmp_path):
        manager, _ = _manager(tmp_path)
        manager.scan_page()
        first_result = manager.scan_page()
        old_path = first_result["path"]

        rescanned = manager.rescan_last()

        assert manager.page_count() == 2
        assert rescanned["page_number"] == 2
        assert rescanned["path"] != old_path
        assert not os.path.exists(old_path)

    def test_rescan_last_with_no_pages_raises(self, tmp_path):
        manager, _ = _manager(tmp_path)
        manager.start_session()
        with pytest.raises(ScannerError):
            manager.rescan_last()

    def test_cancel_deletes_all_page_files(self, tmp_path):
        manager, _ = _manager(tmp_path)
        manager.scan_page()
        page_path = manager.scan_page()["path"]

        manager.cancel()

        assert manager.page_count() == 0
        assert not os.path.exists(page_path)

    def test_start_session_discards_previous_leftovers(self, tmp_path):
        manager, _ = _manager(tmp_path)
        stale_path = manager.scan_page()["path"]

        manager.start_session()

        assert manager.page_count() == 0
        assert not os.path.exists(stale_path)


class TestScannerManagerFinish:
    def test_finish_combines_pages_into_pdf_with_exact_page_count(self, tmp_path):
        manager, _ = _manager(tmp_path)
        for _ in range(3):
            manager.scan_page()

        result = manager.finish()

        doc = fitz.open(result["pdf_path"])
        assert len(doc) == 3
        doc.close()
        assert result["page_count"] == 3

    def test_finish_with_no_pages_raises(self, tmp_path):
        manager, _ = _manager(tmp_path)
        manager.start_session()
        with pytest.raises(ScannerError):
            manager.finish()

    def test_finish_clears_pages_and_deletes_source_images(self, tmp_path):
        manager, _ = _manager(tmp_path)
        page_paths = [manager.scan_page()["path"] for _ in range(2)]

        manager.finish()

        assert manager.page_count() == 0
        for path in page_paths:
            assert not os.path.exists(path)


class TestSaneAirscanScanner:
    def test_scan_page_raises_immediately_with_no_device_configured(self):
        scanner = SaneAirscanScanner(device="", timeout=5)
        with pytest.raises(ScannerError):
            scanner.scan_page(dpi=200)

    def test_is_available_false_with_no_device_configured(self):
        scanner = SaneAirscanScanner(device="", timeout=5)
        assert scanner.is_available() is False

    def test_scan_page_maps_missing_scanimage_binary(self, monkeypatch):
        scanner = SaneAirscanScanner(device="airscan:e0:Test Scanner", timeout=5)

        def fake_run(*args, **kwargs):
            raise FileNotFoundError("scanimage not found")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(ScannerError, match="scanimage"):
            scanner.scan_page(dpi=200)

    def test_scan_page_maps_timeout(self, monkeypatch):
        scanner = SaneAirscanScanner(device="airscan:e0:Test Scanner", timeout=5)

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="scanimage", timeout=5)

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(ScannerError, match="timed out"):
            scanner.scan_page(dpi=200)

    def test_scan_page_maps_called_process_error(self, monkeypatch):
        scanner = SaneAirscanScanner(device="airscan:e0:Test Scanner", timeout=5)

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(returncode=1, cmd="scanimage", stderr=b"no such device")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(ScannerError, match="no such device"):
            scanner.scan_page(dpi=200)
