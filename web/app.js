// piboard dashboard. Polls the local server's /api/* endpoints and keeps
// showing the last good data whenever a request fails.
"use strict";

const $ = (id) => document.getElementById(id);
const loadedAt = new Date();
const params = new URLSearchParams(location.search);
let cfg = {
  title: "", accent: "#ffb45c", clock_24h: false, reload_at: "03:00", poll_seconds: 60, map: {},
  photos: { rotate_minutes: 10 },
  night: { start: "22:00", end: "06:00", dim: 0.7, hide_map: true },
  ambience: { sky: true, weather: true },
  seasonal: { card_seconds: 20, fire_months: [], summer_months: [], winter_months: [], frost_months: [], roads: { highways: [] }, collection: [] },
};
let weatherData = null;
let calendarData = null;

// Server icon names -> Meteocons files in web/icons/.
const ICON_FILES = {
  "clear-day": "clear-day", "clear-night": "clear-night",
  "partly-day": "partly-cloudy-day", "partly-night": "partly-cloudy-night",
  cloudy: "cloudy", fog: "fog", drizzle: "drizzle", rain: "rain",
  sleet: "sleet", snow: "snow", thunder: "thunderstorms-rain",
};
const AQHI_COLOURS = { Low: "#7bd389", Moderate: "#f2d45c", High: "#f39c4a", "Very high": "#ff6b6b" };

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const icon = (name) => `<img class="wx" src="icons/${ICON_FILES[name] || name || "cloudy"}.svg" alt="">`;
const parseDate = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
const startOfToday = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
const sameDay = (a, b) => a.toDateString() === b.toDateString();
const pad = (n) => String(n).padStart(2, "0");
const localHourKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
const minutesOf = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };

// "2026-10-21T17:54" -> "5:54pm"; with hourOnly -> "5pm"
function fmtTime(iso, hourOnly = false) {
  const [h, m] = iso.slice(11, 16).split(":").map(Number);
  if (cfg.clock_24h) return hourOnly ? `${pad(h)}:00` : `${pad(h)}:${pad(m)}`;
  const suffix = h < 12 ? "am" : "pm";
  return hourOnly ? `${h % 12 || 12}${suffix}` : `${h % 12 || 12}:${pad(m)}${suffix}`;
}

async function getJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    res.body?.cancel(); // release the response (see the ping in tick())
    throw new Error(`${path}: HTTP ${res.status}`);
  }
  return res.json();
}

// Fetch an endpoint now and every `seconds`; re-render only when the data changes.
// Until the server has something for this source, ask again every few seconds.
function poll(name, render, seconds) {
  let last = "";
  const run = async () => {
    try {
      const body = await getJSON(`/api/${name}`);
      const json = JSON.stringify(body.data);
      if (body.data && json !== last) {
        last = json;
        render(body.data);
      }
    } catch (err) {
      console.warn(err);
    }
    setTimeout(run, last ? seconds * 1000 : 5000);
  };
  run();
}

/* Sky light follows the sun. ?at=HH:MM simulates a time of day (for testing). */
function updateSky(now) {
  if (!cfg.ambience.sky || !weatherData) return;
  const today = weatherData.daily.find((d) => sameDay(parseDate(d.date), now));
  if (!today || !today.sunrise) return;
  const minute = params.has("at") ? minutesOf(params.get("at")) : now.getHours() * 60 + now.getMinutes();
  Ambience.setSky(today.sunrise, today.sunset, minute);
}

/* Clock: a single timer aligned to the second drives everything time-based. */
let lastDay = "";
let lastHour = -1;
let lastMinute = -1;
function tick() {
  const now = new Date();
  const h = now.getHours();
  const hm = cfg.clock_24h ? `${pad(h)}:${pad(now.getMinutes())}` : `${h % 12 || 12}:${pad(now.getMinutes())}`;
  if ($("hm").textContent !== hm) $("hm").textContent = hm;
  $("sec").textContent = pad(now.getSeconds());

  if (now.toDateString() !== lastDay) {
    lastDay = now.toDateString();
    $("date").textContent = now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
    if (calendarData) renderCalendar(calendarData);
  }
  if (h !== lastHour) {
    lastHour = h;
    if (weatherData) renderWeather(weatherData); // shifts the hourly strip and "Today"
    renderMoon(now);
  }
  if (now.getMinutes() !== lastMinute) {
    lastMinute = now.getMinutes();
    updateSky(now);
    // Heartbeat for bin/kiosk.sh: it restarts Chromium if the page never loads or freezes.
    // Read the (tiny) body: Chromium keeps a 2 MB shared-memory buffer open for each
    // unread response, and a renderer that runs out of file handles goes white.
    fetch("/api/ping", { cache: "no-store" }).then((r) => r.text()).catch(() => {});
  }
  updateNight(now);
  maybeReload(now);
  setTimeout(tick, 1000 - now.getMilliseconds() + 10);
}

/* Reload once a day, but only when the server is up so we never land on an error page. */
let reloadPending = false;
async function maybeReload(now) {
  if (reloadPending) return;
  const due = new Date(now);
  due.setHours(0, minutesOf(cfg.reload_at), 0, 0);
  if (now < due || loadedAt >= due) return;
  reloadPending = true;
  try {
    await getJSON("/api/health");
    location.reload();
  } catch {
    setTimeout(() => { reloadPending = false; }, 60000);
  }
}

/* Night mode: dim the screen and stop the map between night.start and night.end.
   ?night=1 / ?night=0 forces it on or off for testing. */
let isNight = null;
function updateNight(now) {
  const n = cfg.night;
  let on;
  if (params.has("night")) {
    on = params.get("night") === "1";
  } else {
    const m = now.getHours() * 60 + now.getMinutes();
    const s = minutesOf(n.start), e = minutesOf(n.end);
    on = s <= e ? m >= s && m < e : m >= s || m < e;
  }
  if (on === isNight) return;
  isNight = on;
  document.body.classList.toggle("night", on);
  if (n.hide_map) setMapActive(!on);
  Ambience.pause(on);
}

function renderWeather(w) {
  weatherData = w;
  $("now-temp").textContent = `${Math.round(w.current.temp)}°`;
  $("now-icon").innerHTML = icon(w.current.icon);
  // ?wx=rain|drizzle|thunder|snow|sleet|fog forces visible weather (for testing).
  if (cfg.ambience.weather) Ambience.setWeather(params.get("wx") || w.current.icon);
  updateSky(new Date());
  Cards.set("weather", w);

  const today = startOfToday();
  const days = w.daily.filter((d) => parseDate(d.date) >= today);
  $("forecast").innerHTML = days.slice(0, 4).map((d) => {
    const date = parseDate(d.date);
    const label = sameDay(date, today) ? "Today" : date.toLocaleDateString("en-US", { weekday: "short" });
    return `<div class="day"><div class="label">${label}</div>${icon(d.icon)}` +
      `<div class="hilo"><span class="hi">${Math.round(d.hi)}°</span><span class="lo">${Math.round(d.lo)}°</span></div></div>`;
  }).join("");

  // Hourly strip: now, then every second hour.
  const key = localHourKey(new Date());
  const hours = (w.hourly || []).filter((x) => x.time >= key).filter((_, i) => i % 2 === 0).slice(0, 8);
  $("hourly").innerHTML = hours.map((x, i) =>
    `<div class="hr"><div class="t">${i === 0 ? "Now" : fmtTime(x.time, true)}</div>${icon(x.icon)}` +
    `<div class="temp">${Math.round(x.temp)}°</div><div class="pop">${x.pop >= 20 ? `${x.pop}%` : ""}</div></div>`
  ).join("");

  const sunDay = days[0];
  $("sun").innerHTML = sunDay && sunDay.sunrise
    ? `<div class="kicker">Sun</div>` +
      `<div class="row">${icon("sunrise")}${fmtTime(sunDay.sunrise)}</div>` +
      `<div class="row">${icon("sunset")}${fmtTime(sunDay.sunset)}</div>`
    : "";
}

function renderAir(a) {
  const colour = AQHI_COLOURS[a.risk] || "#fff";
  $("aqhi").innerHTML =
    `<div class="kicker">Air quality</div>` +
    `<div class="value" style="color:${colour}">${a.aqhi}</div>` +
    `<div class="risk">AQHI · ${esc(a.risk)}</div>`;
  Cards.set("air", a);
}

function renderCalendar(c) {
  calendarData = c;
  const today = startOfToday();
  const days = c.days.map((d) => ({ ...d, date: parseDate(d.date) }));

  $("cal-head").innerHTML = days.slice(0, 7).map((d) =>
    `<div${d.date.getDay() === today.getDay() ? ' class="today"' : ""}>${d.date.toLocaleDateString("en-US", { weekday: "short" })}</div>`
  ).join("");

  $("cal-grid").style.gridTemplateRows = `repeat(${days.length / 7}, minmax(0, 1fr))`;
  $("cal-grid").innerHTML = days.map((d, i) => {
    const cls = sameDay(d.date, today) ? "cell today" : d.date < today ? "cell past" : "cell";
    const label = i === 0 || d.date.getDate() === 1
      ? d.date.toLocaleDateString("en-US", { month: "short", day: "numeric" })
      : d.date.getDate();
    const evs = d.events.map((e) => e.time
      ? `<div class="ev"><span class="time">${esc(e.time)}</span> ${esc(e.title)}</div>`
      : `<div class="ev allday${e.holiday ? " holiday" : ""}">${esc(e.title)}</div>`
    ).join("");
    return `<div class="${cls}"><div class="num"><span>${label}</span></div><div class="evs">${evs}</div></div>`;
  }).join("");

  // Fade out only the cells whose events don't fit.
  for (const el of document.querySelectorAll(".evs")) {
    el.classList.toggle("overflow", el.scrollHeight > el.clientHeight + 1);
  }
}

function renderWotd(w) {
  Cards.set("wotd", w);
}

function renderFx(f) {
  $("fx").innerHTML = `<div class="kicker">1 ${esc(f.base)}</div><div class="rates">` + f.rates.map((r) =>
    `<div class="rate"><div class="code">${esc(r.code)}</div>` +
    `<div class="val">${r.rate.toFixed(r.rate < 10 ? 3 : 2)}</div></div>`
  ).join("") + `</div>`;
}

function renderMoon(now) {
  const m = Moon.info(now);
  // Within a day of full, point at the next new moon instead.
  const fullSoon = (m.nextFull - now) / 86400000 < (m.nextNew - now) / 86400000;
  const [label, when] = fullSoon && m.name !== "Full moon" ? ["Full moon", m.nextFull] : ["New moon", m.nextNew];
  const date = `${when.toLocaleDateString("en-US", { weekday: "short" })} ${when.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
  $("moon").innerHTML = Moon.svg(m.phase) +
    `<div><div class="kicker">Moon</div><div class="name">${m.name}</div>` +
    `<div class="line">${Math.round(m.illumination * 100)}% lit</div><div class="line">${label} ${date}</div></div>`;
}

/* Background photos: crossfade between two layers. */
let photos = [];
let photoIdx = 0;
let front = $("photoA");
let back = $("photoB");

function showPhoto(p) {
  const img = new Image();
  img.onload = () => {
    back.style.backgroundImage = `url("${p.url}")`;
    back.classList.add("on");
    front.classList.remove("on");
    [front, back] = [back, front];
    $("credit").textContent = p.credit ? `Photo: ${p.credit}` : "";
  };
  img.src = p.url;
}

async function loadPhotos() {
  try {
    // Older servers return plain URLs; newer ones {url, credit}.
    const list = ((await getJSON("/api/photos")).data || []).map((p) => (typeof p === "string" ? { url: p, credit: "" } : p));
    const sig = list.map((p) => p.url).join();
    if (sig !== photos.map((p) => p.url).join()) {
      photos = list;
      // ?photo=N starts on a given photo (for testing).
      photoIdx = Math.min(Number(params.get("photo")) || 0, Math.max(photos.length - 1, 0));
      if (photos.length) showPhoto(photos[photoIdx]);
    }
  } catch (err) {
    console.warn(err);
  }
}

function nextPhoto() {
  if (photos.length < 2) return;
  photoIdx = (photoIdx + 1) % photos.length;
  showPhoto(photos[photoIdx]);
}

/* Wind map: loaded while active, blanked at night to save CPU. */
let mapActive = false;
function setMapActive(on) {
  const url = cfg.map && cfg.map.url;
  if (!url || on === mapActive) return;
  mapActive = on;
  $("map-frame").src = on ? url : "about:blank";
}

function setupMap() {
  const { url, reload_minutes: minutes } = cfg.map || {};
  if (!url) {
    $("map").hidden = true;
    return;
  }
  if (!isNight || !cfg.night.hide_map) setMapActive(true);
  // The wind data updates every few hours; a periodic reload keeps it current.
  if (minutes) {
    setInterval(() => {
      if (!mapActive) return;
      $("map-frame").src = "about:blank";
      setTimeout(() => { if (mapActive) $("map-frame").src = url; }, 1000);
    }, minutes * 60000);
  }
}

async function init() {
  try {
    cfg = { ...cfg, ...(await getJSON("/api/config")) };
  } catch (err) {
    console.warn(err);
  }
  $("title").textContent = cfg.title;
  document.documentElement.style.setProperty("--accent", cfg.accent);
  document.documentElement.style.setProperty("--night-dim", cfg.night.dim);
  document.body.classList.toggle("hide-map", !!cfg.night.hide_map);
  tick();
  setupMap();
  loadPhotos();
  setInterval(loadPhotos, 3600000);
  setInterval(nextPhoto, cfg.photos.rotate_minutes * 60000);

  Cards.start(cfg, params);
  const s = cfg.poll_seconds;
  poll("weather", renderWeather, s);
  poll("air", renderAir, s * 5);
  poll("calendar", renderCalendar, s);
  poll("wotd", renderWotd, s * 5);
  poll("fx", renderFx, s * 5);
}

init();
