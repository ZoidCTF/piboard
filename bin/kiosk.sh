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
    "$PAGE" &
  PID=$!

  # Watchdog: the page pings the server once a minute (see /api/health's page_age).
  # If Chromium comes up blank (e.g. its network service crashed during a busy boot and
  # the first load was lost) or the page freezes, restart it. Only the page going quiet
  # counts: if the server itself is down, Chromium is left alone.
  started=$(date +%s)
  quiet_since=""
  while kill -0 "$PID" 2>/dev/null; do
    sleep 15
    age=$(curl -fs --max-time 5 "${URL}api/health" |
          python3 -c 'import json,sys; a=json.load(sys.stdin).get("page_age"); print("none" if a is None else a)' 2>/dev/null) || continue
    now=$(date +%s)
    if [ "$age" = "none" ] || [ "$age" -gt "$PAGE_STALE" ] || [ "$age" -gt $((now - started)) ]; then
      quiet_since=${quiet_since:-$now}
      if [ $((now - started)) -ge "$PAGE_GRACE" ] && [ $((now - quiet_since)) -ge "$PAGE_GRACE" ]; then
        echo "kiosk: page silent (page_age=$age), restarting Chromium"
        kill "$PID"
        for _ in $(seq 1 10); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
        kill -9 "$PID" 2>/dev/null
        break
      fi
    else
      quiet_since=""
    fi
  done
  wait "$PID" 2>/dev/null
  sleep 5
done
