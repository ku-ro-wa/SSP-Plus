"""Find which GPIO the coin acceptor and each hopper's coin-out sensor are wired to.

Listens on every GPIO that isn't an output the app drives (the acceptor inhibits and
hopper motor enables, from .env / KIOSK_MODEL) and counts low pulses on each, with
the same 5 ms glitch filter the app uses. Pins that pulse in the baseline are noise;
the right pin shows one clean burst per coin in the other runs. Run it on the kiosk
from the repo root with the kiosk app stopped (it shares pigpiod's pins):

    python scripts/gpio_scan.py baseline              # nothing happening, motors off
    python scripts/gpio_scan.py coins                 # acceptors on; insert coins/bills
    python scripts/gpio_scan.py hopper A              # runs hopper A's motor for 1 s
    python scripts/gpio_scan.py hopper B --seconds 2
    python scripts/gpio_scan.py empty B               # runs hopper B until Ctrl+C (max 180 s)

After the per-pin totals, each pin's pulses are listed in bursts, split where the line
stays quiet for --gap ms (default 500, the app's coin/bill timeout), so each burst is
what the app would count as one coin or bill. --no-filter drops the 5 ms glitch filter
to see what the app's unfiltered bill line sees:

    python scripts/gpio_scan.py coins --seconds 15 --no-filter   # insert one bill

`empty` runs the motor whatever the sensor says, so it works with a miswired sensor:
watch the hopper and press Ctrl+C once coins stop. It prints the sensor's running
pulse count each second; compare the total with the coins that came out.

On the old kiosk (2026-10-15) coins showed 3/5/8/11 pulses for ₱1/₱5/₱10/₱20, each
~66-74 ms wide; a hopper shows one 43-183 ms pulse per coin out (~5 coins/s).
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'SSP')))

GLITCH_FILTER_US = 5000  # same as the app's coin and hopper-sensor filters
MAX_MOTOR_SECONDS = 3.0  # ~15 coins; a `hopper` run never runs the motor longer
MAX_EMPTY_SECONDS = 180  # an `empty` run stops here even without Ctrl+C
BCM_PINS = range(2, 28)


class PulseRecorder:
    """Low pulses (falling edge to rising edge) per pin: start ticks and widths in ms."""

    def __init__(self, pigpio, start_tick):
        self.pigpio = pigpio
        self.start_tick = start_tick
        self.fell_at = {}
        self.widths = {}
        self.starts = {}

    def edge(self, gpio, level, tick):
        if level == 0:
            self.fell_at[gpio] = tick
        elif level == 1 and gpio in self.fell_at:
            fell = self.fell_at.pop(gpio)
            self.widths.setdefault(gpio, []).append(self.pigpio.tickDiff(fell, tick) / 1000)
            self.starts.setdefault(gpio, []).append(self.pigpio.tickDiff(self.start_tick, fell) / 1000)

    def bursts(self, gpio, gap_ms):
        """Split a pin's pulses where the line stays high for more than gap_ms."""
        groups = []
        prev_end = None
        for start, width in zip(self.starts[gpio], self.widths[gpio]):
            if prev_end is None or start - prev_end > gap_ms:
                groups.append([])
            groups[-1].append((start, width, None if prev_end is None else start - prev_end))
            prev_end = start + width
        return groups

    def report(self, labels, gap_ms, max_listed=300):
        if not self.widths:
            print("No low pulses on any watched pin.")
            return
        print(f"{'GPIO':>4}  {'pulses':>6}  {'width ms (min-max)':>18}  note")
        pins = sorted(self.widths, key=lambda g: -len(self.widths[g]))
        for gpio in pins:
            w = self.widths[gpio]
            print(f"{gpio:>4}  {len(w):>6}  {min(w):>8.1f}-{max(w):<9.1f}  {labels.get(gpio, '')}")
        for gpio in pins:
            if len(self.widths[gpio]) > max_listed:
                print(f"\nGPIO {gpio}: {len(self.widths[gpio])} pulses, too many to list (noise?)")
                continue
            print(f"\nGPIO {gpio} bursts (split at > {gap_ms:g} ms quiet):")
            for group in self.bursts(gpio, gap_ms):
                widths = [w for _, w, _ in group]
                gaps = [g for _, _, g in group[1:]]
                line = (f"  at {group[0][0] / 1000:7.3f} s  {len(group):>3} pulses  "
                        f"width {min(widths):.1f}-{max(widths):.1f} ms")
                if gaps:
                    line += f"  gaps {min(gaps):.1f}-{max(gaps):.1f} ms"
                print(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=['baseline', 'coins', 'hopper', 'empty'])
    parser.add_argument('hopper', nargs='?', choices=['A', 'B'], help="hopper to run (hopper and empty modes)")
    parser.add_argument('--seconds', type=float,
                        help="how long to listen (baseline 10, coins 30) or run the motor "
                             f"(hopper 1, max {MAX_MOTOR_SECONDS:g}; empty {MAX_EMPTY_SECONDS})")
    parser.add_argument('--gap', type=float, default=500,
                        help="quiet ms that ends a burst in the report (default 500, the app's timeout)")
    parser.add_argument('--no-filter', action='store_true',
                        help=f"no {GLITCH_FILTER_US // 1000} ms glitch filter: see sub-ms spikes too")
    args = parser.parse_args()
    if args.mode in ('hopper', 'empty') and not args.hopper:
        parser.error(f"{args.mode} mode needs A or B")

    import pigpio
    from config import get_config
    cfg = get_config()

    enables = {'A': cfg.hopper_a_enable_pin, 'B': cfg.hopper_b_enable_pin}
    signals = {'A': cfg.hopper_a_signal_pin, 'B': cfg.hopper_b_signal_pin}
    outputs = {cfg.coin_inhibit_pin: 'coin inhibit', cfg.bill_inhibit_pin: 'bill inhibit',
               enables['A']: 'hopper A enable', enables['B']: 'hopper B enable'}
    labels = {
        cfg.coin_pin: 'configured coin', cfg.bill_pin: 'configured bill',
        cfg.hopper_a_signal_pin: 'configured hopper A sensor',
        cfg.hopper_b_signal_pin: 'configured hopper B sensor',
    }

    pi = pigpio.pi()
    if not pi.connected:
        sys.exit("pigpiod isn't running (sudo systemctl start pigpiod)")

    # Motors off before anything else; written before the pins become outputs.
    for pin in enables.values():
        pi.write(pin, 1)

    watched = [g for g in BCM_PINS if g not in outputs and pi.get_mode(g) == pigpio.INPUT]
    recorder = PulseRecorder(pigpio, pi.get_current_tick())
    callbacks = []
    for gpio in watched:
        pi.set_pull_up_down(gpio, pigpio.PUD_UP)
        pi.set_glitch_filter(gpio, 0 if args.no_filter else GLITCH_FILTER_US)
        callbacks.append(pi.callback(gpio, pigpio.EITHER_EDGE, recorder.edge))

    print(f"KIOSK_MODEL={cfg.kiosk_model}; glitch filter {'OFF' if args.no_filter else f'{GLITCH_FILTER_US} us'}; "
          f"watching GPIO {', '.join(map(str, watched))}")
    print(f"Not watched (outputs): {', '.join(f'{p} {n}' for p, n in sorted(outputs.items()))}")
    try:
        if args.mode == 'hopper':
            seconds = min(args.seconds or 1.0, MAX_MOTOR_SECONDS)
            pin = enables[args.hopper]
            time.sleep(1)  # settle, so motor-start noise isn't mixed with idle noise
            print(f"Hopper {args.hopper} motor ON (GPIO {pin}) for {seconds:g} s — count the coins out")
            pi.write(pin, 0)  # active low
            time.sleep(seconds)
            pi.write(pin, 1)
            print(f"Hopper {args.hopper} motor OFF")
            time.sleep(1)  # catch the last coin's pulse
        elif args.mode == 'empty':
            seconds = min(args.seconds or MAX_EMPTY_SECONDS, MAX_EMPTY_SECONDS)
            pin, sensor = enables[args.hopper], signals[args.hopper]
            print(f"Hopper {args.hopper} motor ON (GPIO {pin}) until Ctrl+C, at most {seconds:g} s")
            pi.write(pin, 0)  # active low
            started = time.monotonic()
            while time.monotonic() - started < seconds:
                time.sleep(1)
                print(f"  {time.monotonic() - started:4.0f} s  pulses on GPIO {sensor}: "
                      f"{len(recorder.widths.get(sensor, []))}")
            print("Time limit reached")
        else:
            seconds = args.seconds or (30 if args.mode == 'coins' else 10)
            if args.mode == 'coins':
                pi.write(cfg.coin_inhibit_pin, 1)  # active high: enabled
                pi.write(cfg.bill_inhibit_pin, 0)  # active low: enabled
                print(f"Acceptors ON — insert coins one at a time, noting each ({seconds:g} s)")
            else:
                print(f"Listening for {seconds:g} s — don't touch the kiosk")
            time.sleep(seconds)
    except KeyboardInterrupt:
        print("Stopped early")
    finally:
        for pin in enables.values():
            pi.write(pin, 1)
        if args.mode == 'empty':
            print(f"Hopper {args.hopper} motor OFF")
        if args.mode == 'coins':
            pi.write(cfg.coin_inhibit_pin, 0)
            pi.write(cfg.bill_inhibit_pin, 1)
        for cb in callbacks:
            cb.cancel()
        for gpio in watched:
            pi.set_glitch_filter(gpio, 0)
        pi.stop()

    recorder.report(labels, args.gap)


if __name__ == '__main__':
    main()
