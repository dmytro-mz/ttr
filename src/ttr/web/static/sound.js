// Sound effects (WebAudio): mostly synthesised, plus a few recorded clips from /static/sounds/.

let ctx = null;
let out = null;
let muted = localStorage.getItem("ttr.muted") === "1";
let volume = Number(localStorage.getItem("ttr.volume") ?? 0.85);
let noiseBuffer = null;
const CLIPS = { turn: "/static/sounds/your-turn.mp3", tunnel: "/static/sounds/tunnel.mp3" };
const clipData = Object.fromEntries(
  Object.entries(CLIPS).map(([name, url]) => [
    name,
    fetch(url)
      .then((r) => r.arrayBuffer())
      .catch(() => null),
  ]),
);
const clipBuffers = {};
const playing = {};
// The effects are written at modest per-sound gains; this lifts them to a loud level at full volume.
const BOOST = 5;

export const isMuted = () => muted;
export const getVolume = () => volume;

export function setMuted(value) {
  muted = value;
  localStorage.setItem("ttr.muted", value ? "1" : "0");
}

export function setVolume(value) {
  volume = Math.min(1, Math.max(0, value));
  localStorage.setItem("ttr.volume", String(volume));
  if (out) out.gain.setTargetAtTime(volume * BOOST, ctx.currentTime, 0.02);
}

// Browsers only start audio after a user gesture.
export function unlockAudio() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    ctx = new AC();
    const limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -10;
    limiter.knee.value = 6;
    limiter.ratio.value = 12;
    limiter.attack.value = 0.003;
    limiter.release.value = 0.15;
    out = ctx.createGain();
    out.gain.value = volume * BOOST;
    out.connect(limiter).connect(ctx.destination);
    for (const [name, data] of Object.entries(clipData)) {
      data
        .then((bytes) => bytes && ctx.decodeAudioData(bytes))
        .then((buf) => buf && (clipBuffers[name] = buf))
        .catch(() => {});
    }
  }
  if (ctx.state === "suspended") ctx.resume();
}

// Recorded clips are mastered at full level, so they skip the BOOST; a new start cuts off the previous one.
function clip(name) {
  if (!ready() || !clipBuffers[name]) return;
  playing[name]?.stop();
  const src = ctx.createBufferSource();
  src.buffer = clipBuffers[name];
  const amp = ctx.createGain();
  amp.gain.value = 1 / BOOST;
  src.connect(amp).connect(out);
  src.onended = () => playing[name] === src && delete playing[name];
  playing[name] = src;
  src.start();
}

function ready() {
  return !muted && volume > 0 && ctx && ctx.state === "running";
}

function tone(freq, dur, { type = "sine", gain = 0.07, at = 0, slide = 0, vibrato = 0 } = {}) {
  if (!ready()) return;
  const t = ctx.currentTime + at;
  const osc = ctx.createOscillator();
  const amp = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t);
  if (slide) osc.frequency.exponentialRampToValueAtTime(freq * slide, t + dur);
  if (vibrato) {
    const lfo = ctx.createOscillator();
    const depth = ctx.createGain();
    lfo.frequency.value = 6;
    depth.gain.value = vibrato;
    lfo.connect(depth).connect(osc.frequency);
    lfo.start(t);
    lfo.stop(t + dur + 0.05);
  }
  amp.gain.setValueAtTime(0.0001, t);
  amp.gain.exponentialRampToValueAtTime(gain, t + 0.03);
  amp.gain.setValueAtTime(gain, t + Math.max(0.03, dur - 0.08));
  amp.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(amp).connect(out);
  osc.start(t);
  osc.stop(t + dur + 0.05);
}

function noise(dur, { gain = 0.06, at = 0, freq = 2500, q = 0.9, attack = 0, slide = 0 } = {}) {
  if (!ready()) return null;
  if (!noiseBuffer) {
    noiseBuffer = ctx.createBuffer(1, ctx.sampleRate * 0.5, ctx.sampleRate);
    const data = noiseBuffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  }
  const t = ctx.currentTime + at;
  const src = ctx.createBufferSource();
  src.buffer = noiseBuffer;
  src.loop = true;
  const filter = ctx.createBiquadFilter();
  filter.type = "bandpass";
  filter.frequency.setValueAtTime(freq, t);
  if (slide) filter.frequency.exponentialRampToValueAtTime(freq * slide, t + dur);
  filter.Q.value = q;
  const amp = ctx.createGain();
  if (attack) {
    amp.gain.setValueAtTime(0.0001, t);
    amp.gain.exponentialRampToValueAtTime(gain, t + attack);
  } else amp.gain.setValueAtTime(gain, t);
  amp.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  src.connect(filter).connect(amp).connect(out);
  src.start(t);
  src.stop(t + dur + 0.05);
  return amp;
}

// Warning siren, wailing up and down twice.
function siren(at = 0) {
  if (!ready()) return;
  const t = ctx.currentTime + at;
  const osc = ctx.createOscillator();
  osc.type = "square";
  osc.frequency.setValueAtTime(620, t);
  [1040, 620, 1040, 620].forEach((f, i) => osc.frequency.linearRampToValueAtTime(f, t + (i + 1) * 0.42));
  const filter = ctx.createBiquadFilter();
  filter.type = "lowpass";
  filter.frequency.value = 2400;
  const amp = ctx.createGain();
  amp.gain.setValueAtTime(0.0001, t);
  amp.gain.exponentialRampToValueAtTime(0.045, t + 0.05);
  amp.gain.setValueAtTime(0.045, t + 1.55);
  amp.gain.exponentialRampToValueAtTime(0.0001, t + 1.75);
  osc.connect(filter).connect(amp).connect(out);
  osc.start(t);
  osc.stop(t + 1.8);
}

// Steam whistle: two detuned square-ish tones with vibrato.
function whistle(at = 0, dur = 0.5, gain = 0.03) {
  tone(740, dur, { type: "triangle", gain, at, vibrato: 4 });
  tone(932, dur, { type: "triangle", gain: gain * 0.8, at, vibrato: 4 });
  noise(dur * 0.8, { gain: gain * 0.6, at, freq: 3000, q: 3 });
}

export const sfx = {
  card: () => noise(0.09, { gain: 0.08, freq: 3400 }),
  ticket: () => {
    noise(0.12, { gain: 0.06, freq: 1800 });
    noise(0.1, { gain: 0.05, freq: 2600, at: 0.08 });
  },
  claim: (length = 3) => {
    for (let i = 0; i < Math.min(length, 8); i++) {
      noise(0.06, { gain: 0.09, freq: 900, at: i * 0.09 });
      tone(120, 0.06, { type: "square", gain: 0.02, at: i * 0.09 });
    }
    if (length >= 4) whistle(Math.min(length, 8) * 0.09, 0.45);
  },
  station: () => [523, 784].forEach((f, i) => tone(f, 0.18, { type: "triangle", gain: 0.05, at: i * 0.1 })),
  tunnel: () => clip("tunnel"),
  turn: () => clip("turn"),
  alert: () => siren(),
  win: () => {
    [523, 659, 784, 1047, 784, 1047].forEach((f, i) => tone(f, 0.24, { type: "triangle", gain: 0.06, at: i * 0.11 }));
    whistle(0.75, 0.7);
  },
  lose: () => [392, 349, 311].forEach((f, i) => tone(f, 0.3, { type: "triangle", gain: 0.05, at: i * 0.16 })),
  tick: () => tone(1250, 0.03, { type: "square", gain: 0.018 }),
  error: () => tone(170, 0.16, { type: "sawtooth", gain: 0.03 }),
  chat: () => tone(880, 0.07, { gain: 0.03 }),
  reset: () => noise(0.35, { gain: 0.06, freq: 2200 }),
};
