import json
import sys
import unittest
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import icalendar  # noqa: E402

import ical  # noqa: E402
import seasonal  # noqa: E402
import sources  # noqa: E402

TZ = ZoneInfo("America/Vancouver")

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VTIMEZONE
TZID:America/Vancouver
BEGIN:STANDARD
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:weekly
SUMMARY:Weekly reminder
DTSTART;TZID=America/Vancouver:20260105T073000
DTEND;TZID=America/Vancouver:20260105T074500
RRULE:FREQ=WEEKLY;BYDAY=MO
EXDATE;TZID=America/Vancouver:20261026T073000
END:VEVENT
BEGIN:VEVENT
UID:trip
SUMMARY:Trip
DTSTART;VALUE=DATE:20261029
DTEND;VALUE=DATE:20261101
END:VEVENT
BEGIN:VEVENT
UID:utc
SUMMARY:Pack Windows
DTSTART:20261022T150000Z
DTEND:20261022T160000Z
END:VEVENT
BEGIN:VEVENT
UID:late
SUMMARY:Overnight
DTSTART;TZID=America/Vancouver:20261023T220000
DTEND;TZID=America/Vancouver:20261024T020000
END:VEVENT
END:VCALENDAR
"""


class CalendarTest(unittest.TestCase):
    def setUp(self):
        cal = icalendar.Calendar.from_ical(ICS)
        grid = ical.build_grid([cal], date(2026, 10, 21), 3, TZ)
        self.start = grid["start"]
        self.days = {d["date"]: d["events"] for d in grid["days"]}

    def test_grid_starts_sunday(self):
        self.assertEqual(self.start, "2026-10-18")
        self.assertEqual(len(self.days), 21)

    def test_weekly_recurrence_with_exdate(self):
        self.assertEqual(self.days["2026-10-19"], [{"time": "7:30am", "title": "Weekly reminder", "all_day": False}])
        self.assertEqual(self.days["2026-10-26"], [])  # excluded occurrence
        # Same local time across Nov 1 (BC stays on UTC-7 from 2026; the US falls back).
        self.assertEqual(self.days["2026-11-02"][0]["time"], "7:30am")

    def test_multi_day_all_day(self):
        for d in ("2026-10-29", "2026-10-30", "2026-10-31"):
            self.assertEqual(self.days[d], [{"time": "", "title": "Trip", "all_day": True}])
        self.assertEqual(self.days["2026-11-01"], [])

    def test_utc_converted_to_local(self):
        self.assertEqual(self.days["2026-10-22"][0]["time"], "8:00am")

    def test_overnight_spills_into_next_day(self):
        self.assertEqual(self.days["2026-10-23"][0]["time"], "10:00pm")
        self.assertEqual(self.days["2026-10-24"][0], {"time": "", "title": "Overnight", "all_day": True})


HOLIDAYS_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
BEGIN:VEVENT
UID:rem
DTSTART;VALUE=DATE:20261111
DTEND;VALUE=DATE:20261112
SUMMARY:Remembrance Day (regional holiday)
DESCRIPTION:Public holiday in Alberta\\, British Columbia\\, Manitoba
END:VEVENT
BEGIN:VEVENT
UID:qc
DTSTART;VALUE=DATE:20261112
DTEND;VALUE=DATE:20261113
SUMMARY:Some Quebec Day (regional holiday)
DESCRIPTION:Public holiday in Quebec
END:VEVENT
BEGIN:VEVENT
UID:bcday
DTSTART;VALUE=DATE:20261113
DTEND;VALUE=DATE:20261114
SUMMARY:Civic/Provincial Day
DESCRIPTION:Public holiday
END:VEVENT
BEGIN:VEVENT
UID:dst
DTSTART;VALUE=DATE:20261101
DTEND;VALUE=DATE:20261102
SUMMARY:Daylight Saving Time ends in parts of Canada
DESCRIPTION:Observance\\nTo hide observances\\, go to Google Calendar Settings
END:VEVENT
BEGIN:VEVENT
UID:halloween
DTSTART;VALUE=DATE:20261031
DTEND;VALUE=DATE:20261101
SUMMARY:Halloween
DESCRIPTION:Observance\\nTo hide observances\\, go to Google Calendar Settings
END:VEVENT
END:VCALENDAR
"""


class HolidayTest(unittest.TestCase):
    def setUp(self):
        cal = icalendar.Calendar.from_ical(HOLIDAYS_ICS)
        opts = {"region": "British Columbia", "observances": ["Halloween"], "rename": {"Civic/Provincial Day": "BC Day"}}
        grid = ical.build_grid([(cal, ical.holiday_titles(opts))], date(2026, 11, 2), 3, TZ)
        self.days = {d["date"]: [e["title"] for e in d["events"]] for d in grid["days"]}
        self.flags = {d["date"]: [e.get("holiday") for e in d["events"]] for d in grid["days"]}

    def test_public_holiday_in_region_cleaned_up(self):
        self.assertEqual(self.days["2026-11-11"], ["Remembrance Day"])
        self.assertEqual(self.flags["2026-11-11"], [True])

    def test_other_province_dropped(self):
        self.assertEqual(self.days["2026-11-12"], [])

    def test_nationwide_holiday_renamed(self):
        self.assertEqual(self.days["2026-11-13"], ["BC Day"])

    def test_observances_only_when_listed(self):
        grid_start = "2026-11-01"
        self.assertEqual(self.days[grid_start], [])  # DST observance dropped
        cal = icalendar.Calendar.from_ical(HOLIDAYS_ICS)
        grid = ical.build_grid([(cal, ical.holiday_titles({"observances": ["Halloween"]}))], date(2026, 10, 28), 1, TZ)
        titles = {d["date"]: [e["title"] for e in d["events"]] for d in grid["days"]}
        self.assertEqual(titles["2026-10-31"], ["Halloween"])


class AirTest(unittest.TestCase):
    def test_aqhi_clean_air_is_low(self):
        self.assertLess(sources.aqhi(30, 5, 3), 3)

    def test_aqhi_smoke_is_high(self):
        # Heavy wildfire smoke: PM2.5 ~ 150 µg/m³.
        self.assertGreaterEqual(round(sources.aqhi(30, 10, 150)), 7)


class SeasonalTest(unittest.TestCase):
    def test_trip_destination(self):
        d = seasonal.destination
        self.assertEqual(d("Flight: Kelowna - Toronto (AC 123)", "Kelowna"), "Toronto")
        self.assertEqual(d("Flight to Calgary", "Kelowna"), "Calgary")
        self.assertEqual(d("Kelowna → San Diego", "Kelowna"), "San Diego")
        self.assertIsNone(d("Flight: Toronto - Kelowna", "Kelowna"))  # the trip home
        self.assertIsNone(d("Dentist", "Kelowna"))

    def test_distance_and_direction(self):
        # Kelowna to Vernon is ~45 km, roughly north.
        self.assertAlmostEqual(seasonal.distance_km(49.888, -119.496, 50.267, -119.272), 45, delta=3)
        self.assertEqual(seasonal.compass(49.888, -119.496, 50.267, -119.272), "N")
        self.assertEqual(seasonal.compass(49.888, -119.496, 49.89, -121.45), "W")

    def test_highway_and_points(self):
        self.assertEqual(seasonal.highway_of("Highway 97C, Okanagan Connector"), "97C")
        self.assertIsNone(seasonal.highway_of("E 25th Street Offramp"))
        self.assertEqual(seasonal._points({"type": "Point", "coordinates": [1, 2]}), [[1, 2]])
        self.assertEqual(seasonal._points({"type": "LineString", "coordinates": [[1, 2], [3, 4]]}), [[1, 2], [3, 4]])
        self.assertEqual(seasonal._points({"type": "MultiLineString", "coordinates": [[[1, 2]], [[3, 4]]]}), [[1, 2], [3, 4]])


class CreditsTest(unittest.TestCase):
    def test_first_indented_line_per_file(self):
        import tempfile
        import app

        with tempfile.TemporaryDirectory() as d:
            Path(d, "CREDITS.txt").write_text(
                "Header line\n\na.jpg\n  Photo by A, CC BY 2.0\n  https://example.com/a\n\nb.jpg\n  Photo by B\n",
                encoding="utf-8")
            self.assertEqual(app.read_credits(Path(d)), {"a.jpg": "Photo by A, CC BY 2.0", "b.jpg": "Photo by B"})


class WotdTest(unittest.TestCase):
    def test_parse(self):
        desc = """<p><strong>jilt</strong> &#149; \\JILT\\&nbsp; &#149; <em>verb</em><br />
    <p>To jilt someone is usually to abruptly end a romantic relationship with them. <em>Jilt</em> is also applied to various kinds of abrupt rejection. </p>
<p>// The novel begins...</p>"""
        w = sources.parse_wotd("jilt", desc)
        self.assertEqual(w["pronunciation"], "\\JILT\\")
        self.assertEqual(w["part_of_speech"], "verb")
        self.assertTrue(w["definition_html"].startswith("To jilt someone"))
        self.assertIn("<em>Jilt</em> is also", w["definition_html"])


class AuroraTest(unittest.TestCase):
    def test_peak_kp_and_cloud_per_dark_night(self):
        from datetime import datetime, timedelta, timezone
        utc = timezone.utc
        sunset, sunrise = datetime(2026, 11, 15, 0, 15, tzinfo=utc), datetime(2026, 11, 15, 14, 50, tzinfo=utc)
        blocks = [
            {"time_tag": "2026-11-14T21:00:00", "kp": 8.0, "observed": "predicted", "noaa_scale": "G4"},  # before dark
            {"time_tag": "2026-11-15T03:00:00", "kp": 5.67, "observed": "predicted", "noaa_scale": "G2"},
            {"time_tag": "2026-11-15T06:00:00", "kp": 4.0, "observed": "predicted", "noaa_scale": None},
            {"time_tag": "2026-11-15T15:00:00", "kp": 9.0, "observed": "predicted", "noaa_scale": "G5"},  # after dawn
        ]
        clouds = {sunset + timedelta(hours=h): 40 if h < 6 else 100 for h in range(24)}
        now = datetime(2026, 11, 14, 20, 0, tzinfo=utc)
        (n,) = seasonal.aurora_nights(blocks, [(sunset, sunrise)], clouds, TZ, now)
        self.assertEqual(n["date"], "2026-11-14")      # the night is named after its evening
        self.assertEqual(n["kp"], 5.67)
        self.assertEqual(n["scale"], "G2")
        self.assertEqual(n["peak"], "2026-11-14T20:00")  # 03:00 UTC in Kelowna (UTC-7)
        self.assertEqual(n["dark_from"], "2026-11-14T18:15")
        self.assertEqual(n["cloud"], 77)                # dark hours 1-13 after sunset: 5 x 40 %, 8 x 100 %

    def test_past_nights_dropped(self):
        from datetime import datetime, timezone
        utc = timezone.utc
        sun = [(datetime(2026, 11, 14, 0, 15, tzinfo=utc), datetime(2026, 11, 14, 14, 50, tzinfo=utc))]
        blocks = [{"time_tag": "2026-11-14T03:00:00", "kp": 6.0, "observed": "observed"}]
        now = datetime(2026, 11, 14, 18, 0, tzinfo=utc)
        self.assertEqual(seasonal.aurora_nights(blocks, sun, {}, TZ, now), [])


if __name__ == "__main__":
    unittest.main()


class HomeAssistantTest(unittest.TestCase):
    def test_summarize(self):
        from datetime import datetime, timezone
        import homeassistant
        now = datetime(2026, 11, 14, 20, 0, tzinfo=timezone.utc)
        st = lambda eid, state, changed="2026-11-14T19:00:00+00:00", **attrs: (
            eid, {"entity_id": eid, "state": state, "last_changed": changed, "attributes": attrs})
        states = dict([
            st("climate.up", "heat", friendly_name="Upstairs", current_temperature=21.3, current_humidity=45, temperature=20.5, hvac_action="heating"),
            st("climate.gone", "unavailable"),
            st("sensor.co2", "1150"),
            st("binary_sensor.leak", "on", friendly_name="Water Leak Sensor 2 Alarm Status"),
            st("binary_sensor.dry", "off"),
            st("binary_sensor.freezer", "on", "2026-11-14T19:55:00+00:00", friendly_name="Fridge freezer Freezer door"),
            st("binary_sensor.fridge", "on", "2026-11-14T19:59:00+00:00"),  # open a minute: not yet
            st("switch.oven", "on", "2026-11-14T18:00:00+00:00"),
            st("sensor.oven_t", "204.4"),
            st("alarm_control_panel.a", "armed_away"),
            st("sensor.kw", "7.24"), st("sensor.kwh", "12.04"), st("sensor.kw2", "0.0"),
            st("event.ring", "2026-11-14T19:59:10.1+00:00"),
        ])
        ha = {**homeassistant.DEFAULTS, "climate": ["climate.up", "climate.gone"], "co2": "sensor.co2",
              "leaks": ["binary_sensor.leak", "binary_sensor.dry"], "doors": ["binary_sensor.freezer", "binary_sensor.fridge"],
              "ovens": [{"name": "Top oven", "power": "switch.oven", "temp": "sensor.oven_t"}],
              "alarm": "alarm_control_panel.a",
              "chargers": [{"name": "Car", "power": "sensor.kw", "energy": "sensor.kwh"}, {"name": "Other", "power": "sensor.kw2"}],
              "doorbell": {"ring": "event.ring", "package": "event.missing", "camera": "camera.door"}}
        out = homeassistant.summarize(states, ha, now)
        self.assertEqual(out["climate"], [{"name": "Upstairs", "temp": 21.3, "humidity": 45, "target": 20.5, "heating": True}])
        self.assertEqual(out["co2"], 1150)
        self.assertEqual(out["leaks"], ["Water Leak Sensor 2"])
        self.assertEqual(out["doors"], [{"name": "Freezer door", "minutes": 5}])
        self.assertEqual(out["ovens"], [{"name": "Top oven", "minutes": 120, "temp": 204.4}])
        self.assertEqual(out["alarm"], "away")
        self.assertEqual(out["chargers"], [{"name": "Car", "kw": 7.2, "kwh": 12.0}])
        self.assertEqual(out["doorbell"], {"ring": "2026-11-14T19:59:10.1+00:00", "camera": True, "package_camera": False})
        self.assertNotIn("token", json.dumps(out))
