SHELL := /bin/bash

# Auto-detect Python: picks up the Windows Python inside WSL, falls back to
# python3 on native Linux/macOS. Override any time: make PYTHON=/path/to/python test
# Find the first Windows Python (sorted ascending) that has pytest installed
_WIN_PY := $(shell for p in $$(ls /mnt/c/Users/*/AppData/Local/Programs/Python/Python3*/python.exe 2>/dev/null | sort -V); do $$p -c "import pytest" 2>/dev/null && echo $$p && break; done)
PYTHON ?= $(if $(_WIN_PY),$(_WIN_PY),python3)

.PHONY: run run-sim test lint

# Run the app on the kiosk (requires hardware + CUPS + pigpiod)
# Runs from repo root so config.py finds .env here (SSP/.env is gitignored)
# -X utf8 forces UTF-8 stdout on Windows (avoids CP1252 emoji errors)
run:
	$(PYTHON) -X utf8 SSP/main_app.py

# Run the app in simulation mode — no GPIO, CUPS, or modem required
run-sim:
	SIM_MODE=true $(PYTHON) -X utf8 SSP/main_app.py

# Run the test suite
test:
	$(PYTHON) -m pytest tests/ -v

# Lint the source tree (max line length 120, ignoring cache dirs)
lint:
	$(PYTHON) -m flake8 SSP/ --max-line-length=120 --exclude=__pycache__,__init__.py
