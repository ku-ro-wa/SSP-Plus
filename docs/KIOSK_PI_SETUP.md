# Kiosk Pi Setup (from a blank card)

This guide builds the kiosk Pi from a blank microSD card. For laptop development, see
`docs/SETUP.md`. Several steps below point to sections of `SETUP.md` rather than repeating them.

The kiosk's first card died on 2026-10-14 (cracked and discoloured, cause unknown). This guide
was written while rebuilding on a new card, so the next rebuild needs only the repo.

## Status (2026-10-15)

| Step | Status |
|------|--------|
| 1–7, 9–12 | Done on the new card |
| 8. Printer (CUPS) and scanner | Printer done 2026-10-16: fixed driverless queue `HP_Smart_Tank` over `ipp-usb`. Scanner done 2026-10-20: sane-airscan over `ipp-usb`. Printer swapped to a Smart Tank 660-670 on 2026-10-20; both now use the model-independent `localhost:60000` addresses |
| 13. QR reader | **In progress**: reads over serial and `QR_READER_PORT` set, 2026-10-20. udev rule, settings barcodes and the issue #38 checks not done |
| 14. Start at boot (systemd) | **Not done yet**: the app is still started by hand with `make run` |
| 15. Tailscale | **Not done yet**: planned in ADR-0005, not set up |
| 16–17. Checks and backup image | Baseline image taken 2026-10-15, before steps 8 and 13–15 |

Steps marked **not done yet** describe the plan and haven't been checked on the Pi. Whoever does
them should fix anything that turns out wrong and update this table.

---

## 1. Card

- **64 GB high-endurance microSD**: SanDisk High/MAX Endurance, Samsung PRO Endurance or Kingston
  High Endurance. The kiosk writes logs and SQLite all day, which wears out normal cards. A
  Raspberry Pi-branded card or an A2-rated Samsung EVO/PRO Plus or SanDisk Extreme also works.
- Buy from the brand's official store. Marketplace fakes report the wrong capacity and corrupt
  data once they fill up.
- Test the card before flashing it (on a Mac):

  ```bash
  brew install f3
  f3write /Volumes/<card> && f3read /Volumes/<card>   # any errors = fake or bad card
  ```

A USB SSD would last longer and is set up the same way, but it uses a USB port and needs a solid
power supply. Not done yet.

## 2. Flash Raspberry Pi OS

In Raspberry Pi Imager (`brew install --cask raspberry-pi-imager`):

- **OS:** Raspberry Pi OS (64-bit), the **desktop** version, not Lite. The kiosk GUI needs a
  desktop session. The kiosk was verified on Debian 13 "trixie" (see `SETUP.md`, "Verified on the
  kiosk Pi").
- **Edit Settings:**
  - Hostname `aio-spark-kiosk`. `scripts/generate_tls_cert.py` puts `aio-spark-kiosk.local` in
    the portal's certificate.
  - Username and password: record them where the team keeps credentials, never in the repo.
  - Timezone `Asia/Manila`, so transaction timestamps are right.
  - Services: enable SSH.
  - Wi-Fi is optional. The hotspot (step 10) takes `wlan0` away, so set the kiosk up over
    Ethernet.

Leave Raspberry Pi Connect off. ADR-0005 makes Tailscale the only remote way in. If Connect is
ever turned on as a stopgap, sign in with the project account and remove it afterwards
(`rpi-connect signout`, then `sudo apt remove rpi-connect`, then delete the device at
connect.raspberrypi.com). Remove it before taking a backup image, or every card restored from the
image comes up signed in.

## 3. First boot

Connect Ethernet, boot, then:

```bash
ssh <user>@aio-spark-kiosk.local
cat /proc/device-tree/model   # record the Pi model: it matters for pigpio (step 5)
pgrep -a apt                  # wait until this prints nothing; don't kill apt
sudo apt update && sudo apt full-upgrade -y
```

## 4. Clone the repo

```bash
sudo apt install -y git
git clone <repo-url> ~/SSP-Plus
cd ~/SSP-Plus
```

Clone it; don't copy it. A copy without `.git` can't `git pull`. If the repo is private, use a
read-only deploy key for the kiosk (`ssh-keygen -t ed25519`, add the public key under GitHub repo
→ Settings → Deploy keys), not a personal login.

## 5. System packages and groups

```bash
sudo apt install -y cups libcups2-dev poppler-utils python3-venv python3-dev
sudo apt install -y sane-utils sane-airscan
sudo apt install -y pigpio
sudo systemctl enable --now cups pigpiod
sudo usermod -aG lpadmin,dialout <user>
```

Log out and back in for the groups to apply. `lpadmin` lets you manage printers; `dialout` lets
the app open serial ports (QR reader, GSM modem). `sane-utils` and `sane-airscan` are for the
scanner (step 8).

pigpio doesn't support the Pi 5. If the `pigpio` package isn't available, build it from source
(github.com/joan2937/pigpio).

## 6. Python environment

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`make` uses `.venv` on its own. Check that `opencv-python-headless` was installed, not
`opencv-python` (see `SETUP.md` → Troubleshooting). If the PyQt5 install fails or tries to build
from source, use the system package: `sudo apt install python3-pyqt5`, then recreate the venv with
`python3 -m venv --system-site-packages .venv`.

## 7. `.env`

```bash
cp .env.example .env   # at the repo root, never in SSP/
```

Set at least the following. Restore the values from the team's credential store, not from memory:

| Key | Kiosk value |
|-----|-------------|
| `SIM_MODE` | `false` |
| `PRINTER_NAME` | from step 8 |
| `ADMIN_PIN` | not `1234` |
| `ADMIN_DASHBOARD_SECRET_KEY` | a long random string (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`) |
| `API_DOCS_ENABLED` | `false` |
| `PHONE_NUMBER` | the operator's number for SMS alerts |
| `EMAIL_USER` / `EMAIL_PASSWORD` | the dedicated Gmail account and its App Password |
| `KIOSK_ID`, `WIFI_HOTSPOT_*`, `PORTAL_HOSTNAME` | see step 10 |
| `QR_READER_PORT` | from step 13 |
| `COIN_PIN`, `BILL_PIN`, `*_INHIBIT_PIN` | the defaults unless the wiring changed |
| `SCANNER_DEVICE` | from step 8 |

The backup image (step 17) contains `.env`, so keep images private.

## 8. Printer (CUPS) and scanner

The printer is an HP Smart Tank on USB (a 580/590 until 2026-10-20, now a 660-670). `ipp-usb`
(running by default) exposes whichever printer is plugged in as an IPP printer at
`localhost:60000`, and the app prints to it driverless. Both the print queue and the scanner point
at that address rather than at the model or serial number, so a printer swap needs no `.env` change.

Don't use the queue that appears on its own (named after the model, e.g.
`HP_Smart_Tank_580_590_series_5E0E1D_USB`, device `implicitclass://…`). cups-browsed creates it, and it only works while cups-browsed is running to
hand it the printer's address. When that fails, CUPS **disables** the queue (`lpstat -p` says
`disabled`, `Alerts: paused`) and keeps it disabled across reboots, so nothing prints, paper or not.
Make a fixed queue instead:

```bash
lpstat -p                                                  # find the auto-made queue's name, if any
sudo lpadmin -x <that queue name>                          # if cups-browsed made one
sudo systemctl disable --now cups-browsed                  # so it never comes back
sudo lpadmin -p HP_Smart_Tank -E -v ipp://localhost:60000/ipp/print -m everywhere
lpstat -l -p HP_Smart_Tank        # enabled, no Alerts line (or "Alerts: none")
lp -d HP_Smart_Tank /etc/hostname # should print a page
```

If `lpadmin` can't reach `localhost:60000`, use the `ipp://…(USB)._ipp._tcp.local/` address that
`sudo lpinfo -v` lists, in quotes. Then set `PRINTER_NAME=HP_Smart_Tank` in `.env`.

If the queue ever ends up `disabled` again: `sudo cupsenable HP_Smart_Tank`, and clear stuck
jobs with `cancel -a HP_Smart_Tank`.

`HP_Smart_Tank` is only the queue's name, chosen when it was made. It says nothing about which
printer is attached.

### Scanner

The printer's flatbed scanner goes through the same `ipp-usb` connection. The app runs
`scanimage` (from `sane-utils`, step 5) with the `sane-airscan` driver, so there's no HP driver to
install. List the scanner:

```bash
scanimage -L
```

It shows up twice, once per SANE driver:

```
device `escl:http://localhost:60000' is a HP Smart Tank 660-670 series [1074DB] (USB) platen scanner
device `airscan:e0:HP Smart Tank 660-670 series [1074DB] (USB)' is a eSCL HP Smart Tank 660-670 series [1074DB] (USB) ip=127.0.0.1, ::1
```

Use the `escl:` address. It's the same `ipp-usb` port the print queue uses, with no model name in
it, so it keeps working after a printer swap:

```env
SCANNER_DEVICE=escl:http://localhost:60000
```

The app checks that this exact name is in `scanimage -L`'s output before it scans. The `airscan:`
name works too (copy it whole, in quotes, into `.env`), but it contains the model and an ID, so it
has to be updated whenever the printer changes. The kiosk used it until 2026-10-20; the 17 s scan
time below was measured with it. Try it if the `escl:` driver misbehaves.
`SCANNER_DPI` (200) and `SCANNER_TIMEOUT` (60 s) can stay at their defaults.

Check it with a real page on the glass. This is the same scan the app runs, so the time it prints
is what a customer waits per page (about 17 s on 2026-10-20):

```bash
time scanimage -d 'escl:http://localhost:60000' \
    --format=png --mode=Color --resolution 200 -p > ~/scan-test.png
```

To look at the result from a laptop: `scp <user>@aio-spark-kiosk.local:~/scan-test.png .`

### Finding the actual printer and scanner

To see which printer is really attached (after a swap, or when printing or scanning stops):

```bash
lsusb | grep -i hp           # what's plugged in, e.g. "HP, Inc Smart Tank 660-670 series"
lpstat -v                    # where the queue sends jobs (device-uri), should be ipp://localhost:60000/ipp/print
sudo lpinfo -v               # every device CUPS can see now, with model and serial
lpoptions -p HP_Smart_Tank | tr ' ' '\n' | grep -i -E 'make|model|uri'
scanimage -L                 # scanner names, including the model
```

In `lpoptions`, `device-uri` is the printer the queue sends to. `printer-uri-supported` is just
the queue's own address (`ipp://localhost/printers/HP_Smart_Tank`) and says nothing about the
hardware.

If `lpstat -v` shows anything other than `ipp://localhost:60000/ipp/print` (for example a
`usb://…?serial=…` URI left over from an older printer), make the queue again with the `lpadmin`
commands above. Its name stays `HP_Smart_Tank`, so `.env` needs no change.

If more than one IPP-over-USB printer is ever plugged in, `ipp-usb` gives the second one
`localhost:60001`, and which one gets which port depends on which it finds first. The kiosk has
only one, so this doesn't come up.

## 9. Display

In `sudo raspi-config`:

- System Options → Boot / Auto Login → **Desktop Autologin**
- Display Options → **Screen Blanking: off**

`UI_SCALE` in `.env` is blank (auto) for the 1920×1080 panel. Not covered yet: screen rotation and
hiding the cursor.

The app always draws through X11 (Xwayland under labwc) and ships its own font, so a launch from
the desktop, from systemd and over SSH (`DISPLAY=:0 make run`) look the same. Each prints a
`Render:` line at startup; on this panel it should read `platform=xcb screen=1920x1080 scale=1.35
... font=Inter 18px`.

## 10. Hotspot

Over Ethernet, once no apt job is running:

```bash
sudo python3 scripts/setup_hotspot.py --dry-run
sudo python3 scripts/setup_hotspot.py
```

Details and gotchas: `SETUP.md` → "Kiosk hotspot". On a fresh OS there's no RaspAP to clean up.

## 11. Portal TLS certificate

```bash
.venv/bin/python scripts/generate_tls_cert.py   # writes certs/cert.pem + certs/key.pem
```

## 12. First run by hand

```bash
make test   # dependencies work on the Pi
make run    # creates SSP/database/ssp_database.db on first start
```

Then:

- **Coin Inventory:** a new database starts at 0 coins, so the kiosk dispenses no change and issues
  a Voucher for all of it. In Kiosk Admin → Coin Inventory, set ₱1/₱5 to what the hoppers
  actually hold (`SETUP.md` → "Coin hoppers").
- **Admin Dashboard account:**

  ```bash
  PYTHONPATH=SSP .venv/bin/python -m admin_dashboard.cli create-account --username <name> --password <pw> --role admin
  ```

## 13. QR reader — in progress

Done on 2026-10-20: the reader shows up as `ttyACM0`, scans come through as text, and `.env` points
at its by-id path:

```bash
ls -l /dev/serial/by-id/
# usb-NetChip_USB_Serial_Gadget_20080411-if00 -> ../../ttyACM0
cat /dev/ttyACM0             # scan a code: its text prints. Ctrl+C before starting the app
```

```
QR_READER_PORT=/dev/serial/by-id/usb-NetChip_USB_Serial_Gadget_20080411-if00
```

Use the by-id path, not `/dev/ttyACM0`, because the `ttyACM` number can change with USB order at
boot. The serial `20080411` is the chip's generic default, so two of these readers on one Pi would
get the same by-id name. In that case, use `/dev/serial/by-path/` instead. The user running the app
must be in `dialout` (step 5). If nothing new appears under `/dev/tty*` when the reader is
plugged in, it's in keyboard mode. Scan the manual's USB COM settings barcode to switch it back.

Still to do: follow `SETUP.md` → "QR reader (kiosk)": udev rule (vendor/product ID from `lsusb`),
`QR_READER_PORT`, the settings barcodes, and the miniterm check. Then finish issue #38: a phone's
Wi-Fi and email Session QRs open the right flow, and unplugging and replugging the reader shows
in Kiosk Admin without a restart.

## 14. Start at boot (systemd) — not done yet

In production the app starts at boot and restarts if it crashes. Until then, start it by hand
with `make run`.

**Never run `make run` while the service is running.** Two copies fight over port 8000, the QR
reader's serial port, the GPIO pins (coin acceptor and hoppers) and the database. Stop the
service first:

```bash
systemctl --user stop ssp-kiosk          # then make run; afterwards:
systemctl --user start ssp-kiosk
```

`Restart=always` restarts the app only when it crashes or is killed. After `systemctl stop` it
stays stopped until it's started again or the Pi reboots. The same applies to
`make run-admin-dashboard` and the dashboard service (port 8100).

### Kiosk GUI (user service)

It needs the desktop session, so it's a user service started by the desktop.

1. Check the desktop runs labwc (the trixie default): `pgrep -a labwc` prints a line. If it
   doesn't, step 4 doesn't apply.
2. Create `~/.config/systemd/user/ssp-kiosk.service`:

   ```ini
   [Unit]
   Description=SSP kiosk GUI

   [Service]
   WorkingDirectory=%h/SSP-Plus
   ExecStart=%h/SSP-Plus/.venv/bin/python -X utf8 SSP/main_app.py
   Restart=always
   RestartSec=5
   ```

3. `systemctl --user daemon-reload`
4. Have the desktop start it. A user `autostart` file replaces the system one, so copy that
   first or the taskbar disappears:

   ```bash
   mkdir -p ~/.config/labwc
   [ -f ~/.config/labwc/autostart ] || cp /etc/xdg/labwc/autostart ~/.config/labwc/autostart
   ```

   Add as the last line of `~/.config/labwc/autostart`:

   ```bash
   systemctl --user import-environment WAYLAND_DISPLAY DISPLAY && systemctl --user start ssp-kiosk.service
   ```

   The first command passes the display to systemd; without it the GUI has nowhere to draw.
5. Test: reboot, and the app should open on its own. `pkill -f main_app.py` should bring it back
   within about 5 s. Logs: `journalctl --user -u ssp-kiosk -f`.

### Admin Dashboard (system service)

ADR-0005 runs it as its own service, independent of the kiosk GUI. Create
`/etc/systemd/system/ssp-admin-dashboard.service` (replace each `<user>`):

```ini
[Unit]
Description=SSP Admin Dashboard
After=network-online.target

[Service]
User=<user>
WorkingDirectory=/home/<user>/SSP-Plus
Environment=PYTHONPATH=SSP
ExecStart=/home/<user>/SSP-Plus/.venv/bin/python -X utf8 -m admin_dashboard.main
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ssp-admin-dashboard
journalctl -u ssp-admin-dashboard -f
```

### Undo

```bash
systemctl --user stop ssp-kiosk     # and delete the line added to ~/.config/labwc/autostart
sudo systemctl disable --now ssp-admin-dashboard
```

## 15. Tailscale — not done yet

Design: ADR-0005. Accounts: `SETUP.md` → "External accounts". In short:

1. Use the tailnet owned by the project account, never a personal one.
2. Install Tailscale and join with the tags ADR-0005 asks for (the tags must exist in the tailnet
   policy first):

   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --advertise-tags=tag:kiosk,tag:site-<KIOSK_ID>
   sudo tailscale serve --bg 8100
   ```

3. The dashboard is then at `https://aio-spark-kiosk.<tailnet>.ts.net/`.

On a rebuild, remove the old device from the tailnet first. ADR-0005 also moves the dashboard to
`127.0.0.1` behind Serve; until that change lands it listens on `0.0.0.0:8100` (the hotspot
firewall blocks it from phones).

## 16. Final checks

- **Reboot test:** everything comes up without anyone touching it.
- **Power and heat**, after the kiosk has run for a while (ideally after a few prints):

  ```bash
  vcgencmd get_throttled   # 0x0 = fine; anything else = under-voltage or overheating since boot
  vcgencmd measure_temp    # under ~70°C under load
  ```

  The cause of the first card's failure is unknown. A non-zero `get_throttled` points at the power
  supply.

## 17. Backup image

Take an image once the kiosk works, and again after any big setup change. A dead card then costs
a restore, not a rebuild. Shut the Pi down and put the card in a reader on a Mac:

```bash
diskutil list                         # find the card: check its size and bootfs/Linux partitions
diskutil unmountDisk /dev/diskN
sudo dd if=/dev/rdiskN bs=4m status=progress | gzip > ~/ssp-kiosk-$(date +%F).img.gz
```

Restore:

```bash
gunzip -c ssp-kiosk-<date>.img.gz | sudo dd of=/dev/rdiskN bs=4m status=progress
```

**Check the disk number twice.** `dd` overwrites whatever disk it's given. Restore onto the same
card model or a larger one: another brand's "64 GB" may be a few MB smaller, and the restore then
fails near the end. Images contain `.env`, so store them privately, never in the repo or a shared
folder.
