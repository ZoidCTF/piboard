// Moon phase, computed locally. New and full moon times use Meeus, "Astronomical
// Algorithms" ch. 49 (main periodic terms; accurate to a few minutes). The phase drawing
// is for the northern hemisphere: lit on the right while waxing.
"use strict";

const Moon = (() => {
  const SYNODIC = 29.530588861;
  const rad = (d) => (d * Math.PI) / 180;
  const jdToDate = (jd) => new Date((jd - 2440587.5) * 86400000);
  const dateToJd = (d) => d.getTime() / 86400000 + 2440587.5;

  // Julian Ephemeris Day of the new (k integer) or full (k + 0.5) moon number k.
  function phaseJde(k) {
    const T = k / 1236.85;
    const jde = 2451550.09766 + SYNODIC * k + 0.00015437 * T ** 2 - 0.00000015 * T ** 3 + 0.00000000073 * T ** 4;
    const E = 1 - 0.002516 * T - 0.0000074 * T ** 2;
    const M = rad(2.5534 + 29.1053567 * k - 0.0000014 * T ** 2 - 0.00000011 * T ** 3);
    const Mp = rad(201.5643 + 385.81693528 * k + 0.0107582 * T ** 2 + 0.00001238 * T ** 3 - 0.000000058 * T ** 4);
    const F = rad(160.7108 + 390.67050284 * k - 0.0016118 * T ** 2 - 0.00000227 * T ** 3 + 0.000000011 * T ** 4);
    const O = rad(124.7746 - 1.56375588 * k + 0.0020672 * T ** 2 + 0.00000215 * T ** 3);
    const full = k % 1 !== 0;
    const c = full
      ? [-0.40614, 0.17302, 0.01614, 0.01043, 0.00734, -0.00515, 0.00209]
      : [-0.4072, 0.17241, 0.01608, 0.01039, 0.00739, -0.00514, 0.00208];
    return jde
      + c[0] * Math.sin(Mp) + c[1] * E * Math.sin(M) + c[2] * Math.sin(2 * Mp) + c[3] * Math.sin(2 * F)
      + c[4] * E * Math.sin(Mp - M) + c[5] * E * Math.sin(Mp + M) + c[6] * E * E * Math.sin(2 * M)
      - 0.00111 * Math.sin(Mp - 2 * F) - 0.00057 * Math.sin(Mp + 2 * F) + 0.00056 * E * Math.sin(2 * Mp + M)
      - 0.00042 * Math.sin(3 * Mp) + 0.00042 * E * Math.sin(M + 2 * F) + 0.00038 * E * Math.sin(M - 2 * F)
      - 0.00024 * E * Math.sin(2 * Mp - M) - 0.00017 * Math.sin(O);
  }

  // The next new or full moon after `date` (offset 0 = new, 0.5 = full).
  function next(date, offset) {
    const jd = dateToJd(date);
    let k = Math.floor((jd - 2451550.09766) / SYNODIC) - 1 + offset;
    while (phaseJde(k) <= jd) k += 1;
    return jdToDate(phaseJde(k));
  }

  function lastNew(date) {
    const jd = dateToJd(date);
    let k = Math.floor((jd - 2451550.09766) / SYNODIC) + 1;
    while (phaseJde(k) > jd) k -= 1;
    return jdToDate(phaseJde(k));
  }

  const NAMES = ["New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
    "Full moon", "Waning gibbous", "Last quarter", "Waning crescent"];

  function info(date) {
    const age = (date - lastNew(date)) / 86400000;      // days since new moon
    const p = (age / SYNODIC) % 1;                        // 0 new, 0.5 full
    return {
      phase: p,
      name: NAMES[Math.round(p * 8) % 8],
      illumination: (1 - Math.cos(2 * Math.PI * p)) / 2,
      nextFull: next(date, 0.5),
      nextNew: next(date, 0),
    };
  }

  // SVG of the moon at phase p: a dark disc, the lit limb, and the terminator ellipse.
  function svg(p) {
    const waxing = p < 0.5;
    const crescent = p < 0.25 || p > 0.75;
    const rx = Math.abs(40 * Math.cos(2 * Math.PI * p)).toFixed(2);
    const limb = waxing ? 1 : 0;
    const term = waxing === crescent ? 0 : 1;
    return `<svg viewBox="0 0 100 100" aria-hidden="true"><circle class="moon-dark" cx="50" cy="50" r="40"/>` +
      `<path class="moon-lit" d="M50 10 A40 40 0 0 ${limb} 50 90 A${rx} 40 0 0 ${term} 50 10Z"/></svg>`;
  }

  return { info, svg, phaseJde, next };
})();

if (typeof module !== "undefined") module.exports = Moon;
