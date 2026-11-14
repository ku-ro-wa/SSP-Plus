#!/usr/bin/env bash
# Logs what the printer and CUPS each report, every few seconds, so a real jam
# (or any other fault) leaves a record of which signals actually change.
#
# Run on the kiosk with the app stopped (systemctl --user stop ssp-kiosk):
#   scripts/printer_watch.sh [interval_seconds] [outfile]
# then do the thing you want to observe (print from a terminal, cause the
# fault, clear it) and stop with Ctrl+C. A line is written only when something
# changes, with a timestamp, so the file stays short.
#
# Each sample records:
#   ipp   printer-state, printer-state-reasons and the non-empty
#         printer-alert-description entries, straight from the printer
#   cups  the queue's state line and its Alerts: line
#   jobs  jobs still queued (lpstat -o)
#   scan  whether eSCL answers at all (HTTP status of /eSCL/ScannerStatus)

INTERVAL="${1:-3}"
OUT="${2:-printer-watch-$(date +%Y%m%d-%H%M%S).log}"
PRINTER="${PRINTER_NAME:-HP_Smart_Tank}"
URI="ipp://localhost:60000/ipp/print"

sample() {
    local ipp cups jobs scan
    ipp=$(timeout 8 ipptool -tv "$URI" get-printer-attributes.test 2>/dev/null |
        awk -F' = ' '
            /printer-state \(enum\)/                 {s=$2}
            /printer-state-reasons \(/               {r=$2}
            /printer-alert-description \(/           {d=$2}
            /media-ready \(/                         {m=$2}
            END {
                if (s == "" && r == "") { print "NO-ANSWER"; exit }
                gsub(/,+/, ",", d); gsub(/^,|,$/, "", d)
                print "state=" s " reasons=" r " media-ready=" m " alerts=" d
            }')
    [ -z "$ipp" ] && ipp="NO-ANSWER"
    cups=$(timeout 8 lpstat -l -p "$PRINTER" 2>&1 |
        awk '/^printer /{st=$0} /Alerts:/{a=$0} END{gsub(/^[ \t]+/,"",a); print st " | " a}')
    jobs=$(timeout 8 lpstat -o 2>&1 | tr '\n' ';')
    scan=$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://localhost:60000/eSCL/ScannerStatus)
    echo "ipp: $ipp | cups: $cups | jobs: ${jobs:-none} | scan: $scan"
}

echo "Watching $PRINTER every ${INTERVAL}s -> $OUT (Ctrl+C to stop)"
last=""
while true; do
    now=$(sample)
    if [ "$now" != "$last" ]; then
        line="$(date '+%Y-%m-%d %H:%M:%S') $now"
        echo "$line" | tee -a "$OUT"
        last="$now"
    fi
    sleep "$INTERVAL"
done
