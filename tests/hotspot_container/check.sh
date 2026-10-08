#!/bin/bash
# Runs inside the container (see run.sh). Renders the hotspot files with
# scripts/setup_hotspot.py --root, then checks them against real nft and
# dnsmasq: a "phone" network namespace sits on a veth named wlan0, an
# "uplink" namespace stands in for the router on eth0.
#
# Not covered (needs the Pi): hostapd on a real radio, ap_isolate,
# NetworkManager, systemd units, real phones.
set -uo pipefail

FAILED=0
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILED=1; }
check() {  # check "<description>" <command...>   expects success
    local desc=$1; shift
    if "$@" >/dev/null 2>&1; then pass "$desc"; else fail "$desc"; fi
}
refuse() {  # refuse "<description>" <command...>  expects failure
    local desc=$1; shift
    if "$@" >/dev/null 2>&1; then fail "$desc"; else pass "$desc"; fi
}

PI=10.3.141.1
HOST=print.aio-spark.example
STAGE=/stage
in_phone() { ip netns exec phone "$@"; }
in_uplink() { ip netns exec uplink "$@"; }

# --- render ----------------------------------------------------------------
# Render from .env.example (not the developer's own .env) in a scratch copy, so
# the result doesn't depend on whoever runs it. config.py reads .env from cwd.
mkdir -p /tmp/repo/SSP
cp -r /repo/scripts /tmp/repo/
cp /repo/SSP/config.py /tmp/repo/SSP/
cp /repo/.env.example /tmp/repo/.env
cd /tmp/repo
export WIFI_HOTSPOT_ENABLED=true KIOSK_ID=kiosk-01
check "setup_hotspot.py renders under --root" python3 scripts/setup_hotspot.py --root "$STAGE"

NFT=$STAGE/etc/ssp-hotspot/firewall.nft
DNSMASQ=$STAGE/etc/dnsmasq.d/ssp-hotspot.conf

# --- syntax ------------------------------------------------------------------
check "nft accepts the ruleset (nft -c)" nft -c -f "$NFT"
check "dnsmasq accepts its config (dnsmasq --test)" dnsmasq --test --conf-file="$DNSMASQ"

# --- topology ----------------------------------------------------------------
#   phone ns [phone0 10.3.141.x] --veth-- [wlan0 10.3.141.1] kiosk [eth0-up 192.168.50.1] --veth-- [up0 192.168.50.2] uplink ns
ip netns add phone
ip netns add uplink
ip link add wlan0 type veth peer name phone0
ip link set phone0 netns phone
ip link add eth0-up type veth peer name up0
ip link set up0 netns uplink
ip addr add $PI/24 dev wlan0 && ip link set wlan0 up
ip addr add 192.168.50.1/24 dev eth0-up && ip link set eth0-up up
in_phone ip link set lo up && in_phone ip link set phone0 up
in_uplink ip link set lo up
in_uplink ip addr add 192.168.50.2/24 dev up0 && in_uplink ip link set up0 up
in_uplink ip route add 10.3.141.0/24 via 192.168.50.1
echo 1 > /proc/sys/net/ipv4/ip_forward   # worst case: kernel forwarding on, firewall must still stop it

# Listeners on the kiosk: SSH, the dashboard, the Portal. Plus one in the uplink.
for port in 22 8100 8000; do nc -lk -p $port >/dev/null 2>&1 & done
in_uplink nc -lk -p 80 >/dev/null 2>&1 &
sleep 0.5

# --- control: without our firewall, everything is reachable -----------------
# (proves the checks below would catch a firewall that does nothing)
in_phone ip addr add 10.3.141.200/24 dev phone0
in_phone ip route add default via $PI
check "control: phone reaches SSH with no firewall" in_phone nc -z -w2 $PI 22
check "control: phone reaches uplink with no firewall" in_phone nc -z -w2 192.168.50.2 80
in_phone ip addr flush dev phone0

# --- with our firewall + dnsmasq --------------------------------------------
check "firewall loads" nft -f "$NFT"
check "firewall reloads idempotently" nft -f "$NFT"
check "firewall is its own table only" bash -c "[ \"\$(nft list tables)\" = 'table inet ssp_hotspot' ]"

dnsmasq --conf-file="$DNSMASQ" --pid-file=/run/dnsmasq.pid --dhcp-leasefile=/tmp/leases
sleep 0.5

LEASE=$(in_phone busybox udhcpc -i phone0 -n -q -f -t 3 -s /bin/true 2>&1 | grep -oE 'lease of [0-9.]+' | awk '{print $3}')
if [[ "$LEASE" =~ ^10\.3\.141\.([0-9]+)$ ]] && [ "${BASH_REMATCH[1]}" -ge 2 ]; then
    pass "phone gets a DHCP lease in range ($LEASE)"
else
    fail "phone gets a DHCP lease (got '$LEASE')"
    LEASE=10.3.141.200
fi
in_phone ip addr add "$LEASE"/24 dev phone0 2>/dev/null
in_phone ip route replace default via $PI

ANSWER=$(in_phone dig +short +time=2 +tries=1 @$PI $HOST A)
if [ "$ANSWER" = "$PI" ]; then pass "dnsmasq answers $HOST with $PI"; else fail "dnsmasq answers $HOST (got '$ANSWER')"; fi
ANSWER=$(in_phone dig +short +time=2 +tries=1 @$PI example.com A)
if [ -z "$ANSWER" ]; then pass "dnsmasq resolves nothing else (example.com)"; else fail "dnsmasq resolved example.com: $ANSWER"; fi
check "DNS over TCP is allowed" in_phone dig +tcp +short +time=2 +tries=1 @$PI $HOST A

check  "phone reaches the Portal (tcp/8000)" in_phone nc -z -w2 $PI 8000
refuse "phone can't reach SSH (tcp/22)" in_phone nc -z -w2 $PI 22
refuse "phone can't reach the dashboard (tcp/8100)" in_phone nc -z -w2 $PI 8100
refuse "phone can't ping the kiosk" in_phone ping -c1 -W1 $PI
refuse "phone can't reach the uplink side through the kiosk" in_phone nc -z -w2 192.168.50.2 80
check  "phone's internet traffic is refused at once, not left to time out" bash -c \
    's=$(date +%s%N); ! ip netns exec phone nc -z -w5 192.168.50.2 80; [ $(( ($(date +%s%N) - s) / 1000000 )) -lt 1000 ]'
refuse "phone can't reach the kiosk's uplink address" in_phone nc -z -w2 192.168.50.1 22
refuse "uplink can't reach into the hotspot" in_uplink nc -z -w2 "$LEASE" 80
check  "SSH over the uplink still works" in_uplink nc -z -w2 192.168.50.1 22
check  "dashboard over the uplink still works (loopback binding is ADR 0005's job)" in_uplink nc -z -w2 192.168.50.1 8100

echo
if [ $FAILED -eq 0 ]; then echo "All hotspot container checks passed."; else echo "Some hotspot container checks FAILED."; fi
exit $FAILED
