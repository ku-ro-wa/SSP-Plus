# screens/scan_destination/thumbnail_thread.py
#
# Renders each page of the composed scan PDF to a QPixmap off the main
# thread, so the preview strip on scan_destination doesn't block the UI.
# Mirrors screens/file_browser/view.py's PDFPreviewThread (same fitz ->
# QImage -> QPixmap approach) but kept local to this screen rather than
# imported across screen packages, matching the rest of the codebase's
# convention of screens not reaching into each other's view modules.
# Runs unmodified against SIM_MODE's placeholder pages too, since it just
# renders whatever PDF ScannerManager.finish() produced.

import fitz  # PyMuPDF
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap


class ThumbnailRenderThread(QThread):
    thumbnail_ready = pyqtSignal(int, QPixmap)  # 1-indexed page number
    render_failed = pyqtSignal(str)

    def __init__(self, pdf_path: str, target_height_px: int = 220):
        super().__init__()
        self.pdf_path = pdf_path
        self.target_height_px = target_height_px
        self.running = True

    def run(self):
        try:
            doc = fitz.open(self.pdf_path)
            for i, page in enumerate(doc):
                if not self.running:
                    break
                scale = self.target_height_px / max(1.0, page.rect.height)
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                self.thumbnail_ready.emit(i + 1, QPixmap.fromImage(qimg.copy()))
            doc.close()
        except Exception as e:
            self.render_failed.emit(str(e))

    def stop(self):
        self.running = False
