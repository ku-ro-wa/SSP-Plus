"""
A PDF that PyMuPDF can't open (corrupted, truncated, or not a PDF at all) used to get
`pages: 1` at intake and go all the way to payment, failing only at print time after
the customer had paid. It must be flagged when it's copied in and blocked in the file
browser. A damaged PDF that MuPDF can repair still prints, so it must stay accepted.
"""
import os
import tempfile
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import fitz  # noqa: E402
import pytest  # noqa: E402
from PyQt5.QtCore import QEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402

from managers.usb_file_manager import USBFileManager  # noqa: E402

app = QApplication.instance() or QApplication([])


def _write_good_pdf(path, pages=3):
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"page {i + 1} " * 20)
    doc.save(path)
    doc.close()


@pytest.fixture
def usb_drive(tmp_path, monkeypatch):
    """A fake USB drive holding one good, one repairable and one unreadable PDF."""
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path / 'tmp'))
    drive = tmp_path / 'drive'
    drive.mkdir()
    _write_good_pdf(drive / 'good.pdf')
    good = (drive / 'good.pdf').read_bytes()
    (drive / 'repairable.pdf').write_bytes(good[:len(good) // 2])  # truncated, MuPDF repairs it
    (drive / 'broken.pdf').write_bytes(b"%PDF-1.7\n" + os.urandom(4000))
    return drive


def _copy_from(drive):
    manager = USBFileManager()
    manager._auto_eject_usb_drive = lambda path: None  # never umount anything in tests
    return {f['filename']: f for f in manager.scan_and_copy_pdf_files(str(drive))}


def test_usb_copy_flags_a_pdf_that_cannot_be_opened(usb_drive):
    files = _copy_from(usb_drive)

    assert files['broken.pdf']['error']
    assert files['good.pdf']['error'] is None
    assert files['good.pdf']['pages'] == 3
    assert files['repairable.pdf']['error'] is None
    assert files['repairable.pdf']['pages'] == 3


def test_copy_by_paths_flags_a_pdf_that_cannot_be_opened(usb_drive, tmp_path):
    manager = USBFileManager()
    files = {f['filename']: f for f in manager.scan_and_copy_pdf_files_by_paths(
        [str(usb_drive / 'good.pdf'), str(usb_drive / 'broken.pdf')])}

    assert files['broken.pdf']['error']
    assert files['good.pdf']['error'] is None


@pytest.fixture
def file_browser(monkeypatch):
    from screens.file_browser.controller import FileBrowserController
    monkeypatch.setattr(QMessageBox, 'warning', MagicMock())
    main_app = MagicMock()
    controller = FileBrowserController(main_app)
    controller.set_source('usb')
    yield controller, main_app
    controller.view.clear_preview()


def test_file_browser_blocks_an_unreadable_pdf(usb_drive, file_browser):
    controller, main_app = file_browser
    files = _copy_from(usb_drive)
    controller.load_pdf_files([files['broken.pdf']])
    view = controller.view

    assert not view.continue_btn.isEnabled()
    messages = [label.text() for label in view.preview_container.findChildren(QLabel, "UnreadableFileMessage")]
    assert len(messages) == 1 and "can't be opened" in messages[0]

    controller._continue_to_payment()
    main_app.printing_options_screen.set_pdf_data.assert_not_called()


def test_file_browser_still_lets_a_readable_pdf_through_next_to_a_broken_one(usb_drive, file_browser):
    controller, main_app = file_browser
    files = _copy_from(usb_drive)
    controller.load_pdf_files([files['good.pdf'], files['broken.pdf']])
    view = controller.view

    broken = next(p for p in view.pdf_files_data if p['filename'] == 'broken.pdf')
    controller.model.select_pdf(broken)
    controller._continue_to_payment()
    main_app.printing_options_screen.set_pdf_data.assert_not_called()

    good = next(p for p in view.pdf_files_data if p['filename'] == 'good.pdf')
    controller.model.select_pdf(good)
    assert view.continue_btn.isEnabled()
    assert not view.view_all_btn.isHidden() and not view.view_single_btn.isHidden()
    app.sendPostedEvents(None, QEvent.DeferredDelete)  # clear_preview() uses deleteLater()
    assert not view.preview_container.findChildren(QLabel, "UnreadableFileMessage")
    controller._continue_to_payment()
    main_app.printing_options_screen.set_pdf_data.assert_called_once()
    assert main_app.printing_options_screen.set_pdf_data.call_args.args[1] == [1, 2, 3]
