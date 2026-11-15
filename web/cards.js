// Bottom-middle panel: a notices row for things that shouldn't wait their turn
// (weather warnings, frost, smoke, collection day, imminent trips) above a
// rotating set of cards (word of the day plus seasonal cards).
// Uses helpers from app.js (poll, esc, icon, fmtTime, parseDate, ...), which is
// loaded after this file; Cards.start() is called from app.js once it's ready.
"use strict";

const Cards = (() => {
  const data = {};
  let s = null; // seasonal settings from config
  let monthOverride = null;
  let auroraOverride = null;
  let pinned = null;
  let cards = [];
  let index = 0;
  let rotateTimer = 0;

  const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
  const ALERT_COLOURS = { warning: "#ff6b6b", watch: "#f39c4a", advisory: "#f2d45c", statement: "#f2d45c" };
  const UV_LEVELS = [[2, "Low", "#7bd389"], [5, "Moderate", "#f2d45c"], [7, "High", "#f39c4a"], [10, "Very high", "#ff6b6b"], [99, "Extreme", "#c58af9"]];
  const month = () => monthOverride || new Date().getMonth() + 1;
  const inSeason = (months) => months.includes(month());
  const dayDiff = (a, b) => Math.round((startOf(a) - startOf(b)) / 86400000);
  const startOf = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; };
  const dayLabel = (date) => date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  const temps = (hi, lo) => `<span class="hi">${Math.round(hi)}°</span><span class="lo">${Math.round(lo)}°</span>`;

  /* ---- Collection day (from config: weekday, every_weeks, optional "next" anchor date) ---- */

  function nextPickup(item, today) {
    const wd = WEEKDAYS.indexOf(String(item.weekday).toLowerCase());
    if (wd < 0) return null;
    const d = startOf(today);
    d.setDate(d.getDate() + ((wd - d.getDay() + 7) % 7));
    const every = item.every_weeks || 1;
    if (every > 1 && item.next) {
      const weeks = Math.round(dayDiff(d, parseDate(item.next)) / 7);
      const off = ((weeks % every) + every) % every;
      if (off) d.setDate(d.getDate() + 7 * (every - off));
    }
    return d;
  }

  /* ---- Notices ---- */

  function notices(now) {
    const out = [];
    for (const a of data.alerts || []) {
      const ends = a.ends ? ` until ${new Date(a.ends).toLocaleString("en-US", { weekday: "short", hour: "numeric" })}` : "";
      out.push({ colour: ALERT_COLOURS[a.type] || "#f2d45c", text: `${a.name}${ends}` });
    }
    const w = data.weather;
    if (w && inSeason(s.frost_months)) {
      const today = w.daily.find((d) => sameDay(parseDate(d.date), now));
      const tomorrow = w.daily.find((d) => dayDiff(parseDate(d.date), now) === 1);
      if (now.getHours() >= 12 && tomorrow && tomorrow.lo <= 0) {
        out.push({ colour: "#9fd3ff", text: `Frost tonight · low ${Math.round(tomorrow.lo)}°` });
      } else if (now.getHours() < 10 && today && today.lo <= 0) {
        out.push({ colour: "#9fd3ff", text: `Frosty morning · low ${Math.round(today.lo)}°` });
      }
    }
    const air = data.air;
    if (air && air.aqhi >= 7) out.push({ colour: "#f39c4a", text: `Smoky air · AQHI ${air.aqhi} (${air.risk.toLowerCase()} risk)` });

    const due = { today: [], tomorrow: [] };
    for (const item of s.collection || []) {
      const d = nextPickup(item, now);
      if (!d) continue;
      const diff = dayDiff(d, now);
      if (diff === 0 && now.getHours() < 10) due.today.push(item.name);
      if (diff === 1 && now.getHours() >= 12) due.tomorrow.push(item.name);
    }
    if (due.today.length) out.push({ colour: "#7bd389", text: `${due.today.join(" & ")} today` });
    if (due.tomorrow.length) out.push({ colour: "#7bd389", text: `${due.tomorrow.join(" & ")} tomorrow` });

    // Aurora: tonight's forecast from mid-afternoon, or a storm happening while it's dark.
    const a = data.aurora;
    if (a) {
      const tonight = auroraNights().find((n) => dayDiff(parseDate(n.date), now) <= 0);
      const darkNow = a.nights.some((n) => now >= new Date(n.dark_from) && now < new Date(n.dark_until));
      if (a.now_kp >= a.min_kp && darkNow) {
        out.push({ colour: "#c58af9", text: `Aurora active now · Kp ${Math.round(a.now_kp)} · look north` });
      } else if (tonight && now.getHours() >= 15) {
        out.push({ colour: "#c58af9", text: `Aurora possible tonight · Kp ${tonight.kp.toFixed(1)} · after ${fmtTime(tonight.dark_from)}` });
      }
    }

    // Home Assistant: problems first, then the doorbell and things worth knowing.
    const h = data.home;
    if (h) {
      for (const name of h.leaks) out.push({ colour: "#ff6b6b", text: `Water leak · ${name}` });
      for (const d of h.doors) out.push({ colour: "#f39c4a", text: `${d.name} open · ${duration(d.minutes)}` });
      for (const o of h.ovens) out.push({ colour: "#f39c4a", text: `${o.name} on for ${duration(o.minutes)}${o.temp != null ? ` · ${Math.round(o.temp)}°` : ""}` });
      if (h.co2 != null && h.co2 >= h.co2_limit) out.push({ colour: "#f2d45c", text: `CO₂ ${Math.round(h.co2).toLocaleString()} ppm · open a window` });
      const rang = recent(h.doorbell.ring, now, DOORBELL_MINUTES);
      if (rang) out.push({ colour: "var(--accent)", text: `Doorbell · ${clock(rang)}` });
      const pkg = recent(h.doorbell.package, now, PACKAGE_MINUTES);
      if (pkg) out.push({ colour: "var(--accent)", text: `Package at the door · ${clock(pkg)}` });
      if (h.alarm) out.push({ colour: "#9fd3ff", text: `Alarm armed · ${h.alarm}` });
      for (const c of h.chargers) out.push({ colour: "#7bd389", text: `${c.name} charging · ${c.kw} kW${c.kwh != null ? ` · ${c.kwh} kWh` : ""}` });
    }

    for (const t of data.trips || []) {
      const diff = dayDiff(parseDate(t.date), now);
      if (diff === 0 || diff === 1) out.push({ colour: "var(--accent)", text: `Trip to ${t.destination} ${diff ? "tomorrow" : "today"} · ${t.time}` });
    }
    return out;
  }

  /* ---- Cards ---- */

  function wotdCard(w) {
    return `<div class="kicker">Word of the day</div>` +
      `<div class="word">${esc(w.word)}</div>` +
      `<div class="meta">${esc(w.pronunciation)} · <i>${esc(w.part_of_speech)}</i></div>` +
      // definition_html is sanitised server-side to text plus <em>.
      `<div class="def">${w.definition_html}</div>`;
  }

  function tripCard(t, now) {
    const date = parseDate(t.date);
    const diff = dayDiff(date, now);
    const when = diff === 0 ? "today" : diff === 1 ? "tomorrow" : `in ${diff} days`;
    const fc = t.forecast
      ? `<div class="trip-wx">${icon(t.forecast.icon)}<div class="hilo">${temps(t.forecast.hi, t.forecast.lo)}</div></div>`
      : "";
    return `<div class="kicker">Upcoming trip</div>` +
      `<div class="card-row"><div><div class="big-name">${esc(t.destination)}</div>` +
      `<div class="sub">${esc(t.region)}</div>` +
      `<div class="line">${dayLabel(date)} · ${esc(t.time)} · <b>${when}</b></div></div>${fc}</div>`;
  }

  function firesCard(f) {
    const list = f.nearest.map((x) =>
      `<li><b>${esc(x.name)}</b> · ${x.km} km ${x.dir} · ${x.size_ha.toLocaleString()} ha · <span class="${x.status === "Out of Control" ? "hot" : ""}">${esc(x.status)}</span></li>`
    ).join("");
    return `<div class="kicker">Wildfires within ${f.radius_km} km</div>` +
      `<div class="card-row"><div class="stat"><div class="num${f.out_of_control ? " hot" : ""}">${f.active}</div><div class="lbl">active</div></div>` +
      `<div class="stat"><div class="num${f.out_of_control ? " hot" : ""}">${f.out_of_control}</div><div class="lbl">out of control</div></div>` +
      `<ul class="fire-list">${list}</ul></div>`;
  }

  function summerCard(w, lake, now) {
    const today = w && w.daily.find((d) => sameDay(parseDate(d.date), now));
    let uv = "";
    if (today && today.uv != null) {
      const [, label, colour] = UV_LEVELS.find(([max]) => today.uv <= max);
      uv = `<div class="stat"><div class="num" style="color:${colour}">${Math.round(today.uv)}</div><div class="lbl">UV · ${label}</div></div>`;
    }
    let lk = "";
    if (lake) {
      const ch = lake.change_cm_7d;
      const trend = ch == null ? "" : ch === 0 ? "steady this week" : `${ch > 0 ? "▲" : "▼"} ${Math.abs(ch)} cm this week`;
      lk = `<div class="lake"><div class="big-name">Okanagan Lake</div><div class="line">${trend}</div>` +
        `<div class="sub">Kelowna gauge ${lake.level_m.toFixed(2)} m</div></div>`;
    }
    return `<div class="kicker">Sun &amp; lake</div><div class="card-row">${uv}${lk}</div>`;
  }

  function snowCard(sn) {
    return `<div class="kicker">${esc(sn.name)}</div>` +
      `<div class="card-row">` +
      `<div class="stat"><div class="num">${sn.new_24h_cm}</div><div class="lbl">cm new · 24 h</div></div>` +
      `<div class="stat"><div class="num">${sn.next_72h_cm}</div><div class="lbl">cm next 3 days</div></div>` +
      `<div class="stat"><div class="num">${sn.depth_cm}</div><div class="lbl">cm base</div></div>` +
      `<div class="trip-wx">${icon(sn.icon)}<div class="hilo"><span class="hi">${Math.round(sn.temp)}°</span></div></div></div>`;
  }

  function roadsCard(r) {
    const bust = Math.floor(Date.now() / 600000); // new webcam image every 10 minutes
    const cams = r.cameras.map((c) =>
      `<figure class="cam"><img src="${c.url}?t=${bust}" alt=""><figcaption>${esc(c.name)}</figcaption></figure>`
    ).join("");
    const ev = r.events.length
      ? r.events.slice(0, 2).map((e) => `<div class="line${e.closed ? " hot" : ""}"><b>Hwy ${esc(e.highway)}</b> ${esc(e.text)}</div>`).join("")
      : `<div class="line">No closures or major incidents on Hwy ${s.roads.highways.join(", ")}</div>`;
    return `<div class="kicker">Mountain passes</div><div class="cams">${cams}</div>${ev}`;
  }

  /* ---- Home (Home Assistant) ---- */

  const DOORBELL_MINUTES = 3;   // doorbell card and notice after a ring
  const PACKAGE_MINUTES = 240;  // "package at the door" notice
  const duration = (m) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`);
  const clock = (d) => d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).replace(" ", "").toLowerCase();
  // An event entity's time, if it happened within `minutes` (and isn't in the future).
  const recent = (iso, now, minutes) => {
    if (!iso) return null;
    const d = new Date(iso);
    const age = (now - d) / 60000;
    return age >= -1 && age <= minutes ? d : null;
  };

  function homeCard(h) {
    const zones = h.climate.map((z) =>
      `<div class="stat"><div class="num">${Math.round(z.temp)}°${z.heating ? `<span class="heat" title="heating"></span>` : ""}</div>` +
      `<div class="lbl">${esc(z.name)}${z.humidity != null ? ` · ${Math.round(z.humidity)}%` : ""}</div></div>`
    ).join("");
    const co2 = h.co2 != null
      ? `<div class="stat"><div class="num${h.co2 >= h.co2_limit ? " hot" : ""}">${Math.round(h.co2)}</div><div class="lbl">CO₂ ppm</div></div>`
      : "";
    return `<div class="kicker">Inside</div><div class="card-row">${zones}${co2}</div>`;
  }

  function doorbellCard(h, now) {
    const rang = recent(h.doorbell.ring, now, DOORBELL_MINUTES);
    const which = rang || !h.doorbell.package_camera ? "camera" : "package_camera";
    const bust = Math.floor(Date.now() / 10000); // a fresh snapshot every 10 s while it's up
    return `<div class="kicker">${rang ? `Doorbell · ${clock(rang)}` : "Package at the door"}</div>` +
      `<figure class="cam doorbell"><img src="/api/camera/${which}?t=${bust}" alt=""></figure>`;
  }

  /* ---- Northern lights ---- */

  // Nights ahead whose forecast Kp reaches the visibility threshold (?aurora=N fakes tonight's Kp).
  function auroraNights() {
    const a = data.aurora;
    if (!a) return [];
    const nights = a.nights.map((n, i) => (i === 0 && auroraOverride != null ? { ...n, kp: auroraOverride } : n));
    return nights.filter((n) => n.kp >= a.min_kp);
  }

  const nightName = (n, now) => {
    const diff = dayDiff(parseDate(n.date), now);
    return diff <= 0 ? "tonight" : diff === 1 ? "tomorrow night" : `${parseDate(n.date).toLocaleDateString("en-US", { weekday: "long" })} night`;
  };

  function auroraCard(a, nights, now) {
    const n = nights[0];
    const overhead = n.kp >= a.overhead_kp;
    const cloudy = n.cloud != null && n.cloud >= 70;
    const after = new Date(n.peak) > new Date(n.dark_from) ? n.peak : n.dark_from;
    const more = nights.slice(1, 3).map((x) => `${nightName(x, now)} Kp ${x.kp.toFixed(1)}`).join(" · ");
    return `<div class="kicker">Northern lights</div>` +
      `<div class="card-row"><div><div class="big-name">${overhead ? "Likely" : "Possible"} ${nightName(n, now)}</div>` +
      `<div class="line">${overhead ? "Strong storm: may reach high in the sky" : "Look low on the northern horizon"}, best after <b>${fmtTime(after)}</b></div>` +
      `<div class="sub">${cloudy ? `Cloudy (${n.cloud}%), so it may be hidden` : n.cloud != null ? `Cloud cover ${n.cloud}%` : ""}${more ? ` · ${more}` : ""}</div></div>` +
      `<div class="stat"><div class="num" style="color:${overhead ? "#c58af9" : "#7bd389"}">${n.kp.toFixed(1)}</div><div class="lbl">Kp${n.scale ? ` · ${esc(n.scale)} storm` : ""}</div></div></div>`;
  }

  function buildCards(now) {
    const list = [];
    if (data.wotd) list.push({ key: "wotd", html: wotdCard(data.wotd) });
    for (const t of data.trips || []) list.push({ key: `trip-${t.date}`, html: tripCard(t, now) });
    if (data.fires && data.fires.active && inSeason(s.fire_months)) list.push({ key: "fires", html: firesCard(data.fires) });
    if (inSeason(s.summer_months) && (data.weather || data.lake)) list.push({ key: "summer", html: summerCard(data.weather, data.lake, now) });
    if (data.snow && inSeason(s.winter_months)) list.push({ key: "snow", html: snowCard(data.snow) });
    if (data.roads && inSeason(s.winter_months)) list.push({ key: "roads", html: roadsCard(data.roads) });
    const h = data.home;
    if (h && h.climate.length) list.push({ key: "home", html: homeCard(h) });
    const aurora = auroraNights();
    // Lead with it: a storm is short-lived news.
    if (aurora.length) list.splice(0, 0, { key: "aurora", html: auroraCard(data.aurora, aurora, now) });
    // Someone at the door (or a parcel just left) takes over the panel for a few minutes.
    if (h && h.doorbell.camera && (recent(h.doorbell.ring, now, DOORBELL_MINUTES) || recent(h.doorbell.package, now, 10))) {
      list.splice(0, 0, { key: "doorbell", html: doorbellCard(h, now) });
    }
    return list;
  }

  /* ---- Rendering ---- */

  function render() {
    if (!s) return;
    const now = new Date();
    const n = notices(now);
    const box = $("notices");
    box.hidden = !n.length;
    box.innerHTML = n.map((x) => `<div class="notice"><span class="dot" style="background:${x.colour}"></span>${esc(x.text)}</div>`).join("");

    const currentKey = pinned || (cards[index] && cards[index].key);
    const hadDoorbell = cards.some((c) => c.key === "doorbell");
    cards = buildCards(now);
    index = Math.max(0, cards.findIndex((c) => c.key.startsWith(currentKey)));
    if (!hadDoorbell && !pinned && cards[0] && cards[0].key === "doorbell") index = 0; // jump to it
    show(false);
  }

  function show(fade) {
    const stage = $("card-stage");
    const card = cards[index];
    $("card-dots").innerHTML = cards.length > 1 ? cards.map((_, i) => `<span class="${i === index ? "on" : ""}"></span>`).join("") : "";
    if (!card) {
      stage.innerHTML = "";
      return;
    }
    if (!fade) {
      // Data polls re-render often; leave the DOM alone unless the card changed.
      if (stage.dataset.html === card.html) return;
      stage.className = `card card-${card.key.split("-")[0]}`;
      stage.innerHTML = card.html;
      stage.dataset.html = card.html;
      return;
    }
    stage.classList.add("out");
    setTimeout(() => {
      stage.className = `card card-${card.key.split("-")[0]} out`;
      stage.innerHTML = card.html;
      stage.dataset.html = card.html;
      requestAnimationFrame(() => stage.classList.remove("out"));
    }, 600);
  }

  function rotate() {
    if (cards.length < 2 || pinned || cards[index].key === "doorbell") return;
    index = (index + 1) % cards.length;
    show(true);
  }

  return {
    set(name, value) {
      data[name] = value;
      render();
    },
    start(config, params) {
      s = config.seasonal;
      // For testing: ?month=N previews another season's cards; ?card=fires (or
      // wotd, trip, summer, snow, roads) holds that card instead of rotating.
      if (params.has("month")) monthOverride = Number(params.get("month"));
      if (params.has("card")) pinned = params.get("card");
      if (params.has("aurora")) auroraOverride = Number(params.get("aurora")); // fake tonight's Kp
      const p = config.poll_seconds;
      for (const name of ["alerts", "fires", "lake", "snow", "roads", "trips", "aurora"]) {
        poll(name, (v) => Cards.set(name, v), p * 5);
      }
      // Home Assistant is on the LAN and the server polls it every few seconds; ask often
      // so the doorbell shows up promptly.
      if (config.home) poll("home", (v) => Cards.set("home", v), 5);
      clearInterval(rotateTimer);
      rotateTimer = setInterval(rotate, s.card_seconds * 1000);
      setInterval(render, 60000); // notices depend on the time of day
      render();
    },
  };
})();
