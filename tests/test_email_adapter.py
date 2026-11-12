"""
Tests for EmailAdapter — pure logic, no real IMAP/SMTP server (greenmail or
otherwise) required. ImapClient/SmtpClient are replaced with in-memory fakes,
and SessionManager is wired to the same FakeDBManager used elsewhere, so
these exercise the full poll -> validate -> session -> reply path offline.
"""
import json
import os
import smtplib
from email.message import EmailMessage

from managers.adapters.email_adapter import EmailAdapter
from managers.session_manager import SessionManager
from tests.test_session_manager import FakeDBManager

PDF_BYTES = b"%PDF-1.4 fake pdf content"
SUBJECT_KEYWORD = "DEMO_TRIGGER"


def _make_raw_email(subject, pdf_bytes=None, sender="alice@example.com", message_id="<abc@test>",
                    extra_pdfs=()):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "kiosk@example.com"
    msg["Message-ID"] = message_id
    msg.set_content("body text")
    if pdf_bytes is not None:
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="doc.pdf")
    for i, extra in enumerate(extra_pdfs, start=2):
        msg.add_attachment(extra, maintype="application", subtype="pdf", filename=f"doc{i}.pdf")
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


def _make_adapter(tmp_path, imap_messages=None, uidvalidity=1, max_size_bytes=1024 * 1024,
                  max_total_bytes=50 * 1024 * 1024):
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
        max_total_bytes=max_total_bytes,
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
        with open(result.session.files[0]['path'], "rb") as f:
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

    def test_two_pdfs_become_one_session_with_both_files(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path, imap_messages={
            1: _make_raw_email(f"{SUBJECT_KEYWORD}: two", PDF_BYTES, extra_pdfs=[PDF_BYTES + b"2"]),
        })

        assert adapter.poll_inbox() == 1
        assert len(os.listdir(adapter.upload_dir)) == 2
        assert len(db.email_log) == 1
        assert len(db.sessions) == 1
        files = json.loads(next(iter(db.sessions.values()))["files"])
        assert [f["original_filename"] for f in files] == ["doc.pdf", "doc2.pdf"]

    def test_one_bad_pdf_rejects_whole_email_and_writes_nothing(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path)
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: mixed", PDF_BYTES, extra_pdfs=[b"not a pdf"])

        assert adapter._handle_message(raw).outcome == "rejected_attachment"
        assert os.listdir(adapter.upload_dir) == []

    def test_total_over_cap_rejects_whole_email_and_writes_nothing(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path, max_total_bytes=len(PDF_BYTES) * 2 - 1)
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: big", PDF_BYTES, extra_pdfs=[PDF_BYTES])

        assert adapter._handle_message(raw).outcome == "rejected_attachment"
        assert os.listdir(adapter.upload_dir) == []

    def test_total_exactly_at_cap_is_accepted(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path, max_total_bytes=len(PDF_BYTES) * 2)
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: ok", PDF_BYTES, extra_pdfs=[PDF_BYTES])

        assert adapter._handle_message(raw).outcome == "accepted"

    def test_reply_for_two_pdfs_carries_one_otp_and_one_qr(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path, imap_messages={
            1: _make_raw_email(f"{SUBJECT_KEYWORD}: two", PDF_BYTES, extra_pdfs=[PDF_BYTES]),
        })
        adapter.poll_inbox()

        reply = smtp.sent[0]
        assert len(list(reply.iter_attachments())) == 1
        assert reply.get_body().get_content().count("Your pickup code is:") == 1

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


class TestReplyFailure:
    def _failing_smtp(self, adapter, exc, times=1):
        calls = {"n": 0}
        real = adapter.smtp_client.send

        def send(msg):
            calls["n"] += 1
            if calls["n"] <= times:
                raise exc
            real(msg)

        adapter.smtp_client.send = send

    def test_failed_send_leaves_message_unlogged_and_unseen_then_retries(self, tmp_path):
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: x", PDF_BYTES)
        adapter, db, imap, smtp = _make_adapter(tmp_path, imap_messages={1: raw})
        self._failing_smtp(adapter, OSError("name resolution"))

        assert adapter.poll_inbox() == 0
        assert 1 not in imap.seen
        assert db.get_email_intake_log(1, 1) is None
        assert len(db.sessions) == 0
        assert os.listdir(adapter.upload_dir) == []

        assert adapter.poll_inbox() == 1
        assert 1 in imap.seen
        assert len(smtp.sent) == 1
        assert len(db.sessions) == 1

    def test_failure_does_not_block_other_messages(self, tmp_path):
        a = _make_raw_email(f"{SUBJECT_KEYWORD}: a", PDF_BYTES, message_id="<a@t>")
        b = _make_raw_email("nope", PDF_BYTES, message_id="<b@t>")
        adapter, db, imap, smtp = _make_adapter(tmp_path, imap_messages={1: a, 2: b})
        self._failing_smtp(adapter, OSError("down"))

        assert adapter.poll_inbox() == 1
        assert db.get_email_intake_log(1, 2)["outcome"] == "rejected_subject"
        assert db.get_email_intake_log(1, 1) is None

    def test_refused_recipient_is_logged_as_error_and_not_retried(self, tmp_path):
        raw = _make_raw_email(f"{SUBJECT_KEYWORD}: x", PDF_BYTES)
        adapter, db, imap, smtp = _make_adapter(tmp_path, imap_messages={1: raw})
        self._failing_smtp(adapter, smtplib.SMTPRecipientsRefused({"a@b": (550, b"no")}))

        assert adapter.poll_inbox() == 1
        assert 1 in imap.seen
        assert db.get_email_intake_log(1, 1)["outcome"] == "error"
        assert len(db.sessions) == 0


class TestSendResponse:
    def test_email_contains_otp_and_qr_attachment(self, tmp_path):
        adapter, db, imap, smtp = _make_adapter(tmp_path)
        session = adapter.session_manager.create_session(
            "email", [{"path": "/tmp/fake.pdf", "original_filename": "fake.pdf"}]
        )

        adapter.send_response("bob@example.com", session)

        assert len(smtp.sent) == 1
        sent = smtp.sent[0]
        assert sent["To"] == "bob@example.com"
        body = sent.get_body(preferencelist=("plain",))
        assert session.otp in body.get_content()
        assert "brightness" in body.get_content().lower()
        attachments = list(sent.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_content() == session.qr_bytes
