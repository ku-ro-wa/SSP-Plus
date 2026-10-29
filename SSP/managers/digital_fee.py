# managers/digital_fee.py
#
# The flat fee (whole pesos) for the digital copy of a scan (download/email).
# Kiosk Admin edits the 'scan_digital_fee' setting; until it's set, the
# SCAN_DIGITAL_FEE env value (config.scan_digital_fee, default 5) applies.

from config import get_config

SETTING_KEY = 'scan_digital_fee'


def get_digital_fee(db_manager) -> int:
    value = db_manager.get_setting(SETTING_KEY, None)
    try:
        fee = int(round(float(value)))
    except (TypeError, ValueError):
        fee = int(round(get_config().scan_digital_fee))
    return max(0, fee)


def set_digital_fee(db_manager, fee: int) -> int:
    fee = max(0, int(fee))
    db_manager.update_setting(SETTING_KEY, fee)
    return fee
