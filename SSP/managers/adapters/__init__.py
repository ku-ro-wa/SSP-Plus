# managers/adapters/__init__.py
#
# Intake adapters (wifi_adapter, email_adapter) — each validates input from
# one modality and hands the result to SessionManager. Deliberately not
# re-exported here like managers/__init__.py does for hardware managers:
# these have no SIM_MODE fallback concerns, so callers import them directly,
# e.g. `from managers.adapters.wifi_adapter import WifiAdapter`.
