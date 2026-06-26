# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

The application must be run from the `SSP/` subdirectory, which is where `config.py` resolves the `.env` path:

```bash
cd SSP
python main_app.py
```

The `.env` file lives at the **repo root** (`SSP-Plus/.env`), but `config.py` looks for `.env` relative to the working directory, so always run from `SSP/`. If the `.env` file is missing, the app exits immediately with an error.

Install Python dependencies (no requirements.txt exists — install manually):

```bash
pip install PyQt5 PyMuPDF python-dotenv pdf2image opencv-python numpy pyserial pigpio
```

System-level dependencies (Linux/Raspberry Pi):

```bash
sudo apt-get install cups libcups2-dev python3-dev poppler-utils
sudo systemctl start cups
sudo systemctl start pigpiod   # Required for GPIO (coin/bill acceptors, hoppers)
```

## Architecture

### Screen Navigation (MVC + QStackedWidget)

`PrintingSystemApp` (in `main_app.py`) owns a `QStackedWidget` and navigates via `show_screen(screen_name)`. The `SCREEN_MAP` dict maps name → index. Always use `show_screen()` — it calls `on_leave()` on the current screen and `on_enter()` on the new one, and also checks paper count before most transitions.

Each screen in `screens/` follows the MVC pattern with three files:
- `controller.py` — wires view signals to model methods, handles navigation
- `model.py` — business logic, hardware interaction, data
- `view.py` — PyQt5 widgets and layout

Screens: `idle` → `usb` → `file_browser` → `print_options` → `payment` → `thank_you`. `admin` and `data_viewer` are side-paths accessed via PIN dialog.

### Background Threads

Two persistent QThread managers are started at app launch and must be stopped in `cleanup()`:
- `DatabaseThreadManager` (`managers/db_threader.py`) — serializes all SQLite writes to avoid thread conflicts
- `InkAnalysisThreadManager` (`managers/ink_analysis_threader.py`) — runs PDF ink analysis off the main thread

### Hardware Integration

| Component | Manager | Library |
|-----------|---------|---------|
| Printer (CUPS) | `managers/printer_manager.py` | `subprocess` (`lp`/`lpstat`) |
| Coin/bill acceptors | `managers/persistent_gpio.py` + payment model | `pigpio` (GPIO pulses) |
| Coin hoppers (change dispenser) | `managers/hopper_manager.py` | `pigpio` |
| SMS alerts | `managers/sms_manager.py` | `pyserial` (AT commands to GSM modem) |

`pigpio` requires the `pigpiod` daemon running. All GPIO code gracefully degrades when `pigpio` is unavailable (simulated mode with print warnings).

GPIO pin assignments:
- Coin acceptor input: GPIO 17; inhibit (enable/disable): GPIO 22
- Bill acceptor input: GPIO 18; inhibit: GPIO 23
- Hopper A (₱1 coins): signal GPIO 10, enable GPIO 24
- Hopper B (₱5 coins): signal GPIO 11, enable GPIO 25

### Database

SQLite at `SSP/database/ssp_database.db`. Schema is initialized by `database/models.py:init_db()` (called at startup). Tables: `transactions`, `cash_inventory`, `error_log`, `printer_status`, `cmyk_ink_levels`, `settings`.

All DB access should go through `DatabaseManager` (`database/db_manager.py`). For writes triggered from non-main threads, use the `db_threader` to avoid SQLite threading issues.

### Configuration

All runtime config comes from `.env` via `config.py`. Access via `get_config()` which returns the global `Config` singleton. Key variables: `PRINTER_NAME`, `BLACK_AND_WHITE_PRICE`, `COLOR_PRICE`, `PDF_ANALYSIS_DPI`. The config loads `.env` relative to the working directory on first import.

### Print Job Flow

1. User selects file (`file_browser`) → sets options (`print_options`) → inserts payment (`payment`)
2. `payment_screen` emits `payment_completed` signal → `main_app.on_payment_completed()` calls `printer_manager.print_file()`
3. `PrinterThread` creates a temp PDF with only selected pages, sends to CUPS via `lp`, polls `lpstat` for completion
4. On success: `main_app` decrements paper count and coin inventory, then triggers ink analysis on the temp PDF
5. Ink analysis (`InkAnalysisManager`) uses `pdf2image` + OpenCV to estimate CMYK consumption and updates `cmyk_ink_levels`
6. Temp PDF is cleaned up after ink analysis completes

### Payment Logic

`PaymentAlgorithmManager` (`managers/payment_algorithm_manager.py`) calculates change availability given the current coin inventory (₱1 and ₱5 coins). It suggests optimal payment amounts to customers when exact change cannot be made. Min coin thresholds and max change limit are configurable in the `settings` DB table.
