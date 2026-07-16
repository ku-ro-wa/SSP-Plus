# managers/adapters/wifi_adapter.py
#
# Validates files coming through the Wi-Fi captive-portal upload (magic
# bytes + MIME per project_objectives.txt #5) and hands accepted ones to
# SessionManager. Deliberately has no FastAPI import: webapp/routers/upload.py
# is the only layer that knows about HTTP, so this class takes plain bytes
# in and returns a plain result, testable the same way as
# PaymentAlgorithmManager (construct with a fake collaborator, call methods).
 
import os
import uuid
from typing import BinaryIO, Optional, Tuple

from managers.session_manager import Session

PDF_MAGIC = b"%PDF"
PDF_MIME_TYPES = {"application/pdf"}


class WifiAdapter:
    def __init__(self, session_manager, upload_dir: str, max_size_bytes: int):
        self.session_manager = session_manager
        self.upload_dir = upload_dir
        self.max_size_bytes = max_size_bytes
        os.makedirs(self.upload_dir, exist_ok=True)

    def handle_upload(
        self, file_obj: BinaryIO, filename: str, content_type: str, metadata: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Session]]:
        """
        Validate an uploaded file and, on success, register it with
        SessionManager. Returns (success, message, session).
        """
        mime = (content_type or "").split(";", 1)[0].strip().lower()
        if mime not in PDF_MIME_TYPES:
            return False, f"Unsupported content type: {content_type}", None

        data = file_obj.read(self.max_size_bytes + 1)
        if len(data) > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            return False, f"File exceeds the {max_mb:.0f}MB limit", None
        if not data:
            return False, "Empty file", None
        if not data.startswith(PDF_MAGIC):
            return False, "File is not a valid PDF (missing %PDF header)", None

        # Filename is stored as metadata only, never used to build a path —
        # the on-disk name is always a fresh UUID so a malicious filename
        # (e.g. "../../etc/passwd") can't escape upload_dir.
        dest_path = os.path.join(self.upload_dir, f"{uuid.uuid4().hex}.pdf")
        with open(dest_path, "wb") as f:
            f.write(data)

        session = self.session_manager.create_session(
            source="wifi",
            file_path=dest_path,
            original_filename=filename,
            metadata=metadata,
        )
        return True, "Upload accepted", session
