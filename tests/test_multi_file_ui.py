"""
Choosing several files (#119 / #124): the file browser's tick boxes and the print
options screen's per-file settings and pricing. Offscreen Qt, real PDFs.
"""
import os
import time
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import fitz  # noqa: E402
import pytest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

import screens.print_options.model as po_model  # noqa: E402
from managers.print_items import MAX_FILES_PER_TRANSACTION, PrintItem  # noqa: E402
from screens.file_browser.controller import FileBrowserController  # noqa: E402
from screens.print_options.controller import PrintOptionsController  # noqa: E402
from screens.print_options.model import PrintOptionsModel  # noqa: E402

app = QApplication.instance() or QApplication([])


def make_pdf(path, pages=3, color_pages=()):
    doc = fitz.open()
    for number in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {number}")
        if number in color_pages:
            page.draw_rect(fitz.Rect(50, 100, 400, 500), color=(1, 0, 0), fill=(1, 0, 0))
    doc.save(str(path))
    doc.close()
    return str(path)


def pdf_data(tmp_path, name, pages=3, color_pages=(), error=None):
    path = make_pdf(tmp_path / name, pages, color_pages)
    return {'filename': name, 'path': path, 'pages': pages, 'size': 1000, 'error': error}


def wait_until(condition, what="the analysis"):
    deadline = time.time() + 20
    while not condition():
        assert time.time() < deadline, f"timed out waiting for {what}"
        app.processEvents()
        time.sleep(0.01)


# ---- file_browser ticks -----------------------------------------------------------

@pytest.fixture
def browser(monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: warnings.append(a[2]))
    main_app = MagicMock()
    controller = FileBrowserController(main_app)
    controller.set_source('usb')
    controller.warnings = warnings
    yield controller, main_app
    controller.view.clear_preview()
    controller.model.cleanup()


def names(view):
    return [p['filename'] for p in view.ticked]


def positions(view):
    return [row.tick_btn.text() for row in view.file_rows]


def test_the_first_readable_file_is_ticked_on_load(tmp_path, browser):
    controller, main_app = browser
    controller.load_pdf_files([pdf_data(tmp_path, 'bad.pdf', error='x'), pdf_data(tmp_path, 'a.pdf'),
                               pdf_data(tmp_path, 'b.pdf')])

    assert names(controller.view) == ['a.pdf']
    assert positions(controller.view) == ['', '1', '']


def test_one_file_needs_no_extra_tap(tmp_path, browser):
    controller, main_app = browser
    controller.load_pdf_files([pdf_data(tmp_path, 'a.pdf')])

    controller._continue_to_payment()

    [item] = main_app.printing_options_screen.set_items.call_args.args[0]
    assert (item.file_name, item.pages) == ('a.pdf', [1, 2, 3])


def test_tick_order_is_print_order_and_unticking_renumbers(tmp_path, browser):
    controller, _ = browser
    files = [pdf_data(tmp_path, f'{n}.pdf') for n in 'abcd']
    controller.load_pdf_files(files)
    view = controller.view

    view.toggle_tick(files[3])
    view.toggle_tick(files[1])
    assert names(view) == ['a.pdf', 'd.pdf', 'b.pdf']
    assert positions(view) == ['1', '3', '', '2']

    view.toggle_tick(files[0])   # untick the first: the rest move up
    assert names(view) == ['d.pdf', 'b.pdf']
    assert positions(view) == ['', '2', '', '1']


def test_an_unreadable_file_cannot_be_ticked(tmp_path, browser):
    controller, _ = browser
    bad = pdf_data(tmp_path, 'bad.pdf', error='broken')
    controller.load_pdf_files([pdf_data(tmp_path, 'a.pdf'), bad])

    controller.view.toggle_tick(bad)

    assert names(controller.view) == ['a.pdf']
    assert not controller.view.file_rows[1].tick_btn.isEnabled()


def test_the_eleventh_tick_is_refused_with_a_message(tmp_path, browser):
    controller, _ = browser
    files = [pdf_data(tmp_path, f'f{n:02d}.pdf', pages=1) for n in range(MAX_FILES_PER_TRANSACTION + 1)]
    controller.load_pdf_files(files)
    view = controller.view
    for pdf in files[1:MAX_FILES_PER_TRANSACTION]:
        view.toggle_tick(pdf)
    assert len(view.ticked) == MAX_FILES_PER_TRANSACTION

    view.toggle_tick(files[MAX_FILES_PER_TRANSACTION])

    assert len(view.ticked) == MAX_FILES_PER_TRANSACTION
    assert str(MAX_FILES_PER_TRANSACTION) in view.tick_hint.text()
    assert view.file_rows[-1].tick_btn.text() == ''
    view.toggle_tick(files[0])   # room again
    view.toggle_tick(files[MAX_FILES_PER_TRANSACTION])
    assert len(view.ticked) == MAX_FILES_PER_TRANSACTION and names(view)[-1] == 'f10.pdf'


def test_continue_passes_each_ticked_files_own_pages_in_tick_order(tmp_path, browser):
    controller, main_app = browser
    files = [pdf_data(tmp_path, 'a.pdf'), pdf_data(tmp_path, 'b.pdf', pages=4), pdf_data(tmp_path, 'c.pdf')]
    controller.load_pdf_files(files)
    view = controller.view
    controller.model.select_pdf(files[1])             # preview b, drop its pages 1 and 3
    controller._page_checkbox_clicked(1, False)
    controller._page_checkbox_clicked(3, False)
    view.toggle_tick(files[2])
    view.toggle_tick(files[1])
    controller.model.select_pdf(files[0])             # back to a: b's choice is remembered
    controller._page_checkbox_clicked(2, False)

    controller._continue_to_payment()

    items = main_app.printing_options_screen.set_items.call_args.args[0]
    assert [(i.file_name, i.pages) for i in items] == [('a.pdf', [1, 3]), ('c.pdf', [1, 2, 3]), ('b.pdf', [2, 4])]
    assert main_app.printing_options_screen.set_items.call_args.args[1] == 'usb'
    main_app.show_screen.assert_called_with('printing_options')


def test_continue_is_off_until_something_is_ticked_and_names_a_file_with_no_pages(tmp_path, browser):
    controller, main_app = browser
    files = [pdf_data(tmp_path, 'a.pdf'), pdf_data(tmp_path, 'b.pdf')]
    controller.load_pdf_files(files)
    view = controller.view
    assert view.continue_btn.isEnabled()

    view.toggle_tick(files[0])   # untick the only one
    assert not view.continue_btn.isEnabled()
    controller._continue_to_payment()
    main_app.printing_options_screen.set_items.assert_not_called()

    view.toggle_tick(files[1])
    controller.model.select_pdf(files[1])
    view.deselect_all_pages()
    assert not view.continue_btn.isEnabled()
    assert 'b.pdf' in view.tick_hint.text()

    controller._page_checkbox_clicked(2, True)
    assert view.continue_btn.isEnabled()


def test_a_ticked_file_never_opened_prints_all_its_pages(tmp_path, browser):
    controller, main_app = browser
    files = [pdf_data(tmp_path, 'a.pdf'), pdf_data(tmp_path, 'b.pdf', pages=5)]
    controller.load_pdf_files(files)
    controller.view.toggle_tick(files[1])

    controller._continue_to_payment()

    items = main_app.printing_options_screen.set_items.call_args.args[0]
    assert items[1].pages == [1, 2, 3, 4, 5]


# ---- print_options: per-file settings and pricing ---------------------------------

BW_PRICE = po_model.PDFColorAnalyzer().black_price
COLOR_PRICE = po_model.PDFColorAnalyzer().color_price


@pytest.fixture
def model():
    m = PrintOptionsModel()
    yield m
    m.stop_analysis()


def priced(model):
    wait_until(model.is_priced, "every file to be priced")


def test_each_file_has_its_own_mode_and_copies_and_the_total_is_the_sum(tmp_path, model):
    a = PrintItem(pdf_data(tmp_path, 'a.pdf', pages=3), [1, 2, 3])
    b = PrintItem(pdf_data(tmp_path, 'b.pdf', pages=2, color_pages=(1,)), [1, 2])
    model.set_items([a, b], digital_fee=0)
    assert a.cost == pytest.approx(3 * BW_PRICE) and b.cost == pytest.approx(2 * BW_PRICE)

    model.set_item_color_mode(1, "Color")
    priced(model)
    model.change_item_copies(0, +1)
    model.change_item_copies(0, +1)

    assert (a.copies, a.color_mode, b.copies, b.color_mode) == (3, "Black and White", 1, "Color")
    assert a.cost == pytest.approx(3 * BW_PRICE * 3)
    assert b.cost == pytest.approx(COLOR_PRICE + BW_PRICE)   # page 2 has no color: B&W price
    data = model.get_payment_data()
    assert data['items'] == [a, b]
    assert data['total_cost'] == pytest.approx(a.cost + b.cost)
    assert [i.analysis['pricing']['color_pages_count'] for i in data['items']] == [0, 1]


def test_a_scans_digital_fee_is_added_to_the_total_not_to_a_file(tmp_path, model):
    a = PrintItem(pdf_data(tmp_path, 'a.pdf', pages=1), [1])
    model.set_items([a], digital_fee=5)
    assert a.cost == pytest.approx(BW_PRICE)
    assert model.get_payment_data()['total_cost'] == pytest.approx(BW_PRICE + 5)
    assert model.get_payment_data()['digital_copy'] == {'fee': 5}


def test_color_analysis_is_per_file_and_colorless_pages_cost_the_bw_price(tmp_path, model):
    colorless = PrintItem(pdf_data(tmp_path, 'plain.pdf', pages=2), [1, 2])
    colored = PrintItem(pdf_data(tmp_path, 'red.pdf', pages=2, color_pages=(1, 2)), [1, 2])
    model.set_items([colorless, colored])
    model.set_item_color_mode(0, "Color")
    model.set_item_color_mode(1, "Color")
    priced(model)

    assert colorless.cost == pytest.approx(2 * BW_PRICE)
    assert colored.cost == pytest.approx(2 * COLOR_PRICE)


def test_the_price_is_missing_while_a_color_file_is_analysed(tmp_path, model):
    a = PrintItem(pdf_data(tmp_path, 'a.pdf', pages=2, color_pages=(1,)), [1, 2])
    model.set_items([a])
    model.set_item_color_mode(0, "Color")

    assert model.is_analysing() and model.get_payment_data() is None
    priced(model)
    assert not model.is_analysing() and model.get_payment_data() is not None


def test_toggling_back_to_color_reuses_that_files_analysis(tmp_path, model, monkeypatch):
    runs = []
    real = po_model.AnalysisThread

    def counting(*args, **kwargs):
        runs.append(args[1])
        return real(*args, **kwargs)
    monkeypatch.setattr(po_model, 'AnalysisThread', counting)
    a = PrintItem(pdf_data(tmp_path, 'a.pdf', pages=2, color_pages=(1,)), [1, 2])
    model.set_items([a])

    model.set_item_color_mode(0, "Color")
    priced(model)
    first = a.cost
    model.set_item_color_mode(0, "Black and White")
    assert not model.is_analysing()
    model.set_item_color_mode(0, "Color")

    assert not model.is_analysing()   # priced at once, from the cache
    assert a.cost == pytest.approx(first)
    assert len(runs) == 1


def test_two_files_can_be_analysed_at_once_and_stop_analysis_stops_both(tmp_path, model):
    items = [PrintItem(pdf_data(tmp_path, f'{n}.pdf', pages=6, color_pages=(1,)), [1, 2, 3, 4, 5, 6]) for n in 'ab']
    model.set_items(items)
    model.set_item_color_mode(0, "Color")
    model.set_item_color_mode(1, "Color")
    assert len(model._threads) == 2

    model.stop_analysis()

    assert not model.is_analysing()


def test_the_model_refuses_no_files_and_too_many(tmp_path, model):
    with pytest.raises(ValueError):
        model.set_items([])
    too_many = [PrintItem(pdf_data(tmp_path, f'{n}.pdf', pages=1), [1]) for n in range(MAX_FILES_PER_TRANSACTION + 1)]
    with pytest.raises(ValueError):
        model.set_items(too_many)


# ---- print_options controller -----------------------------------------------------

@pytest.fixture
def options(monkeypatch):
    monkeypatch.setattr(QMessageBox, 'warning', MagicMock())
    main_app = MagicMock()
    main_app.admin_screen.get_paper_count.return_value = 100
    controller = PrintOptionsController(main_app)
    yield controller, main_app
    controller.model.stop_analysis()


def test_each_row_changes_only_its_own_file(tmp_path, options):
    controller, _ = options
    items = [PrintItem(pdf_data(tmp_path, 'a.pdf', pages=2), [1, 2]), PrintItem(pdf_data(tmp_path, 'b.pdf', pages=1), [1])]
    controller.set_items(items, 'usb')
    rows = controller.view.item_rows
    assert [r.price_label.text() for r in rows] == [f"₱{2 * BW_PRICE:.2f}", f"₱{BW_PRICE:.2f}"]

    controller.view.item_copies_step.emit(1, 1)
    controller.view.item_color_clicked.emit(0, "Color")
    wait_until(controller.model.is_priced)

    assert rows[1].copies_count_label.text() == "2" and rows[0].copies_count_label.text() == "1"
    assert rows[0].color_btn.isChecked() and rows[1].bw_btn.isChecked()
    assert rows[1].price_label.text() == f"₱{2 * BW_PRICE:.2f}"


def test_continue_stays_off_while_any_file_is_analysed(tmp_path, options):
    controller, _ = options
    items = [PrintItem(pdf_data(tmp_path, 'a.pdf', pages=4, color_pages=(1,)), [1, 2, 3, 4]),
             PrintItem(pdf_data(tmp_path, 'b.pdf', pages=1), [1])]
    controller.set_items(items, 'usb')
    app.processEvents()

    controller.view.item_color_clicked.emit(0, "Color")
    assert not controller.view.continue_btn.isEnabled()
    assert controller.view.item_rows[0].price_label.text() == "Calculating…"
    controller.view.item_copies_step.emit(1, 1)   # another change must not re-enable it
    assert not controller.view.continue_btn.isEnabled()

    wait_until(controller.model.is_priced)
    wait_until(lambda: controller.view.continue_btn.isEnabled(), "Continue to come back")
    assert controller.view.item_rows[0].price_label.text() != "Calculating…"


def test_the_paper_check_counts_every_files_sheets(tmp_path, options):
    controller, main_app = options
    items = [PrintItem(pdf_data(tmp_path, 'a.pdf', pages=3), [1, 2, 3]), PrintItem(pdf_data(tmp_path, 'b.pdf', pages=2), [1, 2])]
    main_app.admin_screen.get_paper_count.return_value = 6
    controller.set_items(items, 'usb')

    controller._check_paper_availability()
    assert controller.view.continue_btn.isEnabled()          # 5 sheets, 6 in the tray

    controller.view.item_copies_step.emit(1, 1)               # 7 sheets
    assert not controller.view.continue_btn.isEnabled()
    assert controller.view.continue_btn.text() == "Insufficient Paper"
    controller._continue_to_payment()
    main_app.payment_screen.set_payment_data.assert_not_called()


def test_continue_hands_every_item_to_payment(tmp_path, options):
    controller, main_app = options
    items = [PrintItem(pdf_data(tmp_path, 'a.pdf', pages=2), [1, 2]), PrintItem(pdf_data(tmp_path, 'b.pdf', pages=1), [1])]
    controller.set_items(items, 'wifi')
    controller.view.item_copies_step.emit(0, 1)

    controller._continue_to_payment()

    data = main_app.payment_screen.set_payment_data.call_args.args[0]
    assert [(i.file_name, i.copies) for i in data['items']] == [('a.pdf', 2), ('b.pdf', 1)]
    assert data['source'] == 'wifi'
    assert data['total_cost'] == pytest.approx(4 * BW_PRICE + BW_PRICE)
    main_app.show_screen.assert_called_with('payment')


# ---- coming back from payment ------------------------------------------------------

def test_backing_out_of_payment_changing_the_job_and_returning_works_twice(tmp_path, options, monkeypatch):
    """Back from payment lands on print options with the job as it was; the customer can
    change copies and color and go to payment again, more than once."""
    controller, main_app = options
    warned = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: warned.append(a[2]))
    items = [PrintItem(pdf_data(tmp_path, 'a.pdf', pages=3, color_pages=(1,)), [1, 2, 3]),
             PrintItem(pdf_data(tmp_path, 'b.pdf', pages=1), [1])]
    controller.set_items(items, 'usb')
    controller.view.item_color_clicked.emit(0, "Color")
    wait_until(controller.model.is_priced)
    controller._continue_to_payment()
    first = main_app.payment_screen.set_payment_data.call_args.args[0]['total_cost']

    for round_trip, (mode, step) in enumerate([("Black and White", 1), ("Color", 1)], 1):
        controller.on_leave()           # what show_screen does on the way to payment...
        controller.on_enter()           # ...and on the way back
        assert controller.view.continue_btn.isEnabled() or controller.model.is_analysing()
        controller.view.item_color_clicked.emit(0, mode)
        controller.view.item_copies_step.emit(1, step)
        wait_until(controller.model.is_priced)
        wait_until(lambda: controller.view.continue_btn.isEnabled(), "Continue")
        controller._continue_to_payment()
        data = main_app.payment_screen.set_payment_data.call_args.args[0]
        assert main_app.payment_screen.set_payment_data.call_count == round_trip + 1
        assert data['items'][1].copies == 1 + round_trip

    assert warned == []
    assert data['total_cost'] != first


def test_continue_during_a_stalled_price_recovers_instead_of_a_popup(tmp_path, options, monkeypatch):
    controller, main_app = options
    warned = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: warned.append(a[2]))
    item = PrintItem(pdf_data(tmp_path, 'a.pdf', pages=2, color_pages=(1,)), [1, 2])
    controller.set_items([item], 'usb')
    item.analysis = None            # a price that never arrived (failed or stopped analysis)
    item.color_mode = "Color"

    controller._continue_to_payment()
    assert warned == [] and not controller.view.continue_btn.isEnabled()
    main_app.payment_screen.set_payment_data.assert_not_called()

    wait_until(controller.model.is_priced, "the price to be recalculated")
    wait_until(lambda: controller.view.continue_btn.isEnabled(), "Continue")
    controller._continue_to_payment()
    main_app.payment_screen.set_payment_data.assert_called_once()
