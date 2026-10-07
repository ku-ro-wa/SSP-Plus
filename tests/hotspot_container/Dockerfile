# Linux stand-in for the kiosk Pi, used by `make test-hotspot`. Same Debian
# release as Raspberry Pi OS Bookworm, so nft and dnsmasq are the versions the
# Pi gets. There's no Wi-Fi radio here: hostapd isn't run, and wlan0 is a veth.
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      nftables dnsmasq iproute2 dnsutils netcat-openbsd busybox python3 \
 && rm -rf /var/lib/apt/lists/*
