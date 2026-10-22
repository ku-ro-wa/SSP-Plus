"""
The "Hold your QR code up to the reader" hint shows only when a QR reader is
configured (QR_READER_PORT): with no reader, nothing reads the code it asks for.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402

from screens.email.view import EmailScreenView  # noqa: E402
from screens.wifi.view import WifiScreenView  # noqa: E402
from ui.widgets import ReaderHint  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("value", ["", "   "])
def test_hidden_without_a_reader(qapp, monkeypatch, value):
    monkeypatch.setenv("QR_READER_PORT", value)
    parent = QWidget()
    hint = ReaderHint(parent)
    parent.show()
    assert not hint.isVisible()
    parent.close()


def test_shown_with_a_reader(qapp, monkeypatch):
    monkeypatch.setenv("QR_READER_PORT", "/dev/ttyACM0")
    hint = ReaderHint()
    assert not hint.isVisible()  # not opened as a stray window before it has a parent
    parent = QWidget()
    hint.setParent(parent)
    parent.show()
    assert hint.isVisible()
    parent.close()


@pytest.mark.parametrize("view_class", [WifiScreenView, EmailScreenView])
def test_code_screens_follow_the_reader_setting(qapp, monkeypatch, view_class):
    monkeypatch.setenv("QR_READER_PORT", "")
    view = view_class()
    view.show()
    assert not view.reader_hint.isVisible()
    assert view.otp_entry.isVisible()  # typing the code is still on offer
    view.close()

    monkeypatch.setenv("QR_READER_PORT", "/dev/ttyACM0")
    view = view_class()
    view.show()
    assert view.reader_hint.isVisible()
    view.close()
