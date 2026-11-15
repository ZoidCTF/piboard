# piboard

A self-hosted wall dashboard for a Raspberry Pi 5 driving a 1920×1080 screen. See [SPEC.md](SPEC.md).

- `server/` is a stdlib Python HTTP server. It fetches weather (Open-Meteo), the calendar (iCal), the word of the day (Merriam-Webster RSS) and currency rates (Frankfurter, with open.er-api.com as a fallback) on a schedule, and caches the last good result in `cache/`.
- `web/` holds the full-screen page. It polls `/api/*` and keeps showing old data if a request fails.
- `bin/kiosk.sh` waits for the server, then keeps Chromium running in kiosk mode. The page pings `/api/ping` once a minute; if it goes silent for two minutes (a blank page after a busy boot, or a frozen tab), the script restarts Chromium.
- `install.sh` sets up the venv, the systemd service, desktop autostart, autologin and no screen blanking. It's safe to re-run.

## Install on the Pi

```bash
git clone <this repo> ~/piboard   # or copy the folder over
cd ~/piboard
bash install.sh
nano config.json                  # paste the Google "Secret address in iCal format" into calendar.urls
sudo systemctl restart piboard
sudo reboot
```

Put background photos (`.jpg`, `.png`, `.webp`) in `photos/`. With more than one, they crossfade every `photos.rotate_minutes`. Prepare them first with `tools/prep_photos.py`: it crops to 1920×1080 (full-size photos waste a lot of the Pi's memory) and mutes the colour so the text stands out. Credits for the current set are in `photos/CREDITS.txt`; originals of non-Commons photos are kept in `photos/originals/`, which the dashboard ignores.

## Look and behaviour

- Sections sit on translucent panels; `accent` in `config.json` sets the highlight colour.
- Night mode (`night` in `config.json`, default 22:00–06:00) dims the screen and parks the wind map.
- The middle strip shows an hourly forecast, the AQHI (computed from Open-Meteo air quality) and sunrise/sunset.
- Weather icons are Meteocons and fonts are bundled in `web/`, so nothing loads from the internet except data; see `web/THIRD_PARTY.txt`.
- Sky light (`ambience.sky`): the accent colour and a wash over the photo follow the sun through night, dawn, day, golden hour and blue hour.
- Visible weather (`ambience.weather`): rain or snow on the glass, drifting fog and lightning, matching current conditions. Nothing is drawn (and nothing runs) in clear weather; rain and snow pause in night mode.
- Seasonal cards rotate with the word of the day (`seasonal` in `config.json`; months and places have defaults in `server/seasonal.py`): an upcoming trip from the calendar with the destination's forecast, wildfires within 150 km (BC Wildfire Service), UV and Okanagan Lake level, Big White snow, Coquihalla/Connector webcams with DriveBC closures, and a northern-lights card on nights when NOAA's Kp forecast reaches `seasonal.aurora.min_kp` (default 5; 7+ means it may be overhead), with Open-Meteo cloud cover.
- A notices row above the cards shows Environment Canada alerts, frost, smoke, aurora tonight (or active now), imminent trips and collection day. Collection day is set in `seasonal.collection`, e.g. `[{"name": "Garbage", "weekday": "Thursday", "every_weeks": 1}, {"name": "Recycling", "weekday": "Thursday", "every_weeks": 2, "next": "2026-10-22"}]`.
- Home Assistant (`home_assistant` in `config.json`: `url`, a long-lived access `token` from your HA profile, and entity ids; see `config.example.json`): an "Inside" card with each thermostat's temperature, humidity and a dot while heating, plus CO₂; notices for a water leak, a fridge/freezer door left open, an oven on for 90+ minutes, high CO₂, the alarm being armed, a car charging, and a package at the door. When the doorbell rings, its camera takes over the card panel for three minutes. The token stays on the server: the page gets a summary from `/api/home` and snapshots from `/api/camera/camera` (or `package_camera`). Leave `token` empty to turn it off.
- For testing: `?month=N` previews another season's cards, `?card=fires` (or `wotd`, `trip`, `summer`, `snow`, `roads`, `aurora`) holds one card, `?aurora=N` fakes tonight's Kp, `?night=1` / `?night=0` forces night mode, `?photo=N` starts on a given photo, `?at=HH:MM` simulates the time of day for the sky light, and `?wx=rain|drizzle|thunder|snow|sleet|fog` forces visible weather. On the Pi, `bin/kiosk.sh '?wx=rain'` runs the kiosk with such a suffix.

## Handy commands

```bash
journalctl -u piboard -f          # server log
curl -s localhost:8080/api/calendar | head -c 500
pkill -f kiosk.sh; pkill chromium # drop to the desktop until next reboot
```

## Developing

```bash
python -m unittest tests/test_parsers.py
PIBOARD_CONFIG=some-config.json python server/app.py
```

## Licence

MIT for the project code (see [LICENSE](LICENSE)). Bundled icons and fonts keep their own licences; see `web/THIRD_PARTY.txt`.
