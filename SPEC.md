# piboard — self-hosted wall dashboard

A self-hosted wall dashboard that runs entirely on a Raspberry Pi, with no paid services.

## Architecture
- Small Python service (venv, systemd unit) on the Pi serving one full-screen HTML page plus JSON endpoints under `/api/*`.
- The server fetches and caches all external data (needed for CORS on the calendar and RSS feeds, and so the screen survives network blips). The page polls the API and keeps showing the last good data if a fetch fails.
- Chromium in kiosk mode at `http://localhost:<port>`, launched at login. Disable screen blanking, hide the cursor, reload the page once a day.
- Layout is 16:9 landscape and scales with viewport units (vw/vh) so it works at any resolution.
- `config.json` holds coordinates, the calendar URL, refresh intervals, and the photo folder. The calendar URL is a secret: keep it out of git.
- `install.sh` must be idempotent: create the venv, install the systemd service, and set up kiosk autostart.

## Layout
- **Top left:** the home's name (from config) in italic, large clock with small seconds, and the full date (e.g. "Wednesday, October 21").
- **Below the clock:** current temperature with a condition icon, then a 4-day forecast (Today, Thu, Fri, Sat) showing icon and high/low.
- **Bottom left:** weather map panel.
- **Top right, wide:** calendar grid, 3 weeks starting on the Sunday of the current week. Today's date is highlighted, and each day lists its event times and titles.
- **Bottom middle:** word of the day showing the word, pronunciation, part of speech, and definition.
- **Bottom:** currency rates for CAD into USD, EUR, and JPY.
- **Background:** a photo of the Okanagan valley, with a slight darkening scrim so the text stays readable. Load photos from a local folder and rotate through them if there are several.

## Data sources (no API keys)
- **Weather:** Open-Meteo forecast API for Kelowna, lat 49.888, lon -119.496, metric units, timezone America/Vancouver. Map WMO weather codes to icons. Refresh every 15 min.
- **Weather map:** an earth.nullschool-style wind view. Options:
  - Windy embed (`embed.windy.com`, wind or radar overlay).
  - Leaflet with the ECCC MSC GeoMet WMS radar layer (`geo.weather.gc.ca/geomet`).
  - Check whether earth.nullschool.net allows iframing; it's unverified.
- **Calendar:** Google Calendar's "Secret address in iCal format". Parse it server-side with `icalendar` and `recurring-ical-events`, because recurring events must expand correctly (e.g. a weekly Monday reminder). Handle all-day and multi-day events. Refresh every 10 min.
- **Word of the day:** Merriam-Webster RSS at `https://www.merriam-webster.com/wotd/feed/rss2`. Fetch once a day and strip the HTML into word, pronunciation, part of speech, and definition.
- **Currency:** Frankfurter (ECB rates), CAD to USD, EUR, and JPY. Verify the current endpoint, since it may be `api.frankfurter.app` or `api.frankfurter.dev/v1`. Add `open.er-api.com/v6/latest/CAD` as a fallback. Refresh every few hours.

## Pi-specific checks (do these first)
- Check the OS and session:
  - Raspberry Pi OS Bullseye uses X11/LXDE: `~/.config/lxsession/LXDE-pi/autostart`
  - Early Bookworm uses Wayfire: `~/.config/wayfire.ini` `[autostart]`
  - Late Bookworm and Trixie use labwc: `~/.config/labwc/autostart`
- The Chromium binary is `chromium-browser` on Bookworm and older, and `chromium` on Trixie. Detect which one exists rather than assuming.
- Check the Pi model and RAM before choosing animations. Keep the CPU load low: no heavy CSS blur, and the clock should update with one timer.

## Later (optional)
- Pull weather and calendar from Home Assistant (VM on Proxmox) instead of the external sources.
