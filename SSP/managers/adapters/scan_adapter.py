# managers/adapters/scan_adapter.py
#
# Registers a scanner-composed PDF as a SessionManager session so it can be
# picked up (downloaded or emailed) from the phone-side redeem portal
# (webapp/routers/redeem.py). Mirrors wifi_adapter.py's division of labor —
# never mints its own OTP, just validates and hands off to create_session().

import os
import shutil
import uuid
from typing import Optional, Tuple

from managers.session_manager import Session

PDF_MAGIC = b"%PDF"


class ScanAdapter:
    def __init__(self, session_manager, upload_dir: str):
        self.session_manager = session_manager
        self.upload_dir = upload_dir
        os.makedirs(self.upload_dir, exist_ok=True)

    def handle_scan(
        self, pdf_path: str, filename: str = "scan.pdf"
    ) -> Tuple[bool, str, Optional[Session]]:
        """
        Copy an already-composed scan PDF into upload_dir and register a
        source='scan' session for it. Copies rather than moves — the
        scanner's own session directory (managers/scanner_manager.py) is
        cleaned up separately by its caller.
        """
        if not pdf_path or not os.path.isfile(pdf_path):
            return False, "Scan file not found", None

        with open(pdf_path, "rb") as f:
            header = f.read(len(PDF_MAGIC))
        if header != PDF_MAGIC:
            return False, "Not a valid PDF", None

        dest_path = os.path.join(self.upload_dir, f"{uuid.uuid4().hex}.pdf")
        shutil.copy2(pdf_path, dest_path)

        session = self.session_manager.create_session(
            source="scan",
            files=[{"path": dest_path, "original_filename": filename}],
        )
        return True, "Scan registered", session
