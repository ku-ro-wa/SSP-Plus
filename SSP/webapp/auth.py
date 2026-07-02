# webapp/auth.py
#
# Placeholder admin-auth dependency: routes under /admin should already
# Depends(require_admin) so real auth (Phase 7 — likely PIN/session-based,
# mirroring screens/dialogs/pin_dialog) can be dropped in here later without
# touching route code.

def require_admin():
    return True
