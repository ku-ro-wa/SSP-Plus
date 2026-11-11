# screens/settings/model.py
#
# Kiosk Admin's runtime-settings screen (issue #106). Rendering and validation
# come from managers/settings_catalog.py, shared with the Admin Dashboard.

from managers.admin_actions import record_setting_changes, ACTOR_KIOSK, WHERE_TOUCHSCREEN
from managers.settings_catalog import CATALOG, KIOSK, get_value, save_many, settings_for

CATALOG_KEYS = {s.key for s in CATALOG}


class SettingsModel:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def entries(self):
        """(Setting, current value) for each setting offered on the kiosk."""
        return [(s, get_value(self.db_manager, s.key)) for s in settings_for(KIOSK)]

    def save(self, raw_values: dict):
        """All-or-nothing. Returns {key: message} for the bad fields; {} means saved."""
        old = {key: get_value(self.db_manager, key) for key in raw_values if key in CATALOG_KEYS}
        cleaned, errors = save_many(self.db_manager, raw_values, surface=KIOSK)
        if not errors:
            record_setting_changes(self.db_manager, old, cleaned, actor=ACTOR_KIOSK, where=WHERE_TOUCHSCREEN)
        return errors
