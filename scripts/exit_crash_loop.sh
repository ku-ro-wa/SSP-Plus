#!/usr/bin/env bash
# Start and close the kiosk app N times and count the runs that crash on the way out.
#
# For the occasional segfault after the app has closed (crash.log, Nov 6). Each
# run starts the app, waits for it to come up, sends SIGTERM (the same close ->
# cleanup() -> exit path as Ctrl+C or a systemd stop) and records how it ended.
# A segfault exits 139, an abort 134, a clean close 0.
#
# On the kiosk, with the graphical session up and the service stopped:
#   systemctl --user stop ssp-kiosk
#   scripts/exit_crash_loop.sh 40        # runs, default 30
#   systemctl --user start ssp-kiosk
#
# UP_SECONDS (default 25) is how long each run stays up before the close.
# The summary goes to SSP/logs/exit-loop-<time>.txt; the dumps themselves are in
# SSP/logs/crash.log under each run's "--- pid N ..." markers, and each run's
# output is in SSP/logs/app.log.
set -u

cd "$(dirname "$0")/.." || exit 1
RUNS=${1:-30}
UP_SECONDS=${UP_SECONDS:-25}
PYTHON=${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}
SUMMARY="SSP/logs/exit-loop-$(date +%Y%m%d-%H%M%S).txt"
mkdir -p SSP/logs
RUN_OUT=$(mktemp)
trap 'rm -f "$RUN_OUT"' EXIT

if pgrep -f "SSP/main_app.py" >/dev/null; then
    echo "The kiosk app is running (pgrep -af main_app.py). Stop it first:"
    echo "  systemctl --user stop ssp-kiosk"
    exit 1
fi

clean=0; segv=0; abrt=0; other=0
echo "exit-crash loop: $RUNS runs, ${UP_SECONDS}s up, $PYTHON, $(git rev-parse --short HEAD)" | tee "$SUMMARY"

for i in $(seq 1 "$RUNS"); do
    # The terminal output, not app.log: Qt writes its own fatal messages (e.g.
    # "could not connect to display") straight to stderr, which app.log never sees.
    "$PYTHON" -X utf8 SSP/main_app.py >"$RUN_OUT" 2>&1 &
    pid=$!
    sleep "$UP_SECONDS"
    if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid"; code=$?
        # A run that dies before the close never tests the exit, and the next
        # one will almost certainly die the same way: stop and show why.
        other=$((other + 1))
        {
            echo "run $i pid $pid: died before the close, exit $code. Stopping: this tests startup, not exit."
            [ "$code" -eq 3 ] && echo "Another copy holds the lock."
            echo "--- end of its output ---"
            tail -15 "$RUN_OUT"
        } | tee -a "$SUMMARY"
        echo "If it says it can't connect to the display, run this from a terminal on the kiosk's"
        echo "own desktop, or over SSH with the session's DISPLAY and XAUTHORITY exported."
        break
    fi
    kill -TERM "$pid"
    # cleanup() waits on threads; give it a minute, then say so instead of hanging.
    for _ in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    if kill -0 "$pid" 2>/dev/null; then
        echo "run $i pid $pid: still running 60s after SIGTERM, killing" | tee -a "$SUMMARY"
        kill -KILL "$pid"
    fi
    wait "$pid"; code=$?
    case $code in
        0)   clean=$((clean + 1)); what="clean" ;;
        139) segv=$((segv + 1));   what="SEGFAULT" ;;
        134) abrt=$((abrt + 1));   what="ABORT" ;;
        *)   other=$((other + 1)); what="other" ;;
    esac
    echo "run $i pid $pid: exit $code $what" | tee -a "$SUMMARY"
done

echo "clean $clean, segfault $segv, abort $abrt, other $other" | tee -a "$SUMMARY"
echo "Summary: $SUMMARY. Dumps: grep -n -A3 'pid <N> ' SSP/logs/crash.log"
