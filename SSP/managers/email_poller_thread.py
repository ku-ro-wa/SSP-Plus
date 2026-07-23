# managers/email_poller_thread.py
#
# Runs EmailAdapter.poll_inbox() on a fixed interval in a background thread.
# Plain threading.Thread rather than QThread — this isn't PyQt-signal-driven
# like db_threader/ink_analysis_threader, it's a backend service loop, same
# category as webapp_thread.py's WebAppThreadManager. Same start()/stop()
# shape as the other thread managers so it drops into main_app.py's
# __init__/cleanup() the same way.

import threading

from config import get_config
from database.db_manager import DatabaseManager
from managers.adapters.email_adapter import EmailAdapter
from managers.adapters.email_client import ImapClient, SmtpClient
from managers.session_manager import SessionManager

# Joining with a short fixed timeout rather than one tied to poll_interval:
# the thread is a daemon, so process exit was never blocked on it anyway,
# and a long poll_interval shouldn't make stop() hang waiting on a join.
_JOIN_TIMEOUT_SECONDS = 2.0


class EmailPollerThreadManager:
    def __init__(self, email_adapter: EmailAdapter, poll_interval_seconds: int):
        self.email_adapter = email_adapter
        self.poll_interval_seconds = poll_interval_seconds
        self.thread = None
        self._stop_event = threading.Event()

    @classmethod
    def from_config(cls, db_manager: DatabaseManager = None) -> "EmailPollerThreadManager":
        """Build the full ImapClient/SmtpClient/SessionManager/EmailAdapter chain from config.py/.env."""
        config = get_config()
        db_manager = db_manager or DatabaseManager()

        imap_client = ImapClient(
            host=config.email_imap_host,
            port=config.email_imap_port,
            username=config.email_user,
            password=config.email_password,
            use_ssl=config.email_use_ssl,
            mailbox=config.email_mailbox,
        )
        smtp_client = SmtpClient(
            host=config.email_smtp_host,
            port=config.email_smtp_port,
            username=config.email_user,
            password=config.email_password,
            use_ssl=config.email_use_ssl,
        )
        session_manager = SessionManager(db_manager)
        email_adapter = EmailAdapter(
            session_manager=session_manager,
            db_manager=db_manager,
            imap_client=imap_client,
            smtp_client=smtp_client,
            upload_dir=config.email_upload_dir,
            max_size_bytes=config.email_max_attachment_size_mb * 1024 * 1024,
            subject_keyword=config.email_subject_keyword,
            from_address=config.email_user,
        )
        return cls(email_adapter, config.email_poll_interval_seconds)

    def start(self):
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=_JOIN_TIMEOUT_SECONDS)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.email_adapter.poll_inbox()
            except Exception as e:
                # A single bad cycle (network blip, IMAP hiccup) shouldn't
                # kill the loop — log it and try again next interval.
                print(f"Error during email poll cycle: {e}")
            self._stop_event.wait(self.poll_interval_seconds)
