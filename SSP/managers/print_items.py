"""
The files of one print transaction (#119).

A transaction prints one or more PDFs from the customer's Session, each with
its own pages, copies and color mode. `PrintItem` is one of them; the list of
items is in print order (the order the customer ticked them).
"""
import os
from dataclasses import dataclass
from typing import Optional

MAX_FILES_PER_TRANSACTION = 10


@dataclass
class PrintItem:
    pdf_data: dict                       # the file_browser dict: 'path', 'filename', 'pages', ...
    pages: list                          # selected 1-based pages, ascending
    copies: int = 1
    color_mode: str = "Black and White"  # or "Color"
    cost: float = 0.0                    # this file's price, all copies
    analysis: Optional[dict] = None      # this file's page analysis (pricing counts)

    @property
    def path(self):
        return self.pdf_data.get('path')

    @property
    def file_name(self):
        """The name the customer sees: the original filename, not the stored <uuid>.pdf."""
        return self.pdf_data.get('filename') or os.path.basename(self.pdf_data.get('path') or '')

    @property
    def sheets(self):
        return len(self.pages) * self.copies


def total_sheets(items):
    return sum(item.sheets for item in items)


def summary_columns(items):
    """The transactions row's file_name/pages/copies/color_mode/file_count.

    One item is exactly what was logged before multi-file printing. Several:
    pages is the total sheets and copies is 1, so pages * copies is still the
    sheets printed for any query that multiplies them."""
    items = list(items)
    if len(items) == 1:
        item = items[0]
        return {'file_name': item.file_name, 'pages': len(item.pages),
                'copies': item.copies, 'color_mode': item.color_mode, 'file_count': 1}
    modes = {item.color_mode for item in items}
    return {'file_name': f"{items[0].file_name} +{len(items) - 1} more",
            'pages': total_sheets(items), 'copies': 1,
            'color_mode': modes.pop() if len(modes) == 1 else "Mixed",
            'file_count': len(items)}
