// Train cards, destination tickets and colour constants.
import { h, s } from "./dom.js";

export const CARD_ORDER = ["purple", "white", "blue", "yellow", "orange", "black", "red", "green", "loco"];
export const COLOR_NAMES = {
  purple: "Purple",
  white: "White",
  blue: "Blue",
  yellow: "Yellow",
  orange: "Orange",
  black: "Black",
  red: "Red",
  green: "Green",
  loco: "Locomotive",
};
// Route space fills (the printed board's paint).
export const ROUTE_FILL = {
  purple: "#b383b8",
  white: "#eeedea",
  blue: "#2aa3dc",
  yellow: "#ecd320",
  orange: "#e9933f",
  black: "#3c4648",
  red: "#cf4134",
  green: "#93c95a",
  gray: "#a9aaa7",
};
// Plastic train pieces: [light, dark].
export const PLAYER_FILL = {
  red: ["#f05a4b", "#9c1d14"],
  blue: ["#4f9bf0", "#174f9a"],
  green: ["#4fcf6a", "#16702e"],
  yellow: ["#ffe05a", "#c39306"],
  black: ["#5d5d63", "#151518"],
};

// A different wagon drawing per colour, like the real cards.
const WAGONS = {
  purple: "passenger",
  white: "reefer",
  blue: "passenger",
  yellow: "box",
  orange: "box",
  black: "hopper",
  red: "tank",
  green: "caboose",
};

function wheels(y) {
  return [16, 30, 70, 84].map((x) => s("circle", { cx: x, cy: y, r: 5.2, class: "wheel" }));
}

function wagonIcon(color) {
  const kind = color === "loco" ? "loco" : WAGONS[color];
  const g = s("g", { class: "wagon" });
  if (kind === "loco") {
    g.append(
      s("rect", { x: 8, y: 26, width: 58, height: 22, rx: 4, class: "body" }),
      s("rect", { x: 60, y: 14, width: 28, height: 34, rx: 3, class: "body" }),
      s("rect", { x: 66, y: 19, width: 16, height: 11, rx: 1.5, class: "win" }),
      s("rect", { x: 14, y: 10, width: 9, height: 17, rx: 1.5, class: "body" }),
      s("path", { d: "M4 48 L0 56 L18 56 L14 48 Z", class: "body" }),
      s("circle", { cx: 8, cy: 37, r: 4, class: "win" }),
      ...[22, 42, 74].map((x) => s("circle", { cx: x, cy: 54, r: 7, class: "wheel" })),
      s("rect", { x: 18, y: 51.5, width: 58, height: 3, class: "rod" }),
    );
    return g;
  }
  const body = { x: 6, y: 18, width: 88, height: 30, rx: 3, class: "body" };
  if (kind === "passenger") {
    g.append(s("rect", body), s("rect", { x: 3, y: 14, width: 94, height: 6, rx: 3, class: "roof" }));
    for (let i = 0; i < 6; i++) g.append(s("rect", { x: 12 + i * 13.5, y: 24, width: 9, height: 11, rx: 1.5, class: "win" }));
  } else if (kind === "reefer") {
    g.append(s("rect", body), s("rect", { x: 40, y: 22, width: 20, height: 22, rx: 1, class: "line" }));
    g.append(s("path", { d: "M10 24 H34 M10 31 H34 M10 38 H34 M66 24 H90 M66 31 H90 M66 38 H90", class: "line" }));
  } else if (kind === "box") {
    g.append(s("rect", body), s("path", { d: "M38 20 V46 M62 20 V46 M38 20 L62 46 M62 20 L38 46", class: "line" }));
  } else if (kind === "hopper") {
    g.append(s("path", { d: "M4 18 H96 L84 48 H16 Z", class: "body" }), s("path", { d: "M8 16 Q30 4 50 12 Q72 4 92 16 Z", class: "coal" }));
  } else if (kind === "tank") {
    g.append(s("rect", { x: 6, y: 20, width: 88, height: 26, rx: 13, class: "body" }), s("rect", { x: 44, y: 12, width: 12, height: 10, rx: 2, class: "body" }));
    g.append(s("path", { d: "M10 33 H90", class: "line" }));
  } else if (kind === "caboose") {
    g.append(s("rect", body), s("rect", { x: 32, y: 6, width: 36, height: 14, rx: 2, class: "body" }));
    g.append(s("rect", { x: 14, y: 24, width: 12, height: 10, rx: 1.5, class: "win" }), s("rect", { x: 74, y: 24, width: 12, height: 10, rx: 1.5, class: "win" }));
    g.append(s("rect", { x: 38, y: 9, width: 10, height: 7, class: "win" }), s("rect", { x: 52, y: 9, width: 10, height: 7, class: "win" }));
  }
  g.append(s("rect", { x: 2, y: 47, width: 96, height: 3, class: "rod" }), ...wheels(53));
  return g;
}

export function trainCard(color, { count = 0, cls = "", ...attrs } = {}) {
  return h(
    "div",
    { class: `tcard c-${color} ${cls}`, title: COLOR_NAMES[color], "data-color": color, ...attrs },
    h("div", { class: "tcard-inner" }, s("svg", { viewBox: "0 0 100 62", class: "tcard-art" }, wagonIcon(color))),
    count ? h("span", { class: "tcount" }, count) : null,
  );
}

export function cardBack({ cls = "", ...attrs } = {}) {
  return h("div", { class: `tcard back ${cls}`, ...attrs });
}

export function chip(color, n = null) {
  return h("span", { class: `chip-card c-${color}`, title: COLOR_NAMES[color] || color }, n != null ? n : "");
}

// Rich log text: "[red]" -> card chip.
export function richText(text) {
  return text.split(/\[([a-z]+)\]/).map((part, i) => (i % 2 ? chip(part) : part));
}

export function paymentChips(length, color, locos) {
  const parts = [];
  if (length - locos > 0) parts.push(chip(color, length - locos));
  if (locos) parts.push(chip("loco", locos));
  return parts;
}

// The card's map window: both cities with room for their labels, at the card's aspect ratio.
const TM_ASPECT = 1.45;
const size = { w: 1000, h: 650 }; // the board the land symbol is drawn for
export function setMapSize(w, h) {
  size.w = w;
  size.h = h;
}

function ticketView(a, b) {
  const minW = size.w * 0.42;
  let w = Math.max(minW, Math.abs(a.x - b.x) * 1.25 + size.w * 0.12);
  let h = w / TM_ASPECT;
  const needH = Math.abs(a.y - b.y) + w * 0.34;
  if (needH > h) [h, w] = [needH, needH * TM_ASPECT];
  return { x: (a.x + b.x) / 2 - w / 2, y: (a.y + b.y) / 2 - h / 2, w, h };
}

function ticketLabel(city, other, name, fs, v) {
  const above = city.y < other.y || (city.y === other.y && city.x < other.x);
  const width = name.length * fs * 0.66;
  const pad = fs * 0.25;
  const x = Math.min(Math.max(city.x - width / 2, v.x + pad), v.x + v.w - pad - width);
  const y = above ? city.y - fs * 0.75 : city.y + fs * 1.45;
  return s("text", { x, y, "font-size": fs, textLength: width, lengthAdjust: "spacingAndGlyphs", class: "tm-name" }, name);
}

// A destination ticket with a mini map (the land shape is a <symbol id="land-sym"> on the page).
export function ticketCard(ticket, cityPos, { done = false, cls = "", ...attrs } = {}) {
  const a = cityPos[ticket.a];
  const b = cityPos[ticket.b];
  const v = ticketView(a, b);
  const fs = v.w * 0.085;
  const dot = v.w * 0.028;
  return h(
    "div",
    {
      class: `ticket ${ticket.long ? "long" : ""} ${done ? "done" : ""} ${cls}`,
      "data-ticket": ticket.id,
      "aria-label": `${ticket.a} – ${ticket.b}, ${ticket.value} points`,
      ...attrs,
    },
    h(
      "div",
      { class: "ticket-map" },
      s(
        "svg",
        { viewBox: `${v.x} ${v.y} ${v.w} ${v.h}`, preserveAspectRatio: "xMidYMid meet" },
        s("rect", { x: v.x - v.w, y: v.y - v.h, width: v.w * 3, height: v.h * 3, class: "tm-sea" }),
        s("use", { href: "#land-sym", x: 0, y: 0, width: size.w, height: size.h, class: "tm-land" }),
        s("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "tm-line", "stroke-width": dot * 0.45, "stroke-dasharray": `${dot} ${dot * 0.6}` }),
        ...[a, b].map((c) => flagEl(c.country, dot * 1.6, { x: c.x, y: c.y }) || s("circle", { cx: c.x, cy: c.y, r: dot, class: "tm-city", "stroke-width": dot * 0.3 })),
        ticketLabel(a, b, ticket.a, fs, v),
        ticketLabel(b, a, ticket.b, fs, v),
      ),
    ),
    h("span", { class: "ticket-value" }, ticket.value),
    done ? h("span", { class: "ticket-done", title: "Completed" }, "✓") : null,
  );
}

// A tiny round country flag (UK map), drawn in a -1..1 square and clipped to a circle by #flag-clip.
const FLAGS = {
  england: () => [rect(-1, -1, 2, 2, "#fff"), rect(-1, -0.24, 2, 0.48, "#ce1124"), rect(-0.24, -1, 0.48, 2, "#ce1124")],
  scotland: () => [
    rect(-1, -1, 2, 2, "#0065bd"),
    s("path", { d: "M-1 -1 L1 1 M1 -1 L-1 1", stroke: "#fff", "stroke-width": 0.42 }),
  ],
  wales: () => [
    rect(-1, -1, 2, 1, "#fff"),
    rect(-1, 0, 2, 1, "#00a03c"),
    s("path", { d: "M-0.72 0.42 L-0.38 0.05 L-0.5 -0.3 L-0.18 -0.12 L0.05 -0.5 L0.2 -0.2 L0.55 -0.42 L0.42 -0.02 L0.72 0.12 L0.3 0.25 L0.38 0.5 L0.05 0.3 L-0.3 0.5 Z", fill: "#d30731" }),
  ],
  ireland: () => [rect(-1, -1, 0.67, 2, "#169b62"), rect(-0.34, -1, 0.68, 2, "#fff"), rect(0.33, -1, 0.67, 2, "#ff883e")],
  france: () => [rect(-1, -1, 0.67, 2, "#0055a4"), rect(-0.34, -1, 0.68, 2, "#fff"), rect(0.33, -1, 0.67, 2, "#ef4135")],
  free: () => [
    ...[0, 1, 2, 3, 4, 5, 6].map((i) => rect(-1, -1 + (i * 2) / 7, 2, 1 / 7 + 0.01, i % 2 ? "#fff" : "#b22234")),
    rect(-1, -1, 1, 1.15, "#3c3b6e"),
  ],
};

function rect(x, y, width, height, fill) {
  return s("rect", { x, y, width, height, fill });
}

const COUNTRY_NAMES = { england: "England", scotland: "Scotland", wales: "Wales", ireland: "Ireland", france: "France", free: "America" };

export function countryName(country) {
  return COUNTRY_NAMES[country] || "";
}

export function flagEl(country, r, { x = 0, y = 0, cls = "" } = {}) {
  const draw = FLAGS[country];
  if (!draw) return null;
  return s(
    "g",
    { class: `flag ${cls}`, transform: `translate(${x} ${y}) scale(${r})` },
    s("g", { "clip-path": "url(#flag-clip)" }, draw()),
    s("circle", { r: 1, class: "flag-ring", "stroke-width": 0.22 }),
  );
}

export function ticketBack({ cls = "", ...attrs } = {}) {
  return h("div", { class: `ticket back ${cls}`, ...attrs }, h("span", { class: "ticket-back-label" }, "TICKET"));
}
