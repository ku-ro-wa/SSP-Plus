# screens/scan_destination/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import CARD_QSS, COLORS, FONT
from ui.widgets import BackButton, Card, Header, PrimaryButton, StatusBanner

# Appended after CARD_QSS (same QFrame#Card selector, later rule wins) to
# highlight a selected DestinationOption without touching Card itself —
# other screens rely on Card's plain, non-toggling appearance.
SELECTED_CARD_QSS = f"""
QFrame#Card {{
    border: 3px solid {COLORS['primary']};
    background-color: {COLORS['bg_subtle']};
}}
"""

THUMBNAIL_HEIGHT = 220


class DestinationOption(QFrame):
    """Wraps a Card to add local checked/toggle state, without changing
    Card's own click-fires-immediately behavior that other screens depend
    on. Clicking toggles selection and re-emits it rather than acting."""
    toggled = pyqtSignal(str, bool)  # key, is_selected

    def __init__(self, key, title, description, icon_name=None, parent=None):
        super().__init__(parent)
        self._key = key
        self._selected = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.card = Card(key, title, description, icon_name=icon_name)
        self.card.clicked.connect(self._on_card_clicked)
        layout.addWidget(self.card)

    def _on_card_clicked(self, _key):
        self.set_selected(not self._selected)
        self.toggled.emit(self._key, self._selected)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.card.setStyleSheet(CARD_QSS + (SELECTED_CARD_QSS if selected else ""))

    def is_selected(self) -> bool:
        return self._selected

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.card.setEnabled(enabled)


class ScanDestinationScreenView(QWidget):
    """The user interface for choosing what happens to a finished scan. Contains no logic."""
    cancel_clicked = pyqtSignal()
    continue_clicked = pyqtSignal()
    destination_toggled = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumbnail_labels = []
        self.setup_ui()

    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['bg']};")
        body_layout = QVBoxLayout(content)
        body_layout.setContentsMargins(60, 20, 60, 24)
        body_layout.setSpacing(10)
        outer_layout.addWidget(content, 1)

        self.cancel_button = BackButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_clicked.emit)

        body_layout.addStretch(1)

        title = QLabel("Scan Complete")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        self.summary_label = QLabel("")
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        body_layout.addWidget(title)
        body_layout.addSpacing(6)
        body_layout.addWidget(self.summary_label)
        body_layout.addSpacing(16)

        self.thumbnail_scroll = self._build_thumbnail_strip()
        body_layout.addWidget(self.thumbnail_scroll)

        body_layout.addSpacing(20)

        self.print_option = DestinationOption('print', "Print Now", "Print this scan right away (photocopy).")
        self.print_option.toggled.connect(self._on_option_toggled)

        self.send_wifi_option = DestinationOption(
            'send_wifi', "Download or Email",
            "Get a code to download or email this scan from your own device — phone, tablet, or laptop.",
            icon_name='wifi',
        )
        self.send_wifi_option.toggled.connect(self._on_option_toggled)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(24)
        cards_row.addStretch()
        cards_row.addWidget(self.print_option)
        cards_row.addWidget(self.send_wifi_option)
        cards_row.addStretch()
        body_layout.addLayout(cards_row)

        body_layout.addSpacing(16)

        self.continue_button = PrimaryButton("Continue")
        self.continue_button.setEnabled(False)
        self.continue_button.clicked.connect(self.continue_clicked.emit)

        continue_row = QHBoxLayout()
        continue_row.addStretch()
        continue_row.addWidget(self.continue_button)
        continue_row.addStretch()
        body_layout.addLayout(continue_row)

        body_layout.addSpacing(16)

        self.status_banner = StatusBanner()
        body_layout.addWidget(self.status_banner)

        body_layout.addStretch(2)

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.cancel_button, 0, Qt.AlignLeft)
        nav_row.addStretch()
        body_layout.addLayout(nav_row)

    def _build_thumbnail_strip(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(THUMBNAIL_HEIGHT + 24)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ border: 1px solid {COLORS['border']}; border-radius: 8px; }}")

        strip = QWidget()
        self._thumbnail_layout = QHBoxLayout(strip)
        self._thumbnail_layout.setContentsMargins(12, 12, 12, 12)
        self._thumbnail_layout.setSpacing(12)
        self._thumbnail_layout.addStretch()
        strip.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)

        scroll.setWidget(strip)
        return scroll

    def _on_option_toggled(self, key, is_selected):
        self.continue_button.setEnabled(bool(self.get_selected_keys()))
        self.destination_toggled.emit(key, is_selected)

    def clear_thumbnails(self):
        for label in self._thumbnail_labels:
            label.setParent(None)
        self._thumbnail_labels = []

    def add_thumbnail(self, page_number: int, pixmap):
        label = QLabel()
        label.setPixmap(pixmap)
        label.setStyleSheet(f"border: 1px solid {COLORS['border']}; border-radius: 6px;")
        label.setToolTip(f"Page {page_number}")
        # insert before the trailing stretch
        self._thumbnail_layout.insertWidget(self._thumbnail_layout.count() - 1, label)
        self._thumbnail_labels.append(label)

    def get_selected_keys(self) -> set:
        keys = set()
        if self.print_option.is_selected():
            keys.add('print')
        if self.send_wifi_option.is_selected():
            keys.add('send_wifi')
        return keys

    def reset_selection(self):
        self.print_option.set_selected(False)
        self.send_wifi_option.set_selected(False)
        self.continue_button.setEnabled(False)

    def set_continue_enabled(self, enabled: bool):
        self.continue_button.setEnabled(enabled)

    def set_summary(self, page_count: int):
        if page_count == 1:
            self.summary_label.setText("1 page scanned — choose what to do with it.")
        else:
            self.summary_label.setText(f"{page_count} pages scanned — choose what to do with them.")

    def show_status(self, message, is_error=True):
        self.status_banner.show_message(message, variant="error" if is_error else "success")

    def set_busy(self, busy: bool):
        self.print_option.setEnabled(not busy)
        self.send_wifi_option.setEnabled(not busy)
        self.continue_button.setEnabled(not busy and bool(self.get_selected_keys()))
