#!/bin/bash
# =============================================================
# AIO SPARK — Wi-Fi Captive Portal Deployment Script
# Target: Raspberry Pi 4 running Raspberry Pi OS (Bookworm)
# Run as: sudo bash deploy_wifi_portal.sh
# =============================================================
# Sets up the captive portal infrastructure for the Wi-Fi
# Transfer Module. This script is Pi-specific — the FastAPI
# portal itself runs on any machine, but RaspAP and
# Nodogsplash require Linux + a physical Wi-Fi adapter.
#
# What this script does:
#   Phase 1 — System preparation
#   Phase 2 — RaspAP (Access Point)
#   Phase 3 — Nodogsplash (Captive Portal redirect)
#   Phase 4 — TLS Certificate
#   Phase 5 — FastAPI portal launch
# =============================================================

# Stop the script immediately if any command fails
set -euo pipefail

# =============================================================
# PHASE 1 — SYSTEM PREPARATION
# =============================================================

echo ">>> Phase 1: Updating system and installing dependencies..."

# Refresh the package list so apt knows about the latest versions
sudo apt update

# Create .env from example if it doesn't exist
# The app calls sys.exit(1) on startup if .env is missing
if [ ! -f .env ]; then
    cp .env.example .env
    echo ">>> Created .env from .env.example"
    echo ">>> ACTION REQUIRED: Edit .env and fill in email credentials, admin PIN, etc."
fi

# Install Python pip and venv if not already present
sudo apt install -y python3-pip python3-venv

# Install git if not already present
sudo apt install -y git

echo ">>> Phase 1 complete."

# =============================================================
# PHASE 2 — RASPAP (ACCESS POINT)
# =============================================================

echo ">>> Phase 2: Installing RaspAP..."

# RaspAP turns the Pi's built-in Wi-Fi adapter (wlan0) into
# an Access Point. It manages hostapd (broadcasts the SSID),
# dnsmasq (assigns IP addresses to connecting devices via DHCP),
# and provides a web dashboard for AP configuration.
#
# Default AP after install:
#   SSID:     raspi-webgui
#   Password: ChangeMe
#   Gateway:  10.3.141.1
#
# After install, change the SSID to "AIO-SPARK" and set a
# strong password via the RaspAP dashboard at http://10.3.141.1

# Download and run the official RaspAP installer
# -s = silent mode (less output), -L = follow redirects
curl -sL https://install.raspap.com | bash

echo ">>> Phase 2 complete."
echo ">>> ACTION REQUIRED: Open http://10.3.141.1 in a browser"
echo ">>> and change the SSID to AIO-SPARK and set a password."


# =============================================================
# PHASE 3 — TLS CERTIFICATE
# =============================================================

echo ">>> Phase 3: Generating self-signed TLS certificate..."

# Riley's generate_tls_cert.py creates two files:
#   certs/cert.pem  — the certificate
#   certs/key.pem   — the private key
#
# These are self-signed, meaning no Certificate Authority
# issued them. The browser will show a trust warning on
# first connection — this is expected on a private LAN
# with no registered domain. The user clicks "Advanced"
# and proceeds anyway.
#
# The cert is valid for 825 days and is tied to the hostname
# aio-spark-kiosk.local and the gateway IP 10.3.141.1

# Navigate to the repo root first
cd "$(dirname "$0")/.."

# Run Riley's cert generator
python3 scripts/generate_tls_cert.py

# Set the cert and key paths in the environment
# WebAppThreadManager reads these to enable TLS on Uvicorn
export WIFI_TLS_CERTFILE=certs/cert.pem
export WIFI_TLS_KEYFILE=certs/key.pem

echo ">>> Phase 3 complete."
echo ">>> Certificate saved to certs/cert.pem"
echo ">>> Key saved to certs/key.pem"

# =============================================================
# PHASE 4 — NODOGSPLASH (CAPTIVE PORTAL REDIRECT)
# =============================================================

echo ">>> Phase 4: Installing and configuring Nodogsplash..."

# Nodogsplash intercepts the first HTTP request from any device
# that connects to the AIO-SPARK AP and redirects their browser
# to the FastAPI upload portal at https://10.3.141.1:8000/upload
#
# How it works:
#   1. Phone connects to AIO-SPARK Wi-Fi
#   2. Phone tries to open any website
#   3. Nodogsplash intercepts the HTTP request
#   4. Phone browser is redirected to the upload portal
#   5. User uploads PDF normally from there

# Install Nodogsplash from apt
sudo apt install -y nodogsplash

# Check if cert was generated successfully
# If cert exists use https, otherwise fall back to http

if [ -f "certs/cert.pem" ] && [ -f "certs/key.pem" ]; then
    PORTAL_SCHEME="https"
else
    PORTAL_SCHEME="http"
    echo ">>> WARNING: TLS cert not found, falling back to http"
fi

# Write Nodogsplash config using detected scheme
sudo tee /etc/nodogsplash/nodogsplash.conf > /dev/null << EOF
GatewayInterface wlan0
GatewayAddress 10.3.141.1
RedirectURL ${PORTAL_SCHEME}://10.3.141.1:8000/upload
FirewallRule allow tcp port 8000
Syslog 1
EOF

# Enable and start Nodogsplash
sudo systemctl enable nodogsplash
sudo systemctl start nodogsplash

echo ">>> Phase 4 complete."
echo ">>> Nodogsplash will redirect connecting devices to"
echo ">>> ${PORTAL_SCHEME}://10.3.141.1:8000/upload"

# =============================================================
# PHASE 5 — LAUNCH FASTAPI PORTAL
# =============================================================

echo ">>> Phase 5: Launching AIO SPARK Wi-Fi portal..."

# The portal runs as part of the full kiosk application via
# WebAppThreadManager. For standalone testing without the
# Kivy GUI, you can also run Uvicorn directly using the
# command below.
#
# WebAppThreadManager automatically picks up WIFI_TLS_CERTFILE
# and WIFI_TLS_KEYFILE from the environment (set in Phase 4)
# and passes them to Uvicorn — so TLS is enabled automatically
# when those variables are present.
#
# The portal will be reachable at:
#   https://10.3.141.1:8000/upload
#
# Connecting phones will be redirected here automatically
# by Nodogsplash (Phase 3).

# Option A — Full kiosk launch (normal production use):
echo ">>> To launch the full kiosk run:"
echo ">>>   python3 SSP/main_app.py"
echo ""

# Option B — Standalone portal only (for testing without GUI):
echo ">>> To launch the portal standalone run:"
echo ">>>   python3 -m uvicorn webapp.main:app \\"
echo ">>>     --app-dir SSP \\"
echo ">>>     --host 0.0.0.0 \\"
echo ">>>     --port 8000 \\"
echo ">>>     --ssl-certfile certs/cert.pem \\"
echo ">>>     --ssl-keyfile certs/key.pem"
echo ""

echo ">>> Phase 5 complete."
echo ">>> Deployment finished. AIO SPARK is ready."
echo ">>> Connect a phone to the AIO-SPARK Wi-Fi to test."

# =============================================================
# QUICK REFERENCE — POST DEPLOYMENT
# =============================================================
#
# Portal URL:       https://10.3.141.1:8000/upload
# RaspAP dashboard: http://10.3.141.1
# Default SSID:     raspi-webgui (change to AIO-SPARK)
# Default password: ChangeMe    (change immediately)
#
# Useful commands:
#   Check Nodogsplash status:  sudo systemctl status nodogsplash
#   Restart Nodogsplash:       sudo systemctl restart nodogsplash
#   Check RaspAP logs:         sudo journalctl -u hostapd
#   Check portal logs:         sudo journalctl -u uvicorn
#
# TLS certificate files:
#   certs/cert.pem  — present certificate to browser
#   certs/key.pem   — never share this file
#
# Browser trust warning:
#   Expected behavior on first connection. Click "Advanced"
#   then "Proceed to 10.3.141.1" to continue.
#
# Developer note (per docs/adr/0001-wifi-portal-...tls.md):
#   RaspAP + Nodogsplash is Pi-only infrastructure.
#   For local dev, run the portal directly with:
#   SIM_MODE=true make run-sim
# =============================================================