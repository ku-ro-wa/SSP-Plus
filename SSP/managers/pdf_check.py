"""Decide whether a PDF can actually be printed, before the customer is shown it.

A file that passes this check opens in PyMuPDF, has at least one page, and every page
loads, which is what PrinterThread needs to build its print job. A damaged file that
MuPDF repairs on open still passes, because it previews and prints fine.
"""
from typing import Optional, Tuple

import fitz  # PyMuPDF


def check_pdf(path: str) -> Tuple[int, Optional[str]]:
    """Returns (page_count, error). error is None when the file can be printed;
    otherwise it's a short reason the customer can be shown and page_count is 0."""
    try:
        doc = fitz.open(path)
    except Exception as e:
        print(f"⚠️ Can't open PDF {path}: {e}")
        return 0, "The file is damaged or isn't really a PDF."

    try:
        if doc.needs_pass:
            return 0, "The file is password-protected."
        page_count = len(doc)
        if page_count < 1:
            return 0, "The file has no pages."
        for i in range(page_count):
            doc.load_page(i)
        return page_count, None
    except Exception as e:
        print(f"⚠️ Can't read PDF {path}: {e}")
        return 0, "The file is damaged or isn't really a PDF."
    finally:
        doc.close()
