# managers/adapters/email_adapter.py
#
# Polls a dedicated inbox for print-request emails (subject keyword + PDF
# attachment per project_objectives.txt #6), hands accepted attachments to
# SessionManager, and emails the OTP/QR back to the sender. Talks to IMAP/SMTP
# only through ImapClient/SmtpClient (email_client.py) — greenmail (dev) and
# the real dedicated Gmail account are just different EMAIL_* config values,
# no branching here. Session/OTP/QR generation is entirely SessionManager's
# job: this adapter never mints its own OTP, it only delivers the one
# create_session() already generated (mirrors wifi_adapter's division of
# labor with session_manager).

import email
import os
import shutil
import smtplib
import uuid
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import EmailMessage
from typing import Optional

from managers.session_manager import Session

PDF_MAGIC = b"%PDF"
DEFAULT_MAX_TOTAL_BYTES = 50 * 1024 * 1024


def attachment_filename(part) -> Optional[str]:
    """The attachment's filename as the sender saw it. get_filename() decodes
    RFC 2231 (filename*=) but leaves RFC 2047 encoded-words (=?UTF-8?B?...?=),
    which many mail clients use for non-ASCII names, so decode those here."""
    name = part.get_filename()
    if not name:
        return None
    try:
        return str(make_header(decode_header(name)))
    except Exception:
        return name


@dataclass
class MessageResult:
    outcome: str  # 'accepted' | 'rejected_subject' | 'rejected_attachment' | 'error'
    session: Optional[Session]
    message_id: Optional[str]
    sender: Optional[str]


class EmailAdapter:
    def __init__(
        self, session_manager, db_manager, imap_client, smtp_client,
        upload_dir: str, max_size_bytes: int, subject_keyword: str, from_address: str,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    ):
        self.session_manager = session_manager
        self.db_manager = db_manager
        self.imap_client = imap_client
        self.smtp_client = smtp_client
        self.upload_dir = upload_dir
        self.max_size_bytes = max_size_bytes
        self.max_total_bytes = max_total_bytes
        self.subject_keyword = subject_keyword
        self.from_address = from_address
        os.makedirs(self.upload_dir, exist_ok=True)

    def poll_inbox(self) -> int:
        """
        Run one poll cycle: fetch unseen messages, process each, and email a
        reply to accepted ones. Returns the number of messages newly logged.
        """
        processed = 0
        with self.imap_client as client:
            uidvalidity, uids = client.search_unseen()

            for uid in uids:
                # Cheap pre-check: if a prior cycle already logged this uid,
                # skip it even if mark_seen() didn't stick (e.g. a crash
                # between logging and marking Seen) — without this, that
                # message would look UNSEEN again and get double-processed,
                # creating a second session for the same email.
                if self.db_manager.get_email_intake_log(uidvalidity, uid):
                    continue

                raw = client.fetch(uid)
                result = self._handle_message(raw)

                # Reply BEFORE logging/marking Seen. If the send fails (flaky
                # 4G, DNS, SMTP hiccup) the session is discarded and the email
                # stays unlogged and UNSEEN, so the next poll retries it —
                # otherwise the sender would never get their code.
                if result.outcome == "accepted" and result.session and result.sender:
                    try:
                        self.send_response(result.sender, result.session)
                    except smtplib.SMTPRecipientsRefused as e:
                        # Permanent: retrying can't help. Log it and move on.
                        print(f"Email reply to {result.sender!r} refused, giving up: {e}")
                        self._discard_session(result.session)
                        result = MessageResult("error", None, result.message_id, result.sender)
                    except Exception as e:
                        print(f"Email reply to {result.sender!r} failed, will retry next poll: {e}")
                        self._discard_session(result.session)
                        continue

                inserted = self.db_manager.log_email_intake(
                    uidvalidity=uidvalidity,
                    uid=uid,
                    message_id=result.message_id,
                    outcome=result.outcome,
                    session_id=result.session.session_id if result.session else None,
                )
                if not inserted:
                    continue  # lost a race with another poller on this uid

                client.mark_seen(uid)
                processed += 1

        return processed

    def _discard_session(self, session: Session):
        """Undo an accepted message whose reply couldn't be sent: files and DB row."""
        for f in session.files:
            try:
                path = f["path"]
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.isfile(path):
                    os.remove(path)
            except OSError as e:
                print(f"Error removing file of discarded session: {e}")
        self.db_manager.delete_session(session.session_id)

    def _handle_message(self, raw: bytes) -> MessageResult:
        """
        Parse one raw RFC822 message, validate subject + PDF attachment, and
        on success save the attachment and register a session. Never raises —
        unexpected failures are reported as outcome='error'.
        """
        message_id = None
        sender = None
        try:
            msg = email.message_from_bytes(raw)
            message_id = msg.get("Message-ID")
            sender = msg.get("From")
            subject = str(msg.get("Subject", ""))

            if self.subject_keyword.lower() not in subject.lower():
                return MessageResult("rejected_subject", None, message_id, sender)

            # Validate every PDF before writing any, so a rejection leaves
            # nothing behind in the upload directory.
            pdfs = []  # (bytes, original filename)
            total = 0
            for part in msg.walk():
                if part.get_content_type() != "application/pdf":
                    continue
                data = part.get_payload(decode=True) or b""
                total += len(data)
                if (
                    not data
                    or len(data) > self.max_size_bytes
                    or total > self.max_total_bytes
                    or not data.startswith(PDF_MAGIC)
                ):
                    return MessageResult("rejected_attachment", None, message_id, sender)
                pdfs.append((data, attachment_filename(part)))
            if not pdfs:
                return MessageResult("rejected_attachment", None, message_id, sender)

            files = []
            try:
                for data, name in pdfs:
                    dest_path = os.path.join(self.upload_dir, f"{uuid.uuid4().hex}.pdf")
                    files.append({"path": dest_path, "original_filename": name})
                    with open(dest_path, "wb") as f:
                        f.write(data)
                session = self.session_manager.create_session(
                    source="email", files=files, metadata=sender,
                )
            except Exception:
                for f in files:
                    try:
                        os.remove(f["path"])
                    except OSError:
                        pass
                raise
            return MessageResult("accepted", session, message_id, sender)

        except Exception as e:
            print(f"Error handling email message: {e}")
            return MessageResult("error", None, message_id, sender)

    def send_response(self, recipient_email: str, session: Session):
        """Email the OTP + QR code (already generated by SessionManager) back to the sender."""
        msg = EmailMessage()
        msg["Subject"] = "Your OTP and QR Code"
        msg["From"] = self.from_address
        msg["To"] = recipient_email
        msg.set_content(
            f"Your pickup code is: {session.otp}\n\n"
            "Scan the attached QR code at the kiosk, or enter the code manually.\n"
            "Turn your screen brightness all the way up so the kiosk can read the QR image.\n"
            f"This code expires at {session.expires_at.isoformat()}."
        )
        msg.add_attachment(session.qr_bytes, maintype="image", subtype="png", filename="qr.png")
        self.smtp_client.send(msg)
