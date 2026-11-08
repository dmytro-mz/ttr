import { Board } from "./board.js";
import { CARD_ORDER, COLOR_NAMES, PLAYER_FILL, cardBack, chip, paymentChips, richText, ticketBack, ticketCard, trainCard } from "./cards.js";
import { copyText, h, openDialog, s, toast } from "./dom.js";
import { getVolume, isMuted, setMuted, setVolume, sfx, unlockAudio } from "./sound.js";

const REACTIONS = ["👍", "😂", "😱", "😡", "🎉", "🤔", "😭", "🔥", "👏", "🙈"];
const MAX_SEATS = 5;
const SUMMARY_DELAY = 1800;

const app = document.getElementById("app");
const fx = document.getElementById("fx");
const overlay = document.getElementById("overlay");

const URL_TOKEN = takeTokenFromUrl();

const S = {
  config: { public_url: null, lan_url: null, bots: [] },
  map: null,
  land: null,
  cityPos: {},
  token: URL_TOKEN || localStorage.getItem("ttr.token") || newToken(),
  name: localStorage.getItem("ttr.name") || "",
  code: null,
  ws: null,
  retry: 0,
  reconnectTimer: null,
  connected: false,
  fatal: null,
  me: null,
  bots: [],
  log: [],
  state: null,
  board: null,
  boardGame: 0,
  ui: freshUi(),
  timer: { endAt: 0, total: 0, lastTick: 0 },
};
localStorage.setItem("ttr.token", S.token);

function freshUi() {
  return {
    selected: new Set(),
    offerKey: "",
    offerHidden: false,
    hover: null,
    pinned: new Set(),
    handColor: null,
    showClaimable: localStorage.getItem("ttr.showClaimable") === "1",
    hint: null,
    sideOpen: false,
    unread: 0,
    menu: false,
    summaryHidden: false,
    summaryAt: 0,
    focusSeat: null,
    pending: false,
  };
}

// "Continue on another device" links carry the player's token: /r/CODE?me=TOKEN.
function takeTokenFromUrl() {
  const params = new URLSearchParams(location.search);
  const token = params.get("me");
  if (!token || !/^[0-9a-f]{16,64}$/.test(token)) return null;
  history.replaceState({}, "", location.pathname);
  return token;
}

function newToken() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

const ADJECTIVES = ["Swift", "Lucky", "Steamy", "Brave", "Jolly", "Rusty", "Golden", "Express", "Midnight", "Royal"];
const NOUNS = ["Conductor", "Stoker", "Engineer", "Traveller", "Porter", "Signalman", "Brakeman", "Navigator", "Voyager", "Driver"];
const pick = (xs) => xs[Math.floor(Math.random() * xs.length)];
const suggestName = () => `${pick(ADJECTIVES)} ${pick(NOUNS)}`;

function saveName(name) {
  name = (name || "").trim().slice(0, 20);
  if (!name) return S.name;
  S.name = name;
  localStorage.setItem("ttr.name", name);
  return name;
}

const $ = (sel) => document.querySelector(sel);
const route = (id) => S.map.routes[id];
const ticket = (id) => S.map.tickets[id];
const seatColor = (st, seat) => st.seats[seat]?.color || "black";
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

// ------------------------------------------------------------------ routing
function go(path) {
  history.pushState({}, "", path);
  router();
}

function router() {
  const match = location.pathname.match(/^\/r\/([A-Za-z0-9]{4,8})\/?$/);
  overlay.replaceChildren();
  if (match) enterRoom(match[1].toUpperCase());
  else showHome();
}
window.addEventListener("popstate", router);

// ------------------------------------------------------------------ home
function showHome() {
  closeSocket();
  S.code = null;
  S.state = null;
  document.title = "Ticket to Ride · Europe";
  const nameInput = h("input", { class: "text", value: S.name, placeholder: suggestName(), maxlength: 20 });
  const codeInput = h("input", { class: "text", placeholder: "CODE", maxlength: 8, autocapitalize: "characters" });
  const create = async () => {
    saveName(nameInput.value || nameInput.placeholder);
    try {
      const res = await fetch("/api/rooms", { method: "POST" });
      if (!res.ok) throw new Error((await res.json()).detail || "Could not create a table");
      go(`/r/${(await res.json()).room}`);
    } catch (e) {
      toast(e.message, true);
    }
  };
  const join = async () => {
    const code = codeInput.value.trim().toUpperCase();
    if (!code) return codeInput.focus();
    saveName(nameInput.value || nameInput.placeholder);
    const res = await fetch(`/api/rooms/${encodeURIComponent(code)}`);
    if (!res.ok) return toast("No table with that code", true);
    go(`/r/${code}`);
  };
  codeInput.addEventListener("keydown", (e) => e.key === "Enter" && join());
  nameInput.addEventListener("keydown", (e) => e.key === "Enter" && create());
  const backdrop = h("div", { class: "home-map" });
  if (S.map) {
    const b = new Board(S.map, S.land);
    backdrop.append(b.el);
  }
  app.replaceChildren(
    h(
      "div",
      { class: "home" },
      backdrop,
      h(
        "div",
        { class: "home-card" },
        h("div", { class: "logo" }, h("span", { class: "logo-top" }, "Ticket to Ride"), h("span", { class: "logo-sub" }, "Europe")),
        h("div", { class: "hero-cards" }, ["red", "loco", "blue", "yellow", "green"].map((c) => trainCard(c))),
        h(
          "p",
          { class: "tagline" },
          "Build railways across 1900s Europe — tunnels through the Alps, ferries over the Black Sea. Invite friends with a link and fill empty seats with bots.",
        ),
        h(
          "div",
          { class: "home-form" },
          h("label", {}, "Your name", nameInput),
          h("button", { class: "btn primary big", onclick: create }, "🚂 Create a table"),
          h("div", { class: "or" }, "or join with a code"),
          h("div", { class: "join-row" }, codeInput, h("button", { class: "btn", onclick: join }, "Join")),
        ),
        h("div", { class: "home-links" }, h("button", { class: "linklike", onclick: showRules }, "How to play")),
      ),
    ),
  );
}

// ------------------------------------------------------------------ room / socket
async function enterRoom(code) {
  closeSocket();
  Object.assign(S, { code, state: null, log: [], fatal: null, me: null, connected: false, retry: 0 });
  S.ui = freshUi();
  S.board = null;
  document.title = `Ticket to Ride · ${code}`;
  if (!S.name && !URL_TOKEN) await askName(`Join table ${code}`);
  buildShell();
  connect();
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${S.code}`);
  S.ws = ws;
  ws.onopen = () => ws.send(JSON.stringify({ type: "hello", token: S.token, name: S.name }));
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onclose = () => {
    if (S.ws !== ws) return;
    S.connected = false;
    renderConn();
    if (S.fatal) return;
    const delay = Math.min(8000, 400 * 2 ** S.retry++);
    S.reconnectTimer = setTimeout(connect, delay);
  };
}

function closeSocket() {
  clearTimeout(S.reconnectTimer);
  const ws = S.ws;
  S.ws = null;
  if (ws) ws.close();
}

function send(msg) {
  if (S.ws && S.ws.readyState === WebSocket.OPEN) S.ws.send(JSON.stringify(msg));
  else toast("Not connected — reconnecting…", true);
}

function act(action) {
  S.ui.hint = null;
  S.ui.pending = true;
  closePopover();
  send({ type: "action", action });
}

function onMessage(msg) {
  switch (msg.type) {
    case "welcome":
      S.me = msg.you;
      S.bots = msg.bots;
      S.log = msg.log;
      S.connected = true;
      S.retry = 0;
      renderConn();
      renderFeed();
      break;
    case "state":
      applyState(msg);
      break;
    case "log":
      S.log.push(msg.entry);
      appendFeed(msg.entry);
      if (msg.entry.kind === "chat" && msg.entry.member !== S.me) {
        sfx.chat();
        if (!S.ui.sideOpen && window.matchMedia("(max-width: 1100px)").matches) {
          S.ui.unread++;
          renderTop();
        }
      }
      break;
    case "react":
      showReaction(msg);
      break;
    case "hint":
      showHint(msg.action);
      break;
    case "error":
      S.ui.pending = false;
      toast(msg.message, true);
      sfx.error();
      if (S.state) render();
      break;
    case "fatal":
      S.fatal = msg.message;
      closeSocket();
      showFatal(msg.message);
      break;
  }
}

function showFatal(message) {
  app.replaceChildren(
    h(
      "div",
      { class: "center-msg" },
      h(
        "div",
        {},
        h("div", { class: "logo" }, h("span", { class: "logo-top" }, "Ticket to Ride")),
        h("h2", {}, message),
        h("p", {}, "Tables close a while after everyone has left."),
        h("button", { class: "btn primary big", onclick: () => go("/") }, "Start a new table"),
      ),
    ),
  );
}

// ------------------------------------------------------------------ state + effects
function captureRects() {
  const rects = {};
  for (const el of document.querySelectorAll("[data-fly]")) rects[el.dataset.fly] = el.getBoundingClientRect();
  return rects;
}

function applyState(next) {
  const prev = S.state;
  const rects = captureRects();
  S.state = next;
  S.ui.pending = false;
  if (!prev) renderFeed();
  const g = next.game;
  if (g && g.time_left != null) {
    S.timer.endAt = performance.now() + g.time_left * 1000;
    S.timer.total = g.time_total;
  } else S.timer.endAt = 0;
  const offerKey = g?.me?.offer?.join(",") || "";
  if (offerKey !== S.ui.offerKey) {
    S.ui.offerKey = offerKey;
    S.ui.selected = new Set(g?.phase === "initial_tickets" ? [] : []);
    S.ui.offerHidden = false;
  }
  if (next.status !== prev?.status) {
    S.ui.summaryHidden = false;
    if (next.status === "game_over" && prev?.status === "playing") {
      S.ui.summaryAt = performance.now() + SUMMARY_DELAY;
      setTimeout(renderOverlay, SUMMARY_DELAY + 20);
    } else S.ui.summaryAt = 0;
  }
  if (next.event?.kind === "game_start") {
    S.board?.clearTrains();
    S.ui.pinned = new Set();
    S.ui.focusSeat = null;
  }
  const events = next.event?.kind === "move" ? next.event.events : [];
  const fresh = events.find((e) => e.kind === "claim");
  render({ freshRoute: fresh ? fresh.route : null });
  if (prev && next.seq === prev.seq + 1 && !document.hidden) playEffects(prev, next, events, rects);
  afterApply(prev, next);
}

function afterApply(prev, next) {
  const mine = (st) => {
    const g = st?.game;
    if (!g || st.status !== "playing" || !g.me) return false;
    return g.me.my_turn || (g.phase === "initial_tickets" && g.me.offer.length > 0);
  };
  if (mine(next) && !mine(prev)) {
    sfx.turn();
    if (document.hidden) document.title = "🔔 Your turn! · Ticket to Ride";
  }
  if (prev?.status === "playing" && next.status === "game_over") {
    const won = next.game.result?.winners.includes(next.you.seat);
    setTimeout(() => {
      if (won) {
        sfx.win();
        confetti();
      } else sfx.lose();
    }, SUMMARY_DELAY);
  }
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && S.code) document.title = `Ticket to Ride · ${S.code}`;
});

function seatTarget(st, seat) {
  if (seat === st.you.seat) return $(".dock .hand") || $(".dock");
  return $(`.pl-row[data-seat="${seat}"]`);
}

function fly(fromRect, toEl, node, { delay = 0, dur = 520 } = {}) {
  if (!fromRect || !toEl || !fromRect.width) return;
  const to = toEl.getBoundingClientRect();
  const wrap = h("div", { class: "fly", style: { width: `${fromRect.width}px`, height: `${fromRect.height}px` } }, node);
  fx.append(wrap);
  const tx = to.left + to.width / 2 - fromRect.width / 2;
  const ty = to.top + to.height / 2 - fromRect.height / 2;
  const scale = Math.min(1, Math.max(0.35, to.height / fromRect.height));
  const anim = wrap.animate(
    [
      { transform: `translate(${fromRect.left}px, ${fromRect.top}px) scale(1)`, opacity: 1 },
      { transform: `translate(${(fromRect.left + tx) / 2}px, ${Math.min(fromRect.top, ty) - 40}px) scale(1.12)`, opacity: 1, offset: 0.45 },
      { transform: `translate(${tx}px, ${ty}px) scale(${scale})`, opacity: 0.2 },
    ],
    { duration: dur, delay, easing: "cubic-bezier(.35,.6,.3,1)", fill: "both" },
  );
  anim.finished.then(
    () => wrap.remove(),
    () => wrap.remove(),
  );
}

function playEffects(prev, next, events, rects) {
  let delay = 0;
  for (const ev of events) {
    const target = ev.seat != null ? seatTarget(next, ev.seat) : null;
    switch (ev.kind) {
      case "draw_face_up":
        fly(rects[`fu-${ev.slot}`], target, trainCard(ev.card), { delay });
        sfx.card();
        delay += 120;
        break;
      case "draw_blind":
        fly(rects.deck, target, ev.card ? trainCard(ev.card) : cardBack(), { delay });
        sfx.card();
        delay += 120;
        break;
      case "draw_tickets":
        for (let i = 0; i < ev.count; i++) fly(rects.tickets, target, ticketBack(), { delay: delay + i * 90 });
        sfx.ticket();
        break;
      case "keep_tickets":
        if (ev.seat !== next.you.seat) sfx.ticket();
        break;
      case "claim":
        sfx.claim(route(ev.route).length);
        break;
      case "station":
        sfx.station();
        break;
      case "market_reset":
        sfx.reset();
        $(".market")?.classList.add("flash");
        setTimeout(() => $(".market")?.classList.remove("flash"), 900);
        break;
      case "last_round":
        sfx.alert();
        break;
    }
  }
}

// ------------------------------------------------------------------ shell
function buildShell() {
  const input = h("input", { class: "text", placeholder: "Say something…", maxlength: 240, enterkeyhint: "send" });
  const form = h(
    "form",
    {
      class: "chat-form",
      onsubmit: (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        send({ type: "chat", text });
        input.value = "";
      },
    },
    input,
    h("button", { class: "btn small" }, "Send"),
  );
  app.replaceChildren(
    h(
      "div",
      { class: "shell" },
      h("header", { class: "topbar", id: "topbar" }),
      h("main", { class: "main", id: "main" }, h("div", { class: "center-msg" }, h("p", {}, "Connecting…"))),
      h(
        "aside",
        { class: "side", id: "side" },
        h("div", { class: "players", id: "players" }),
        h("div", { class: "side-head" }, "Table talk", h("button", { class: "icon-btn only-narrow", onclick: toggleSide, title: "Close" }, "✕")),
        h("div", { class: "feed", id: "feed" }),
        h(
          "div",
          { class: "reactions" },
          REACTIONS.map((emoji) => h("button", { title: "React", onclick: () => send({ type: "react", emoji }) }, emoji)),
        ),
        form,
      ),
    ),
    h("div", { id: "conn", class: "conn-banner hidden" }, "Reconnecting…"),
    h("div", { id: "tooltip", class: "tooltip hidden" }),
  );
  renderTop();
}

function renderConn() {
  $("#conn")?.classList.toggle("hidden", S.connected || !!S.fatal || !S.code);
}

function toggleSide() {
  S.ui.sideOpen = !S.ui.sideOpen;
  if (S.ui.sideOpen) S.ui.unread = 0;
  $("#side")?.classList.toggle("open", S.ui.sideOpen);
  renderTop();
}

function feedEntry(entry) {
  const time = new Date(entry.ts * 1000).toLocaleTimeString();
  if (entry.kind === "chat") return h("div", { class: "entry chat", title: time }, h("b", {}, entry.name), ": ", entry.text);
  const st = S.state;
  const color = entry.seat != null && st?.seats[entry.seat] ? st.seats[entry.seat].color : null;
  const dot = color ? h("span", { class: "who", style: { background: PLAYER_FILL[color][0] } }) : null;
  return h("div", { class: "entry log", title: time }, dot, richText(entry.text));
}

function renderFeed() {
  const feed = $("#feed");
  if (!feed) return;
  feed.replaceChildren(...S.log.map(feedEntry));
  feed.scrollTop = feed.scrollHeight;
}

function appendFeed(entry) {
  const feed = $("#feed");
  if (!feed) return;
  const atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 60;
  feed.append(feedEntry(entry));
  while (feed.children.length > 400) feed.firstChild.remove();
  if (atBottom || entry.member === S.me) feed.scrollTop = feed.scrollHeight;
}

function iconBtn(icon, title, onclick, cls = "", badge = 0) {
  return h("button", { class: `icon-btn ${cls}`, title, "aria-label": title, onclick }, icon, badge ? h("span", { class: "badge-dot" }, badge) : null);
}

// Speaker button with a volume slider on hover. Built once and kept in place, so re-rendering the top bar
// never interrupts a drag on the slider.
const volumeControl = (() => {
  const btn = h("button", { class: "icon-btn" });
  const range = h("input", { type: "range", min: 0, max: 100, step: 1, class: "vol-range", "aria-label": "Volume" });
  const pct = h("span", { class: "vol-pct" });
  const sync = () => {
    const vol = getVolume();
    const off = isMuted() || vol === 0;
    btn.textContent = off ? "🔇" : vol < 0.4 ? "🔉" : "🔊";
    btn.title = off ? "Sound off — click to turn on" : "Click to mute";
    btn.setAttribute("aria-label", btn.title);
    range.value = String(Math.round(vol * 100));
    pct.textContent = off ? "off" : `${Math.round(vol * 100)}%`;
  };
  btn.addEventListener("click", () => {
    unlockAudio();
    if (isMuted() || getVolume() === 0) {
      setMuted(false);
      if (getVolume() === 0) setVolume(0.85);
      sync();
      sfx.card();
    } else {
      setMuted(true);
      sync();
    }
  });
  range.addEventListener("input", () => {
    setVolume(Number(range.value) / 100);
    if (isMuted()) setMuted(false);
    sync();
  });
  range.addEventListener("change", () => sfx.card());
  sync();
  const place = () => {
    const r = btn.getBoundingClientRect();
    wrap.style.setProperty("--vol-top", `${r.bottom + 4}px`);
    wrap.style.setProperty("--vol-right", `${Math.max(8, window.innerWidth - r.right - 60)}px`);
  };
  const wrap = h(
    "div",
    { class: "vol", onpointerenter: place, onfocusin: place },
    btn,
    h("div", { class: "vol-pop" }, h("span", { class: "vol-ico" }, "🔈"), range, pct),
  );
  return wrap;
})();

function renderTop() {
  const top = $("#topbar");
  if (!top) return;
  const st = S.state;
  const g = st?.game;
  let info = "";
  if (st?.status === "lobby") info = "Lobby";
  else if (g) info = `Turn ${Math.floor(g.turn / Math.max(1, st.seats.length)) + 1} · ${plural(g.tickets_left, "ticket")} left in the pile`;
  const before = [
    h("span", { class: "brand", title: "Home", onclick: leaveTable }, "🚂 Ticket to Ride", h("small", {}, " Europe")),
    h("span", { class: "chip code", title: "Copy table code", onclick: copyCode }, "📋 ", S.code),
    h("span", { class: "round-info" }, info),
    h("span", { class: "spacer" }),
    g ? iconBtn("📊", "Scores", showScores) : null,
    iconBtn("❓", "How to play", showRules),
  ].filter(Boolean);
  const after = [iconBtn("💬", "Chat & players", toggleSide, "only-narrow", S.ui.unread), iconBtn("⋯", "Menu", toggleMenu)];
  if (volumeControl.parentNode !== top) top.append(volumeControl);
  for (const el of [...top.children]) if (el !== volumeControl) el.remove();
  volumeControl.before(...before);
  volumeControl.after(...after);
  document.getElementById("menu")?.remove();
  if (S.ui.menu) document.body.append(renderMenu());
}

function toggleMenu() {
  S.ui.menu = !S.ui.menu;
  renderTop();
}

function renderMenu() {
  const st = S.state;
  const isHost = st?.host === S.me;
  const item = (label, fn) =>
    h(
      "button",
      {
        onclick: () => {
          S.ui.menu = false;
          renderTop();
          fn();
        },
      },
      label,
    );
  return h(
    "div",
    { class: "menu", id: "menu" },
    item("🔗 Copy invite link", copyInvite),
    item("📱 Continue on another device", async () => {
      const url = `${inviteUrl()}?me=${S.token}`;
      const ok = await copyText(url);
      toast(ok ? "Personal link copied — open it on your other device (don't share it!)" : url, !ok);
    }),
    item("✏️ Change my name", async () => {
      const name = await askName("Change your name", true);
      if (name) send({ type: "rename", name });
    }),
    isHost && st?.status !== "lobby"
      ? item("⏹ End game, back to lobby", () => {
          if (confirm("End the current game for everyone?")) send({ type: "to_lobby" });
        })
      : null,
    item("🚪 Leave table", leaveTable),
  );
}

document.addEventListener("click", (e) => {
  if (S.ui.menu && !e.target.closest(".menu") && !e.target.closest('[title="Menu"]')) {
    S.ui.menu = false;
    renderTop();
  }
});

function leaveTable() {
  S.ui.menu = false;
  document.getElementById("menu")?.remove();
  closeSocket();
  go("/");
}

function inviteUrl() {
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  const base = S.config.public_url || (local && S.config.lan_url) || location.origin;
  return `${base.replace(/\/$/, "")}/r/${S.code}`;
}

async function copyCode() {
  const ok = await copyText(S.code);
  toast(ok ? `Table code ${S.code} copied` : `Table code: ${S.code}`, !ok);
}

async function copyInvite() {
  const ok = await copyText(inviteUrl());
  toast(ok ? "Invite link copied — send it to your friends!" : inviteUrl(), !ok);
}

// ------------------------------------------------------------------ dialogs
function askName(title, dismissable = false) {
  return new Promise((resolve) => {
    const suggestion = S.name || suggestName();
    const input = h("input", { class: "text", value: S.name, placeholder: suggestion, maxlength: 20, style: { width: "100%" } });
    let close = null;
    const done = (e) => {
      e?.preventDefault();
      const name = saveName(input.value || suggestion);
      close();
      resolve(name);
    };
    close = openDialog(
      h(
        "div",
        { class: "modal" },
        h("h2", {}, title),
        h("p", { class: "sub" }, "Pick a name the other players will see."),
        h("form", { onsubmit: done }, input, h("div", { class: "actions" }, h("button", { class: "btn primary", type: "submit" }, "All aboard!"))),
      ),
      { dismissable, onClose: () => resolve(null) },
    );
    input.focus();
  });
}

function showRules() {
  let close = null;
  const pts = [
    [1, 1],
    [2, 2],
    [3, 4],
    [4, 7],
    [6, 15],
    [8, 21],
  ];
  close = openDialog(
    h(
      "div",
      { class: "modal wide rules" },
      h("h2", {}, "How to play Ticket to Ride: Europe"),
      h(
        "div",
        { class: "rules-text" },
        h("p", {}, h("b", {}, "Goal: "), "score the most points by claiming railway routes, connecting the cities on your destination tickets and building the longest continuous railway."),
        h("h4", {}, "Setup"),
        h("ul", {}, h("li", {}, "Everyone starts with 45 trains, 3 stations and 4 train cards."), h("li", {}, "You get 1 long and 3 regular destination tickets and keep at least 2. Returned long tickets leave the game.")),
        h("h4", {}, "On your turn, do exactly one of"),
        h(
          "ul",
          {},
          h("li", {}, h("b", {}, "Draw 2 train cards"), " — from the 5 face-up cards or blind from the deck. A face-up ", chip("loco"), " locomotive counts as both cards (and can't be your second card). Locomotives are wild."),
          h("li", {}, h("b", {}, "Claim a route"), " — play as many cards of the route's colour as it has spaces. Gray routes take any one colour. Click a route on the map."),
          h("li", {}, h("b", {}, "Draw 3 destination tickets"), " and keep at least 1."),
          h("li", {}, h("b", {}, "Build a station"), " in a city without one: the 1st costs 1 card, the 2nd 2, the 3rd 3 (one colour). Click a city on the map."),
        ),
        h("h4", {}, "Special routes"),
        h(
          "ul",
          {},
          h("li", {}, h("b", {}, "Tunnels"), " (dark dashed border): after you play the cards, 3 cards are turned from the deck. Each one matching your colour — or a locomotive — costs one extra card. Pay it or give up (you keep your cards)."),
          h("li", {}, h("b", {}, "Ferries"), " (spaces with a locomotive symbol): need at least that many locomotives."),
          h("li", {}, h("b", {}, "Double routes"), ": one player can't take both tracks; with 2–3 players only one track can be used."),
        ),
        h("h4", {}, "Scoring"),
        h("div", { class: "score-legend" }, pts.map(([l, p]) => h("span", {}, h("b", {}, l), " 🚃 → ", h("b", {}, p), " pts"))),
        h(
          "ul",
          {},
          h("li", {}, "Completed tickets add their value, unfinished ones subtract it."),
          h("li", {}, "Each station lets you use one route of another player into its city (for your tickets only, not the longest route). The route is chosen at the end of the game — automatically the one that scores you the most. Each unused station is worth 4 points."),
          h("li", {}, "The ", h("b", {}, "European Express"), " bonus (10 points) goes to the longest continuous path."),
          h("li", {}, "When a player ends a turn with 2 or fewer trains, everyone — including them — plays one last turn."),
        ),
        h("h4", {}, "Controls"),
        h(
          "ul",
          {},
          h("li", {}, "Click face-up cards or the deck to draw; click a route or a city to build. Hover your cards to see where you can build with them."),
          h("li", {}, "Scroll or pinch to zoom the map, drag to pan. Keys: ", h("b", {}, "D"), " deck, ", h("b", {}, "1–5"), " face-up cards, ", h("b", {}, "T"), " tickets, ", h("b", {}, "H"), " hint, ", h("b", {}, "0"), " reset zoom."),
        ),
      ),
      h("div", { class: "actions" }, h("button", { class: "btn primary", onclick: () => close() }, "Got it")),
    ),
  );
}

function showScores() {
  const st = S.state;
  if (!st?.game) return;
  let close = null;
  close = openDialog(
    h(
      "div",
      { class: "modal wide" },
      h("h2", {}, st.game.result ? "Final scores" : "Scoreboard"),
      st.game.result ? resultTable(st) : liveTable(st),
      h("div", { class: "actions" }, h("button", { class: "btn primary", onclick: () => close() }, "Close")),
    ),
  );
}

function liveTable(st) {
  const g = st.game;
  return h(
    "table",
    { class: "scores" },
    h("thead", {}, h("tr", {}, ["Player", "Route points", "Trains", "Routes", "Longest", "Stations", "Cards", "Tickets"].map((t) => h("th", {}, t)))),
    h(
      "tbody",
      {},
      g.players.map((p, seat) =>
        h(
          "tr",
          {},
          h("td", { class: "pl" }, swatch(st, seat), st.seats[seat].name, seat === st.you.seat ? " (you)" : ""),
          h("td", {}, p.points),
          h("td", {}, p.trains),
          h("td", {}, p.routes),
          h("td", {}, p.longest),
          h("td", {}, 3 - p.stations.length),
          h("td", {}, p.hand),
          h("td", {}, p.tickets),
        ),
      ),
    ),
  );
}

function resultTable(st) {
  const g = st.game;
  const res = g.result;
  const rows = [
    ["Routes", (r) => r.route_points],
    ["Tickets", (r) => (r.ticket_points >= 0 ? `+${r.ticket_points}` : r.ticket_points)],
    ["Stations", (r) => (r.station_points ? `+${r.station_points}` : "0")],
    ["European Express", (r) => (r.express ? `+${r.express_points} (${r.longest})` : `— (${r.longest})`)],
  ];
  return h(
    "div",
    { class: "scores-wrap" },
    h(
      "table",
      { class: "scores result" },
      h("thead", {}, h("tr", {}, h("th", {}, ""), st.seats.map((s, i) => h("th", { class: res.winners.includes(i) ? "win" : "" }, swatch(st, i), s.name)))),
      h(
        "tbody",
        {},
        rows.map(([label, fn]) => h("tr", {}, h("td", { class: "pl" }, label), res.players.map((r) => h("td", {}, fn(r))))),
        h("tr", { class: "total-row" }, h("td", { class: "pl" }, "Total"), res.players.map((r, i) => h("td", { class: res.winners.includes(i) ? "win" : "" }, r.total))),
      ),
    ),
    h(
      "div",
      { class: "result-tickets" },
      res.players.map((r, seat) =>
        h(
          "div",
          { class: "rt-col" },
          h("div", { class: "rt-head" }, swatch(st, seat), st.seats[seat].name),
          r.tickets.map((t) => {
            const tk = ticket(t.id);
            return h("div", { class: `rt ${t.done ? "ok" : "fail"}` }, h("span", {}, t.done ? "✓" : "✗"), ` ${tk.a} – ${tk.b} `, h("b", {}, t.done ? `+${tk.value}` : `−${tk.value}`));
          }),
          Object.entries(r.borrowed || {}).map(([city, rid]) => {
            const used = rid == null ? null : route(rid);
            return h("div", { class: "rt station-use" }, h("span", {}, "🏠"), ` ${city}: `, used ? `uses ${used.a} – ${used.b}` : "no route needed");
          }),
        ),
      ),
    ),
  );
}

function swatch(st, seat) {
  const [light, dark] = PLAYER_FILL[seatColor(st, seat)];
  return h("span", { class: "swatch", style: { background: light, borderColor: dark } });
}

// ------------------------------------------------------------------ rendering
function render(opts = {}) {
  renderTop();
  const st = S.state;
  const main = $("#main");
  if (!st || !main) return;
  if (st.status === "lobby") {
    renderPlayers(st);
    renderLobby(st, main);
  } else renderGame(st, main, opts);
  renderOverlay();
}

function avatar(st, seat, s, online) {
  const label = s.bot ? "🤖" : (s.name || "?").trim().charAt(0).toUpperCase();
  const [light, dark] = PLAYER_FILL[s.color || "black"];
  return h("span", { class: `avatar ${s.bot ? "" : online ? "online" : "offline"}`, style: { background: `linear-gradient(180deg, ${light}, ${dark})` } }, label);
}

const botInfo = (key) => S.bots.find((b) => b.key === key);

function renderLobby(st, main) {
  S.board = null;
  const isHost = st.host === S.me;
  const mySeat = st.you.seat;
  const n = st.seats.length;
  const hostName = st.seats.find((s) => s.member === st.host)?.name || st.spectators.find((s) => s.member === st.host)?.name || "the host";
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  let note = null;
  if (!S.config.public_url) {
    if (local && !S.config.lan_url) note = "This link only works on this computer. Restart with `uv run ttr serve --tunnel` to invite people over the internet.";
    else if (!location.hostname.endsWith("trycloudflare.com")) note = "Works for people on the same network. For friends elsewhere, run `uv run ttr serve --tunnel`.";
  }
  const linkInput = h("input", { class: "text", readonly: true, value: inviteUrl(), onclick: (e) => e.target.select() });
  const invite = h(
    "div",
    { class: "invite" },
    h("div", {}, h("h2", {}, "Invite friends"), h("p", {}, "Anyone who opens the link joins this table. Fill the remaining seats with bots (2–5 players)."), note ? h("p", { class: "note" }, "ℹ️ ", note) : null),
    h(
      "div",
      { class: "link-box" },
      linkInput,
      h("button", { class: "btn primary", onclick: copyInvite }, "Copy link"),
      navigator.share ? h("button", { class: "btn", onclick: () => navigator.share({ title: "Play Ticket to Ride with me", url: inviteUrl() }).catch(() => {}) }, "Share") : null,
    ),
  );
  const seatRows = st.seats.map((s, i) => {
    const bot = s.bot ? botInfo(s.bot) : null;
    const isMe = i === mySeat;
    return h(
      "div",
      { class: "seat-row" },
      avatar(st, i, s, s.connected),
      h("span", { class: "name" }, s.name),
      h("span", { class: "train-swatch", title: `${COLOR_NAMES[s.color] || s.color} trains`, style: { background: PLAYER_FILL[s.color][0] } }),
      s.member === st.host ? h("span", { class: "tag host" }, "Host") : null,
      isMe ? h("span", { class: "tag you" }, "You") : null,
      bot ? h("span", { class: "tag", title: bot.description }, "★".repeat(bot.stars)) : null,
      !s.bot && !s.connected ? h("span", { class: "tag" }, "offline") : null,
      isMe ? h("button", { class: "icon-btn", title: "Leave seat (watch instead)", onclick: () => send({ type: "stand" }) }, "⏏") : null,
      isHost && !isMe ? h("button", { class: "icon-btn", title: "Remove", onclick: () => send({ type: "remove_seat", seat: i }) }, "✕") : null,
    );
  });
  if (n < MAX_SEATS) seatRows.push(h("div", { class: "seat-empty" }, `${MAX_SEATS - n} empty seat${MAX_SEATS - n === 1 ? "" : "s"} — invite someone or add a bot`));
  const spectators = st.spectators.filter((s) => s.connected);
  const seatsPanel = h(
    "div",
    { class: "panel" },
    h("h3", {}, "Players", h("small", {}, `${n} / ${MAX_SEATS}`)),
    h("div", { class: "seat-list" }, seatRows),
    spectators.length ? h("p", { class: "waiting" }, "Watching: ", spectators.map((s) => s.name).join(", ")) : null,
    mySeat == null && n < MAX_SEATS ? h("div", { style: { marginTop: "10px" } }, h("button", { class: "btn primary", onclick: () => send({ type: "sit" }) }, "Take a seat")) : null,
  );
  const botsPanel = h(
    "div",
    { class: "panel" },
    h("h3", {}, "Add a bot", isHost ? null : h("small", {}, "host only")),
    h(
      "div",
      { class: "bot-grid" },
      S.bots.map((b) =>
        h(
          "button",
          { class: "bot-btn", disabled: !isHost || n >= MAX_SEATS, title: b.description, onclick: () => send({ type: "add_bot", bot: b.key }) },
          h("span", { class: "bname" }, b.label),
          h("span", { class: "stars" }, "★".repeat(b.stars), h("span", { style: { opacity: 0.3 } }, "★".repeat(5 - b.stars))),
          h("span", { class: "bdesc" }, b.description),
        ),
      ),
    ),
  );
  const set = st.settings;
  const change = (k, v) => send({ type: "settings", changes: { [k]: v } });
  const select = (k, options) =>
    h(
      "select",
      { class: "select", disabled: !isHost, onchange: (e) => change(k, isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value)) },
      options.map(([value, label]) => {
        const opt = h("option", { value }, label);
        opt.selected = String(set[k]) === String(value);
        return opt;
      }),
    );
  const toggle = (k) => {
    const input = h("input", { type: "checkbox", disabled: !isHost, onchange: (e) => change(k, e.target.checked) });
    input.checked = !!set[k];
    return h("label", { class: "switch" }, input, h("span"));
  };
  const row = (label, help, control) => h("div", { class: "setting" }, h("span", { class: "label" }, label, h("small", {}, help)), control);
  const settingsPanel = h(
    "div",
    { class: "panel" },
    h("h3", {}, "Table rules", isHost ? null : h("small", {}, "set by the host")),
    h(
      "div",
      { class: "settings" },
      row("Turn timer", "The autopilot moves when time runs out", select("turn_timer", [[0, "Off"], [30, "30 s"], [60, "1 min"], [90, "90 s"], [180, "3 min"]])),
      row("Bot speed", "How fast bots play their moves", select("bot_speed", [["slow", "Relaxed"], ["normal", "Normal"], ["fast", "Fast"]])),
      row("Hints", "Players may ask the Expert bot for advice", toggle("hints")),
      row("Both double tracks", "House rule: use both tracks of double routes with 2–3 players", toggle("doubles_all")),
    ),
  );
  const actions = isHost
    ? h(
        "div",
        { class: "lobby-actions" },
        h("button", { class: "btn", disabled: n < 2, onclick: () => send({ type: "shuffle" }) }, "🔀 Shuffle seats"),
        h("button", { class: "btn primary big", disabled: n < 2, onclick: () => send({ type: "start" }) }, n < 2 ? "Need 2+ players" : `🚂 Start game · ${n} players`),
      )
    : h("div", { class: "lobby-actions" }, h("span", { class: "waiting" }, `Waiting for ${hostName} to start the game…`));
  main.replaceChildren(h("section", { class: "lobby" }, invite, h("div", { class: "lobby-grid" }, seatsPanel, botsPanel, settingsPanel), actions));
}

// ------------------------------------------------------------------ game view
function ensureBoard(st, main) {
  if (S.board && main.querySelector(".game")) return;
  if (!S.board) {
    S.board = new Board(S.map, S.land, { onRoute: onRouteClick, onCity: onCityClick, onHover: onBoardHover });
  }
  const zoom = h(
    "div",
    { class: "zoom" },
    h("button", { class: "icon-btn", title: "Zoom in", onclick: () => S.board.zoomAt(1.4) }, "+"),
    h("button", { class: "icon-btn", title: "Zoom out", onclick: () => S.board.zoomAt(1 / 1.4) }, "−"),
    h("button", { class: "icon-btn", title: "Whole map (0)", onclick: () => S.board.resetView() }, "⤢"),
  );
  main.replaceChildren(
    h(
      "section",
      { class: "game" },
      h("div", { class: "board-wrap", id: "board-wrap" }, S.board.el, zoom, h("div", { class: "status", id: "status" }), h("div", { id: "panel" })),
      h("div", { class: "market", id: "market" }),
      h("div", { class: "dock", id: "dock" }),
    ),
  );
}

function renderGame(st, main, opts) {
  ensureBoard(st, main);
  const g = st.game;
  S.board.update(g, st.seats, { freshRoute: opts.freshRoute });
  renderBoardHighlights(st);
  renderPlayers(st);
  renderMarket(st);
  renderDock(st);
  renderStatus(st);
  renderPanel(st);
}

function myColorRoutes(st, color) {
  const out = new Set();
  const claimable = st.game.me?.claimable || {};
  for (const [rid, opts] of Object.entries(claimable)) {
    if (opts.some(([c, l]) => c === color || (color === "loco" && (c === null || l > 0)))) out.add(rid);
  }
  return out;
}

function renderBoardHighlights(st) {
  const g = st.game;
  const me = g.me;
  const routes = {};
  const cities = {};
  const ui = S.ui;
  if (me?.my_turn && g.phase === "turn") {
    if (ui.handColor) for (const rid of myColorRoutes(st, ui.handColor)) routes[rid] = "claimable";
    else if (ui.showClaimable) for (const rid of Object.keys(me.claimable)) routes[rid] = "claimable";
  }
  if (g.tunnel) routes[g.tunnel.route] = "focus";
  const hint = ui.hint;
  if (hint?.type === "claim") routes[hint.route] = "hint";
  const focus = ui.hover?.ticket != null ? [ui.hover.ticket] : [];
  for (const tid of [...ui.pinned, ...focus]) {
    const t = ticket(tid);
    if (!t) continue;
    cities[t.a] = "hl";
    cities[t.b] = "hl";
  }
  if (hint?.type === "station") cities[hint.city] = "hint";
  S.board.setRouteClasses(routes);
  S.board.setCityClasses(cities);
  S.board.setDim(ui.focusSeat);
}

function renderPlayers(st) {
  const box = $("#players");
  if (!box) return;
  const g = st.game;
  if (!g || st.status === "lobby") {
    box.replaceChildren();
    return;
  }
  const isHost = st.host === S.me;
  box.replaceChildren(
    ...st.seats.map((s, seat) => {
      const p = g.players[seat];
      const current = g.current === seat;
      const bot = s.bot ? botInfo(s.bot) : null;
      const badges = [];
      if (bot && !s.name.startsWith(bot.label)) badges.push(bot.label);
      if (s.autoplay) badges.push("autopilot");
      if (!s.bot && !s.connected) badges.push("offline");
      const lead = Math.max(...g.players.map((q) => q.longest));
      const takeOver =
        isHost && st.status === "playing" && !s.bot && !s.connected && !s.autoplay
          ? h("button", { class: "btn small", onclick: () => send({ type: "autoplay", seat, on: true }) }, "🤖 Let a bot play")
          : null;
      const flag = current ? (g.final_turns != null ? "Last turn" : "Playing") : p.choosing ? "Choosing tickets" : null;
      return h(
        "div",
        {
          class: `pl-row ${current ? "current" : ""} ${S.ui.focusSeat === seat ? "focus" : ""}`,
          "data-seat": seat,
          title: "Click to highlight this player's routes",
          onclick: () => {
            S.ui.focusSeat = S.ui.focusSeat === seat ? null : seat;
            render();
          },
        },
        h(
          "div",
          { class: "pl-top" },
          avatar(st, seat, s, s.connected),
          h("span", { class: "pl-name" }, s.name, seat === st.you.seat ? h("small", {}, " (you)") : null),
          badges.length ? h("span", { class: "pbadge" }, badges.join(" · ")) : null,
          flag ? h("span", { class: `turn-flag ${g.final_turns != null && current ? "last" : ""}` }, flag) : null,
          g.result
            ? h("span", { class: "pl-score", title: "Final score" }, g.result.players[seat].total)
            : h("span", { class: "pl-score", title: "Route points so far (tickets are scored at the end)" }, p.points),
        ),
        h(
          "div",
          { class: "pl-stats" },
          h("span", { title: "Trains left", class: p.trains <= 6 ? "warn" : "" }, "🚃 ", p.trains),
          h("span", { title: "Train cards in hand" }, "🂠 ", p.hand),
          h("span", { title: "Destination tickets" }, "🎫 ", p.tickets),
          h("span", { title: "Stations left" }, "🏠 ", 3 - p.stations.length),
          h("span", { title: "Longest continuous path", class: p.longest && p.longest === lead ? "lead" : "" }, "⟿ ", p.longest),
        ),
        takeOver,
      );
    }),
  );
}

function renderMarket(st) {
  const box = $("#market");
  if (!box) return;
  const g = st.game;
  const me = g.me;
  const myTurn = me?.my_turn && !S.ui.pending;
  const hint = S.ui.hint;
  const ticketPile = h(
    "div",
    {
      class: `pile tickets-pile ${myTurn && me.can_tickets ? "clickable" : ""} ${hint?.type === "draw_tickets" ? "hint" : ""}`,
      "data-fly": "tickets",
      title: "Draw 3 destination tickets (T)",
      onclick: () => myTurn && me.can_tickets && act({ type: "draw_tickets" }),
    },
    g.tickets_left ? ticketBack() : h("div", { class: "ticket empty" }, "empty"),
    h("span", { class: "plabel" }, `Destination tickets · ${g.tickets_left}`),
  );
  const faceUp = g.face_up.map((c, i) => {
    const ok = myTurn && me.face_up_ok[i];
    const cls = `${ok ? "clickable" : ""} ${hint?.type === "draw_card" && hint.slot === i ? "hint" : ""} ${myTurn && !me.face_up_ok[i] && c ? "blocked" : ""}`;
    if (!c) return h("div", { class: "tcard empty", "data-fly": `fu-${i}` });
    return trainCard(c, { cls, "data-fly": `fu-${i}`, onclick: () => ok && act({ type: "draw_card", slot: i }) });
  });
  const canBlind = myTurn && me.can_blind;
  const deck = h(
    "div",
    {
      class: `pile deck-pile ${canBlind ? "clickable" : ""} ${hint?.type === "draw_card" && hint.slot == null ? "hint" : ""}`,
      "data-fly": "deck",
      title: "Draw from the deck (D)",
      onclick: () => canBlind && act({ type: "draw_card", slot: null }),
    },
    g.deck ? h("div", { class: "deck-stack" }, cardBack(), cardBack(), cardBack()) : h("div", { class: "tcard empty" }, "empty"),
    h("span", { class: "plabel" }, `Deck · ${g.deck}`, g.discard ? h("small", {}, ` · discard ${g.discard}`) : null),
  );
  box.replaceChildren(deck, h("div", { class: "face-up" }, faceUp), ticketPile);
}

function renderDock(st) {
  const box = $("#dock");
  if (!box) return;
  const g = st.game;
  const me = g.me;
  if (!me) {
    box.replaceChildren(h("div", { class: "watching" }, "👀 You're watching this game. You'll get a seat when the host returns to the lobby."));
    return;
  }
  const cards = CARD_ORDER.filter((c) => me.hand[c]).map((c) =>
    trainCard(c, {
      count: me.hand[c],
      cls: S.ui.handColor === c ? "active" : "",
      onpointerenter: () => {
        S.ui.handColor = c;
        renderBoardHighlights(st);
      },
      onpointerleave: () => {
        S.ui.handColor = null;
        renderBoardHighlights(st);
      },
    }),
  );
  const total = Object.values(me.hand).reduce((a, b) => a + b, 0);
  const hand = h(
    "div",
    { class: `hand ${cards.length > 4 ? "two-rows" : ""}`, style: { "--cols": Math.ceil(cards.length / 2) } },
    cards.length ? cards : h("span", { class: "empty-note" }, "No train cards yet"),
  );
  const tickets = me.tickets.map((t) =>
    ticketCard(ticket(t.id), S.cityPos, {
      done: t.done,
      cls: S.ui.pinned.has(t.id) ? "pinned" : "",
      title: `${ticket(t.id).a} – ${ticket(t.id).b} · ${ticket(t.id).value} points${t.done ? " · completed" : ""} (click to pin on the map)`,
      onpointerenter: () => {
        S.ui.hover = { ticket: t.id };
        renderBoardHighlights(st);
      },
      onpointerleave: () => {
        S.ui.hover = null;
        renderBoardHighlights(st);
      },
      onclick: () => {
        if (S.ui.pinned.has(t.id)) S.ui.pinned.delete(t.id);
        else S.ui.pinned.add(t.id);
        render();
      },
    }),
  );
  // Offered tickets while the chooser is hidden: still visible (and hoverable) here, framed as undecided.
  const pending =
    me.offer.length && S.ui.offerHidden
      ? me.offer.map((tid) =>
          h(
            "div",
            { class: "offered-wrap", title: "Not chosen yet — click to choose your tickets" },
            ticketCard(ticket(tid), S.cityPos, {
              cls: S.ui.selected.has(tid) ? "offered picked" : "offered",
              onpointerenter: () => {
                S.ui.hover = { ticket: tid };
                renderBoardHighlights(st);
              },
              onpointerleave: () => {
                S.ui.hover = null;
                renderBoardHighlights(st);
              },
              onclick: () => {
                S.ui.offerHidden = false;
                S.ui.hover = null;
                render();
              },
            }),
          ),
        )
      : [];
  const doneValue = me.tickets.filter((t) => t.done).reduce((a, t) => a + ticket(t.id).value, 0);
  const openValue = me.tickets.filter((t) => !t.done).reduce((a, t) => a + ticket(t.id).value, 0);
  const myTurn = me.my_turn && !S.ui.pending;
  const tools = h(
    "div",
    { class: "tools" },
    st.settings.hints && st.status === "playing" && (myTurn || me.offer.length)
      ? h("button", { class: "btn small", title: "Ask the Expert bot (H)", onclick: () => send({ type: "hint" }) }, "💡 Hint")
      : null,
    h(
      "label",
      { class: "check", title: "Glow routes you can claim right now" },
      h("input", {
        type: "checkbox",
        checked: S.ui.showClaimable,
        onchange: (e) => {
          S.ui.showClaimable = e.target.checked;
          localStorage.setItem("ttr.showClaimable", e.target.checked ? "1" : "0");
          renderBoardHighlights(st);
        },
      }),
      " show claimable",
    ),
    myTurn && me.can_pass ? h("button", { class: "btn small", onclick: () => act({ type: "pass" }) }, "Pass") : null,
  );
  box.replaceChildren(
    h("div", { class: "dock-sec hand-sec" }, h("div", { class: "dock-title" }, `Your train cards · ${total}`), hand),
    h(
      "div",
      { class: "dock-sec tickets-sec" },
      h(
        "div",
        { class: "dock-title" },
        `Your tickets · `,
        h("span", { class: "ok" }, `✓ ${doneValue}`),
        " ",
        h("span", { class: "bad" }, `○ ${openValue}`),
        pending.length ? h("span", { class: "pending-note" }, ` · ⚠ choose at least ${me.offer_min} of the framed ones`) : null,
      ),
      h("div", { class: "my-tickets" }, pending, tickets.length || pending.length ? tickets : h("span", { class: "empty-note" }, "No tickets yet")),
    ),
    tools,
  );
}

function statusText(st) {
  const g = st.game;
  const me = g.me;
  const mySeat = st.you.seat;
  if (st.status === "game_over") return { parts: ["🏁 Game over"] };
  if (g.phase === "initial_tickets") {
    if (me?.offer.length) return { mine: true, parts: [`Choose your destination tickets — keep at least ${me.offer_min}`] };
    const waiting = st.seats.filter((_, i) => g.players[i].choosing).map((s) => s.name);
    return { parts: [`Waiting for ${waiting.join(", ")} to choose tickets…`] };
  }
  const cur = g.current;
  const name = st.seats[cur]?.name;
  let final = null;
  if (g.final_turns != null) final = cur === mySeat ? "⚠️ Your last turn!" : `🏁 Last round — ${plural(g.final_turns, "turn")} left`;
  if (me?.my_turn) {
    switch (g.phase) {
      case "turn":
        return { mine: true, final, parts: ["Your turn — draw 2 cards, claim a route, draw tickets or build a station"] };
      case "second_card":
        return { mine: true, final, parts: ["Draw your second card (not a face-up locomotive)"] };
      case "choose_tickets":
        return { mine: true, final, parts: [`Keep at least ${me.offer_min} of the new tickets`] };
      case "tunnel":
        return { mine: true, final, parts: ["Tunnel! Pay the extra cards or give up"] };
    }
  }
  const who = st.seats[cur]?.bot ? `${name} 🤖` : name;
  const doing = { turn: "is thinking…", second_card: "is drawing a second card…", choose_tickets: "is choosing tickets…", tunnel: "is digging a tunnel…" }[g.phase];
  return { final, parts: [`${who} ${doing || ""}`] };
}

function renderStatus(st) {
  const box = $("#status");
  if (!box) return;
  const info = statusText(st);
  const g = st.game;
  const cur = g.current;
  const dot = cur != null ? h("span", { class: "swatch", style: { background: PLAYER_FILL[seatColor(st, cur)][0] } }) : null;
  box.className = `status ${info.mine ? "mine" : ""} ${info.final ? "final" : ""}`;
  box.replaceChildren(
    ...[
      info.final ? h("span", { class: "beacon", "aria-hidden": "true" }) : null,
      info.final ? h("span", { class: "final-banner" }, info.final) : null,
      h("span", { class: "stext" }, dot, info.parts),
      info.final ? h("span", { class: "beacon", "aria-hidden": "true" }) : null,
      h("div", { class: "timer", id: "timer", style: { width: "0" } }),
    ].filter(Boolean),
  );
}

// Panels over the map: ticket choice and tunnel resolution.
function renderPanel(st) {
  const box = $("#panel");
  if (!box) return;
  const g = st.game;
  const me = g.me;
  if (st.status === "playing" && me?.offer.length && !S.ui.pending) {
    const key = `${me.offer.join(",")}|${S.ui.offerHidden ? "hidden" : "open"}`;
    const current = box.firstElementChild;
    if (current?.dataset.offer === key) syncChooser(current, me);
    else box.replaceChildren(ticketChooser(st, key));
    return;
  }
  if (g.tunnel && st.status === "playing") {
    box.replaceChildren(tunnelPanel(st));
    return;
  }
  box.replaceChildren();
}

// Selecting tickets only touches the affected classes and the button: rebuilding would replay the panel animation.
function syncChooser(panel, me) {
  const sel = S.ui.selected;
  for (const el of panel.querySelectorAll(".ticket.choice")) el.classList.toggle("selected", sel.has(Number(el.dataset.ticket)));
  const keep = panel.querySelector(".keep-btn");
  if (!keep) return;
  const enough = sel.size >= me.offer_min;
  keep.disabled = !enough;
  keep.textContent = enough ? `Keep ${plural(sel.size, "ticket")}` : `Select ${me.offer_min - sel.size} more`;
}

function ticketChooser(st, key) {
  const g = st.game;
  const me = g.me;
  if (S.ui.offerHidden) {
    return h(
      "div",
      { class: "panel-mini", "data-offer": key },
      "🎫 Choose your tickets",
      h("button", { class: "btn small primary", onclick: () => ((S.ui.offerHidden = false), render()) }, "Show"),
    );
  }
  const sel = S.ui.selected;
  const enough = sel.size >= me.offer_min;
  const cards = me.offer.map((tid) =>
    ticketCard(ticket(tid), S.cityPos, {
      cls: `choice ${sel.has(tid) ? "selected" : ""}`,
      onclick: (e) => {
        if (S.ui.selected.has(tid)) S.ui.selected.delete(tid);
        else S.ui.selected.add(tid);
        syncChooser(e.currentTarget.closest(".tickets-panel"), me);
      },
      onpointerenter: () => {
        S.ui.hover = { ticket: tid };
        renderBoardHighlights(st);
      },
      onpointerleave: () => {
        S.ui.hover = null;
        renderBoardHighlights(st);
      },
    }),
  );
  const initial = g.phase === "initial_tickets";
  return h(
    "div",
    { class: "float-panel tickets-panel", "data-offer": key },
    h("h3", {}, initial ? "Your first destination tickets" : "New destination tickets"),
    h("p", { class: "sub" }, `Click to select. Keep at least ${me.offer_min}. Completed tickets score their value, unfinished ones lose it.${initial ? " The blue one is a long route." : ""}`),
    h("div", { class: "offer" }, cards),
    h(
      "div",
      { class: "actions" },
      h("button", { class: "btn ghost small", onclick: () => ((S.ui.offerHidden = true), render()) }, "👀 Look at the map"),
      h(
        "button",
        {
          class: "btn small",
          onclick: (e) => {
            S.ui.selected = new Set(me.offer);
            syncChooser(e.currentTarget.closest(".tickets-panel"), me);
          },
        },
        "Select all",
      ),
      h(
        "button",
        { class: "btn primary keep-btn", disabled: !enough, onclick: () => act({ type: "keep_tickets", tickets: [...S.ui.selected] }) },
        enough ? `Keep ${plural(sel.size, "ticket")}` : `Select ${me.offer_min - sel.size} more`,
      ),
    ),
  );
}

function tunnelPanel(st) {
  const g = st.game;
  const t = g.tunnel;
  const r = route(t.route);
  const me = g.me;
  const mine = t.seat === st.you.seat && me?.my_turn;
  const colorName = t.color ? COLOR_NAMES[t.color].toLowerCase() : null;
  const revealed = h("div", { class: "revealed" }, t.revealed.map((c, i) => trainCard(c, { cls: `reveal ${c === "loco" || c === t.color ? "match" : ""}`, style: { "--i": i } })));
  const need = t.extra ? `${plural(t.extra, "extra card")} needed (${colorName ? `${colorName} or locomotive` : "locomotives"})` : "No extra cards needed";
  const options = mine
    ? me.tunnel_options.map((locos) =>
        h("button", { class: "btn primary", onclick: () => act({ type: "tunnel_pay", locos }) }, "Pay ", paymentChips(t.extra, t.color, locos)),
      )
    : [];
  return h(
    "div",
    { class: "float-panel tunnel-panel" },
    h("h3", {}, `⛰ Tunnel ${r.a} – ${r.b}`),
    h("p", { class: "sub" }, mine ? `${plural(t.revealed.length, "card")} turned from the deck:` : `${st.seats[t.seat].name} turned ${plural(t.revealed.length, "card")}:`),
    revealed,
    h("p", { class: "need" }, need),
    mine
      ? h(
          "div",
          { class: "actions" },
          options.length ? null : h("span", { class: "grow" }, "You can't pay — you get your cards back."),
          h("button", { class: "btn", onclick: () => act({ type: "tunnel_decline" }) }, "Give up the route"),
          options,
        )
      : null,
  );
}

// ------------------------------------------------------------------ board interaction
let popoverEl = null;

function closePopover() {
  popoverEl?.remove();
  popoverEl = null;
}

function openPopover(x, y, content) {
  closePopover();
  popoverEl = h("div", { class: "popover" }, h("button", { class: "icon-btn close", onclick: closePopover, title: "Close" }, "✕"), content);
  document.body.append(popoverEl);
  const r = popoverEl.getBoundingClientRect();
  const left = Math.min(innerWidth - r.width - 8, Math.max(8, x - r.width / 2));
  const top = y - r.height - 16 > 60 ? y - r.height - 16 : Math.min(innerHeight - r.height - 8, y + 18);
  popoverEl.style.left = `${left}px`;
  popoverEl.style.top = `${top}px`;
}

document.addEventListener("pointerdown", (e) => {
  if (popoverEl && !e.target.closest(".popover") && !e.target.closest(".route") && !e.target.closest(".city")) closePopover();
});

function routeMeta(r) {
  const bits = [`${r.length} ${r.length === 1 ? "space" : "spaces"}`, r.color ? COLOR_NAMES[r.color] : "Gray (any one colour)", `${r.points} points`];
  if (r.tunnel) bits.push("⛰ tunnel");
  if (r.ferry) bits.push(`⛴ ferry · ${plural(r.ferry, "locomotive")} required`);
  return bits.join(" · ");
}

function routeBlocker(st, r) {
  const g = st.game;
  const owner = g.owners[r.id];
  if (owner != null) return `Claimed by ${st.seats[owner].name}`;
  const twin = r.twin != null ? g.owners[r.twin] : undefined;
  if (twin != null) {
    if (twin === st.you.seat) return "You already own the other track of this double route";
    if (st.seats.length < g.double_min_players) return `With ${st.seats.length} players only one track of a double route can be used`;
  }
  const me = g.me;
  if (!me) return null;
  if (!me.my_turn) return "Wait for your turn";
  if (g.phase !== "turn") return "Finish your current action first";
  if (g.players[st.you.seat].trains < r.length) return "Not enough trains left";
  const color = r.color ? `${r.length} ${COLOR_NAMES[r.color].toLowerCase()}` : `${r.length} cards of one colour`;
  return `You need ${color}${r.ferry ? ` including ${plural(r.ferry, "locomotive")}` : ""} (locomotives are wild)`;
}

function onRouteClick(rid, e) {
  const st = S.state;
  if (!st?.game) return;
  const r = route(rid);
  if (r.tunnel) sfx.tunnel();
  const me = st.game.me;
  const options = me?.my_turn && !S.ui.pending ? me.claimable[rid] : null;
  const title = h("h4", {}, `${r.a} – ${r.b}`);
  const meta = h("p", { class: "meta" }, routeMeta(r));
  if (!options) {
    openPopover(e.clientX, e.clientY, h("div", {}, title, meta, h("p", { class: "why" }, routeBlocker(st, r))));
    return;
  }
  const buttons = options.map(([color, locos]) =>
    h("button", { class: "btn pay", onclick: () => act({ type: "claim", route: rid, color, locos }) }, paymentChips(r.length, color, locos)),
  );
  openPopover(
    e.clientX,
    e.clientY,
    h(
      "div",
      {},
      title,
      meta,
      r.tunnel ? h("p", { class: "why" }, "Tunnel: 3 cards will be turned and may cost extra cards.") : null,
      h("p", { class: "label" }, "Pay with:"),
      h("div", { class: "pay-list" }, buttons),
    ),
  );
}

function onCityClick(name, e) {
  const st = S.state;
  if (!st?.game) return;
  const g = st.game;
  const me = g.me;
  const owner = g.stations[name];
  const myTickets = me ? me.tickets.filter((t) => ticket(t.id).a === name || ticket(t.id).b === name) : [];
  const parts = [h("h4", {}, name)];
  if (myTickets.length) parts.push(h("p", { class: "meta" }, "Your tickets: ", myTickets.map((t) => `${ticket(t.id).a}–${ticket(t.id).b}`).join(", ")));
  if (owner != null) parts.push(h("p", { class: "why" }, `🏠 ${st.seats[owner].name} has a station here.`));
  else if (me?.my_turn && g.phase === "turn" && !S.ui.pending) {
    const opts = me.station_options;
    if (opts.length) {
      parts.push(h("p", { class: "label" }, `Build a station (${plural(me.station_cost, "card")} of one colour):`));
      parts.push(
        h(
          "div",
          { class: "pay-list" },
          opts.map(([color, locos]) => h("button", { class: "btn pay", onclick: () => act({ type: "station", city: name, color, locos }) }, paymentChips(me.station_cost, color, locos))),
        ),
      );
      parts.push(h("p", { class: "why" }, "A station lets you use one opponent route into this city for your tickets. You don't pick it now: at the end of the game the route that scores you the most is used. Unused stations score 4 points each."));
    } else if (g.players[st.you.seat].stations.length >= 3) parts.push(h("p", { class: "why" }, "You have no stations left."));
    else parts.push(h("p", { class: "why" }, `A station here costs ${plural(me.station_cost, "card")} of one colour.`));
  }
  openPopover(e.clientX, e.clientY, h("div", {}, parts));
}

function onBoardHover(target, e) {
  const tip = $("#tooltip");
  if (!tip) return;
  if (!target || !S.state?.game) {
    tip.classList.add("hidden");
    return;
  }
  const st = S.state;
  if (target.route != null) {
    const r = route(target.route);
    const owner = st.game.owners[r.id];
    tip.replaceChildren(h("b", {}, `${r.a} – ${r.b}`), h("div", {}, routeMeta(r)), h("div", {}, owner != null ? `Claimed by ${st.seats[owner].name}` : null));
  } else {
    const owner = st.game.stations[target.city];
    tip.replaceChildren(h("b", {}, target.city), h("div", {}, owner != null ? `🏠 Station of ${st.seats[owner].name}` : null));
  }
  tip.classList.remove("hidden");
  tip.style.left = `${e.clientX + 14}px`;
  tip.style.top = `${e.clientY + 14}px`;
}

function showHint(action) {
  const st = S.state;
  S.ui.hint = action;
  let text = "";
  switch (action.type) {
    case "claim": {
      const r = route(action.route);
      text = `Claim ${r.a} – ${r.b}`;
      break;
    }
    case "draw_card":
      text = action.slot == null ? "Draw from the deck" : `Take the face-up ${COLOR_NAMES[st.game.face_up[action.slot]].toLowerCase()} card`;
      break;
    case "draw_tickets":
      text = "Draw new destination tickets";
      break;
    case "keep_tickets":
      S.ui.selected = new Set(action.tickets);
      text = `Keep ${plural(action.tickets.length, "ticket")} (selected for you)`;
      break;
    case "station":
      text = `Build a station in ${action.city}`;
      break;
    case "tunnel_pay":
      text = "Pay for the tunnel";
      break;
    case "tunnel_decline":
      text = "Give up this tunnel";
      break;
    default:
      text = "Pass";
  }
  toast(`💡 ${text}`);
  render();
}

// ------------------------------------------------------------------ game over overlay
function renderOverlay() {
  const st = S.state;
  if (!st || !st.game || st.status !== "game_over" || performance.now() < S.ui.summaryAt) {
    overlay.replaceChildren();
    return;
  }
  if (S.ui.summaryHidden) {
    overlay.replaceChildren(h("div", { class: "mini-bar" }, "🏁 Game over", h("button", { class: "btn small primary", onclick: () => ((S.ui.summaryHidden = false), renderOverlay()) }, "Show scores")));
    return;
  }
  const res = st.game.result;
  const me = st.you.seat;
  const isHost = st.host === S.me;
  const winners = res.winners.map((w) => st.seats[w].name);
  let title = winners.length > 1 ? `🤝 ${winners.join(" & ")} share the win!` : `🏆 ${winners[0]} wins!`;
  if (me != null && res.winners.includes(me)) title = winners.length > 1 ? "🤝 You share the win!" : "🏆 You win!";
  overlay.replaceChildren(
    h(
      "div",
      { class: "backdrop" },
      h(
        "div",
        { class: "modal wide" },
        h("h2", { style: { textAlign: "center" } }, title),
        resultTable(st),
        h(
          "div",
          { class: "actions" },
          h("button", { class: "btn ghost", onclick: () => ((S.ui.summaryHidden = true), renderOverlay()) }, "👀 Look at the board"),
          isHost ? h("button", { class: "btn", onclick: () => send({ type: "to_lobby" }) }, "Back to lobby") : null,
          isHost
            ? h("button", { class: "btn primary", onclick: () => send({ type: "play_again" }) }, "Play again ↻")
            : h("span", { class: "grow", style: { textAlign: "right" } }, "Waiting for the host to start a rematch…"),
        ),
      ),
    ),
  );
}

function confetti() {
  const layer = h("div", { class: "confetti" });
  const colors = ["#d9412f", "#3f8fd8", "#5aab48", "#f1cf37", "#ee8c2f", "#b866b9"];
  for (let i = 0; i < 90; i++) {
    layer.append(
      h("i", {
        style: {
          left: `${Math.random() * 100}%`,
          background: pick(colors),
          animationDuration: `${2.2 + Math.random() * 2}s`,
          animationDelay: `${Math.random() * 0.8}s`,
          transform: `rotate(${Math.random() * 360}deg)`,
        },
      }),
    );
  }
  document.body.append(layer);
  setTimeout(() => layer.remove(), 5200);
}

function showReaction(msg) {
  const st = S.state;
  const name = st?.seats.find((s) => s.member === msg.member)?.name || st?.spectators.find((s) => s.member === msg.member)?.name || "";
  let rect = msg.seat != null ? $(`.pl-row[data-seat="${msg.seat}"]`)?.getBoundingClientRect() : null;
  if (!rect) rect = $("#main")?.getBoundingClientRect();
  if (!rect) return;
  const bubble = h(
    "div",
    { class: "bubble", style: { left: `${rect.left + rect.width / 2 + (Math.random() - 0.5) * 40}px`, top: `${rect.top + 10}px` } },
    msg.emoji,
    h("small", {}, name),
  );
  document.body.append(bubble);
  setTimeout(() => bubble.remove(), 2300);
}

// ------------------------------------------------------------------ timer + keyboard
function tickTimer() {
  const bar = $("#timer");
  if (bar) {
    const st = S.state;
    if (S.timer.endAt && st?.status === "playing") {
      const left = Math.max(0, S.timer.endAt - performance.now());
      const frac = S.timer.total ? left / (S.timer.total * 1000) : 0;
      bar.style.width = `${(frac * 100).toFixed(2)}%`;
      bar.classList.toggle("low", left < 8000);
      const mine = st.game?.me?.my_turn || st.game?.me?.offer.length;
      if (left > 0 && left < 5000 && mine) {
        const sec = Math.ceil(left / 1000);
        if (sec !== S.timer.lastTick) {
          S.timer.lastTick = sec;
          sfx.tick();
        }
      }
    } else bar.style.width = "0";
  }
  requestAnimationFrame(tickTimer);
}
requestAnimationFrame(tickTimer);

document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
  const st = S.state;
  if (e.key === "Escape") closePopover();
  if (!st?.game || st.status === "lobby") return;
  if (e.key === "0") S.board?.resetView();
  if (e.key === "+" || e.key === "=") S.board?.zoomAt(1.3);
  if (e.key === "-") S.board?.zoomAt(1 / 1.3);
  const me = st.game.me;
  if (!me) return;
  const k = e.key.toLowerCase();
  if (k === "h" && st.settings.hints && (me.my_turn || me.offer.length)) send({ type: "hint" });
  if (!me.my_turn || S.ui.pending) return;
  if (k === "d" && me.can_blind) act({ type: "draw_card", slot: null });
  else if (/^[1-5]$/.test(k) && me.face_up_ok[Number(k) - 1]) act({ type: "draw_card", slot: Number(k) - 1 });
  else if (k === "t" && me.can_tickets) act({ type: "draw_tickets" });
});

for (const ev of ["pointerdown", "keydown"]) window.addEventListener(ev, unlockAudio, { capture: true });

// ------------------------------------------------------------------ boot
async function boot() {
  const [config, map, land] = await Promise.all([
    fetch("/api/config").then((r) => r.json()),
    fetch("/api/map").then((r) => r.json()),
    fetch("/static/land.json").then((r) => r.json()),
  ]);
  S.config = config;
  S.map = map;
  S.land = land;
  S.cityPos = Object.fromEntries(map.cities.map((c) => [c.name, c]));
  // The land symbol for ticket mini-maps lives in a hidden SVG so it exists on every page.
  document.body.append(s("svg", { class: "defs-holder", width: 0, height: 0 }, s("defs", {}, s("symbol", { id: "land-sym", viewBox: `0 0 ${map.width} ${map.height}` }, s("path", { d: land.land })))));
  router();
}
boot().catch((e) => {
  console.error(e);
  app.replaceChildren(h("div", { class: "center-msg" }, h("p", {}, "Could not load the game. Is the server running?")));
});
