"""Home Assistant: indoor climate, problem notices, doorbell and car charging.

Reads entity states over HA's REST API with a long-lived access token
(`home_assistant` in config.json). The token stays on the server; the page only
sees the summary below and fetches camera snapshots through /api/camera/<name>.
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULTS = {
    "climate": [],      # climate.* entities: temperature, humidity, heating
    "co2": None,        # sensor in ppm
    "co2_limit": 1000,
    "leaks": [],        # binary_sensors that turn on when wet
    "doors": [],        # binary_sensors (e.g. fridge, freezer), reported once open this long:
    "door_minutes": 3,
    "ovens": [],        # {"power": switch, "temp": sensor, "name": ...}, reported once on this long:
    "oven_minutes": 90,
    "alarm": None,      # alarm_control_panel
    "chargers": [],     # {"name", "power": kW sensor, "energy": session kWh sensor}
    "doorbell": {},     # {"ring": event, "package": event, "camera": camera, "package_camera": camera}
}


def settings(cfg):
    return {**DEFAULTS, **cfg.get("home_assistant", {})}


def enabled(cfg):
    ha = cfg.get("home_assistant") or {}
    return bool(ha.get("url") and ha.get("token"))


def _request(ha, path, timeout=10):
    req = urllib.request.Request(ha["url"].rstrip("/") + path,
                                 headers={"Authorization": f"Bearer {ha['token']}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def camera_snapshot(cfg, name):
    """JPEG bytes for a doorbell camera named in config ('camera' or 'package_camera')."""
    ha = settings(cfg)
    entity = ha["doorbell"].get(name)
    if not entity:
        return None
    return _request(ha, f"/api/camera_proxy/{entity}", timeout=15)


def _entry(e):
    """Config entries are an entity id, or a dict with "entity" (or other ids) and "name"."""
    return {"entity": e} if isinstance(e, str) else e


def _num(state):
    try:
        return float(state["state"])
    except (TypeError, KeyError, ValueError):
        return None


def _minutes_since(state, now):
    changed = datetime.fromisoformat(state["last_changed"])
    return round((now - changed).total_seconds() / 60)


def _name(state, entry, strip=()):
    name = entry.get("name") or state["attributes"].get("friendly_name") or state["entity_id"]
    for s in strip:
        name = name.replace(s, "")
    return name.strip()


def summarize(states, ha, now):
    """Turn {entity_id: state} into what the page shows. Missing or unavailable
    entities are skipped rather than failing the whole panel."""
    live = lambda eid: (s := states.get(eid)) and s["state"] not in ("unavailable", "unknown") and s or None
    out = {"climate": [], "co2": None, "co2_limit": ha["co2_limit"], "leaks": [], "doors": [],
           "ovens": [], "alarm": None, "chargers": [], "doorbell": {}}

    for e in map(_entry, ha["climate"]):
        s = live(e["entity"])
        if s:
            a = s["attributes"]
            out["climate"].append({"name": _name(s, e), "temp": a.get("current_temperature"),
                                   "humidity": a.get("current_humidity"), "target": a.get("temperature"),
                                   "heating": a.get("hvac_action") == "heating"})
    if ha["co2"] and (s := live(ha["co2"])):
        out["co2"] = _num(s)

    for e in map(_entry, ha["leaks"]):
        s = live(e["entity"])
        if s and s["state"] == "on":
            out["leaks"].append(_name(s, e, strip=(" Alarm Status",)))
    for e in map(_entry, ha["doors"]):
        s = live(e["entity"])
        if s and s["state"] == "on" and (m := _minutes_since(s, now)) >= ha["door_minutes"]:
            out["doors"].append({"name": _name(s, e, strip=("Fridge freezer ",)), "minutes": m})
    for e in map(_entry, ha["ovens"]):
        s = live(e["power"])
        if s and s["state"] == "on" and (m := _minutes_since(s, now)) >= ha["oven_minutes"]:
            t = live(e.get("temp", ""))
            out["ovens"].append({"name": e.get("name", "Oven"), "minutes": m, "temp": _num(t) if t else None})
    if ha["alarm"] and (s := live(ha["alarm"])) and s["state"].startswith("armed"):
        out["alarm"] = s["state"].removeprefix("armed_").replace("_", " ")

    for e in ha["chargers"]:
        p = live(e["power"])
        kw = _num(p) if p else None
        if kw and kw > 0.1:
            en = live(e.get("energy", ""))
            out["chargers"].append({"name": e.get("name", "Car"), "kw": round(kw, 1),
                                    "kwh": round(_num(en), 1) if en and _num(en) is not None else None})

    db = ha["doorbell"]
    for key in ("ring", "package"):
        s = live(db.get(key, ""))
        if s:
            out["doorbell"][key] = s["state"]   # event entities: the state is the last event's time
    out["doorbell"]["camera"] = bool(db.get("camera"))
    out["doorbell"]["package_camera"] = bool(db.get("package_camera"))
    return out


def entity_ids(ha):
    ids = [_entry(e)["entity"] for k in ("climate", "leaks", "doors") for e in ha[k]]
    ids += [e[k] for e in ha["ovens"] for k in ("power", "temp") if e.get(k)]
    ids += [e[k] for e in ha["chargers"] for k in ("power", "energy") if e.get(k)]
    ids += [ha[k] for k in ("co2", "alarm") if ha[k]]
    ids += [v for k, v in ha["doorbell"].items() if k in ("ring", "package")]
    return ids


def home(cfg):
    ha = settings(cfg)
    states = {}
    for eid in entity_ids(ha):
        try:
            states[eid] = json.loads(_request(ha, f"/api/states/{eid}")[0])
        except urllib.error.HTTPError as exc:
            if exc.code != 404:   # a renamed entity just drops out; anything else is a real failure
                raise
    return summarize(states, ha, datetime.now(timezone.utc))
