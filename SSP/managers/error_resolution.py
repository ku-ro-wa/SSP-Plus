"""
Marking an error_log row resolved (issue #136, ADR 0005). Called by the Dashboard
(`/kiosk`, `/logs`), the touchscreen data viewer and the thank-you screen's PIN
override, so all three mark the same row and write the same `admin_actions` row.
Nothing resolves an error automatically after a later success (ADR 0005).
"""
from managers.admin_actions import ACTION_ERROR_RESOLVED, record_action

MESSAGE_LIMIT = 80


def describe(row):
    """'#12 Printing Error: <message>' (the message cut short), for the audit row."""
    message = str(row["error_message"] or "").replace("\n", " ")
    if len(message) > MESSAGE_LIMIT:
        message = message[:MESSAGE_LIMIT - 1] + "…"
    return f"#{row['id']} {row['error_type']}: {message}"


def resolve_error(db, error_id, who):
    """Mark one error resolved and write its audit row.

    Returns "resolved", "already" (someone got there first; nothing written) or
    "missing" (no such id)."""
    row, changed = db.mark_error_resolved(error_id)
    if row is None:
        return "missing"
    if not changed:
        return "already"
    record_action(db, ACTION_ERROR_RESOLVED, describe(row), "resolved", **who)
    return "resolved"
