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
  keyboard mode, change its line ending to TAB or F1–F12, or restore factory defaults. Three
  defences follow:
  - The kiosk OS ignores the reader as an input device (a udev rule matching its vendor and
    product ID), so a reader switched to keyboard mode can't type anything.
  - The app checks that the serial port is still there. If the port disappears, the app logs it
    and the kiosk falls back to typed codes only.
  - While the port is there, the app re-asserts the reader's config over serial (see below), so
    a changed setting is undone without an operator.

- **The app re-asserts the reader's config over serial.** The manual doesn't say so, but the
  reader accepts settings over USB COM as `#<code>;`, where `<code>` is the text inside that
  setting's barcode (`DK010` is End Mark CR). It replies `06` (ACK) to a known code and `15`
  (NAK) to an unknown one, and ignores malformed frames. A change applies at once and survives
  a replug without a Save. The app sends the kiosk config each time it opens the port: USB COM
  `JA060`, Auto-Sensing `DC010`, 2D-ON `AB060`, 1D-OFF `AB030`, End Mark CR `DK010`, Duplicate
  Detection ON `DN030`, No Swap `JD040`, Display Prefix OFF `DF000`, Display Suffix OFF
  `DG000`, Delete Characters OFF `DP020`, Invoice Function OFF `JD060`, Volume ON `CD010`, Low
  Volume `CD032`. All thirteen were checked for an ACK on 2026-10-01; `DK030`/`DK010` (TAB and
  back) were also checked by scanning. Limits:
  - It only works while the reader is in USB COM mode. Restore Defaults, or a switch to keyboard
    mode, removes the port; that case stays with the udev rule, the lost-reader fallback and
    an operator scanning the paper config.
  - The app never sends Restore Defaults (`AB160`) or keyboard mode (`JA020`): either one would
    cut the app off from the reader.
  - Multi-step parameter entry (Duplicate Detection time: `DN010`, digit codes, Save) is NAKed
    over serial. The reader's own duplicate timer is therefore untrusted; the app drops a
    payload read again within 3 s of its last accepted read itself (`DuplicateReadFilter`).
  - Each reply takes 0.42–0.58 s (measured 2026-10-01), so the app waits up to 1.5 s per code
    and the full send takes about 8 s. Reads that arrive during it are held until it ends.
  - Each command looks like a flash write, so the app sends the config on open, not on a
    timer.

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
- **A different module with a settings-code lockout** (some GM65-family modules document one).
  It would close the gap fully, but re-asserting the config covers every change except leaving
  USB COM, and that case already falls back to typed codes. Worth revisiting if tampering is
  seen in the field.
- **TTL/RS232 wired to the Pi's UART:** no advantage over USB serial. RS232 voltage levels, and
  5V TTL variants, would damage the Pi's 3.3V GPIO pins.
