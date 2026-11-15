#!/usr/bin/env bash
# Idempotent installer for the piboard dashboard on Raspberry Pi OS.
# Run as your normal desktop user from the project folder: ./install.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
KIOSK="$DIR/bin/kiosk.sh"

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as your normal user; it uses sudo where needed." >&2
  exit 1
fi

echo "==> Packages"
pkgs=(python3-venv curl fonts-roboto)
if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
  if apt-cache show chromium >/dev/null 2>&1; then pkgs+=(chromium); else pkgs+=(chromium-browser); fi
fi
missing=()
for p in "${pkgs[@]}"; do
  dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
done
if [ ${#missing[@]} -gt 0 ]; then
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
fi

echo "==> Python venv"
[ -x "$DIR/.venv/bin/python" ] || python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --quiet --upgrade -r "$DIR/requirements.txt"

echo "==> Config"
if [ ! -f "$DIR/config.json" ]; then
  cp "$DIR/config.example.json" "$DIR/config.json"
  echo "    Created config.json; add your calendar URL to it."
fi
chmod 600 "$DIR/config.json"
mkdir -p "$DIR/photos" "$DIR/cache"

echo "==> systemd service"
unit=/etc/systemd/system/piboard.service
tmp=$(mktemp)
cat >"$tmp" <<EOF
[Unit]
Description=piboard dashboard server
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python $DIR/server/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
if ! sudo cmp -s "$tmp" "$unit"; then
  sudo install -m 644 "$tmp" "$unit"
  sudo systemctl daemon-reload
fi
rm -f "$tmp"
sudo systemctl enable piboard.service >/dev/null 2>&1
sudo systemctl restart piboard.service

echo "==> Desktop session"
chmod +x "$KIOSK"
session="${PIBOARD_SESSION:-}"
if [ -z "$session" ]; then
  conf=$(grep -hsE '^(autologin-session|user-session)=' /etc/lightdm/lightdm.conf || true)
  case "$conf" in
    *labwc*) session=labwc ;;
    *wayfire*) session=wayfire ;;
    *LXDE*) session=lxde ;;
    *)
      if command -v labwc >/dev/null; then session=labwc
      elif command -v wayfire >/dev/null; then session=wayfire
      else session=lxde
      fi ;;
  esac
fi
echo "    Session: $session"

# A user autostart file replaces the system one, so seed it from the system copy
# (panel, desktop, display config) before adding our line.
seed_and_add() {
  local file=$1 system=$2 line=$3
  mkdir -p "$(dirname "$file")"
  if [ ! -f "$file" ] && [ -f "$system" ]; then cp "$system" "$file"; fi
  touch "$file"
  grep -qF "$KIOSK" "$file" || echo "$line" >>"$file"
}

case "$session" in
  labwc)
    seed_and_add "$HOME/.config/labwc/autostart" /etc/xdg/labwc/autostart "$KIOSK &"
    # With no mouse attached the pointer never enters the page, so CSS cursor:none
    # never applies. A window rule hides it (and parks it in a corner) when the
    # kiosk window opens; moving a real mouse brings it back.
    rc="$HOME/.config/labwc/rc.xml"
    if [ ! -f "$rc" ] && [ -f /etc/xdg/labwc/rc.xml ]; then cp /etc/xdg/labwc/rc.xml "$rc"; fi
    [ -f "$rc" ] || printf '<?xml version="1.0"?>\n<labwc_config>\n</labwc_config>\n' >"$rc"
    if ! grep -q "piboard: hide the cursor" "$rc"; then
      rule='    <!-- piboard: hide the cursor when the kiosk window opens -->\n    <windowRule identifier="chromium*">\n      <action name="WarpCursor" to="output" x="-1" y="-1" />\n      <action name="HideCursor" />\n    </windowRule>'
      if grep -q "<windowRules>" "$rc"; then
        sed -i "0,/<windowRules>/s##<windowRules>\n$rule#" "$rc"
      else
        sed -i "s#</labwc_config>#  <windowRules>\n$rule\n  </windowRules>\n</labwc_config>#" "$rc"
      fi
    fi
    ;;
  wayfire)
    ini="$HOME/.config/wayfire.ini"
    touch "$ini"
    if ! grep -qF "$KIOSK" "$ini"; then
      if grep -q '^\[autostart\]' "$ini"; then
        sed -i "/^\[autostart\]/a piboard = $KIOSK" "$ini"
      else
        printf '\n[autostart]\npiboard = %s\n' "$KIOSK" >>"$ini"
      fi
    fi
    ;;
  lxde)
    seed_and_add "$HOME/.config/lxsession/LXDE-pi/autostart" /etc/xdg/lxsession/LXDE-pi/autostart "@$KIOSK"
    ;;
esac

if command -v raspi-config >/dev/null; then
  echo "==> Desktop autologin and no screen blanking"
  sudo raspi-config nonint do_boot_behaviour B4
  sudo raspi-config nonint do_blanking 1
fi

echo
echo "Done. Server: http://localhost:$(python3 -c 'import json; print(json.load(open("'"$DIR"'/config.json"))["port"])')/"
echo "Reboot to start the kiosk: sudo reboot"
