// The SVG game board: map art, route spaces, cities, score track, claimed trains and stations.
import { h, s } from "./dom.js";
import { PLAYER_FILL, ROUTE_FILL } from "./cards.js";

const GAP = 2.6; // between cars
const CAR_W = 8.6;
const CITY_R = 10.5; // keep cars this far from a city centre
const TRACK_OFF = 5.1; // half distance between the two tracks of a double route
const RING = 30; // score track thickness around the map
const COMMIT_MS = 140; // gesture idle time before the zoom is re-rendered crisply
const SEA = "#c2cbd3";
const SERIF = '"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif';

// Where a city is drawn: its main spot and any further sites (France has two landings on the UK board).
const sitesOf = (c) => [[c.x, c.y], ...(c.sites || [])];
const dist = (a, b) => Math.hypot(b.x - a.x, b.y - a.y);

// A route is a polyline: city a -> waypoints -> city b. Double tracks are the same polyline pushed
// sideways (mitred at the bends).
function offsetLine(pts, off) {
  if (!off) return pts;
  const dirs = [];
  for (let i = 1; i < pts.length; i++) {
    const d = dist(pts[i - 1], pts[i]) || 1;
    dirs.push({ x: (pts[i].x - pts[i - 1].x) / d, y: (pts[i].y - pts[i - 1].y) / d });
  }
  return pts.map((p, i) => {
    const d0 = dirs[Math.max(0, i - 1)];
    const d1 = dirs[Math.min(dirs.length - 1, i)];
    // normals are (-dy, dx); the mitre is their sum scaled so the offset stays `off` from both segments
    let nx = -d0.y - d1.y;
    let ny = d0.x + d1.x;
    const k = nx * -d0.y + ny * d0.x;
    if (Math.abs(k) < 0.3) {
      nx = -d0.y;
      ny = d0.x;
    } else {
      nx /= k;
      ny /= k;
    }
    return { x: p.x + nx * off, y: p.y + ny * off };
  });
}

function sampleLine(pts) {
  const len = [0];
  for (let i = 1; i < pts.length; i++) len.push(len[i - 1] + dist(pts[i - 1], pts[i]));
  return { pts, len, total: len[len.length - 1] };
}

function at(curve, sLen) {
  const { pts, len } = curve;
  let i = 1;
  while (i < len.length - 1 && len[i] < sLen) i++;
  const t = (sLen - len[i - 1]) / Math.max(1e-6, len[i] - len[i - 1]);
  const p0 = pts[i - 1];
  const p1 = pts[i];
  return { x: p0.x + (p1.x - p0.x) * t, y: p0.y + (p1.y - p0.y) * t };
}

// Cars along a polyline. Each straight piece gets whole cars (the bends fall in the gaps, like the printed
// board); if the pieces can't take them evenly, cars are strung along the line and a car on a bend lies
// along its chord.
function placeCars(curve, L) {
  const { len, total } = curve;
  const a0 = CITY_R;
  const avail = total - 2 * CITY_R;
  const carLen = (avail - (L - 1) * GAP) / L;
  const slot = carLen + GAP;
  const deg = (p, q) => (Math.atan2(q.y - p.y, q.x - p.x) * 180) / Math.PI;
  const segs = [];
  for (let i = 1; i < len.length; i++) {
    const s0 = Math.max(len[i - 1], a0);
    const s1 = Math.min(len[i], total - CITY_R);
    if (s1 - s0 > 1e-6) segs.push([s0, s1]);
  }
  const want = segs.map(([s0, s1]) => (s1 - s0 + GAP) / slot);
  const n = want.map(Math.floor);
  let rest = L - n.reduce((a, b) => a + b, 0);
  want
    .map((w, i) => [w - n[i], i])
    .sort((x, y) => y[0] - x[0])
    .forEach(([, i]) => {
      if (rest-- > 0) n[i]++;
    });
  const cars = [];
  if (rest <= 0 && segs.every(([s0, s1], i) => n[i] * slot - GAP <= s1 - s0 + 2.5)) {
    segs.forEach(([s0, s1], i) => {
      const start = s0 + (s1 - s0 - (n[i] * slot - GAP)) / 2;
      for (let k = 0; k < n[i]; k++) {
        const p = at(curve, start + k * slot);
        const q = at(curve, start + k * slot + carLen);
        cars.push({ x: (p.x + q.x) / 2, y: (p.y + q.y) / 2, angle: deg(p, q) });
      }
    });
    return { cars, carLen };
  }
  for (let i = 0; i < L; i++) {
    const p = at(curve, a0 + i * slot);
    const q = at(curve, a0 + i * slot + carLen);
    cars.push({ x: (p.x + q.x) / 2, y: (p.y + q.y) / 2, angle: deg(p, q) });
  }
  return { cars, carLen };
}

// Car centres/angles for every route, along the polyline traced from the printed board.
export function layoutRoutes(map) {
  const city = Object.fromEntries(map.cities.map((c) => [c.name, c]));
  const out = {};
  for (const r of map.routes) {
    const mid = r.path.map(([x, y]) => ({ x, y }));
    const [from, to] = r.ends ? r.ends.map(([x, y]) => ({ x, y })) : [city[r.a], city[r.b]];
    const curve = sampleLine(offsetLine([from, ...mid, to], r.side * TRACK_OFF));
    const { cars, carLen } = placeCars(curve, r.length);
    const line = [at(curve, CITY_R)];
    for (let i = 1; i < curve.pts.length - 1; i++) if (curve.len[i] > CITY_R && curve.len[i] < curve.total - CITY_R) line.push(curve.pts[i]);
    line.push(at(curve, curve.total - CITY_R));
    out[r.id] = {
      cars,
      carLen,
      path: `M${line.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("L")}`,
      mid: cars[Math.floor(r.length / 2)],
    };
  }
  return out;
}

// The 100 score cells run around the map, in proportion to its sides.
function trackCells(W, H) {
  const top = Math.round((50 * W) / (W + H));
  return { top, right: 50 - top, bottom: top, left: 50 - top };
}

function trackCell(i, W, H) {
  const cells = trackCells(W, H);
  const { top, right, bottom } = cells;
  const c = RING / 2;
  if (i < top) return { x: ((i + 0.5) * W) / top, y: -c };
  i -= top;
  if (i < right) return { x: W + c, y: ((i + 0.5) * H) / right };
  i -= right;
  if (i < bottom) return { x: W - ((i + 0.5) * W) / bottom, y: H + c };
  i -= bottom;
  return { x: -c, y: H - ((i + 0.5) * H) / cells.left };
}

// Deterministic randomness so every client paints the same map.
function rng(seed) {
  return () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 2 ** 32;
  };
}

// The printed map (sea, coast ripples, parchment land, borders, decorations) painted once into a bitmap.
// One full-size canvas instead of tiled patterns: no seams, and nothing heavy for SVG to re-rasterize on zoom.
function paintMap(land, W, H, scale, key) {
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(W * scale);
  canvas.height = Math.round(H * scale);
  const g = canvas.getContext("2d");
  g.scale(scale, scale);
  const rand = rng(7);
  const landP = new Path2D(land.land + (land.lakes || "")); // lakes are holes: always use "evenodd"
  const borderP = new Path2D(land.borders || "");

  g.fillStyle = SEA;
  g.fillRect(0, 0, W, H);
  for (let i = 0; i < 60; i++) {
    const x = rand() * W;
    const y = rand() * H;
    const r = 40 + rand() * 110;
    const grad = g.createRadialGradient(x, y, 0, x, y, r);
    const tone = rand() < 0.5 ? "255, 255, 255" : "70, 95, 115";
    grad.addColorStop(0, `rgba(${tone}, ${0.05 + rand() * 0.06})`);
    grad.addColorStop(1, `rgba(${tone}, 0)`);
    g.fillStyle = grad;
    g.fillRect(x - r, y - r, 2 * r, 2 * r);
  }

  // Ripple lines following the coast, like the engraved sea on the board.
  const ripples = document.createElement("canvas");
  ripples.width = canvas.width;
  ripples.height = canvas.height;
  const rg = ripples.getContext("2d");
  rg.scale(scale, scale);
  rg.lineJoin = "round";
  for (const [w, a] of [
    [34, 0.16],
    [24, 0.22],
    [15, 0.3],
    [8, 0.38],
  ]) {
    rg.globalCompositeOperation = "source-over";
    rg.strokeStyle = `rgba(78, 104, 124, ${a})`;
    rg.lineWidth = w;
    rg.stroke(landP);
    rg.globalCompositeOperation = "destination-out";
    rg.lineWidth = w - 1.1;
    rg.stroke(landP);
  }
  g.drawImage(ripples, 0, 0, W, H);

  // Little wave strokes scattered over open water.
  g.strokeStyle = "rgba(80, 106, 126, 0.32)";
  g.lineWidth = 0.75;
  g.lineCap = "round";
  for (let i = 0; i < 900; i++) {
    const x = rand() * W;
    const y = rand() * H;
    if (g.isPointInPath(landP, x * scale, y * scale, "evenodd")) continue;
    const w = 5 + rand() * 7;
    g.beginPath();
    g.moveTo(x - w, y);
    g.quadraticCurveTo(x - w / 2, y - 2.2, x, y);
    g.quadraticCurveTo(x + w / 2, y + 2.2, x + w, y);
    g.stroke();
  }

  // Land: parchment with sepia blotches, darker towards the coast.
  g.save();
  g.clip(landP, "evenodd");
  g.fillStyle = "#e8d7b8";
  g.fillRect(0, 0, W, H);
  // Countries tinted like the printed board (UK map): clipped to the land by the clip above.
  for (const region of land.regions || []) {
    g.fillStyle = region.fill;
    g.fill(new Path2D(region.d), "evenodd");
  }
  const north = g.createLinearGradient(0, 0, 0, H * 0.45);
  north.addColorStop(0, "rgba(196, 196, 186, 0.55)");
  north.addColorStop(1, "rgba(196, 196, 186, 0)");
  g.fillStyle = north;
  g.fillRect(0, 0, W, H);
  for (let i = 0; i < 260; i++) {
    const x = rand() * W;
    const y = rand() * H;
    const r = 12 + rand() * 60;
    const grad = g.createRadialGradient(x, y, 0, x, y, r);
    const light = rand() < 0.3;
    const tone = light ? "255, 248, 232" : `${140 + rand() * 30}, ${95 + rand() * 25}, ${50 + rand() * 20}`;
    grad.addColorStop(0, `rgba(${tone}, ${light ? 0.25 : 0.06 + rand() * 0.12})`);
    grad.addColorStop(1, `rgba(${tone}, 0)`);
    g.fillStyle = grad;
    g.fillRect(x - r, y - r, 2 * r, 2 * r);
  }
  g.filter = `blur(${2.5 * scale}px)`;
  g.strokeStyle = "rgba(125, 88, 48, 0.4)";
  g.lineWidth = 9;
  g.stroke(landP);
  g.filter = "none";
  g.strokeStyle = "rgba(150, 112, 70, 0.2)";
  g.lineWidth = 2.8;
  g.stroke(borderP);
  g.strokeStyle = "rgba(112, 78, 48, 0.62)";
  g.lineWidth = 0.75;
  g.setLineDash([2.6, 1.6]);
  g.stroke(borderP);
  g.setLineDash([]);
  g.restore();

  g.lineJoin = "round";
  g.strokeStyle = "rgba(84, 60, 38, 0.9)";
  g.lineWidth = 0.9;
  g.stroke(landP);

  (key === "uk" ? decorateUK : decorate)(g, W, H);

  // Fine paper grain over everything (high-frequency, so tiling is invisible).
  const grain = document.createElement("canvas");
  grain.width = grain.height = 192;
  const gg = grain.getContext("2d");
  const img = gg.createImageData(192, 192);
  for (let i = 0; i < img.data.length; i += 4) {
    const dark = rand() < 0.5;
    img.data[i] = dark ? 70 : 255;
    img.data[i + 1] = dark ? 50 : 250;
    img.data[i + 2] = dark ? 30 : 235;
    img.data[i + 3] = rand() * 22;
  }
  gg.putImageData(img, 0, 0);
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.fillStyle = g.createPattern(grain, "repeat");
  g.fillRect(0, 0, canvas.width, canvas.height);
  return canvas;
}

function decorate(g) {
  // Route scoring table in the North Sea, like the printed board.
  const x0 = 228;
  const y0 = 22;
  g.fillStyle = "rgba(240, 232, 214, 0.55)";
  g.strokeStyle = "rgba(90, 70, 48, 0.7)";
  g.lineWidth = 0.8;
  g.beginPath();
  g.roundRect(x0, y0, 128, 70, 3);
  g.fill();
  g.stroke();
  g.font = `800 8px ${SERIF}`;
  g.textBaseline = "middle";
  [
    [1, 1],
    [2, 2],
    [3, 4],
    [4, 7],
    [6, 15],
    [8, 21],
  ].forEach(([len, pts], i) => {
    const y = y0 + 8.5 + i * 10.6;
    g.fillStyle = "#3b2a17";
    g.textAlign = "left";
    g.fillText(len, x0 + 6, y);
    g.textAlign = "right";
    g.fillText(pts, x0 + 122, y);
    for (let k = 0; k < len; k++) {
      g.fillStyle = "#6a7378";
      g.beginPath();
      g.roundRect(x0 + 15 + k * 11.6, y - 2.6, 10, 5.2, 1);
      g.fill();
    }
  });
  // Compass rose in the Atlantic.
  g.save();
  g.translate(58, 300);
  g.globalAlpha = 0.7;
  g.strokeStyle = "#5f5a48";
  g.lineWidth = 0.9;
  g.beginPath();
  g.arc(0, 0, 24, 0, Math.PI * 2);
  g.stroke();
  g.fillStyle = "#8a5b2c";
  g.beginPath();
  g.moveTo(0, -32);
  g.lineTo(5.5, 0);
  g.lineTo(0, 32);
  g.lineTo(-5.5, 0);
  g.fill();
  g.fillStyle = "#5f5a48";
  g.beginPath();
  g.moveTo(-32, 0);
  g.lineTo(0, -5.5);
  g.lineTo(32, 0);
  g.lineTo(0, 5.5);
  g.fill();
  g.font = `800 9px ${SERIF}`;
  g.textAlign = "center";
  g.fillText("N", 0, -38);
  g.restore();
  g.fillStyle = "rgba(84, 108, 122, 0.75)";
  g.textAlign = "left";
  g.font = `italic 700 11px ${SERIF}`;
  g.letterSpacing = "4px";
  g.fillText("OCEANUS", 18, 352);
  g.fillText("ATLANTICUS", 10, 366);
  g.fillText("MARE MEDITERRANEUM", 250, 614);
  g.font = `italic 700 8.5px ${SERIF}`;
  g.letterSpacing = "2px";
  g.fillText("PONTUS", 818, 440);
  g.fillText("EUXINUS", 816, 451);
  g.letterSpacing = "0px";
}

// The UK board: route scoring table top left, compass in the Atlantic and the seas' names.
function decorateUK(g, W, H) {
  const x0 = 20;
  const y0 = 22;
  g.fillStyle = "rgba(240, 232, 214, 0.6)";
  g.strokeStyle = "rgba(90, 70, 48, 0.7)";
  g.lineWidth = 0.8;
  g.beginPath();
  g.roundRect(x0, y0, 128, 84, 3);
  g.fill();
  g.stroke();
  g.font = `800 8px ${SERIF}`;
  g.textBaseline = "middle";
  [
    [1, 1],
    [2, 2],
    [3, 4],
    [4, 7],
    [5, 10],
    [6, 15],
  ].forEach(([len, pts], i) => {
    const y = y0 + 9 + i * 12;
    g.fillStyle = "#3b2a17";
    g.textAlign = "left";
    g.fillText(len, x0 + 6, y);
    g.textAlign = "right";
    g.fillText(pts, x0 + 122, y);
    for (let k = 0; k < len; k++) {
      g.fillStyle = "#6a7378";
      g.beginPath();
      g.roundRect(x0 + 15 + k * 11.6, y - 2.6, 10, 5.2, 1);
      g.fill();
    }
  });
  g.fillStyle = "rgba(84, 108, 122, 0.8)";
  g.textAlign = "center";
  g.font = `italic 700 12px ${SERIF}`;
  g.letterSpacing = "4px";
  g.fillText("ATLANTIC OCEAN", 205, 180);
  g.font = `italic 700 9px ${SERIF}`;
  g.fillText("ENGLISH CHANNEL", 440, 828);
  g.save();
  g.translate(582, 330);
  g.rotate(Math.PI / 2);
  g.font = `italic 700 11px ${SERIF}`;
  g.fillText("NORTH SEA", 0, 0);
  g.restore();
  g.letterSpacing = "0px";
  g.font = `italic 700 9.5px ${SERIF}`;
  g.fillStyle = "rgba(60, 74, 90, 0.85)";
  g.letterSpacing = "0.5px";
  g.fillText("Southampton to New York", 108, 866);
  g.font = `800 10px ${SERIF}`;
  g.fillText("40 points", 108, 880);
  g.letterSpacing = "0px";
  // Compass rose
  g.save();
  g.translate(52, 772);
  g.globalAlpha = 0.55;
  g.strokeStyle = "#5f5a48";
  g.lineWidth = 0.9;
  g.beginPath();
  g.arc(0, 0, 20, 0, Math.PI * 2);
  g.stroke();
  g.fillStyle = "#8a5b2c";
  g.beginPath();
  g.moveTo(0, -27);
  g.lineTo(4.5, 0);
  g.lineTo(0, 27);
  g.lineTo(-4.5, 0);
  g.fill();
  g.fillStyle = "#5f5a48";
  g.beginPath();
  g.moveTo(-27, 0);
  g.lineTo(0, -4.5);
  g.lineTo(27, 0);
  g.lineTo(0, 4.5);
  g.fill();
  g.font = `800 8px ${SERIF}`;
  g.fillText("N", 0, -32);
  g.restore();
}

function locoGlyph(x, y, angle) {
  // Small locomotive marking a ferry space that needs a locomotive card.
  return s(
    "g",
    { class: "ferry-mark", transform: `translate(${x} ${y}) rotate(${angle}) scale(0.58)` },
    s("path", { d: "M-8 3 V-3 H2 V-6 H7 V3 Z M-6 -3 V-6 H-3 V-3 Z" }),
    s("circle", { cx: -5, cy: 4.5, r: 2 }),
    s("circle", { cx: 1, cy: 4.5, r: 2 }),
    s("circle", { cx: 5.5, cy: 4.5, r: 2 }),
  );
}

const LABEL_POS = {
  n: [0, -12.5, "middle"],
  s: [0, 18.5, "middle"],
  e: [11.5, 3.2, "start"],
  w: [-11.5, 3.2, "end"],
  ne: [8, -9, "start"],
  nw: [-8, -9, "end"],
  se: [8, 15, "start"],
  sw: [-8, 15, "end"],
};

export class Board {
  constructor(map, land, handlers = {}) {
    this.map = map;
    this.handlers = handlers;
    this.W = map.width;
    this.H = map.height;
    this.city = Object.fromEntries(map.cities.map((c) => [c.name, c]));
    this.layout = layoutRoutes(map);
    this.full = { x: -RING - 6, y: -RING - 6, w: this.W + 2 * RING + 12, h: this.H + 2 * RING + 12 };
    this.view = { ...this.full }; // what the user sees (may be ahead of the committed viewBox mid-gesture)
    this.shown = { ...this.full }; // what the SVG viewBox currently renders
    this.drawn = new Map(); // route id -> owner seat currently drawn
    this.trainColor = {}; // route id -> player colour, for the overview
    this.svg = this.build(land);
    this.overview = h("canvas", { class: "board-overview" });
    this.el = h("div", { class: "board-view" }, this.overview, this.svg);
    this.bindPanZoom();
    this.drawOverview();
  }

  // A cheap bitmap of the whole board behind the SVG: when a zoom-out gesture uncovers parts the SVG
  // hasn't rendered yet, they are filled at once instead of staying blank until the commit.
  drawOverview() {
    const f = this.full;
    const k = 1.6;
    const c = this.overview;
    c.width = Math.round(f.w * k);
    c.height = Math.round(f.h * k);
    const g = c.getContext("2d");
    g.setTransform(k, 0, 0, k, -f.x * k, -f.y * k);
    g.fillStyle = "#2f4f77";
    g.fillRect(f.x, f.y, f.w, f.h);
    g.fillStyle = "#3b6390";
    g.fillRect(-RING, -RING, this.W + 2 * RING, this.H + 2 * RING);
    if (this.mapCanvas) g.drawImage(this.mapCanvas, 0, 0, this.W, this.H);
    for (const r of this.map.routes) {
      const lay = this.layout[r.id];
      const owner = this.trainColor[r.id];
      g.fillStyle = owner ? PLAYER_FILL[owner][0] : ROUTE_FILL[r.color || "gray"];
      g.strokeStyle = owner ? PLAYER_FILL[owner][1] : "rgba(40, 30, 22, 0.85)";
      g.lineWidth = owner ? 1.1 : 0.7;
      for (const car of lay.cars) {
        g.save();
        g.translate(car.x, car.y);
        g.rotate((car.angle * Math.PI) / 180);
        const w = owner ? lay.carLen + 0.4 : lay.carLen;
        const hgt = owner ? CAR_W + 1.8 : CAR_W;
        g.fillRect(-w / 2, -hgt / 2, w, hgt);
        if (owner) {
          g.save();
          g.beginPath();
          g.rect(-w / 2, -hgt / 2, w, hgt);
          g.clip();
          g.fillStyle = "rgba(0, 0, 0, 0.8)";
          for (let x = -w / 2 - hgt; x < w / 2; x += 3.5) {
            g.beginPath();
            g.moveTo(x, hgt / 2);
            g.lineTo(x + 1.5, hgt / 2);
            g.lineTo(x + 1.5 + hgt, -hgt / 2);
            g.lineTo(x + hgt, -hgt / 2);
            g.fill();
          }
          g.restore();
        }
        g.strokeRect(-w / 2, -hgt / 2, w, hgt);
        g.restore();
      }
    }
    for (const city of this.map.cities) {
      for (const [x, y] of sitesOf(city)) {
        g.fillStyle = "rgba(236, 214, 178, 0.82)";
        g.beginPath();
        g.arc(x, y, 12.5, 0, Math.PI * 2);
        g.fill();
        g.fillStyle = "#d27a2c";
        g.strokeStyle = "#3d230d";
        g.lineWidth = 1.3;
        g.beginPath();
        g.arc(x, y, 5.6, 0, Math.PI * 2);
        g.fill();
        g.stroke();
      }
    }
    this.placeOverview();
  }

  placeOverview() {
    const f = this.full;
    const m = this.fit(this.view);
    const sc = (m.k * f.w) / this.overview.width;
    this.overview.style.transform = `translate(${m.ox + f.x * m.k}px, ${m.oy + f.y * m.k}px) scale(${sc})`;
  }

  build(land) {
    const { W, H } = this;
    const rainbow = s(
      "linearGradient",
      { id: "rainbow", x1: 0, y1: 0, x2: 1, y2: 1 },
      ...["#e04a3a", "#f39a2c", "#f3d23a", "#5cb84a", "#3f8fd8", "#9a5cc4"].map((c, i) => s("stop", { offset: i / 5, "stop-color": c })),
    );
    const playerGrads = Object.entries(PLAYER_FILL).map(([name, [light, dark]]) =>
      s(
        "linearGradient",
        { id: `pl-${name}`, x1: 0, y1: 0, x2: 0, y2: 1 },
        s("stop", { offset: 0, "stop-color": light }),
        s("stop", { offset: 0.5, "stop-color": light }),
        s("stop", { offset: 1, "stop-color": dark }),
      ),
    );
    const hazard = s(
      "pattern",
      { id: "hazard", width: 5, height: 5, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" },
      s("rect", { width: 2.1, height: 5, fill: "rgba(0, 0, 0, 0.8)" }),
    );
    const defs = s("defs", {}, rainbow, hazard, ...playerGrads);

    const frame = s(
      "g",
      { class: "frame" },
      s("rect", { x: -RING - 6, y: -RING - 6, width: W + 2 * RING + 12, height: H + 2 * RING + 12, rx: 10, class: "frame-outer" }),
      s("rect", { x: -RING, y: -RING, width: W + 2 * RING, height: H + 2 * RING, rx: 6, class: "frame-ring" }),
    );
    const track = s("g", { class: "score-track" });
    for (let i = 0; i < 100; i++) {
      const p = trackCell(i, W, H);
      const five = i % 5 === 0;
      track.append(
        s("ellipse", { cx: p.x, cy: p.y, rx: 15.5, ry: 11.5, class: `cell ${five ? "five" : ""}` }),
        s("text", { x: p.x, y: p.y + 3.6, class: "cell-num" }, i),
      );
    }

    const mapArt = s("image", { x: 0, y: 0, width: W, height: H, class: "map-art", preserveAspectRatio: "none" });
    const scale = Math.min(4, Math.max(3, Math.ceil(window.devicePixelRatio || 1) * 2));
    const canvas = paintMap(land, W, H, scale, this.map.key);
    this.mapCanvas = canvas;
    canvas.toBlob((blob) => mapArt.setAttribute("href", URL.createObjectURL(blob)), "image/jpeg", 0.9);

    this.routesG = s("g", { class: "routes" });
    for (const r of this.map.routes) this.routesG.append(this.routeEl(r));
    this.trainsG = s("g", { class: "trains" });
    this.citiesG = s("g", { class: "cities" });
    for (const c of this.map.cities) for (const at of sitesOf(c)) this.citiesG.append(this.cityEl(c, at));
    this.labelsG = s("g", { class: "labels" });
    for (const c of this.map.cities) for (const at of sitesOf(c)) this.labelsG.append(this.labelEl(c, at));
    this.stationsG = s("g", { class: "stations" });
    this.markersG = s("g", { class: "markers" });

    return s(
      "svg",
      { class: "board-svg", viewBox: this.viewBoxStr(this.shown), preserveAspectRatio: "xMidYMid meet" },
      defs,
      frame,
      track,
      mapArt,
      this.routesG,
      this.citiesG,
      this.trainsG,
      this.labelsG,
      this.stationsG,
      this.markersG,
    );
  }

  routeEl(r) {
    const lay = this.layout[r.id];
    const fill = ROUTE_FILL[r.color || "gray"];
    const g = s("g", { class: `route ${r.tunnel ? "tunnel" : ""} ${r.ferry ? "ferry" : ""}`, "data-route": r.id });
    g.append(s("path", { d: lay.path, class: "route-glow" }));
    lay.cars.forEach((c, i) => {
      const t = `translate(${c.x.toFixed(2)} ${c.y.toFixed(2)}) rotate(${c.angle.toFixed(2)})`;
      const car = s("g", { transform: t, class: "space" });
      car.append(s("rect", { x: -lay.carLen / 2, y: -CAR_W / 2, width: lay.carLen, height: CAR_W, rx: 1.4, fill, class: "space-rect" }));
      if (r.tunnel) car.append(s("rect", { x: -lay.carLen / 2 - 0.6, y: -CAR_W / 2 - 0.6, width: lay.carLen + 1.2, height: CAR_W + 1.2, rx: 1.8, class: "tunnel-edge" }));
      g.append(car);
      if (i < r.ferry) g.append(locoGlyph(c.x, c.y, c.angle));
    });
    g.append(s("path", { d: lay.path, class: "route-hit" }));
    g.addEventListener("click", (e) => this.handlers.onRoute?.(r.id, e));
    g.addEventListener("pointerenter", (e) => this.handlers.onHover?.({ route: r.id }, e));
    g.addEventListener("pointerleave", (e) => this.handlers.onHover?.(null, e));
    return g;
  }

  cityEl(c, [x, y]) {
    const g = s("g", { class: "city", "data-city": c.name, transform: `translate(${x} ${y})` });
    g.append(
      s("circle", { r: 12.5, class: "city-plate" }),
      s("circle", { r: 12.5, class: "city-halo" }),
      s("circle", { r: 5.6, class: "city-dot" }),
      s("circle", { r: 2.2, cx: -1, cy: -1, class: "city-core" }),
    );
    g.addEventListener("click", (e) => this.handlers.onCity?.(c.name, e));
    g.addEventListener("pointerenter", (e) => this.handlers.onHover?.({ city: c.name }, e));
    g.addEventListener("pointerleave", (e) => this.handlers.onHover?.(null, e));
    return g;
  }

  labelEl(c, [x, y]) {
    const [dx, dy, anchor] = LABEL_POS[c.label] || LABEL_POS.s;
    const name = c.name.toUpperCase();
    const attrs = { x: x + dx, y: y + dy, "text-anchor": anchor, class: "city-name", "data-city": c.name };
    if (name.length <= 14 || !name.includes(" ")) return s("text", attrs, name);
    // A long name sits on two lines, like the printed board's "Llandrindod Wells".
    const [first, ...rest] = name.split(" ");
    const up = c.label.startsWith("n");
    return s(
      "text",
      attrs,
      s("tspan", { x: attrs.x, dy: up ? "-1.05em" : "0" }, first),
      s("tspan", { x: attrs.x, dy: up ? "1.05em" : "1.05em" }, rest.join(" ")),
    );
  }

  trainEl(rid, color, fresh) {
    // Plastic train pieces with black hazard stripes: bigger than the printed space, with a cast shadow,
    // so a built route can't be mistaken for a free one of the same colour.
    const lay = this.layout[rid];
    const g = s("g", { class: `train ${fresh ? "fresh" : ""}`, "data-route": rid });
    const w = lay.carLen + 0.4;
    const hgt = CAR_W + 1.8;
    lay.cars.forEach((c, i) => {
      // Offsets that point down/right on screen whatever the car's rotation.
      const a = (c.angle * Math.PI) / 180;
      const down = (dx, dy) => ({ x: dx * Math.cos(a) + dy * Math.sin(a), y: -dx * Math.sin(a) + dy * Math.cos(a) });
      const sh = down(0.9, 1.5);
      g.append(
        s(
          "g",
          { transform: `translate(${c.x.toFixed(2)} ${c.y.toFixed(2)}) rotate(${c.angle.toFixed(2)})` },
          s(
            "g",
            { class: "piece", style: { "--i": i } },
            s("rect", { x: -w / 2 + sh.x, y: -hgt / 2 + sh.y, width: w, height: hgt, rx: 2.4, class: "piece-shadow" }),
            s("rect", { x: -w / 2, y: -hgt / 2, width: w, height: hgt, rx: 2.4, fill: `url(#pl-${color})`, class: `piece-body p-${color}` }),
            s("rect", { x: -w / 2, y: -hgt / 2, width: w, height: hgt, rx: 2.4, class: "piece-stripes" }),
            s("rect", { x: -w / 2 + 2.2, y: -hgt / 2 + 1.4, width: w - 4.4, height: 1.9, rx: 0.9, class: "piece-shine" }),
            s("line", { x1: -w / 2 + 2.6, y1: hgt / 2 - 2.1, x2: w / 2 - 2.6, y2: hgt / 2 - 2.1, class: "piece-line" }),
          ),
        ),
      );
    });
    return g;
  }

  stationEl(cityName, color) {
    const c = this.city[cityName];
    const [light, dark] = PLAYER_FILL[color];
    return s(
      "g",
      { class: "station", transform: `translate(${c.x - 9} ${c.y - 11})`, "data-city": cityName },
      s("path", { d: "M-5 7.4 V-0.6 L1 -6.6 L7 -0.6 V7.4 Z", class: "piece-shadow" }),
      s("path", { d: "M-6 6 V-2 L0 -8 L6 -2 V6 Z", fill: light, stroke: dark, "stroke-width": 1.2 }),
      s("rect", { x: -2, y: 1, width: 4, height: 5, fill: dark }),
    );
  }

  // ---------------------------------------------------------------- state
  update(game, seats, { freshRoute = null } = {}) {
    const owners = game.owners;
    let changed = false;
    for (const [rid, seat] of this.drawn) {
      if (owners[rid] !== seat) {
        this.trainsG.querySelector(`.train[data-route="${rid}"]`)?.remove();
        this.drawn.delete(Number(rid));
        delete this.trainColor[rid];
        changed = true;
      }
    }
    for (const [rid, seat] of Object.entries(owners)) {
      const id = Number(rid);
      if (this.drawn.get(id) === seat) continue;
      this.trainsG.append(this.trainEl(id, seats[seat].color, id === freshRoute));
      this.drawn.set(id, seat);
      this.trainColor[id] = seats[seat].color;
      changed = true;
    }
    if (changed) {
      clearTimeout(this.overviewTimer);
      this.overviewTimer = setTimeout(() => this.drawOverview(), 200);
    }
    for (const g of this.routesG.children) g.classList.toggle("owned", g.dataset.route in owners);
    this.stationsG.replaceChildren(...Object.entries(game.stations).map(([city, seat]) => this.stationEl(city, seats[seat].color)));
    this.markersG.replaceChildren(
      ...game.players.map((p, seat) => {
        const points = game.result ? game.result.players[seat].total : p.points;
        const cell = trackCell(((points % 100) + 100) % 100, this.W, this.H);
        const [light, dark] = PLAYER_FILL[seats[seat].color];
        const k = seat - (game.players.length - 1) / 2;
        return s("circle", { cx: cell.x + k * 4.5, cy: cell.y - 2 + Math.abs(k) * 2, r: 6.2, fill: light, stroke: dark, "stroke-width": 1.6, class: "marker" });
      }),
    );
  }

  clearTrains() {
    this.trainsG.replaceChildren();
    this.drawn.clear();
    this.trainColor = {};
    this.drawOverview();
  }

  setRouteClasses(map) {
    // map: route id -> space-separated classes (claimable, hint, ...)
    for (const g of this.routesG.children) {
      g.classList.remove("claimable", "hint", "dim", "focus");
      const cls = map[g.dataset.route];
      if (cls) g.classList.add(...cls.split(" "));
    }
  }

  setCityClasses(map) {
    for (const group of [this.citiesG, this.labelsG]) {
      for (const g of group.children) {
        g.classList.remove("hl", "hint", "buildable", "done");
        const cls = map[g.dataset.city];
        if (cls) g.classList.add(...cls.split(" "));
      }
    }
  }

  setDim(seat) {
    for (const g of this.trainsG.children) g.classList.toggle("faded", seat != null && this.drawn.get(Number(g.dataset.route)) !== seat);
  }

  // ---------------------------------------------------------------- pan & zoom
  // During a gesture only a CSS transform changes (GPU-composited, no re-render, no flashing);
  // the SVG viewBox is updated once the gesture pauses so the result is sharp again.
  viewBoxStr(v) {
    return `${v.x} ${v.y} ${v.w} ${v.h}`;
  }

  // Board -> local pixel mapping of the SVG (preserveAspectRatio meet) for a given viewBox.
  fit(v) {
    const w = this.el.clientWidth || 1;
    const h = this.el.clientHeight || 1;
    const k = Math.min(w / v.w, h / v.h);
    return { k, ox: (w - v.w * k) / 2 - v.x * k, oy: (h - v.h * k) / 2 - v.y * k };
  }

  clamp(v) {
    const f = this.full;
    v.w = Math.min(f.w, Math.max(f.w / 5, v.w));
    v.h = (v.w * f.h) / f.w;
    v.x = Math.min(f.x + f.w - v.w, Math.max(f.x, v.x));
    v.y = Math.min(f.y + f.h - v.h, Math.max(f.y, v.y));
  }

  applyView({ commit = false } = {}) {
    this.clamp(this.view);
    if (commit) return this.commitView();
    if (!this.frame) {
      this.frame = requestAnimationFrame(() => {
        this.frame = null;
        const a = this.fit(this.shown);
        const b = this.fit(this.view);
        const sc = b.k / a.k;
        this.svg.style.transform = `translate(${b.ox - sc * a.ox}px, ${b.oy - sc * a.oy}px) scale(${sc})`;
        this.svg.classList.add("moving");
        this.placeOverview();
      });
    }
    clearTimeout(this.commitTimer);
    this.commitTimer = setTimeout(() => this.commitView(), COMMIT_MS);
  }

  commitView() {
    clearTimeout(this.commitTimer);
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = null;
    this.shown = { ...this.view };
    this.svg.setAttribute("viewBox", this.viewBoxStr(this.shown));
    this.svg.style.transform = "";
    this.svg.classList.remove("moving");
    this.placeOverview();
    this.el.classList.toggle("zoomed", this.view.w < this.full.w - 1);
  }

  toBoard(clientX, clientY) {
    const r = this.el.getBoundingClientRect();
    const f = this.fit(this.view);
    return { x: (clientX - r.left - f.ox) / f.k, y: (clientY - r.top - f.oy) / f.k };
  }

  toClient(x, y) {
    const r = this.el.getBoundingClientRect();
    const f = this.fit(this.view);
    return { x: r.left + f.ox + x * f.k, y: r.top + f.oy + y * f.k };
  }

  zoomAt(factor, clientX, clientY) {
    const v = this.view;
    const p = clientX == null ? { x: v.x + v.w / 2, y: v.y + v.h / 2 } : this.toBoard(clientX, clientY);
    const nw = Math.min(this.full.w, Math.max(this.full.w / 5, v.w / factor));
    const k = nw / v.w;
    v.x = p.x - (p.x - v.x) * k;
    v.y = p.y - (p.y - v.y) * k;
    v.w = nw;
    this.applyView();
  }

  resetView() {
    this.view = { ...this.full };
    this.applyView();
  }

  bindPanZoom() {
    const el = this.el;
    const pointers = new Map();
    let drag = null;
    let pinch = null;
    this.dragged = false;
    el.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        this.zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.012 : 0.0022)), e.clientX, e.clientY);
      },
      { passive: false },
    );
    el.addEventListener("pointerdown", (e) => {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      this.dragged = false;
      if (pointers.size === 1) drag = { x: e.clientX, y: e.clientY, vx: this.view.x, vy: this.view.y };
      else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), w: this.view.w };
        drag = null;
      }
    });
    el.addEventListener("pointermove", (e) => {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pinch && pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        const factor = this.view.w / ((pinch.w * pinch.d) / d);
        this.zoomAt(factor, (a.x + b.x) / 2, (a.y + b.y) / 2);
        this.dragged = true;
      } else if (drag) {
        const dx = e.clientX - drag.x;
        const dy = e.clientY - drag.y;
        if (Math.hypot(dx, dy) > 5) this.dragged = true;
        if (!this.dragged) return;
        const k = this.fit(this.view).k;
        this.view.x = drag.vx - dx / k;
        this.view.y = drag.vy - dy / k;
        this.applyView();
      }
    });
    const end = (e) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
      if (!pointers.size) drag = null;
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
    // A drag must not also click the route or city under the pointer.
    el.addEventListener(
      "click",
      (e) => {
        if (this.dragged) {
          e.stopPropagation();
          e.preventDefault();
          this.dragged = false;
        }
      },
      true,
    );
    new ResizeObserver(() => this.commitView()).observe(el);
  }

  routeCenterClient(rid) {
    const m = this.layout[rid].mid;
    return this.toClient(m.x, m.y);
  }

  cityClient(name) {
    const c = this.city[name];
    return this.toClient(c.x, c.y);
  }
}
