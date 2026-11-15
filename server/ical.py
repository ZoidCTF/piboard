"""Calendar grid from one or more iCal feeds (e.g. Google's secret iCal address).

Named ical rather than calendar so it doesn't shadow the stdlib module.
"""

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import x_wr_timezone

from sources import http_get


def fmt_time(t):
    """7:30am / 12:00pm."""
    return f"{t.hour % 12 or 12}:{t.minute:02d}{'am' if t.hour < 12 else 'pm'}"


def grid_start(today):
    """The Sunday that starts the current week."""
    return today - timedelta(days=(today.weekday() + 1) % 7)


def holiday_titles(opts):
    """Title function for Google's public holiday feeds (e.g. Holidays in Canada).

    Keeps public holidays that apply in opts["region"] (or everywhere), plus any
    observances named in opts["observances"]; returns None for everything else.
    Strips Google's " (regional holiday)" suffix and applies opts["rename"].
    The feed's DESCRIPTION starts "Public holiday[ in A, B, ...]" or "Observance ...".
    """
    region = opts.get("region")
    keep = {o.lower() for o in opts.get("observances", [])}
    rename = opts.get("rename", {})

    def title_for(ev):
        title = re.sub(r"\s*\(regional holiday\)$", "", str(ev.get("SUMMARY", "")).strip())
        first_line = str(ev.get("DESCRIPTION", "")).split("\n")[0].strip()
        if first_line.startswith("Public holiday"):
            places = first_line.partition(" in ")[2]
            if region and places and region not in places:
                return None
        elif title.lower() not in keep:
            return None
        return rename.get(title, title)

    return title_for


def expand(cal, start, end, tz, title_for=None):
    """Yield (day, entry) for every day an event touches within [start, end).

    title_for, if given, maps an event to its displayed title (or None to skip it)
    and marks the entries as holidays.
    """
    win_start = datetime.combine(start, time.min, tz)
    win_end = datetime.combine(end, time.min, tz)
    for ev in recurring_ical_events.of(cal).between(win_start, win_end):
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        if title_for:
            title = title_for(ev)
            if title is None:
                continue
            extra = {"holiday": True}
        else:
            title = str(ev.get("SUMMARY", "")).strip() or "(No title)"
            extra = {}
        s = ev["DTSTART"].dt
        e = ev["DTEND"].dt if "DTEND" in ev else None
        if e is None and "DURATION" in ev:
            e = s + ev["DURATION"].dt

        if isinstance(s, datetime):
            s = s.replace(tzinfo=tz) if s.tzinfo is None else s.astimezone(tz)
            e = s if e is None else (e.replace(tzinfo=tz) if e.tzinfo is None else e.astimezone(tz))
            first = s.date()
            # An event ending exactly at midnight doesn't spill into the next day.
            last = (e - timedelta(microseconds=1)).date() if e > s else first
            for i in range((last - first).days + 1):
                day = first + timedelta(days=i)
                if i == 0:
                    yield day, {"time": fmt_time(s), "title": title, "all_day": False, "_sort": s.time(), **extra}
                else:
                    yield day, {"time": "", "title": title, "all_day": True, "_sort": time.min, **extra}
        else:
            # All-day: DTEND is exclusive.
            e = e if isinstance(e, date) and e > s else s + timedelta(days=1)
            for i in range((e - s).days):
                yield s + timedelta(days=i), {"time": "", "title": title, "all_day": True, "_sort": time.min, **extra}


def build_grid(cals, today, weeks, tz):
    """cals: Calendar objects, or (Calendar, title_for) pairs for holiday feeds."""
    start = grid_start(today)
    end = start + timedelta(days=7 * weeks)
    days = {start + timedelta(days=i): [] for i in range(7 * weeks)}
    for item in cals:
        cal, title_for = item if isinstance(item, tuple) else (item, None)
        for day, entry in expand(cal, start, end, tz, title_for):
            if day in days:
                days[day].append(entry)
    out = []
    for day, events in days.items():
        # Holidays first, then other all-day events, then by time.
        events.sort(key=lambda ev: (not ev.get("holiday"), not ev["all_day"], ev["_sort"], ev["title"].lower()))
        out.append({"date": day.isoformat(),
                    "events": [{k: v for k, v in ev.items() if k != "_sort"} for ev in events]})
    return {"start": start.isoformat(), "days": out}


def calendar(cfg):
    tz = ZoneInfo(cfg["timezone"])
    c = cfg["calendar"]
    cals = []
    # Each entry is a URL, or {"url": ..., "holidays": {...}} for a public holiday feed.
    for entry in c.get("urls", []):
        url = entry.get("url", "") if isinstance(entry, dict) else entry
        if not url:
            continue
        if url.startswith("webcal://"):
            url = "https://" + url[len("webcal://"):]
        cal = x_wr_timezone.to_standard(icalendar.Calendar.from_ical(http_get(url)))
        holidays = entry.get("holidays") if isinstance(entry, dict) else None
        cals.append((cal, holiday_titles(holidays)) if holidays is not None else cal)
    return build_grid(cals, datetime.now(tz).date(), c.get("weeks", 3), tz)
