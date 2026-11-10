# managers/settings_catalog.py
#
# One catalog of the runtime settings an operator may edit (issue #106). Kiosk
# Admin and the Admin Dashboard both render their forms and validate input from
# it, so the two surfaces cannot drift apart.
#
# Every key here is read from the `settings` table at the moment it is used, so
# a saved edit takes effect without restarting the kiosk or the dashboard.
#
# `vouchers_enabled` is deliberately absent: switching it off makes the kiosk
# keep money it owes a customer, so it stays database-only.
#
# The defaults repeat the fallbacks in the managers that read each key;
# tests/test_settings_catalog.py fails if the two ever differ.

from dataclasses import dataclass
from typing import Optional, Tuple

KIOSK = 'kiosk'
DASHBOARD = 'dashboard'


class SettingError(ValueError):
    """A value the catalog rejects. str(error) is the message to show the operator."""


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    unit: str          # '' when the value is a plain count
    minimum: int
    maximum: int
    default: int
    help: str = ''
    surfaces: Tuple[str, ...] = (KIOSK, DASHBOARD)

    def range_text(self) -> str:
        unit = f' {self.unit}' if self.unit else ''
        return f'{self.minimum}–{self.maximum}{unit}'

    def validate(self, raw) -> int:
        """Return `raw` as a whole number inside this setting's range, or raise
        SettingError. Out-of-range input is refused, never clamped."""
        if isinstance(raw, bool):
            raise SettingError(f'{self.label} must be a whole number.')
        if isinstance(raw, int):
            value = raw
        elif isinstance(raw, str):
            text = raw.strip()
            if not text:
                raise SettingError(f'{self.label} is required.')
            try:
                value = int(text)
            except ValueError:
                raise SettingError(f'{self.label} must be a whole number.') from None
        else:
            raise SettingError(f'{self.label} must be a whole number.')
        if value < self.minimum or value > self.maximum:
            raise SettingError(
                f'{self.label} must be between {self.minimum} and {self.maximum}'
                f'{" " + self.unit if self.unit else ""}.'
            )
        return value


CATALOG: Tuple[Setting, ...] = (
    Setting('voucher_expiry_days', 'Voucher expiry', 'days', 1, 365, 30,
            'How long a Voucher stays valid after it is issued.'),
    Setting('voucher_lockout_minutes', 'Voucher lockout', 'minutes', 1, 1440, 5,
            'How long wrong Voucher codes lock checking and applying.'),
    Setting('session_expiry_minutes', 'Pickup window', 'minutes', 1, 10080, 720,
            'How long an uploaded or scanned file can be picked up with its code.'),
    Setting('max_change_limit', 'Maximum change', '₱', 0, 1000, 50,
            'The most change the kiosk will hand out in one payment.'),
    Setting('min_coin_threshold_1', 'Keep ₱1 coins in reserve', 'coins', 0, 1000, 0,
            'Coins left in the ₱1 hopper that change dispensing will not use.'),
    Setting('min_coin_threshold_5', 'Keep ₱5 coins in reserve', 'coins', 0, 1000, 0,
            'Coins left in the ₱5 hopper that change dispensing will not use.'),
    Setting('low_change_warning_threshold', 'Low-change warning', '₱', 0, 1000, 20,
            'Warn customers when the change available falls below this.'),
)

_BY_KEY = {s.key: s for s in CATALOG}


def get_setting_def(key: str) -> Setting:
    try:
        return _BY_KEY[key]
    except KeyError:
        raise SettingError(f'Unknown setting: {key}') from None


def settings_for(surface: str) -> Tuple[Setting, ...]:
    return tuple(s for s in CATALOG if surface in s.surfaces)


def get_value(db_manager, key: str) -> int:
    """The current value: the stored one if it is a valid whole number in range,
    otherwise the default (what the managers that read the key would use)."""
    setting = get_setting_def(key)
    stored = db_manager.get_setting(key, None)
    try:
        return setting.validate(stored if stored is not None else '')
    except SettingError:
        return setting.default


def save_value(db_manager, key: str, raw, surface: Optional[str] = None) -> int:
    """Validate `raw` and store it. Raises SettingError (nothing is written) when
    the key is unknown, not offered on `surface`, or the value is out of range."""
    setting = get_setting_def(key)
    if surface is not None and surface not in setting.surfaces:
        raise SettingError(f'{setting.label} cannot be edited here.')
    value = setting.validate(raw)
    db_manager.update_setting(key, value)
    return value


def validate_many(values: dict, surface: Optional[str] = None):
    """Check every `{key: raw}` pair. Returns (cleaned, errors): `cleaned` maps each
    key to its whole-number value, `errors` maps each bad key to its message."""
    cleaned, errors = {}, {}
    for key, raw in values.items():
        try:
            setting = get_setting_def(key)
            if surface is not None and surface not in setting.surfaces:
                raise SettingError(f'{setting.label} cannot be edited here.')
            cleaned[key] = setting.validate(raw)
        except SettingError as e:
            errors[key] = str(e)
    return cleaned, errors


def save_many(db_manager, values: dict, surface: Optional[str] = None):
    """All-or-nothing save: nothing is written unless every value is valid.
    Returns (cleaned, errors); `errors` is empty exactly when it saved."""
    cleaned, errors = validate_many(values, surface)
    if errors:
        return {}, errors
    for key, value in cleaned.items():
        db_manager.update_setting(key, value)
    return cleaned, {}
