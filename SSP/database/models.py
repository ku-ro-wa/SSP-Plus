import os
import sqlite3
from datetime import datetime


def _column_exists(cursor, table, column):
    """Whether `column` is present on `table`, via PRAGMA table_info (SQLite
    has no ADD COLUMN IF NOT EXISTS, so callers use this to stay idempotent)."""
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _add_column_if_missing(cursor, table, column, column_def):
    """Idempotently add `column` to an already-existing `table`. Safe to call
    against a table created fresh this run (no-op, since CREATE TABLE never
    defines this column itself) or one that predates the column (adds it
    without touching existing rows)."""
    if not _column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")


def init_db(db_path=None):
    """Initialize the database and create tables if they don't exist"""
    if db_path is None:
        # Get absolute path to database directory
        base_dir = os.path.dirname(os.path.dirname(__file__))
        db_dir = os.path.join(base_dir, 'database')
        db_path = os.path.join(db_dir, 'ssp_database.db')
        os.makedirs(db_dir, exist_ok=True)

    print(f"Database path: {db_path}")

    # Connect to database (creates it if it doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Creating database tables...")

    # Create Transactions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME NOT NULL,
        file_name TEXT NOT NULL,
        pages INTEGER NOT NULL,
        copies INTEGER NOT NULL,
        color_mode TEXT NOT NULL,
        total_cost REAL NOT NULL,
        amount_paid REAL NOT NULL,
        change_given REAL NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT
    )
    ''')
    print("OK - Created transactions table")

    # Source column (which intake path a transaction came through — see
    # CONTEXT.md's Source term: usb/wifi/email/scanner). Added via migration
    # rather than the CREATE TABLE above so the same idempotent path handles
    # both a brand-new table and a pre-existing one that predates this column.
    _add_column_if_missing(cursor, 'transactions', 'source', 'TEXT')
    print("OK - Ensured transactions.source column")

    # Create CashInventory table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cash_inventory (
        denomination REAL PRIMARY KEY,
        count INTEGER NOT NULL,
        type TEXT NOT NULL,
        last_updated DATETIME NOT NULL
    )
    ''')
    print("OK - Created cash_inventory table")

    # Create ErrorLog table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS error_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME NOT NULL,
        error_type TEXT NOT NULL,
        error_message TEXT NOT NULL,
        screen_name TEXT NOT NULL,
        resolved BOOLEAN DEFAULT FALSE
    )
    ''')
    print("OK - Created error_log table")

    # Create PrinterStatus table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS printer_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME NOT NULL,
        paper_count INTEGER NOT NULL,
        ink_level INTEGER,
        status TEXT NOT NULL
    )
    ''')
    print("OK - Created printer_status table")

    # Create CMYK Ink Levels table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cmyk_ink_levels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME NOT NULL,
        cyan_level REAL NOT NULL,
        magenta_level REAL NOT NULL,
        yellow_level REAL NOT NULL,
        black_level REAL NOT NULL,
        last_updated DATETIME NOT NULL
    )
    ''')
    print("OK - Created cmyk_ink_levels table")

    # Create Settings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    ''')
    print("OK - Created settings table")

    # Create Sessions table (OTP + QR sessions for Wi-Fi/email intake — see managers/session_manager.py)
    # `files` is a JSON-encoded list of {"path": ..., "original_filename": ...}
    # objects (one session can carry several uploaded files) rather than a
    # child table — session file counts are small and nothing needs to query
    # individual files across sessions.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE NOT NULL,
        otp_hash TEXT NOT NULL,
        source TEXT NOT NULL,
        files TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL,
        expires_at DATETIME NOT NULL,
        metadata TEXT
    )
    ''')
    print("OK - Created sessions table")

    # Create Email Intake Log table (for tracking email intake processing outcomes)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS email_intake_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uidvalidity INTEGER NOT NULL,   -- from IMAP; UIDs are only unique per UIDVALIDITY epoch
    uid INTEGER NOT NULL,           -- IMAP UID, not sequence number
    message_id TEXT,                -- Message-ID header, belt-and-suspenders vs UID resets
    outcome TEXT NOT NULL,          -- 'accepted' | 'rejected_subject' | 'rejected_attachment' | 'error'
    session_id TEXT,                -- FK-ish to sessions.session_id, NULL if rejected
    processed_at DATETIME NOT NULL,
    UNIQUE(uidvalidity, uid)
    )
    ''')
    print("OK - Created email_intake_log table")

    # Create Users table (Admin Dashboard accounts — see CONTEXT.md's
    # "Dashboard admin role" term and docs/adr/0002-admin-dashboard-auth-and-
    # remote-access-architecture.md. Unrelated to the touchscreen ADMIN_PIN.
    # `role` is free-form text rather than a CHECK/enum constraint so more
    # roles can be added later without a migration that touches existing
    # rows. `failed_attempts`/`locked_until` are provisioned now (unused
    # until lockout logic lands) for the same reason — no later migration
    # needed to add them.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at DATETIME NOT NULL,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until DATETIME
    )
    ''')
    print("OK - Created users table")

    # Create Dashboard Login Log table (issue #14's login audit log — every
    # login attempt against the Admin Dashboard, successful or not).
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dashboard_login_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME NOT NULL,
        username TEXT NOT NULL,
        success BOOLEAN NOT NULL,
        source_ip TEXT
    )
    ''')
    print("OK - Created dashboard_login_log table")

    # Initialize default settings if they don't exist
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('paper_count', '100')")
    print("OK - Initialized paper_count setting")
    
    # Initialize default CMYK ink levels if none exist
    cursor.execute("SELECT COUNT(*) FROM cmyk_ink_levels")
    cmyk_count = cursor.fetchone()[0]
    if cmyk_count == 0:
        from datetime import datetime
        cursor.execute("""
            INSERT INTO cmyk_ink_levels (cyan_level, magenta_level, yellow_level, black_level, timestamp, last_updated)
            VALUES (100.0, 100.0, 100.0, 100.0, ?, ?)
        """, (datetime.now(), datetime.now()))
        print("OK - Initialized default CMYK ink levels (100%)")
    else:
        print("OK - CMYK ink levels already exist")

    conn.commit()
    conn.close()
    print("OK - Database initialization complete")