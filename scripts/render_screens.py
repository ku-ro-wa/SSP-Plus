"""Render every kiosk screen to a PNG exactly as the 1920x1080 kiosk panel shows it.

The reference picture for UI work: the font ships with the app and the Qt
environment is pinned (ui/theme.py, ui/scaling.py), so these match the kiosk
whether they're rendered on a laptop or on the Pi. Nothing touches the real
hardware or database: pigpio is blocked, SIM_MODE is on and the screens read a
throwaway SQLite file.

    make screenshots                 # -> screenshots/<screen>.png
    python scripts/render_screens.py --out DIR --height 1080 homepage payment
"""

import argparse
import os
import sys
import tempfile

SSP_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'SSP'))

# Screen name -> controller class in screens.<name>. Customer screens first.
SCREENS = {
    "idle": "IdleController",
    "homepage": "HomepageController",
    "usb": "USBController",
    "wifi": "WifiController",
    "email": "EmailController",
    "scanner": "ScannerController",
    "scan_destination": "ScanDestinationController",
    "scan_result": "ScanResultController",
    "file_browser": "FileBrowserController",
    "print_options": "PrintOptionsController",
    "payment": "PaymentController",
    "voucher": "VoucherController",
    "voucher_balance": "VoucherBalanceController",
    "thank_you": "ThankYouController",
    "admin": "AdminController",
}


def prepare_environment():
    """Headless Qt, simulated hardware and a temp database. Call before importing
    anything from SSP/."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["SIM_MODE"] = "true"
    sys.modules["pigpio"] = None  # `import pigpio` fails, so GPIO code runs simulated
    if SSP_DIR not in sys.path:
        sys.path.insert(0, SSP_DIR)

    import database.db_manager as db_manager
    from database.models import init_db

    temp_db = os.path.join(tempfile.mkdtemp(prefix="ssp-screens-"), "screens.db")
    init_db(temp_db)
    real_init = db_manager.DatabaseManager.__init__

    def init_on_temp_db(self, db_name="ssp_database.db", db_path=None):
        real_init(self, db_name, db_path or temp_db)

    db_manager.DatabaseManager.__init__ = init_on_temp_db


def build_screen(name):
    """The real controller for `name`, wired to a stand-in main app."""
    import importlib
    from unittest.mock import MagicMock

    module = importlib.import_module(f"screens.{name}")
    return getattr(module, SCREENS[name])(MagicMock())


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("screens", nargs="*", metavar="screen", help=f"default: all of {', '.join(SCREENS)}")
    parser.add_argument("--out", default="screenshots")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()
    unknown = set(args.screens) - set(SCREENS)
    if unknown:
        parser.error(f"unknown screen(s): {', '.join(sorted(unknown))}")

    prepare_environment()
    from ui.scaling import pin_render_environment, ui_scale_factor
    pin_render_environment()
    scale = ui_scale_factor(args.height, os.environ.get("UI_SCALE", ""))
    os.environ["QT_SCALE_FACTOR"] = str(scale)

    from PyQt5.QtWidgets import QApplication
    from ui.theme import apply_theme
    app = QApplication(sys.argv)
    apply_theme(app)

    os.makedirs(args.out, exist_ok=True)
    width, height = round(args.width / scale), round(args.height / scale)
    print(f"Rendering at {args.width}x{args.height} (scale {scale}, {width}x{height} logical) into {args.out}/")
    overflowed = []
    for name in args.screens or SCREENS:
        screen = build_screen(name)
        screen.resize(width, height)
        screen.show()
        app.processEvents()
        needed = screen.minimumSizeHint().height()
        screen.grab().save(os.path.join(args.out, f"{name}.png"))
        screen.hide()
        overflow = f"  OVERFLOWS by {needed - height}px" if needed > height else ""
        print(f"  {name:<18} needs {needed}px of {height}px{overflow}")
        if overflow:
            overflowed.append(name)
    if overflowed:
        sys.exit(f"Too tall for the panel: {', '.join(overflowed)}")


if __name__ == "__main__":
    main()
