// Ambient layers over the background photo:
//  - sky light: the accent colour and a tint over the photo follow the sun
//    (night, dawn, day, golden hour, blue hour), blended minute by minute;
//  - visible weather: rain or snow on the glass, drifting fog, lightning.
// The canvas loop only runs while there is weather to draw, at ~30 fps.
"use strict";

const Ambience = (() => {
  const root = document.documentElement;

  /* ---- Sky light ---- */

  const PALETTE = {
    night: { accent: [143, 180, 255], tint: [12, 22, 58, 0.3] },
    dawn: { accent: [255, 160, 178], tint: [255, 130, 160, 0.12] },
    day: { accent: [255, 180, 92], tint: [0, 0, 0, 0] },
    golden: { accent: [255, 160, 60], tint: [255, 140, 40, 0.16] },
    blue: { accent: [127, 176, 255], tint: [35, 60, 165, 0.22] },
  };

  // Phase keyframes in minutes of the day, relative to sunrise and sunset.
  const keyframes = (rise, set) => [
    [rise - 90, "night"], [rise - 25, "dawn"], [rise + 45, "day"],
    [set - 90, "day"], [set - 25, "golden"], [set + 15, "blue"], [set + 70, "night"],
  ];
  const lerp = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
  const minuteOf = (iso) => { const [h, m] = iso.slice(11, 16).split(":").map(Number); return h * 60 + m; };

  function skyAt(minute, rise, set) {
    const k = keyframes(rise, set);
    if (minute <= k[0][0] || minute >= k[k.length - 1][0]) return PALETTE.night;
    for (let i = 0; i < k.length - 1; i++) {
      const [m0, p0] = k[i];
      const [m1, p1] = k[i + 1];
      if (minute <= m1) {
        const t = (minute - m0) / (m1 - m0);
        return { accent: lerp(PALETTE[p0].accent, PALETTE[p1].accent, t), tint: lerp(PALETTE[p0].tint, PALETTE[p1].tint, t) };
      }
    }
    return PALETTE.day;
  }

  function setSky(sunriseIso, sunsetIso, minute) {
    const s = skyAt(minute, minuteOf(sunriseIso), minuteOf(sunsetIso));
    const [r, g, b] = s.accent.map(Math.round);
    const [tr, tg, tb, ta] = s.tint;
    root.style.setProperty("--accent", `rgb(${r}, ${g}, ${b})`);
    root.style.setProperty("--tint", `rgba(${Math.round(tr)}, ${Math.round(tg)}, ${Math.round(tb)}, ${ta.toFixed(3)})`);
  }

  /* ---- Visible weather ---- */

  const MODES = {
    drizzle: { kind: "rain", count: 70, speed: 0.8 },
    rain: { kind: "rain", count: 160, speed: 1 },
    thunder: { kind: "rain", count: 190, speed: 1.15, lightning: true },
    sleet: { kind: "mix", count: 130, speed: 0.9 },
    snow: { kind: "snow", count: 120, speed: 1 },
    fog: { fog: true },
  };

  const canvas = document.getElementById("wx-canvas");
  const ctx = canvas.getContext("2d");
  let mode = null;
  let particles = [];
  let raf = 0;
  let last = 0;
  let paused = false;
  let lightningTimer = 0;

  function resize() {
    canvas.width = innerWidth;
    canvas.height = innerHeight;
  }

  function spawn(kind, anywhere) {
    const w = canvas.width, h = canvas.height;
    const k = kind === "mix" ? (Math.random() < 0.5 ? "rain" : "snow") : kind;
    const p = { k, x: Math.random() * w * 1.2 - w * 0.1, y: anywhere ? Math.random() * h : -30 - Math.random() * h * 0.3 };
    if (k === "rain") {
      p.len = (16 + Math.random() * 26) * h / 1080;
      p.v = (0.9 + Math.random() * 0.5) * h; // px per second
      p.a = 0.18 + Math.random() * 0.22;
    } else {
      p.r = (1.3 + Math.random() * 2.6) * h / 1080;
      p.v = (25 + Math.random() * 40) * h / 1080;
      p.a = 0.5 + Math.random() * 0.35;
      p.phase = Math.random() * Math.PI * 2;
    }
    return p;
  }

  function frame(ts) {
    raf = requestAnimationFrame(frame);
    if (ts - last < 32) return; // ~30 fps is plenty and halves the work
    const dt = Math.min((ts - last) / 1000, 0.1);
    last = ts;
    const w = canvas.width, h = canvas.height, speed = mode.speed;
    ctx.clearRect(0, 0, w, h);
    ctx.lineCap = "round";
    ctx.lineWidth = Math.max(1, h / 720);
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      if (p.k === "rain") {
        p.y += p.v * speed * dt;
        p.x += p.v * speed * 0.15 * dt;
        ctx.strokeStyle = `rgba(205, 222, 255, ${p.a})`;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(p.x - p.len * 0.15, p.y - p.len);
        ctx.stroke();
      } else {
        p.phase += dt;
        p.y += p.v * speed * dt;
        p.x += Math.sin(p.phase) * 14 * dt;
        ctx.fillStyle = `rgba(255, 255, 255, ${p.a})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      if (p.y - 40 > h || p.x > w + 40) particles[i] = spawn(mode.kind, false);
    }
  }

  function scheduleLightning() {
    clearTimeout(lightningTimer);
    if (!mode || !mode.lightning || paused) return;
    lightningTimer = setTimeout(() => {
      const el = document.getElementById("flash");
      el.classList.remove("on");
      void el.offsetWidth; // restart the animation
      el.classList.add("on");
      scheduleLightning();
    }, 15000 + Math.random() * 35000);
  }

  function apply() {
    const running = mode && mode.kind && !paused;
    document.getElementById("fog").classList.toggle("on", !!(mode && mode.fog && !paused));
    if (running && !raf) {
      last = performance.now();
      raf = requestAnimationFrame(frame);
    } else if (!running && raf) {
      cancelAnimationFrame(raf);
      raf = 0;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    scheduleLightning();
  }

  function setWeather(name) {
    const next = MODES[name] || null;
    if (next === mode) return;
    mode = next;
    particles = mode && mode.kind ? Array.from({ length: mode.count }, () => spawn(mode.kind, true)) : [];
    apply();
  }

  function pause(on) {
    paused = on;
    apply();
  }

  resize();
  addEventListener("resize", resize);
  return { setSky, setWeather, pause };
})();
