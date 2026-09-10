# ui/qr.py
#
# Render a string as a QR QPixmap for on-screen display. The Wi-Fi and email
# screens show one so a phone can jump to the upload portal / a mailto: link
# without retyping it. Display-only — kiosk-side QR *scanning* is a separate,
# unbuilt path (project_objectives.txt module 7 / LogicOwl scanner).

import io

import qrcode
from PyQt5.QtGui import QPixmap


def qr_pixmap(data: str, size: int = 180) -> QPixmap:
    """PNG QR of `data`, scaled to a `size`x`size` QPixmap."""
    buf = io.BytesIO()
    qrcode.make(data).save(buf, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue(), "PNG")
    return pixmap.scaled(size, size) if not pixmap.isNull() else pixmap
