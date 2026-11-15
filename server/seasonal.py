"""Seasonal and situational feeds: weather alerts, wildfires, lake level,
ski-hill snow, highway conditions and upcoming trips.

Like sources.py, each fetcher returns JSON-able data or raises. Which cards
actually appear (and in which months) is decided by the page.
"""

import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sources import get_json, wmo_icon

DEFAULTS = {
    "card_seconds": 20,
    "fire_months": [4, 5, 6, 7, 8, 9, 10],
    "fire_radius_km": 150,
    "summer_months": [5, 6, 7, 8, 9],
    "winter_months": [11, 12, 1, 2, 3, 4],
    "frost_months": [3, 4, 5, 9, 10, 11],
    "lake_station": "08NM083",
    "ski": {"name": "Big White", "latitude": 49.7317, "longitude": -118.9431, "elevation": 1950},
    "roads": {
        "highways": ["5", "97C", "97", "33"],
        "radius_km": 150,
        "cameras": [{"id": 685, "name": "Coquihalla Summit"}, {"id": 1156, "name": "Pennask Summit"}],
    },
    # Open-Meteo forecasts reach 16 days, so trips further out get no forecast anyway.
    "trips": {"keywords": ["Flight", "✈"], "home": "Kelowna", "days_ahead": 16},
    "collection": [],
    # Northern lights: Kelowna sits near 55° geomagnetic latitude, so aurora shows low on the
    # northern horizon from about Kp 5 and can climb overhead from about Kp 7.
    "aurora": {"min_kp": 5, "overhead_kp": 7},
}

COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
ALERT_ORDER = {"warning": 0, "watch": 1, "advisory": 2, "statement": 3}
DRIVEBC = "https://www.drivebc.ca"
FIRES_URL = ("https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/"
             "BCWS_ActiveFires_PublicView/FeatureServer/0/query?")


def settings(cfg):
    return {**DEFAULTS, **cfg.get("seasonal", {})}


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def compass(lat1, lon1, lat2, lon2):
    """Direction from point 1 to point 2 as N, NE, E, ..."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    deg = math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                  math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)))
    return COMPASS[round((deg % 360) / 45) % 8]


def _home(cfg):
    return cfg["weather"]["latitude"], cfg["weather"]["longitude"]


# --- Environment Canada weather alerts -----------------------------------------

def alerts(cfg):
    lat, lon = _home(cfg)
    bbox = f"{lon - 0.1},{lat - 0.1},{lon + 0.1},{lat + 0.1}"
    d = get_json("https://api.weather.gc.ca/collections/weather-alerts/items?"
                 + urlencode({"f": "json", "lang": "en", "bbox": bbox, "limit": 50}))
    now = datetime.now(timezone.utc)
    found = {}
    for f in d["features"]:
        p = f["properties"]
        expires = p.get("expiration_datetime")
        if expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) < now:
            continue
        name = p.get("alert_name_en") or p.get("alert_short_name_en")
        if not name or name in found:
            continue
        text = (p.get("alert_text_en") or "").strip()
        found[name] = {
            "name": name[0].upper() + name[1:],
            "type": p.get("alert_type", ""),
            "summary": text.split("\n")[0][:160],
            "ends": p.get("event_end_datetime") or expires,
        }
    return sorted(found.values(), key=lambda a: ALERT_ORDER.get(a["type"], 9))


# --- BC Wildfire Service active fires ------------------------------------------

def fires(cfg):
    lat, lon = _home(cfg)
    radius = settings(cfg)["fire_radius_km"]
    d = get_json(FIRES_URL + urlencode({
        "where": "FIRE_STATUS <> 'Out'",
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "distance": radius,
        "units": "esriSRUnit_Kilometer",
        "outFields": "INCIDENT_NAME,FIRE_STATUS,CURRENT_SIZE,LATITUDE,LONGITUDE",
        "returnGeometry": "false",
        "f": "json",
    }))
    if "error" in d:
        raise ValueError(d["error"].get("message", "fire query failed"))
    found = []
    for f in d["features"]:
        a = f["attributes"]
        found.append({
            "name": a["INCIDENT_NAME"],
            "status": a["FIRE_STATUS"],
            "size_ha": round(a["CURRENT_SIZE"] or 0),
            "km": round(distance_km(lat, lon, a["LATITUDE"], a["LONGITUDE"])),
            "dir": compass(lat, lon, a["LATITUDE"], a["LONGITUDE"]),
        })
    found.sort(key=lambda f: f["km"])
    # "Under Control" fires aren't news; the card is about ones still active.
    active = [f for f in found if f["status"] in ("Out of Control", "Being Held")]
    return {
        "radius_km": radius,
        "count": len(found),
        "active": len(active),
        "out_of_control": sum(f["status"] == "Out of Control" for f in active),
        "nearest": active[:3],
        "largest": max(active, key=lambda f: f["size_ha"]) if active else None,
    }


# --- Okanagan Lake level (Environment Canada hydrometric) ----------------------

def lake(cfg):
    station = settings(cfg)["lake_station"]
    base = "https://api.weather.gc.ca/collections/hydrometric-realtime/items?"
    latest = get_json(base + urlencode({"f": "json", "STATION_NUMBER": station, "limit": 1,
                                        "sortby": "-DATETIME"}))["features"][0]["properties"]
    week_ago = datetime.fromisoformat(latest["DATETIME"].replace("Z", "+00:00")) - timedelta(days=7)
    older = get_json(base + urlencode({"f": "json", "STATION_NUMBER": station, "limit": 1, "sortby": "-DATETIME",
                                       "datetime": "../" + week_ago.strftime("%Y-%m-%dT%H:%M:%SZ")}))["features"]
    prev = older[0]["properties"]["LEVEL"] if older else None
    level = latest["LEVEL"]
    return {
        "name": latest["STATION_NAME"].title(),
        "level_m": level,
        "change_cm_7d": round((level - prev) * 100) if prev is not None else None,
    }


# --- Ski-hill snow (Open-Meteo at the resort's elevation) ----------------------

def snow(cfg):
    s = settings(cfg)["ski"]
    d = get_json("https://api.open-meteo.com/v1/forecast?" + urlencode({
        "latitude": s["latitude"],
        "longitude": s["longitude"],
        "elevation": s["elevation"],
        "current": "temperature_2m,weather_code,is_day",
        "hourly": "snowfall,snow_depth",
        "past_days": 1,
        "forecast_days": 4,
        "timezone": cfg["timezone"],
    }))
    cur, h = d["current"], d["hourly"]
    i = h["time"].index(cur["time"][:13] + ":00")
    fall = [v or 0 for v in h["snowfall"]]
    return {
        "name": s["name"],
        "temp": cur["temperature_2m"],
        "icon": wmo_icon(cur["weather_code"], bool(cur["is_day"])),
        "new_24h_cm": round(sum(fall[max(0, i - 23):i + 1]), 1),
        "next_72h_cm": round(sum(fall[i + 1:i + 73]), 1),
        "depth_cm": round((h["snow_depth"][i] or 0) * 100),
    }


# --- Highways (DriveBC) --------------------------------------------------------

def _points(geometry):
    """All (lon, lat) pairs in a GeoJSON geometry."""
    coords = geometry.get("coordinates", []) if geometry else []
    while coords and isinstance(coords[0], list) and coords[0] and isinstance(coords[0][0], list):
        coords = [c for part in coords for c in part]
    return [coords] if coords and not isinstance(coords[0], list) else coords


def highway_of(route_at):
    m = re.match(r"Highway (\w+)", route_at or "")
    return m.group(1) if m else None


def roads(cfg):
    r = settings(cfg)["roads"]
    lat, lon = _home(cfg)
    events = []
    for e in get_json(DRIVEBC + "/api/events/"):
        hw = highway_of(e.get("route_at"))
        if hw not in r["highways"]:
            continue
        important = e.get("closed") or e.get("severity") == "MAJOR" or e.get("display_category") in ("closures", "majorEvents")
        if not important:
            continue
        pts = _points(e.get("location"))
        if not pts or min(distance_km(lat, lon, p[1], p[0]) for p in pts) > r["radius_km"]:
            continue
        events.append({
            "highway": hw,
            "where": e.get("route_display") or "",
            "text": (e.get("optimized_description") or e.get("description") or "")[:160],
            "closed": bool(e.get("closed")),
        })
    events.sort(key=lambda e: not e["closed"])
    cams = [{"id": c["id"], "name": c["name"], "url": f"{DRIVEBC}/images/{c['id']}.jpg"} for c in r["cameras"]]
    return {"events": events[:4], "event_count": len(events), "cameras": cams}


# --- Northern lights (NOAA SWPC Kp forecast + Open-Meteo cloud cover) ----------

SWPC = "https://services.swpc.noaa.gov"


def aurora_nights(kp_blocks, sun, clouds, tz, now):
    """Peak forecast Kp and mean cloud cover for each dark night ahead.

    kp_blocks: NOAA 3-hour blocks [{"time_tag": UTC ISO, "kp", "observed", "noaa_scale"}].
    sun: [(sunset, next sunrise)] as aware datetimes. clouds: {aware hour: cloud %}.
    A night runs from an hour after sunset to an hour before sunrise (astronomical
    darkness is later still, but bright aurora shows in deep twilight).
    """
    nights = []
    for sunset, sunrise in sun:
        start, end = sunset + timedelta(hours=1), sunrise - timedelta(hours=1)
        if end <= now:
            continue
        best = None
        for b in kp_blocks:
            t0 = datetime.fromisoformat(b["time_tag"]).replace(tzinfo=timezone.utc)
            if t0 + timedelta(hours=3) <= max(start, now) or t0 >= end:
                continue
            if best is None or b["kp"] > best["kp"]:
                best = b | {"start": t0}
        if best is None:
            continue
        cover = [c for h, c in clouds.items() if start <= h < end and c is not None]
        peak = max(best["start"], start).astimezone(tz)
        nights.append({
            "date": sunset.astimezone(tz).date().isoformat(),
            "kp": round(best["kp"], 2),
            "scale": best.get("noaa_scale"),
            "observed": best.get("observed") != "predicted",
            "peak": peak.strftime("%Y-%m-%dT%H:%M"),
            "dark_from": start.astimezone(tz).strftime("%Y-%m-%dT%H:%M"),
            "dark_until": end.astimezone(tz).strftime("%Y-%m-%dT%H:%M"),
            "cloud": round(sum(cover) / len(cover)) if cover else None,
        })
    return nights


def aurora(cfg):
    a = settings(cfg)["aurora"]
    tz = ZoneInfo(cfg["timezone"])
    lat, lon = _home(cfg)
    blocks = get_json(SWPC + "/products/noaa-planetary-k-index-forecast.json")
    latest = get_json(SWPC + "/json/planetary_k_index_1m.json")[-1]
    wx = get_json("https://api.open-meteo.com/v1/forecast?" + urlencode({
        "latitude": lat, "longitude": lon, "hourly": "cloud_cover",
        "daily": "sunrise,sunset", "past_days": 1, "forecast_days": 4, "timezone": "UTC",
    }))
    utc = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    d = wx["daily"]
    sun = list(zip([utc(s) for s in d["sunset"][:-1]], [utc(s) for s in d["sunrise"][1:]]))
    clouds = dict(zip((utc(t) for t in wx["hourly"]["time"]), wx["hourly"]["cloud_cover"]))
    return {
        "min_kp": a["min_kp"],
        "overhead_kp": a["overhead_kp"],
        "now_kp": latest.get("estimated_kp"),
        "nights": aurora_nights(blocks, sun, clouds, tz, datetime.now(timezone.utc))[:3],
    }


# --- Upcoming trips (from the calendar) ----------------------------------------

_geocode_cache = {}


def destination(title, home):
    """'Flight: Kelowna - Toronto (AC 123)' -> 'Toronto'; None for the trip home."""
    text = title.split(":", 1)[1] if ":" in title else title
    m = re.search(r"([A-Za-z .'-]+?)\s+(?:-|–|→|to)\s+([A-Za-z][A-Za-z .'-]*)", text)
    if not m:
        return None
    dest = m.group(2).strip()
    return None if dest.lower() == home.lower() else dest


def geocode(name):
    if name not in _geocode_cache:
        res = get_json("https://geocoding-api.open-meteo.com/v1/search?"
                       + urlencode({"name": name, "count": 1, "language": "en"})).get("results") or []
        _geocode_cache[name] = res[0] if res else None
    return _geocode_cache[name]


def trips(cfg, calendar_data):
    t = settings(cfg)["trips"]
    tz = ZoneInfo(cfg["timezone"])
    today = datetime.now(tz).date()
    last = today + timedelta(days=t["days_ahead"])
    keywords = [k.lower() for k in t["keywords"]]
    found = []
    for day in (calendar_data or {}).get("days", []):
        if not today.isoformat() <= day["date"] <= last.isoformat():
            continue
        for ev in day["events"]:
            if not ev["time"] or not any(k in ev["title"].lower() for k in keywords):
                continue
            dest = destination(ev["title"], t["home"])
            place = geocode(dest) if dest else None
            if not place:
                continue
            trip = {"date": day["date"], "time": ev["time"], "destination": place["name"],
                    "region": place.get("admin1", ""), "forecast": None}
            # Open-Meteo forecasts reach 16 days out.
            d = get_json("https://api.open-meteo.com/v1/forecast?" + urlencode({
                "latitude": place["latitude"], "longitude": place["longitude"],
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": "auto", "start_date": day["date"], "end_date": day["date"],
            }))["daily"]
            if d["time"]:
                trip["forecast"] = {"icon": wmo_icon(d["weather_code"][0]),
                                    "hi": d["temperature_2m_max"][0], "lo": d["temperature_2m_min"][0]}
            found.append(trip)
    return found[:2]
