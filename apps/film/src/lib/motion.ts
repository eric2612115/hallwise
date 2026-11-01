import {Easing, interpolate} from 'remotion';

// The one ease every card, leader and strike uses (spec 4): cubic-bezier(0.22, 1, 0.36, 1).
export const EASE = Easing.bezier(0.22, 1, 0.36, 1);

export const clamp = (x: number, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

// Progress 0..1 of a beat that starts at frame `at` and lasts `dur` frames, eased.
export const seg = (frame: number, at: number, dur: number) =>
  interpolate(frame, [at, at + dur], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE});

// Linear 0..1 (for things that should not ease, like a playhead).
export const lin = (frame: number, at: number, dur: number) => clamp((frame - at) / dur);

// A card landing: opacity and a 26 px rise over 0.45 s (spec 4).
export const land = (p: number, rise = 26) => ({opacity: p, transform: `translateY(${(1 - p) * rise}px)`});

// Fade in over `inF` frames and out over `outF` frames inside a segment of `total` frames.
export const fadeInOut = (frame: number, total: number, inF = 9, outF = 9) =>
  Math.min(clamp(frame / inF), clamp((total - frame) / outF));

export const fmt = (n: number) => Number(n).toLocaleString('en-US');
export const secs = (ms: number, d = 1) => (ms / 1000).toFixed(d) + ' s';
export const sdb = (v: number, d = 1) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d) + ' dB';

// Seeded random (hud.js prng), so particles are the same on every render.
export const prng = (seed: number) => {
  let s = seed >>> 0 || 1;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
};
