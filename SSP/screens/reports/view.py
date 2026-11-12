# screens/reports/view.py

from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (QButtonGroup, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from ui.theme import COLORS, FONT
from ui.widgets import BackButton, Header, nav_row

from .model import COLLECTIONS_SHOWN, RANGES

# The dashboard's chart (admin_dashboard/templates/accounting.html): revenue black
# on the left scale, transactions grey on the right one, one group per Source.
REVENUE_COLOUR = "#000000"
TRANSACTIONS_COLOUR = "#999999"


def peso(amount):
    return f"₱{(amount or 0):.2f}"


def _text(text, size="size_md", colour="text", weight=600, align=None):
    label = QLabel(text)
    label.setStyleSheet(f"color: {COLORS[colour]}; font-size: {FONT[size]}px; font-weight: {weight};")
    if align:
        label.setAlignment(align)
    return label


class SourceChart(QWidget):
    """Revenue and transaction count per Source as grouped bars, drawn with QPainter.
    Two scales like the dashboard's chart: revenue on the left, transactions on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sources = []
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_sources(self, sources):
        self.sources = list(sources)
        self.update()

    @staticmethod
    def _top(values):
        """A scale maximum above the largest value (1 when everything is zero)."""
        biggest = max([v for v in values] + [0])
        return biggest if biggest > 0 else 1

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        small = QFont(self.font())
        small.setPixelSize(FONT["size_sm"])
        p.setFont(small)
        metrics = p.fontMetrics()

        legend_h = metrics.height() + 6
        label_h = metrics.height() + 6
        left = metrics.horizontalAdvance("00000") + 8
        right = metrics.horizontalAdvance("00000") + 8
        plot = QRectF(left, legend_h, self.width() - left - right, self.height() - legend_h - label_h)

        revenue = [s["revenue"] for s in self.sources]
        counts = [s["transaction_count"] for s in self.sources]
        rev_top, count_top = self._top(revenue), self._top(counts)

        # Baseline and the two scales' maximums.
        p.setPen(QPen(QColor(COLORS["border_strong"]), 1))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())
        p.setPen(QColor(COLORS["text_muted"]))
        p.drawText(QRectF(0, plot.top() - 8, left - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{rev_top:g}")
        p.drawText(QRectF(plot.right() + 6, plot.top() - 8, right - 6, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{count_top:g}")

        # Legend.
        x = left
        for colour, name in ((REVENUE_COLOUR, "Revenue (₱)"), (TRANSACTIONS_COLOUR, "Transactions")):
            p.fillRect(QRectF(x, 5, 12, 12), QColor(colour))
            p.setPen(QColor(COLORS["text"]))
            p.drawText(QRectF(x + 18, 0, 200, legend_h), Qt.AlignLeft | Qt.AlignVCenter, name)
            x += 18 + metrics.horizontalAdvance(name) + 24

        if not self.sources:
            return
        group = plot.width() / len(self.sources)
        bar = min(48.0, group / 4)
        for i, source in enumerate(self.sources):
            centre = plot.left() + group * (i + 0.5)
            for offset, value, top, colour in ((-bar, source["revenue"], rev_top, REVENUE_COLOUR),
                                               (0, source["transaction_count"], count_top, TRANSACTIONS_COLOUR)):
                height = plot.height() * value / top
                p.fillRect(QRectF(centre + offset, plot.bottom() - height, bar - 2, height), QColor(colour))
            p.setPen(QColor(COLORS["text"]))
            p.drawText(QRectF(centre - group / 2, plot.bottom() + 4, group, label_h),
                       Qt.AlignHCenter | Qt.AlignTop, source["source"])


class ReportsScreenView(QWidget):
    """Range buttons, a per-Source table and chart, change and Vouchers, collections.
    No logic. Kept within 800 logical px tall (tests/test_screen_render.py)."""

    back_clicked = pyqtSignal()
    range_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.range_buttons = {}
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(Header())

        body = QWidget()
        body.setStyleSheet(f"background-color: {COLORS['bg']};")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(40, 20, 40, 12)
        layout.setSpacing(12)
        outer.addWidget(body, 1)

        top = QHBoxLayout()
        top.addWidget(_text("Reports", "size_lg", weight=700))
        top.addStretch(1)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for label, key in RANGES:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(44)
            button.setMinimumWidth(130)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(self._range_qss())
            button.clicked.connect(lambda _checked, k=key: self.range_selected.emit(k))
            group.addButton(button)
            self.range_buttons[key] = button
            top.addWidget(button)
        layout.addLayout(top)

        columns = QHBoxLayout()
        columns.setSpacing(32)
        layout.addLayout(columns, 1)

        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(_text("Revenue per Source", "size_md", weight=700))
        self.table = QGridLayout()
        self.table.setHorizontalSpacing(24)
        self.table.setVerticalSpacing(4)
        left.addLayout(self.table)
        self.chart = SourceChart()
        left.addWidget(self.chart, 1)
        columns.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(_text("Change and Vouchers", "size_md", weight=700))
        self.voucher_values = {}
        vouchers = QGridLayout()
        vouchers.setHorizontalSpacing(24)
        vouchers.setVerticalSpacing(4)
        for row, (key, label) in enumerate((("change_dispensed", "Change dispensed"),
                                            ("voucher_issued", "Voucher value issued"),
                                            ("voucher_applied", "Vouchers Applied"),
                                            ("liability", "Outstanding Voucher liability"))):
            vouchers.addWidget(_text(label, colour="text_secondary"), row, 0)
            value = _text("", align=Qt.AlignRight)
            self.voucher_values[key] = value
            vouchers.addWidget(value, row, 1)
        right.addLayout(vouchers)
        self.liability_note = _text("Liability is as of now, whatever the range.", "size_sm", "text_muted")
        right.addWidget(self.liability_note)

        right.addSpacing(8)
        right.addWidget(_text("Collections", "size_md", weight=700))
        self.collections_layout = QGridLayout()
        self.collections_layout.setHorizontalSpacing(16)
        self.collections_layout.setVerticalSpacing(4)
        right.addLayout(self.collections_layout)
        self.since_last = _text("")
        self.since_last.setWordWrap(True)
        right.addWidget(self.since_last)
        right.addStretch(1)
        columns.addLayout(right, 2)

        self.back_button = BackButton("Back to Admin")
        layout.addLayout(nav_row(self.back_button))
        self.back_button.clicked.connect(self.back_clicked.emit)

    @staticmethod
    def _range_qss():
        return (
            f"QPushButton {{ background: {COLORS['bg']}; color: {COLORS['text']}; font-size: {FONT['size_md']}px;"
            f" font-weight: 600; border: 1px solid {COLORS['border_strong']}; border-radius: 8px; padding: 0 16px; }}"
            f"QPushButton:checked {{ background: {COLORS['primary']}; color: #FFFFFF; border-color: {COLORS['primary']}; }}"
        )

    @staticmethod
    def _clear(grid):
        while grid.count():
            item = grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def render(self, report):
        """Show `report` (ReportsModel.report())."""
        self.range_buttons[report["range"]].setChecked(True)

        self._clear(self.table)
        for col, (name, align) in enumerate((("Source", Qt.AlignLeft), ("Transactions", Qt.AlignRight),
                                             ("Revenue", Qt.AlignRight))):
            self.table.addWidget(_text(name, "size_sm", "text_muted", align=align), 0, col)
        for row, source in enumerate(report["sources"], start=1):
            self.table.addWidget(_text(source["source"]), row, 0)
            self.table.addWidget(_text(str(source["transaction_count"]), align=Qt.AlignRight), row, 1)
            self.table.addWidget(_text(peso(source["revenue"]), align=Qt.AlignRight), row, 2)
        self.chart.set_sources(report["sources"])

        for key, label in self.voucher_values.items():
            label.setText(peso(report["vouchers"][key]))

        cash = report["cash"]
        self._clear(self.collections_layout)
        shown = cash["collections"][:COLLECTIONS_SHOWN]
        if not shown:
            self.collections_layout.addWidget(_text("No collections recorded yet.", colour="text_secondary"), 0, 0)
        for row, collection in enumerate(shown):
            breakdown = ", ".join(f"₱{i['denomination']:g} × {i['count']}" for i in collection["items"])
            self.collections_layout.addWidget(_text(str(collection["collected_at"])[:16]), row, 0)
            self.collections_layout.addWidget(_text(breakdown, "size_sm", "text_secondary"), row, 1)
            self.collections_layout.addWidget(_text(peso(collection["total"]), align=Qt.AlignRight), row, 2)
        suffix = "" if cash["last_collected_at"] else " (none yet, so all time)"
        self.since_last.setText(f"Revenue since the last collection{suffix}: {peso(cash['revenue_since_last'])}")
