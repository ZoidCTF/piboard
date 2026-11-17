#!/usr/bin/env bash
# Started from the desktop session's autostart: waits for the dashboard server,
# then keeps Chromium running full-screen on it (relaunching if it ever exits).
# An optional argument is appended to the page URL, e.g. kiosk.sh '?wx=rain'.
set -u

DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("port", 8080))' "$DIR/config.json" 2>/dev/null || echo 8080)
URL="http://localhost:$PORT/"
PAGE="$URL${1:-}"
PROFILE="$HOME/.config/piboard-chromium"
BROWSER=$(command -v chromium || command -v chromium-browser)
PAGE_GRACE=120   # seconds the page may go without pinging (after launch, or in a row) before a restart
PAGE_STALE=180   # a ping older than this counts as silent (the page pings every minute)
FD_LIMIT=${FD_LIMIT:-700}     # restart before any Chromium renderer nears the 1024 open-file limit
LOG="$HOME/.cache/piboard-chromium.log"   # Chromium's stderr; the previous run's is kept as .1
LOG_MAX=$((20 * 1024 * 1024))             # and whenever it grows past this
# Chromium only auto-detects Wayland when XDG_SESSION_TYPE is set, which isn't
# the case when launched outside the desktop session (e.g. over SSH).
OZONE=()
[ -n "${WAYLAND_DISPLAY:-}" ] && OZONE=(--ozone-platform=wayland)

for _ in $(seq 1 90); do
  curl -fs -o /dev/null "${URL}api/health" && break
  sleep 1
done

while true; do
  # After a power cut Chromium thinks it crashed and offers to restore; clear that.
  PREFS="$PROFILE/Default/Preferences"
  [ -f "$PREFS" ] && sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$PREFS"
  mkdir -p "$(dirname "$LOG")"
  [ -f "$LOG" ] && mv -f "$LOG" "$LOG.1"   # keep the previous run's log for diagnosis

  "$BROWSER" \
    --kiosk \
    "${OZONE[@]}" \
    --user-data-dir="$PROFILE" \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-session-crashed-bubble \
    --disable-features=Translate,TranslateUI \
    --password-store=basic \
    --check-for-update-interval=31536000 \
    "$PAGE" 2>>"$LOG" &
  PID=$!

  # Watchdog. Restart Chromium when any of these holds:
  # - The page stops pinging the server (it pings once a minute; see /api/health's
  #   page_age): a blank page after a busy boot, or a frozen tab. If the server itself
  #   is down, Chromium is left alone.
  # - A renderer has nearly run out of file descriptors. Each fetch whose response
  #   the page never reads holds a 2 MB shared-memory handle (the page reads them all
  #   now, but a regression would leak one per request); at 1024 it can no longer talk
  #   to the GPU and the screen goes white while the page's JavaScript carries on.
  # - The screen is almost entirely white twice in a row, whatever the cause. The
  #   dashboard never looks like that (dark scrim by day, dimmer still at night).
  started=$(date +%s)
  quiet_since=""
  white=0
  tick=0
  while kill -0 "$PID" 2>/dev/null; do
    sleep 15
    tick=$((tick + 1))
    now=$(date +%s)
    reason=""

    if age=$(curl -fs --max-time 5 "${URL}api/health" |
             python3 -c 'import json,sys; a=json.load(sys.stdin).get("page_age"); print("none" if a is None else a)' 2>/dev/null); then
      if [ "$age" = "none" ] || [ "$age" -gt "$PAGE_STALE" ] || [ "$age" -gt $((now - started)) ]; then
        quiet_since=${quiet_since:-$now}
        if [ $((now - started)) -ge "$PAGE_GRACE" ] && [ $((now - quiet_since)) -ge "$PAGE_GRACE" ]; then
          reason="page silent (page_age=$age)"
        fi
      else
        quiet_since=""
      fi
    fi

    fds=0
    for p in $(pgrep -f -- "--type=renderer"); do
      n=$(ls "/proc/$p/fd" 2>/dev/null | wc -l)
      [ "$n" -gt "$fds" ] && fds=$n
    done
    [ -z "$reason" ] && [ "$fds" -ge "$FD_LIMIT" ] && reason="renderer has $fds open files"

    # Screen check once a minute, after the page has had time to paint.
    if [ -z "$reason" ] && [ $((tick % 4)) -eq 0 ] && [ $((now - started)) -ge "$PAGE_GRACE" ] && command -v grim >/dev/null; then
      if grim -s 0.05 -t ppm - 2>/dev/null | python3 -c '
import re, sys
d = sys.stdin.buffer.read()
m = re.match(rb"P6\s+\d+\s+\d+\s+\d+\s", d)   # binary PPM header, then RGB bytes
px = d[m.end():] if m else b""
n = len(px) // 3
bright = sum(1 for i in range(0, n * 3, 3) if px[i] > 240 and px[i + 1] > 240 and px[i + 2] > 240)
sys.exit(0 if n and bright / n > 0.98 else 1)'; then
        white=$((white + 1))
        [ "$white" -ge 2 ] && reason="screen is white"
      else
        white=0
      fi
    fi

    [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt "$LOG_MAX" ] && : >"$LOG"

    if [ -n "$reason" ]; then
      echo "kiosk: $(date '+%F %T') $reason, restarting Chromium" | tee -a "$LOG"
      kill "$PID"
      for _ in $(seq 1 10); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
      kill -9 "$PID" 2>/dev/null
      break
    fi
  done
  wait "$PID" 2>/dev/null
  sleep 5
done
