# screens/settings/model.py
#
# Kiosk Admin's runtime-settings screen (issue #106). Rendering and validation
# come from managers/settings_catalog.py, shared with the Admin Dashboard.

from managers.settings_catalog import KIOSK, get_value, save_many, settings_for


class SettingsModel:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def entries(self):
        """(Setting, current value) for each setting offered on the kiosk."""
        return [(s, get_value(self.db_manager, s.key)) for s in settings_for(KIOSK)]

    def save(self, raw_values: dict):
        """All-or-nothing. Returns {key: message} for the bad fields; {} means saved."""
        _, errors = save_many(self.db_manager, raw_values, surface=KIOSK)
        return errors
