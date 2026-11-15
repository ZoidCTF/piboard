"""piboard dashboard server.

Serves the page in web/ and cached JSON under /api/*. One background thread
fetches each external source on its own schedule; the last good result is kept
in memory and on disk, so the screen survives network blips and reboots.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from zoneinfo import ZoneInfo

import homeassistant
import ical
import seasonal
import sources

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".avif": "image/avif",
}
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".avif"}

log = logging.getLogger("piboard")


def load_config():
    path = Path(os.environ.get("PIBOARD_CONFIG", ROOT / "config.json"))
    if not path.exists():
        log.warning("%s not found, using config.example.json", path)
        path = ROOT / "config.example.json"
    return json.loads(path.read_text(encoding="utf-8"))


class Source:
    """One external feed: refreshed on an interval, last good result cached."""

    def __init__(self, name, fetch, interval, cache_dir, tz, daily=False):
        self.name = name
        self.fetch = fetch
        self.interval = interval
        self.daily = daily
        self.tz = tz
        self.path = cache_dir / f"{name}.json"
        self.data = None
        self.updated = None
        self.error = None
        self.failures = 0
        self.next_due = 0.0
        self.lock = threading.Lock()
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            self.data, self.updated = saved["data"], saved["updated"]
        except (OSError, ValueError, KeyError):
            pass

    def due(self, now):
        if now >= self.next_due:
            return True
        # Daily sources also refresh as soon as the local date rolls over.
        return (self.daily and self.failures == 0 and self.updated is not None
                and self._day(now) != self._day(self.updated))

    def _day(self, ts):
        return datetime.fromtimestamp(ts, self.tz).date()

    def refresh(self):
        try:
            data = self.fetch()
        except Exception as exc:
            self.failures += 1
            self.error = f"{type(exc).__name__}: {exc}"
            retry = min(60 * 2 ** (self.failures - 1), self.interval)
            self.next_due = time.time() + retry
            log.warning("%s fetch failed (%s); retrying in %ds", self.name, self.error, retry)
            return
        with self.lock:
            self.data, self.updated, self.error, self.failures = data, time.time(), None, 0
        self.next_due = self.updated + self.interval
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"data": data, "updated": self.updated}), encoding="utf-8")
        os.replace(tmp, self.path)
        log.info("%s refreshed", self.name)

    def payload(self):
        with self.lock:
            return {"data": self.data, "updated": self.updated, "error": self.error}


def run_scheduler(srcs):
    while True:
        now = time.time()
        for src in srcs.values():
            if src.due(now):
                src.refresh()
        time.sleep(5)


def read_credits(folder):
    """Map photo filename -> credit line from CREDITS.txt.

    Each entry is a filename on its own line followed by an indented credit;
    only the first indented line is used.
    """
    credits, current = {}, None
    try:
        lines = (folder / "CREDITS.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return credits
    for line in lines:
        if line and not line[0].isspace():
            current = line.strip()
        elif current and line.strip() and current not in credits:
            credits[current] = line.strip()
    return credits


def list_photos(folder):
    if not folder.is_dir():
        return []
    credits = read_credits(folder)
    names = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in PHOTO_TYPES)
    return [{"url": "/photos/" + quote(n), "credit": credits.get(n, "")} for n in names]


CLIENT_DEFAULTS = {
    "title": "",
    "accent": "#ffb45c",
    "clock_24h": False,
    "reload_at": "03:00",
    "poll_seconds": 60,
    "map": {},
    "photos": {"rotate_minutes": 10},
    "night": {"start": "22:00", "end": "06:00", "dim": 0.7, "hide_map": True},
    "ambience": {"sky": True, "weather": True},
    "seasonal": seasonal.DEFAULTS,
}


def client_config(cfg):
    """Settings the page needs, with defaults filled in (one level deep for sections)."""
    out = {}
    for key, default in CLIENT_DEFAULTS.items():
        value = cfg.get(key, default)
        out[key] = {**default, **value} if isinstance(default, dict) and isinstance(value, dict) else value
    out["home"] = homeassistant.enabled(cfg)   # never the token itself
    return out


def make_handler(cfg, srcs):
    photo_dir = (ROOT / cfg["photos"]["folder"]).resolve()
    client_cfg = client_config(cfg)
    last_ping = [None]   # time.monotonic() of the page's last /api/ping

    class Handler(BaseHTTPRequestHandler):
        server_version = "piboard"

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path.startswith("/api/"):
                self.api(path[len("/api/"):])
            elif path.startswith("/photos/"):
                self.file(photo_dir, path[len("/photos/"):], "max-age=86400")
            else:
                self.file(WEB, path.lstrip("/") or "index.html", "no-cache")

        def api(self, name):
            if name in srcs:
                body = srcs[name].payload()
            elif name == "photos":
                body = {"data": list_photos(photo_dir)}
            elif name == "config":
                body = client_cfg
            elif name.startswith("camera/"):
                self.camera(name[len("camera/"):])
                return
            elif name == "ping":
                last_ping[0] = time.monotonic()
                body = {"ok": True}
            elif name == "health":
                # page_age: seconds since the page last pinged (None: not since the server
                # started). bin/kiosk.sh uses it to spot a blank or frozen Chromium.
                age = None if last_ping[0] is None else round(time.monotonic() - last_ping[0])
                body = {"ok": True, "page_age": age}
            else:
                self.send_error(404)
                return
            self.send(json.dumps(body).encode(), "application/json", "no-store")

        def camera(self, which):
            # Doorbell snapshots, fetched from Home Assistant so its token stays here.
            if which not in ("camera", "package_camera") or not homeassistant.enabled(cfg):
                self.send_error(404)
                return
            try:
                got = homeassistant.camera_snapshot(cfg, which)
            except OSError as exc:
                log.warning("camera %s failed: %s", which, exc)
                got = None
            if not got:
                self.send_error(502)
                return
            body, ctype = got
            self.send(body, ctype or "image/jpeg", "no-store")

        def file(self, base, rel, cache):
            target = (base / rel).resolve()
            if not target.is_relative_to(base) or not target.is_file():
                self.send_error(404)
                return
            ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
            self.send(target.read_bytes(), ctype, cache)

        def send(self, body, ctype, cache):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

    return Handler


def main():
    logging.basicConfig(level=os.environ.get("PIBOARD_LOG", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    tz = ZoneInfo(cfg["timezone"])
    cache_dir = ROOT / "cache"
    cache_dir.mkdir(exist_ok=True)
    minutes = {"weather": 15, "air": 30, "calendar": 10, "wotd": 1440, "fx": 180,
               "alerts": 10, "fires": 30, "lake": 60, "snow": 60, "roads": 15, "trips": 60, "aurora": 30, "home": 1 / 6,
               **cfg.get("refresh_minutes", {})}

    def source(name, fetch, daily=False):
        return Source(name, lambda: fetch(cfg), minutes[name] * 60, cache_dir, tz, daily)

    srcs = {
        "weather": source("weather", sources.weather),
        "air": source("air", sources.air),
        "calendar": source("calendar", ical.calendar, daily=True),
        "wotd": source("wotd", sources.wotd, daily=True),
        "fx": source("fx", sources.fx),
        "alerts": source("alerts", seasonal.alerts),
        "fires": source("fires", seasonal.fires),
        "lake": source("lake", seasonal.lake),
        "snow": source("snow", seasonal.snow),
        "roads": source("roads", seasonal.roads),
        "aurora": source("aurora", seasonal.aurora),
    }
    if homeassistant.enabled(cfg):
        srcs["home"] = source("home", homeassistant.home)
    # Trips are read out of the cached calendar, so they refresh after it.
    srcs["trips"] = Source("trips", lambda: seasonal.trips(cfg, srcs["calendar"].data),
                           minutes["trips"] * 60, cache_dir, tz, daily=True)
    threading.Thread(target=run_scheduler, args=(srcs,), daemon=True).start()

    host, port = cfg["host"], cfg["port"]
    server = ThreadingHTTPServer((host, port), make_handler(cfg, srcs))
    log.info("Serving on http://%s:%d", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
