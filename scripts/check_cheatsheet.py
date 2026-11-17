"""Fail if docs/CHEATSHEET.md names a make target or repo path that doesn't exist.

    python scripts/check_cheatsheet.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "docs" / "CHEATSHEET.md"

# Paths in the sheet that are created at runtime, so they needn't exist in the repo.
RUNTIME = {
    "SSP/logs/app.log", "SSP/logs/crash.log", "SSP/database/sim_usb_drive",
    "SSP/logs/exit-loop-<time>.txt", "screenshots/<screen>.png",
}


def main():
    text = SHEET.read_text(encoding="utf-8")
    problems = []

    for target in sorted(set(re.findall(r"\bmake ([a-z][a-z-]*)\b", text))):
        ok = subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True).returncode == 0
        if not ok:
            problems.append(f"make target not found: {target}")

    paths = set(re.findall(r"\b((?:scripts|docs|SSP|tests)/[\w./<>-]+)", text))
    for p in sorted(paths):
        p = p.rstrip(".,:;)")
        if p in RUNTIME or "<" in p:
            continue
        if not (ROOT / p).exists():
            problems.append(f"path not found: {p}")

    modules = set(re.findall(r"-m (admin_dashboard\.[\w.]+)", text))
    for m in sorted(modules):
        if not (ROOT / "SSP" / (m.replace(".", "/") + ".py")).exists():
            problems.append(f"module not found: {m}")

    for line in problems:
        print(line)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
