# screens/print_options/model.py

import fitz
import numpy as np
from typing import List, Dict
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from config import get_config
from managers.print_items import MAX_FILES_PER_TRANSACTION, total_sheets


class PDFColorAnalyzer:
    """Analyzes PDF pages to determine if they are black and white or colored."""

    def __init__(self, black_price: float = None, color_price: float = None):
        config = get_config()
        self.black_price = black_price if black_price is not None else config.black_and_white_price
        self.color_price = color_price if color_price is not None else config.color_price

    def is_page_black_only(self, page_image: np.ndarray,
                           color_tolerance: int = None,
                           pixel_count_threshold: int = None) -> bool:
        """Determines if a page image is black and white only."""
        if page_image.size == 0:
            return True

        # Use config values if not provided
        if color_tolerance is None or pixel_count_threshold is None:
            config = get_config()
            color_tolerance = color_tolerance or config.color_tolerance
            pixel_count_threshold = pixel_count_threshold or config.pixel_count_threshold

        b, g, r = page_image[:, :, 0], page_image[:, :, 1], page_image[:, :, 2]
        channel_max = np.maximum(np.maximum(r, g), b)
        channel_min = np.minimum(np.minimum(r, g), b)
        color_diff = (channel_max - channel_min).astype(np.uint8)
        colored_pixel_count = np.count_nonzero(color_diff > color_tolerance)
        return colored_pixel_count < pixel_count_threshold

    def analyze_pdf_pages(self, pdf_path: str, pages_to_check: List[int], user_wants_color: bool, dpi: int = None) -> Dict:
        """Analyzes PDF pages and calculates pricing."""
        # Use config DPI if not provided
        if dpi is None:
            config = get_config()
            dpi = config.pdf_analysis_dpi

        results = {
            'page_analysis': {},
            'pricing': {'black_pages_count': 0, 'color_pages_count': 0, 'base_cost': 0},
            'error': None
        }

        try:
            pdf_document = fitz.open(pdf_path)
            for page_num_1_based in pages_to_check:
                page_num_0_based = page_num_1_based - 1
                if not (0 <= page_num_0_based < len(pdf_document)):
                    continue

                page = pdf_document[page_num_0_based]
                mat = fitz.Matrix(dpi/72, dpi/72)
                pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
                page_image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

                is_black_only = self.is_page_black_only(page_image)

                page_price = 0

                if user_wants_color and not is_black_only:
                    page_price = self.color_price
                    results['pricing']['color_pages_count'] += 1
                else:
                    page_price = self.black_price
                    results['pricing']['black_pages_count'] += 1

                results['pricing']['base_cost'] += page_price
                results['page_analysis'][page_num_1_based] = {
                    'is_black_only': is_black_only,
                    'final_price': page_price
                }

            pdf_document.close()
            return results
        except Exception as e:
            results['error'] = f"Error processing PDF: {str(e)}"
            return results


class AnalysisThread(QThread):
    """Thread for analyzing PDF pages in the background."""
    analysis_complete = pyqtSignal(dict)

    def __init__(self, analyzer, pdf_path, selected_pages, user_wants_color):
        super().__init__()
        self.analyzer = analyzer
        self.pdf_path = pdf_path
        self.selected_pages = selected_pages
        self.user_wants_color = user_wants_color
        self._is_running = True

    def run(self):
        if not self._is_running:
            return
        results = self.analyzer.analyze_pdf_pages(self.pdf_path, self.selected_pages, self.user_wants_color)
        if self._is_running:
            self.analysis_complete.emit(results)

    def stop(self):
        self._is_running = False


class PrintOptionsModel(QObject):
    """Handles the data and business logic for the print options screen.

    Holds one PrintItem per file (in print order). Each item has its own color
    mode and copies and is priced on its own: black and white directly, color by
    analysing that file's selected pages (cached per file and page selection, so
    toggling back and forth doesn't run it again)."""
    cost_updated = pyqtSignal(str, str)  # Emits total cost text and details text
    item_changed = pyqtSignal(int)       # an item's copies, mode, price or analysis state changed
    analysis_started = pyqtSignal()      # some item began a color analysis
    analysis_completed = pyqtSignal(dict)  # the last running analysis finished (its results)
    analysis_error = pyqtSignal(str)  # Emits error message
    show_message = pyqtSignal(str, str)  # Emits message title and text

    def __init__(self):
        super().__init__()
        self.analyzer = PDFColorAnalyzer()  # Will use config values
        self.items = []
        self._threads = {}       # item index -> running AnalysisThread
        self._retired = []       # stopped threads still finishing; kept alive until they do
        self._color_cache = {}   # (path, pages) -> that file's color analysis
        self.digital_fee = 0  # flat fee for the scan's digital copy; 0 = print only

    def set_items(self, items, digital_fee=0):
        """Sets the job: PrintItems in print order. digital_fee > 0 adds the flat fee for
        a digital copy (scan sent via download/email) to the total. Every item starts
        with the default color mode and minimum copies."""
        items = list(items)
        if not items:
            raise ValueError("a print job needs at least one file")
        if len(items) > MAX_FILES_PER_TRANSACTION:
            raise ValueError(f"at most {MAX_FILES_PER_TRANSACTION} files can be printed together")
        self.stop_analysis()
        config = get_config()
        self.digital_fee = digital_fee
        self._color_cache = {}
        self.items = items
        for item in self.items:
            item.copies = config.min_copies
            item.color_mode = config.default_color_mode
            item.cost = 0.0
            item.analysis = None
        for index in range(len(self.items)):
            self._price(index)

    # --- Per-item settings ---

    def set_item_color_mode(self, index, mode):
        """Sets one file's color mode (Black and White or Color) and prices it again."""
        item = self.items[index]
        if item.color_mode == mode and item.analysis is not None:
            return
        item.color_mode = mode
        self._price(index)

    def change_item_copies(self, index, delta):
        """Changes one file's copies by delta, within the configured limits."""
        config = get_config()
        item = self.items[index]
        new_copies = max(config.min_copies, min(config.max_copies, item.copies + delta))
        if new_copies != item.copies:
            item.copies = new_copies
            if item.analysis is not None:
                item.cost = item.analysis['pricing']['base_cost'] * item.copies
            self.item_changed.emit(index)
            self.update_cost_display()

    # --- Pricing ---

    def is_analysing(self):
        """True while any file's color analysis is running."""
        return bool(self._threads)

    def is_priced(self):
        """True once every file has a price (none analysing, none failed)."""
        return bool(self.items) and all(item.analysis is not None for item in self.items)

    def _price(self, index):
        item = self.items[index]
        self._stop_item_thread(index)
        item.analysis = None
        item.cost = 0.0

        if item.color_mode != "Color":
            # Black and white: every page is the B&W price, no analysis needed
            pages = len(item.pages)
            self._finish_item(index, {
                'pricing': {'base_cost': pages * self.analyzer.black_price,
                            'black_pages_count': pages, 'color_pages_count': 0},
                'page_analysis': {}, 'error': None})
            return

        cached = self._color_cache.get((item.path, tuple(item.pages)))
        if cached:
            self._finish_item(index, cached)
            return

        thread = AnalysisThread(self.analyzer, item.path, item.pages, True)
        thread.analysis_complete.connect(lambda results, t=thread, i=index: self._on_item_analysed(i, t, results))
        self._threads[index] = thread
        self.item_changed.emit(index)
        self.analysis_started.emit()
        thread.start()

    def _on_item_analysed(self, index, thread, results):
        if self._threads.get(index) is not thread:
            return  # superseded by a newer request for this file
        del self._threads[index]
        if results.get('error'):
            self.analysis_error.emit(results['error'])
            self.item_changed.emit(index)
            return
        item = self.items[index]
        self._color_cache[(item.path, tuple(item.pages))] = results
        self._finish_item(index, results)

    def _finish_item(self, index, results):
        item = self.items[index]
        item.analysis = results
        item.cost = results['pricing']['base_cost'] * item.copies
        self.item_changed.emit(index)
        self.update_cost_display()
        if not self.is_analysing():
            self.analysis_completed.emit(results)

    def total_cost(self):
        return sum(item.cost for item in self.items) + self.digital_fee

    def total_sheets(self):
        return total_sheets(self.items)

    def update_cost_display(self):
        """Updates the total and its details; blank until every file is priced."""
        if not self.is_priced():
            return
        cost_text = f"Total Cost: ₱{self.total_cost():.2f}"
        if len(self.items) == 1:
            item = self.items[0]
            pricing = item.analysis['pricing']
            b_count, c_count = pricing['black_pages_count'], pricing['color_pages_count']
            if c_count > 0:
                details_text = f"Based on {item.copies} copies of ({b_count} B&W pages + {c_count} Color pages)"
            else:
                details_text = f"Based on {item.copies} copies of {b_count} Black & White pages"
        else:
            details_text = f"{len(self.items)} files, {self.total_sheets()} sheets in all"
        if self.digital_fee:
            details_text += f" + ₱{self.digital_fee} digital copy"
        self.cost_updated.emit(cost_text, details_text)

    def get_payment_data(self):
        """The payment data for the job, or None while any file is still being priced."""
        if not self.is_priced():
            return None
        data = {
            'items': self.items,
            'total_cost': self.total_cost(),
        }
        if self.digital_fee:
            data['digital_copy'] = {'fee': self.digital_fee}
        return data

    # --- Threads ---

    def _stop_item_thread(self, index):
        thread = self._threads.pop(index, None)
        if thread is None:
            return
        thread.stop()
        self._retired.append(thread)
        thread.finished.connect(lambda t=thread: self._retired.remove(t) if t in self._retired else None)

    def stop_analysis(self):
        """Stops every running analysis."""
        threads = list(self._threads.values()) + list(self._retired)
        self._threads = {}
        for thread in threads:
            if thread.isRunning():
                thread.stop()
                if not thread.wait(2000):
                    print("Warning: Analysis thread did not stop gracefully")
                    thread.terminate()
                    thread.wait(1000)
        self._retired = []
