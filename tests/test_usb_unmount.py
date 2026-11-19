"""
After reading a USB drive the kiosk unmounts it, so a customer pulling it out
doesn't leave the FAT dirty bit set or a half-written sector behind (a test
card ended up unmountable that way). It used to unmount only when PDFs were
found, and said "safe to remove" without checking that umount worked.
"""
import os
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest  # noqa: E402

from managers import usb_file_manager  # noqa: E402
from managers.usb_file_manager import USBFileManager  # noqa: E402
from screens.usb.model import USBScreenModel  # noqa: E402

MOUNT = '/media/kiosk/CARD'
DEVICE = '/dev/sda1'


class FakeSystem:
    """Stands in for findmnt / udisksctl / umount on a Linux kiosk."""

    def __init__(self, udisksctl_ok=True, umount_ok=True, unmount_sticks=True):
        self.mounted = True
        self.udisksctl_ok = udisksctl_ok
        self.umount_ok = umount_ok
        self.unmount_sticks = unmount_sticks  # False: exit 0 but still mounted
        self.calls = []

    def run(self, cmd, **kwargs):
        self.calls.append(cmd[0])
        if cmd[0] == 'findmnt':
            return SimpleNamespace(returncode=0 if self.mounted else 1,
                                   stdout=DEVICE + '\n' if self.mounted else '', stderr='')
        ok = self.udisksctl_ok if cmd[0] == 'udisksctl' else self.umount_ok
        if ok and self.unmount_sticks:
            self.mounted = False
        return SimpleNamespace(returncode=0 if ok else 1, stdout='',
                               stderr='' if ok else f'{cmd[0]}: target is busy')


@pytest.fixture
def kiosk(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path / 'tmp'))
    monkeypatch.setenv('SIM_MODE', 'false')
    monkeypatch.setattr(usb_file_manager.platform, 'system', lambda: 'Linux')

    def install(**kwargs):
        system = FakeSystem(**kwargs)
        monkeypatch.setattr(subprocess, 'run', system.run)
        return system
    return install


def _drive(tmp_path, with_pdf):
    drive = tmp_path / 'drive'
    drive.mkdir(parents=True)
    (drive / ('notes.pdf' if with_pdf else 'notes.txt')).write_bytes(b'%PDF-1.4\n')
    return str(drive)


def test_unmounts_with_udisksctl(kiosk):
    system = kiosk()
    assert USBFileManager()._auto_eject_usb_drive(MOUNT) is True
    assert not system.mounted
    assert 'umount' not in system.calls


def test_falls_back_to_umount(kiosk):
    system = kiosk(udisksctl_ok=False)
    assert USBFileManager()._auto_eject_usb_drive(MOUNT) is True
    assert system.calls.count('umount') == 1


def test_reports_failure_when_both_fail(kiosk):
    kiosk(udisksctl_ok=False, umount_ok=False)
    assert USBFileManager()._auto_eject_usb_drive(MOUNT) is False


def test_exit_zero_but_still_mounted_is_a_failure(kiosk):
    kiosk(unmount_sticks=False)
    assert USBFileManager()._auto_eject_usb_drive(MOUNT) is False


def test_already_gone_counts_as_safe(kiosk):
    system = kiosk()
    system.mounted = False
    assert USBFileManager()._auto_eject_usb_drive(MOUNT) is True
    assert system.calls == ['findmnt']


def test_drive_without_pdfs_is_still_unmounted(kiosk, tmp_path):
    manager = USBFileManager()
    manager._auto_eject_usb_drive = MagicMock(return_value=True)
    assert manager.scan_and_copy_pdf_files(_drive(tmp_path, with_pdf=False)) == []
    manager._auto_eject_usb_drive.assert_called_once()


def _status_after_scan(tmp_path, with_pdf, ejected):
    manager = USBFileManager()
    manager._auto_eject_usb_drive = MagicMock(return_value=ejected)
    model = USBScreenModel()
    model.usb_manager = manager
    model.start_usb_monitoring = lambda: None
    messages = []
    model.status_changed.connect(lambda text, kind: messages.append(text))
    model.scan_files_from_drive(_drive(tmp_path, with_pdf))
    return messages[-1]


@pytest.mark.parametrize('with_pdf', [True, False])
def test_screen_says_safe_only_when_unmounted(kiosk, tmp_path, monkeypatch, with_pdf):
    monkeypatch.setattr(usb_file_manager, 'check_pdf', lambda path: (1, None))
    monkeypatch.setattr('threading.Timer', MagicMock())
    ok = _status_after_scan(tmp_path / 'a', with_pdf, ejected=True)
    failed = _status_after_scan(tmp_path / 'b', with_pdf, ejected=False)
    assert 'remove' in ok
    assert 'remove' not in failed
