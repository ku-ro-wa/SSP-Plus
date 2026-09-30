# QR reader: serial mode, and every payload treated as untrusted

The kiosk's **QR reader** (see `CONTEXT.md`) is a cheap embedded 2D module (the
"M300D/M800D/M900D/9800D-V1.3" manual family). It can act as a USB keyboard or as a USB serial
port, and it's configured by reading settings barcodes. We run it as a serial port. The app
treats every payload it receives as untrusted, because anyone at the kiosk can reconfigure the
reader.

## Decisions

- **USB COM (serial), not keyboard mode.** A reader in keyboard mode types into whatever widget
  has focus. That loses reads on screens with no input field, can change `:` under a non-US
  keyboard layout, and can't be told apart from a person typing. A serial reader thread gets
  each read as one CR-terminated line whatever screen is showing, and the app decides whether
  that screen accepts it.

- **Settings barcodes can't be locked out, so the kiosk protects itself.** The module has no
  option to stop reading settings barcodes. Turning 1D reading off was tested and doesn't block
  them either. So a customer holding up a printed settings barcode can switch the reader into
  keyboard mode, change its line ending to TAB or F1–F12, or restore factory defaults. Two
  defences follow:
  - The kiosk OS ignores the reader as an input device (a udev rule matching its vendor and
    product ID), so a reader switched to keyboard mode can't type anything.
  - The app checks that the serial port is still there. If the port disappears, the app logs it
    and the kiosk falls back to typed codes only.

- **Payloads are checked against exact formats.** A Session payload must be
  `<16 lowercase hex>:<6 digits>`. A Voucher payload must start with `V1:`. Anything else,
  including reads altered by a reconfigured reader, is malformed: the customer is told to type
  their code, and no failed attempt is counted.

- **A read Session payload is checked as the exact pair.** It's verified with
  `verify_otp(session_id, otp)`, so a wrong OTP counts toward the lockout exactly like a typed
  one. Only `wifi` and `email` Sessions are accepted: `scanner`-sourced Sessions exist for phone
  download, not the kiosk print path.

## Considered options

- **Keyboard mode**, the usual choice for point-of-sale readers: no driver or serial code. We
  rejected it for the focus, keyboard-layout and injection reasons above.
- **TTL/RS232 wired to the Pi's UART:** no advantage over USB serial. RS232 voltage levels, and
  5V TTL variants, would damage the Pi's 3.3V GPIO pins.
