# screens/scanner/view.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ui.theme import COLORS, FONT
from ui.widgets import BackButton, Card, Header, PrimaryButton, SecondaryButton, StatusBanner


class ScannerScreenView(QWidget):
    """The user interface for the Scanner screen. Contains no logic."""
    cancel_clicked = pyqtSignal()
    scan_page_clicked = pyqtSignal()
    rescan_clicked = pyqtSignal()
    done_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_pages = False
        self.setup_ui()

    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['bg']};")
        body_layout = QVBoxLayout(content)
        body_layout.setContentsMargins(60, 16, 60, 24)
        body_layout.setSpacing(8)
        outer_layout.addWidget(content, 1)

        self.cancel_button = BackButton("Cancel Scan")
        self.cancel_button.clicked.connect(self.cancel_clicked.emit)

        body_layout.addStretch(1)

        guide_title = QLabel("Usage Guide")
        guide_title.setAlignment(Qt.AlignCenter)
        guide_title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        guide_text = QLabel(
            '1. Place your document face-down on the scanner glass, then tap "Scan Page".<br>'
            '2. Not happy with a page? Tap "Rescan Last Page" to redo it.<br>'
            '3. Repeat for each page of a multi-page document, then tap "Done".'
        )
        guide_text.setAlignment(Qt.AlignCenter)
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        self.page_count_label = QLabel("No pages scanned yet")
        self.page_count_label.setAlignment(Qt.AlignCenter)
        self.page_count_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;"
        )

        self.thumbnail_label = QLabel("")
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setFixedHeight(160)

        body_layout.addWidget(guide_title)
        body_layout.addSpacing(6)
        body_layout.addWidget(guide_text)
        body_layout.addSpacing(10)
        body_layout.addWidget(self.page_count_label)
        body_layout.addWidget(self.thumbnail_label)
        body_layout.addSpacing(10)

        self.scan_card = Card('scan', "Scan Page", "Tap to scan the next page.", icon_name='scanner')
        self.scan_card.clicked.connect(lambda _key: self.scan_page_clicked.emit())

        cards_row = QHBoxLayout()
        cards_row.addStretch()
        cards_row.addWidget(self.scan_card)
        cards_row.addStretch()
        body_layout.addLayout(cards_row)

        body_layout.addSpacing(12)

        self.rescan_button = SecondaryButton("Rescan Last Page")
        self.rescan_button.clicked.connect(self.rescan_clicked.emit)
        self.rescan_button.setEnabled(False)

        self.done_button = PrimaryButton("Done")
        self.done_button.clicked.connect(self.done_clicked.emit)
        self.done_button.setEnabled(False)

        actions_row = QHBoxLayout()
        actions_row.addStretch()
        actions_row.addWidget(self.rescan_button)
        actions_row.addWidget(self.done_button)
        actions_row.addStretch()
        body_layout.addLayout(actions_row)

        body_layout.addSpacing(16)

        self.status_banner = StatusBanner()
        body_layout.addWidget(self.status_banner)

        body_layout.addStretch(2)

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.cancel_button, 0, Qt.AlignLeft)
        nav_row.addStretch()
        body_layout.addLayout(nav_row)

    def show_status(self, message, is_error=True):
        self.status_banner.show_message(message, variant="error" if is_error else "success")

    def set_busy(self, busy: bool):
        self.scan_card.setEnabled(not busy)
        self.rescan_button.setEnabled(not busy and self._has_pages)
        self.done_button.setEnabled(not busy and self._has_pages)

    def update_page_count(self, count: int):
        self._has_pages = count > 0
        if count == 0:
            self.page_count_label.setText("No pages scanned yet")
        elif count == 1:
            self.page_count_label.setText("1 page scanned")
        else:
            self.page_count_label.setText(f"{count} pages scanned")
        self.rescan_button.setEnabled(self._has_pages)
        self.done_button.setEnabled(self._has_pages)

    def show_thumbnail(self, image_path: str):
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap.scaledToHeight(160, Qt.SmoothTransformation))

    def clear_thumbnail(self):
        self.thumbnail_label.clear()

    def reset(self):
        self.update_page_count(0)
        self.clear_thumbnail()
        self.show_status("")
        self.set_busy(False)
