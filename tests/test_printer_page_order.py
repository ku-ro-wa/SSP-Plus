"""
Every print job is sent last page first, with collated copies (issue #118).

The HP Smart Tank puts each sheet face up on top of the last, so a job sent in
reading order comes out reversed; `PrinterThread` therefore builds its
temporary PDF in descending page order. Copies are always collated so two or
more copies come out as whole sets (1,2,3,1,2,3), not 1,1,2,2,3,3.
"""
import os

import fitz
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication  # noqa: E402

from managers.printer_thread import PrinterThread  # noqa: E402

PRINTER = "HP_Smart_Tank_580_590_series_5E0E1D_USB"


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def source_pdf(tmp_path):
    """A 3-page PDF whose pages read `Page 1`, `Page 2`, `Page 3`."""
    path = tmp_path / "source.pdf"
    doc = fitz.open()
    for number in (1, 2, 3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {number}")
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def make_thread(app, source_pdf):
    """The style of tests/test_printer_completion.py, with a real 3-page PDF."""
    created = []

    def _make(selected_pages, copies=1, color_mode="Black and White"):
        thread = PrinterThread(source_pdf, copies, color_mode, selected_pages, PRINTER)
        created.append(thread)
        return thread

    yield _make

    for thread in created:
        thread.cleanup_temp_pdf()


def page_texts(pdf_path):
    doc = fitz.open(pdf_path)
    texts = [page.get_text().strip() for page in doc]
    doc.close()
    return texts


class TestTempPdfPageOrder:
    def test_all_pages_are_written_last_page_first(self, make_thread):
        thread = make_thread([1, 2, 3])
        thread.create_temp_pdf_with_selected_pages()

        assert page_texts(thread.temp_pdf_path) == ["Page 3", "Page 2", "Page 1"]

    def test_selected_pages_are_written_in_descending_order(self, make_thread):
        thread = make_thread([3, 1])
        thread.create_temp_pdf_with_selected_pages()

        assert page_texts(thread.temp_pdf_path) == ["Page 3", "Page 1"]

    def test_a_single_page_is_unchanged(self, make_thread):
        thread = make_thread([2])
        thread.create_temp_pdf_with_selected_pages()

        assert page_texts(thread.temp_pdf_path) == ["Page 2"]

    def test_the_selection_sort_is_kept(self, make_thread):
        """Reversing the list upstream has no effect — the constructor sorts it."""
        thread = make_thread([2, 3, 1])
        assert thread.selected_pages == [1, 2, 3]

        thread.create_temp_pdf_with_selected_pages()
        assert page_texts(thread.temp_pdf_path) == ["Page 3", "Page 2", "Page 1"]

    def test_the_temp_pdf_is_removed_by_cleanup(self, make_thread):
        thread = make_thread([1, 2])
        thread.create_temp_pdf_with_selected_pages()
        temp_path = thread.temp_pdf_path
        assert os.path.exists(temp_path)

        thread.cleanup_temp_pdf()
        assert not os.path.exists(temp_path)


class TestPrintCommand:
    @pytest.fixture
    def command(self, make_thread, monkeypatch):
        thread = make_thread([1, 2, 3], copies=2, color_mode="Color")
        monkeypatch.setattr(thread, "temp_pdf_path", "/tmp/printjob-abc.pdf")
        return thread.build_print_command()

    def test_copies_are_collated(self, command):
        assert any(option == "collate=true" for option in command)
        index = command.index("collate=true")
        assert command[index - 1] == "-o"

    def test_color_mode_is_still_requested(self, command):
        assert "print-color-mode=color" in command

    def test_copies_are_still_passed(self, command):
        index = command.index("-n")
        assert command[index + 1] == "2"

    def test_the_file_path_stays_last(self, command):
        assert command[0] == "lp"
        assert command[-1] == "/tmp/printjob-abc.pdf"

    def test_black_and_white_stays_monochrome(self, make_thread, monkeypatch):
        thread = make_thread([1], color_mode="Black and White")
        monkeypatch.setattr(thread, "temp_pdf_path", "/tmp/printjob-abc.pdf")

        assert "print-color-mode=monochrome" in thread.build_print_command()
