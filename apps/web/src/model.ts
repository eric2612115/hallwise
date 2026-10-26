// The dashboard's state, rebuilt from the server's event stream (live) or event log (replay).

export type Event = { type: string; t_ms: number; [k: string]: unknown }

export interface Person {
  key: string
  name: string
  company: string
  role: string
  language: string
  introducedBy: string
  speakers: string[]
}

export interface Promise {
  key: string
  what: string
  due: string
  replaces: string
  owedBy: string
  owedTo: string
}

export interface Line {
  turn: number
  speaker: string
  text: string
  startMs: number
  endMs: number
}

export interface Suspect {
  heard: string
  likely: string
  turn: number
}

export interface State {
  recording: string
  device: string
  event: string
  venue: string
  layout: string
  ended: boolean
  tMs: number
  yaw: number | null
  ownerSpeakers: string[]
  people: Person[]
  promises: Promise[]
  lines: Line[]
  turnKinds: Record<number, string>
  suspects: Suspect[]
  translations: Record<number, { language: string; english: string }>
  topics: string[]
  speakerAzimuth: Record<string, number>
  speakerLevel: Record<string, number>
  lastSpeaker: { speaker: string; untilMs: number } | null
}

export const empty: State = {
  recording: '',
  device: '',
  event: '',
  venue: '',
  layout: '',
  ended: false,
  tMs: 0,
  yaw: null,
  ownerSpeakers: [],
  people: [],
  promises: [],
  lines: [],
  turnKinds: {},
  suspects: [],
  translations: {},
  topics: [],
  speakerAzimuth: {},
  speakerLevel: {},
  lastSpeaker: null,
}

const str = (v: unknown) => (typeof v === 'string' ? v : '')
const num = (v: unknown) => (typeof v === 'number' ? v : 0)
const strs = (v: unknown) => (Array.isArray(v) ? v.filter((x) => typeof x === 'string') : [])

function upsert<T>(list: T[], item: T, same: (a: T, b: T) => boolean): T[] {
  const i = list.findIndex((x) => same(x, item))
  if (i < 0) return [...list, item]
  const next = list.slice()
  next[i] = item
  return next
}

export function reduce(s: State, e: Event): State {
  const tMs = Math.max(s.tMs, e.t_ms)
  switch (e.type) {
    case 'recording_start':
      return {
        ...s,
        tMs,
        recording: str(e.recording),
        device: str(e.device),
        event: str(e.event),
        venue: str(e.venue),
        layout: str(e.layout),
      }
    case 'recording_end':
      return { ...s, tMs, ended: true, lastSpeaker: null }
    case 'device_pose':
      return { ...s, tMs, yaw: typeof e.yaw === 'number' ? e.yaw : s.yaw }
    case 'speech_start':
      return { ...s, tMs }
    case 'turn': {
      const text = str(e.text)
      if (!text) return { ...s, tMs }
      const speaker = `${num(e.session) || 1}:${str(e.speaker) || '?'}`
      const line: Line = { turn: num(e.turn), speaker, text, startMs: num(e.start_ms), endMs: num(e.end_ms) }
      return {
        ...s,
        tMs,
        lines: upsert(s.lines, line, (a, b) => a.turn === b.turn),
        lastSpeaker: { speaker, untilMs: line.endMs + 1500 },
      }
    }
    case 'turn_kind':
      return { ...s, tMs, turnKinds: { ...s.turnKinds, [num(e.turn)]: str(e.kind) } }
    case 'owner':
      return { ...s, tMs, ownerSpeakers: strs(e.speakers) }
    case 'speaker_position': {
      const next = { ...s, tMs, speakerAzimuth: { ...s.speakerAzimuth, [str(e.speaker)]: num(e.azimuth) } }
      if (typeof e.level_db === 'number') next.speakerLevel = { ...s.speakerLevel, [str(e.speaker)]: e.level_db }
      return next
    }
    case 'person': {
      const p: Person = {
        key: str(e.key),
        name: str(e.name),
        company: str(e.company),
        role: str(e.role),
        language: str(e.preferred_language),
        introducedBy: str(e.introduced_by),
        speakers: strs(e.speakers),
      }
      return { ...s, tMs, people: upsert(s.people, p, (a, b) => a.key === b.key) }
    }
    case 'promise': {
      const p: Promise = {
        key: str(e.key),
        what: str(e.what),
        due: str(e.due),
        replaces: str(e.replaces),
        owedBy: str(e.owed_by),
        owedTo: str(e.owed_to),
      }
      return { ...s, tMs, promises: upsert(s.promises, p, (a, b) => a.key === b.key) }
    }
    case 'suspect_word': {
      const w: Suspect = { heard: str(e.heard), likely: str(e.likely), turn: num(e.turn) }
      return { ...s, tMs, suspects: upsert(s.suspects, w, (a, b) => a.turn === b.turn && a.heard === b.heard) }
    }
    case 'translation':
      return {
        ...s,
        tMs,
        translations: { ...s.translations, [num(e.turn)]: { language: str(e.language), english: str(e.english) } },
      }
    case 'translation_removed': {
      const next = { ...s.translations }
      delete next[num(e.turn)]
      return { ...s, tMs, translations: next }
    }
    case 'person_removed':
      return { ...s, tMs, people: s.people.filter((p) => p.key !== str(e.key)) }
    case 'promise_removed':
      return { ...s, tMs, promises: s.promises.filter((p) => p.key !== str(e.key)) }
    case 'suspect_word_removed':
      return { ...s, tMs, suspects: s.suspects.filter((w) => !(w.turn === num(e.turn) && w.heard === str(e.heard))) }
    case 'room_topics':
      return { ...s, tMs, topics: strs(e.topics) }
    default:
      return { ...s, tMs }
  }
}

export function nameFor(s: State, key: string): string {
  if (key === 'owner') return 'you'
  return s.people.find((p) => p.key === key)?.name ?? key
}

export function personForSpeaker(s: State, speaker: string): Person | undefined {
  return s.people.find((p) => p.speakers.includes(speaker))
}

/** Mean room bearing of a person over their speaker labels, in degrees (counter-clockwise from the badge's x axis). */
export function bearing(s: State, p: Person): number | null {
  const az = p.speakers.map((k) => s.speakerAzimuth[k]).filter((a): a is number => typeof a === 'number')
  if (!az.length) return null
  const x = az.reduce((acc, a) => acc + Math.cos((a * Math.PI) / 180), 0)
  const y = az.reduce((acc, a) => acc + Math.sin((a * Math.PI) / 180), 0)
  return (Math.atan2(y, x) * 180) / Math.PI
}

/** 0 = as close as anyone gets, 1 = far: loudness against the loudest voice that is not the wearer's, over ~18 dB. */
export function distance(s: State, speakers: string[]): number {
  const others = Object.entries(s.speakerLevel)
    .filter(([k]) => !s.ownerSpeakers.includes(k))
    .map(([, v]) => v)
  const levels = speakers.map((k) => s.speakerLevel[k]).filter((v): v is number => typeof v === 'number')
  if (!others.length || !levels.length) return 0.5
  return Math.min(1, Math.max(0, (Math.max(...others) - Math.max(...levels)) / 18))
}

export function mmss(ms: number): string {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
