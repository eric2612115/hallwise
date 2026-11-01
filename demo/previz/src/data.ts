// The shot list is the single source of truth for the animatic.
import raw from '../shotlist.json';

export type Line = {
  at: number; end: number; t: number; tEnd: number; who: string; device: string; text: string; lang: string;
  english?: string; audio?: string; note?: string; choice?: boolean;
};
export type Play = {device: string; file: string; at: number; end: number; t: number; tEnd: number; length: number; note?: string; placeholder?: boolean};
export type Ev = {at: number; t: number; kind: 'buzz' | 'ring' | 'click'; label: string; device: string};
export type Beat = {
  id: number; key: string; name: string; part: string; temp: 'cold' | 'hot'; hot_at?: number; silence?: boolean; xray?: boolean;
  duration: number; start: number; end: number; bed: boolean; bed_off_at?: number;
  eric: {mark: string; markId: string; toMarkId?: string; face: string; pose: string; action: string};
  friend: {spot: string; spotId: string; toSpotId?: string; face: string; action: string};
  camera: {spot: string; spotId: string; toSpotId?: string; framing: string; lookAt: string};
  lines: Line[]; plays: Play[]; events?: Ev[]; post: string[]; proves: string; xraySteps?: string[]; choices?: string[];
};
export type Keyframe = {t: number; x: number; y: number; move: boolean; face?: number; pose?: string; look?: {x: number; y: number}; topDown?: boolean; spot?: string};
export type Device = {id: string; label: string; kind: 'tv' | 'laptop' | 'phone'; x: number; y: number; z: number; w?: number};
export type AudioClip = {src: string; at: number; duration: number; volume: number; kind: string; device: string};

export type Shotlist = {
  title: string; fps: number; duration: number; durationInFrames: number;
  parts: {id: string; label: string}[];
  plan: {
    rooms: {id: string; label: string; x0: number; y0: number; x1: number; y1: number; door: null | {wall: string; from: number; to: number; label: string}}[];
    objects: {id: string; label: string; x0: number; y0: number; x1: number; y1: number; h: number}[];
    devices: Device[];
    marks: {n: number; id: string; label: string; x: number; y: number; pose: string; face: number}[];
    friendSpots: {id: string; label: string; x: number; y: number}[];
    cameraSpots: {id: string; label: string; x: number; y: number; look: {x: number; y: number}; topDown?: boolean}[];
  };
  beats: Beat[];
  keyframes: {eric: Keyframe[]; friend: Keyframe[]; camera: Keyframe[]};
  audio: AudioClip[];
  hallBed: {src: string; on: number; off: number; volume: number; silences: {start: number; end: number}[]};
};

export const shotlist = raw as unknown as Shotlist;

export const beatAt = (t: number): Beat => {
  const b = shotlist.beats.find((x) => t >= x.start && t < x.end);
  return b ?? shotlist.beats[shotlist.beats.length - 1];
};

const easeInOut = (u: number) => (u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2);

const lerpAngle = (a: number, b: number, u: number) => {
  let d = ((b - a + 540) % 360) - 180;
  return (a + d * u + 360) % 360;
};

export type Pose = {x: number; y: number; face: number; pose: string; moving: boolean; look?: {x: number; y: number}; topDown?: boolean; spot?: string};

// Position of a figure at time t: holds at a keyframe until the next one; walks to keyframes flagged move.
export const poseAt = (kfs: Keyframe[], t: number): Pose => {
  let i = 0;
  while (i + 1 < kfs.length && kfs[i + 1].t <= t) i++;
  const k = kfs[i];
  const n = kfs[i + 1];
  const base: Pose = {x: k.x, y: k.y, face: k.face ?? 0, pose: k.pose ?? 'stand', moving: false, look: k.look, topDown: k.topDown, spot: k.spot};
  if (!n) return base;
  const span = n.t - k.t;
  const u = span > 0 ? Math.min(1, Math.max(0, (t - k.t) / span)) : 1;
  if (n.move && span > 0) {
    const e = easeInOut(u);
    const x = k.x + (n.x - k.x) * e;
    const y = k.y + (n.y - k.y) * e;
    const dx = n.x - k.x, dy = n.y - k.y;
    const walkFace = Math.abs(dx) + Math.abs(dy) > 1e-6 ? (Math.atan2(dy, dx) * 180) / Math.PI : (k.face ?? 0);
    const face = u > 0.85 ? lerpAngle(walkFace, n.face ?? walkFace, (u - 0.85) / 0.15) : u < 0.1 ? lerpAngle(k.face ?? walkFace, walkFace, u / 0.1) : walkFace;
    const look = k.look && n.look ? {x: k.look.x + (n.look.x - k.look.x) * e, y: k.look.y + (n.look.y - k.look.y) * e} : n.look ?? k.look;
    return {x, y, face, pose: u < 1 ? (k.pose === 'lie' || k.pose === 'sit' ? (u < 0.3 ? k.pose : 'stand') : 'stand') : (n.pose ?? 'stand'), moving: u < 1, look, topDown: u < 1 ? false : n.topDown, spot: u < 0.5 ? k.spot : n.spot};
  }
  // A step: hold, but ease the facing and look into the next keyframe over its last half second.
  const lead = n.t - 0.5;
  if (t > lead && (n.face !== undefined || n.look)) {
    const v = (t - lead) / 0.5;
    return {
      ...base,
      face: n.face !== undefined ? lerpAngle(k.face ?? 0, n.face, v) : base.face,
      look: k.look && n.look ? {x: k.look.x + (n.look.x - k.look.x) * v, y: k.look.y + (n.look.y - k.look.y) * v} : base.look,
    };
  }
  return base;
};

// The trail walked so far: every keyframe position up to t, plus the current point.
export const trailAt = (kfs: Keyframe[], t: number): {x: number; y: number}[] => {
  const pts: {x: number; y: number}[] = [];
  for (const k of kfs) {
    if (k.t > t) break;
    const last = pts[pts.length - 1];
    if (!last || Math.abs(last.x - k.x) > 1e-6 || Math.abs(last.y - k.y) > 1e-6) pts.push({x: k.x, y: k.y});
  }
  const p = poseAt(kfs, t);
  const last = pts[pts.length - 1];
  if (!last || Math.abs(last.x - p.x) > 1e-6 || Math.abs(last.y - p.y) > 1e-6) pts.push({x: p.x, y: p.y});
  return pts;
};

export const fmtTime = (t: number) => {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s < 10 ? '0' : ''}${s.toFixed(1)}`;
};

export const partLabel = (id: string) => shotlist.parts.find((p) => p.id === id)?.label ?? id;

export const SPEAKER_COLOR: Record<string, string> = {
  Eric: '#C8861B', Friend: '#2F7F72', Leo: '#3B63A8', Margaux: '#B8475F', Julien: '#7A4FA3',
  Waiter: '#8A8578', Siddharth: '#5F8A3C', Kenji: '#C8402F',
};
