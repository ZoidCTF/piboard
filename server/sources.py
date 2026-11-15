"""Fetchers for the external feeds. Each returns JSON-able data or raises."""

import html
import json
import math
import re
import urllib.request
from urllib.parse import urlencode
from xml.etree import ElementTree

USER_AGENT = "Mozilla/5.0 (X11; Linux aarch64) piboard/1.0"

CURRENCY_NAMES = {
    "USD": "US Dollar", "EUR": "Euro", "JPY": "Japanese Yen", "GBP": "British Pound",
    "AUD": "Australian Dollar", "CHF": "Swiss Franc", "CNY": "Chinese Yuan",
    "MXN": "Mexican Peso", "NZD": "New Zealand Dollar", "CAD": "Canadian Dollar",
}


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url):
    return json.loads(http_get(url))


# --- Weather (Open-Meteo) ---------------------------------------------------

def wmo_icon(code, is_day=True):
    """Map a WMO weather code to one of the icon names in web/icons.js."""
    tod = "day" if is_day else "night"
    if code in (0, 1):
        return f"clear-{tod}"
    if code == 2:
        return f"partly-{tod}"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55):
        return "drizzle"
    if code in (56, 57, 66, 67):
        return "sleet"
    if code in (61, 63, 65, 80, 81, 82):
        return "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "thunder"
    return "cloudy"


def weather(cfg):
    w = cfg["weather"]
    query = urlencode({
        "latitude": w["latitude"],
        "longitude": w["longitude"],
        "current": "temperature_2m,weather_code,is_day",
        "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max",
        "timezone": cfg["timezone"],
        # One spare day so the page can drop "yesterday" if the cache is stale.
        "forecast_days": 5,
    })
    d = get_json("https://api.open-meteo.com/v1/forecast?" + query)
    cur, hourly, daily = d["current"], d["hourly"], d["daily"]
    # Times are local ISO strings, so they compare correctly as text.
    this_hour = cur["time"][:13] + ":00"
    hours = [
        {"time": t, "temp": temp, "icon": wmo_icon(code, bool(day)), "pop": pop}
        for t, temp, code, pop, day in zip(hourly["time"], hourly["temperature_2m"], hourly["weather_code"],
                                           hourly["precipitation_probability"], hourly["is_day"])
        if t >= this_hour
    ]
    return {
        "current": {
            "temp": cur["temperature_2m"],
            "icon": wmo_icon(cur["weather_code"], bool(cur["is_day"])),
        },
        "hourly": hours[:25],
        "daily": [
            {"date": day, "icon": wmo_icon(code), "hi": hi, "lo": lo, "sunrise": rise, "sunset": set_, "uv": uv}
            for day, code, hi, lo, rise, set_, uv in zip(daily["time"], daily["weather_code"],
                                                         daily["temperature_2m_max"], daily["temperature_2m_min"],
                                                         daily["sunrise"], daily["sunset"], daily["uv_index_max"])
        ],
    }


# --- Air quality (Open-Meteo, as Canada's AQHI) -------------------------------

AQHI_RISK = ((3, "Low"), (6, "Moderate"), (10, "High"))


def aqhi(o3_ppb, no2_ppb, pm25):
    """Environment Canada's Air Quality Health Index from 3-hour mean concentrations."""
    return (1000 / 10.4) * ((math.exp(0.000537 * o3_ppb) - 1)
                            + (math.exp(0.000871 * no2_ppb) - 1)
                            + (math.exp(0.000487 * pm25) - 1))


def air(cfg):
    w = cfg["weather"]
    query = urlencode({
        "latitude": w["latitude"],
        "longitude": w["longitude"],
        "hourly": "pm2_5,ozone,nitrogen_dioxide",
        "past_hours": 2,
        "forecast_hours": 1,
        "timezone": cfg["timezone"],
    })
    h = get_json("https://air-quality-api.open-meteo.com/v1/air-quality?" + query)["hourly"]

    def mean(values):
        vals = [v for v in values[-3:] if v is not None]
        if not vals:
            raise ValueError("no air-quality readings")
        return sum(vals) / len(vals)

    # Open-Meteo reports µg/m³; the AQHI formula wants ppb for the gases.
    value = aqhi(mean(h["ozone"]) / 1.96, mean(h["nitrogen_dioxide"]) / 1.88, mean(h["pm2_5"]))
    index = max(1, round(value))
    risk = next((label for limit, label in AQHI_RISK if index <= limit), "Very high")
    return {"aqhi": index, "risk": risk, "pm2_5": h["pm2_5"][-1]}


# --- Currency (Frankfurter, open.er-api.com fallback) ------------------------

def fx(cfg):
    base, symbols = cfg["currency"]["base"], cfg["currency"]["symbols"]
    try:
        d = get_json(f"https://api.frankfurter.dev/v1/latest?base={base}&symbols={','.join(symbols)}")
        rates, date, provider = d["rates"], d["date"], "ECB via Frankfurter"
    except Exception:
        d = get_json(f"https://open.er-api.com/v6/latest/{base}")
        rates, date, provider = d["rates"], d["time_last_update_utc"], "ExchangeRate-API"
    return {
        "base": base,
        "date": date,
        "provider": provider,
        "rates": [{"code": s, "name": CURRENCY_NAMES.get(s, s), "rate": rates[s]} for s in symbols],
    }


# --- Word of the day (Merriam-Webster RSS) -----------------------------------

def _text(fragment):
    """Strip tags and entities, collapse whitespace."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _keep_em(fragment):
    """Plain text with only <em> kept, safe to drop into the page as HTML."""
    out = []
    for part in re.split(r"(</?(?:em|i)>)", fragment, flags=re.I):
        if re.fullmatch(r"</?(?:em|i)>", part, flags=re.I):
            out.append("</em>" if part.startswith("</") else "<em>")
        else:
            out.append(html.escape(html.unescape(re.sub(r"<[^>]+>", "", part))))
    return " ".join("".join(out).split())


def parse_wotd(word, desc):
    """Pull pronunciation, part of speech and definition out of the item HTML.

    The description looks like:
      <strong>jilt</strong> &#149; \\JILT\\&nbsp; &#149; <em>verb</em><br />
      <p>To jilt someone is ...</p>
    """
    m = re.search(r"<strong>\s*" + re.escape(word) + r"\s*</strong>(.*?)<br", desc, re.S | re.I)
    if not m:
        raise ValueError(f"unrecognised word-of-the-day layout for {word!r}")
    head = m.group(1)
    pos = re.search(r"<em>(.*?)</em>", head, re.S)
    pron = re.search(r"\\[^\\]+\\", _text(head))
    definition = re.search(r"<p>(.*?)</p>", desc[m.end():], re.S)
    if not definition:
        raise ValueError(f"no definition found for {word!r}")
    return {
        "word": word,
        "pronunciation": pron.group(0) if pron else "",
        "part_of_speech": _text(pos.group(1)) if pos else "",
        "definition_html": _keep_em(definition.group(1)),
    }


def wotd(cfg):
    root = ElementTree.fromstring(http_get(cfg["wotd"]["feed"]))
    item = root.find("channel/item")
    if item is None:
        raise ValueError("feed has no items")
    data = parse_wotd(item.findtext("title", "").strip(), item.findtext("description", ""))
    data["link"] = item.findtext("link", "").strip()
    return data
