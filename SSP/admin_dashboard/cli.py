# admin_dashboard/cli.py
#
# Local CLI for managing Admin Dashboard accounts — the *only* way accounts
# are created or passwords reset (no self-service signup or "forgot
# password" flow exists anywhere in the app, by design; see
# docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md).
# Run by hand on the kiosk:
#   python -m admin_dashboard.cli create-account --username alice --password ... --role dev
#   python -m admin_dashboard.cli reset-password --username alice --password ...
#
# Uses the same DB file as the running dashboard (dependencies.open_db), so
# with SIM_MODE=true accounts go into the demo file, not the real DB.

import argparse
import sys

from admin_dashboard.auth import hash_password
from admin_dashboard.dependencies import open_db

VALID_ROLES = ("dev", "admin")


def create_account(db, username, password, role):
    """Create a new dashboard account with a hashed password. Returns True
    on success, False if the username is already taken."""
    return db.create_user(username, hash_password(password), role)


def reset_password(db, username, password):
    """Reset an existing account's password. Returns True if the account
    existed and was updated, False otherwise."""
    return db.update_user_password(username, hash_password(password))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Manage Admin Dashboard accounts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-account", help="Create a new dashboard account")
    create_parser.add_argument("--username", required=True)
    create_parser.add_argument("--password", required=True)
    create_parser.add_argument("--role", required=True, choices=VALID_ROLES)

    reset_parser = subparsers.add_parser("reset-password", help="Reset an existing account's password")
    reset_parser.add_argument("--username", required=True)
    reset_parser.add_argument("--password", required=True)

    args = parser.parse_args(argv)

    db = open_db()
    print(f"Using database: {db.db_path}")
    try:
        if args.command == "create-account":
            if create_account(db, args.username, args.password, args.role):
                print(f"OK - created account '{args.username}' (role: {args.role})")
            else:
                print(f"Error: username '{args.username}' is already taken", file=sys.stderr)
                sys.exit(1)
        elif args.command == "reset-password":
            if reset_password(db, args.username, args.password):
                print(f"OK - reset password for '{args.username}'")
            else:
                print(f"Error: no account found for '{args.username}'", file=sys.stderr)
                sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
