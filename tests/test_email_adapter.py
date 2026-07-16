"""
Tests for EmailAdapter — pure logic, no real IMAP/SMTP server (greenmail or
otherwise) required. ImapClient/SmtpClient are replaced with in-memory fakes,
and SessionManager is wired to the same FakeDBManager used elsewhere, so
these exercise the full poll -> validate -> session -> reply path offline.
"""
from email.message import EmailMessage

from managers.adapters.email_adapter import EmailAdapter
from managers.session_manager import SessionManager
from tests.test_session_manager import FakeDBManager

PDF_BYTES = b"%PDF-1.4 fake pdf content"
SUBJECT_KEYWORD = "DEMO_TRIGGER"


def _make_raw_email(subject, pdf_bytes=None, sender="alice@example.com", message_id="<abc@test>"):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "kiosk@example.com"
    msg["Message-ID"] = message_id
    msg.set_content("body text")
    if pdf_bytes is not None:
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="doc.pdf")
    return msg.as_bytes()


class FakeImapClient:
    """messages: dict[uid] -> raw RFC822 bytes."""

    def __init__(self, uidvalidity, messages):
        self.uidvalidity = uidvalidity
        self.messages = messages
        self.seen = set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def search_unseen(self):
        unseen = [uid for uid in self.messages if uid not in self.seen]
        return self.uidvalidity, sorted(unseen)

    def fetch(self, uid):
        return self.messages[uid]

    def mark_seen(self, uid):
        self.seen.add(uid)


class FakeSmtpClient:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)


def _make_adapter(tmp_path, imap_messages=None, uidvalidity=1, max_size_bytes=1024 * 1024):
    db = FakeDBManager()
    session_manager = SessionManager(db)
    imap = FakeImapClient(uidvalidity, imap_messages or {})
    smtp = FakeSmtpClient()
    adapter = EmailAdapter(
        session_manager=session_manager,
        db_manager=db,
        imap_client=imap,
        smtp_client=smtp,
        upload_dir=str(tmp_path / "uploads"),
        max_size_bytes=max_size_bytes,
        subject_keyword=SUBJECT_KEYWORD,
        from_address="kiosk@example.com",
    )
    return adapter, db, imap, smtp


class TestHandleMessage:
    def test_accepts_valid_trigger_email(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path)
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: print this", PDF_BYTES)

        result = adapter._handle_message(raw)

        assert result.outcome == "accepted"
        assert result.session is not None
        assert result.sender == "alice@example.com"
        with open(result.session.file_path, "rb") as f:
            assert f.read() == PDF_BYTES

    def test_subject_match_is_case_insensitive(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path)
        raw = _make_raw_email("demo_trigger: print this", PDF_BYTES)

        result = adapter._handle_message(raw)
        assert result.outcome == "accepted"

    def test_rejects_missing_keyword(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path)
        raw = _make_raw_email("please print my file", PDF_BYTES)

        result = adapter._handle_message(raw)
        assert result.outcome == "rejected_subject"
        assert result.session is None

    def test_rejects_missing_attachment(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path)
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: no file here")

        result = adapter._handle_message(raw)
        assert result.outcome == "rejected_attachment"

    def test_rejects_attachment_failing_magic_bytes(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path)
        # A part with the right MIME type but wrong content — Content-Type
        # is just as spoofable in email as the multipart header wifi_adapter
        # checks, so the %PDF check applies here too.
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: spoofed", b"not really a pdf")

        result = adapter._handle_message(raw)
        assert result.outcome == "rejected_attachment"

    def test_rejects_oversized_attachment(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path, max_size_bytes=10)
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: big file", PDF_BYTES)

        result = adapter._handle_message(raw)
        assert result.outcome == "rejected_attachment"

    def test_error_outcome_on_session_creation_failure(self, tmp_path, monkeypatch):
        adapter, db, imap, smtp = _make_adapter(tmp_path)

        def _boom(*args, **kwargs):
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(adapter.session_manager, "create_session", _boom)
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: print this", PDF_BYTES)

        result = adapter._handle_message(raw)
        assert result.outcome == "error"
        assert result.session is None
        assert result.sender == "alice@example.com"  # still captured before the failure


class TestPollInbox:
    def test_accepted_message_gets_logged_marked_seen_and_replied_to(self, tmp_path):
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: print this", PDF_BYTES, message_id="<msg1@test>")
        adapter, db, imap, smtp = _make_adapter(tmp_path, imap_messages={101: raw})

        processed = adapter.poll_inbox()

        assert processed == 1
        assert 101 in imap.seen
        log = db.get_email_intake_log(1, 101)
        assert log["outcome"] == "accepted"
        assert log["message_id"] == "<msg1@test>"
        assert len(smtp.sent) == 1
        assert smtp.sent[0]["To"] == "alice@example.com"

    def test_rejected_message_is_logged_and_marked_seen_but_no_reply_sent(self, tmp_path):
        raw = _make_raw_email("no keyword here", PDF_BYTES)
        adapter, db, imap, smtp = _make_adapter(tmp_path, imap_messages={202: raw})

        processed = adapter.poll_inbox()

        assert processed == 1
        assert 202 in imap.seen
        assert db.get_email_intake_log(1, 202)["outcome"] == "rejected_subject"
        assert smtp.sent == []

    def test_already_logged_uid_is_skipped_on_next_poll(self, tmp_path):
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: print this", PDF_BYTES)
        adapter, db, imap, smtp = _make_adapter(tmp_path, imap_messages={303: raw})

        adapter.poll_inbox()
        sessions_after_first_poll = len(db.sessions)

        # Simulate mark_seen not sticking (e.g. crash/network drop) — the
        # message still looks UNSEEN, but the log row is already there.
        imap.seen.discard(303)
        processed_second = adapter.poll_inbox()

        assert processed_second == 0
        assert len(db.sessions) == sessions_after_first_poll  # no duplicate session
        assert len(smtp.sent) == 1  # no duplicate reply either

    def test_multiple_unseen_messages_all_processed(self, tmp_path):
        accepted = _make_raw_email(f"{SUBJECT_KEYWORD}: one", PDF_BYTES, message_id="<a@test>")
        rejected = _make_raw_email("nope", PDF_BYTES, message_id="<b@test>")
        adapter, db, imap, smtp = _make_adapter(tmp_path, imap_messages={1: accepted, 2: rejected})

        processed = adapter.poll_inbox()

        assert processed == 2
        assert len(smtp.sent) == 1


class TestSendResponse:
    def test_email_contains_otp_and_qr_attachment(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path)
        session = adapter.session_manager.create_session("email", "/tmp/fake.pdf")

        adapter.send_response("bob@example.com", session)

        assert len(smtp.sent) == 1
        sent = smtp.sent[0]
        assert sent["To"] == "bob@example.com"
        body = sent.get_body(preferencelist=("plain",))
        assert session.otp in body.get_content()
        attachments = list(sent.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_content() == session.qr_bytes
