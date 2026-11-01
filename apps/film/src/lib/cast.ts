import {theme} from '../theme';
import type {CastEntry, PersonLog} from './types';

// Who is who, from the data: tools/extract_data.py builds a cast per recording (names as the final person events
// say them, colours in order of first appearance as apps/replay/app.js prepare() assigns --p0..7, the owner from
// the owner event). Nothing here is typed in; another take brings its own cast.
export type CastSource = {cast: Record<string, CastEntry>; people_log?: PersonLog[]; owner_event?: {t_ms: number; speakers: string[]} | null; owner?: {t_ms: number; speakers: string[]} | null};

const unknown = (label: string): CastEntry => ({label, name: 'a voice', short: 'a voice', p: 7, key: null});

// Colour of a voice on paper or on the dark frame.
export const colorOf = (c: CastEntry, ground: 'paper' | 'dark' = 'paper') => {
  if (c.p === 'owner') return ground === 'paper' ? theme.ink : theme.paperWhite;
  const i = c.p % theme.people.length;
  return ground === 'paper' ? theme.people[i] : theme.peopleDark[i];
};

export const castFor = (src: CastSource) => {
  const of = (label: string): CastEntry => src.cast[label] ?? unknown(label);
  // The name a label had at `ms`: the person events logged by then (the owner from the owner event); before
  // that, "a voice". So a frame frozen at t never shows a name the badge had not heard yet.
  const at = (label: string, ms: number): CastEntry => {
    const base = of(label);
    const owner = src.owner_event ?? src.owner ?? null;
    if (base.p === 'owner') return owner && owner.t_ms <= ms ? base : {...base, name: 'a voice', short: 'a voice'};
    const people: Record<string, PersonLog> = {};
    for (const e of src.people_log ?? []) {
      if (e.t_ms > ms) continue;
      if (e.type === 'person') people[e.key] = e;
      else delete people[e.key];
    }
    const hit = Object.values(people).find((e) => (e.speakers ?? []).includes(label));
    return hit && hit.name ? {...base, name: hit.name, short: hit.name.split(' ')[0], key: hit.key} : {...base, name: 'a voice', short: 'a voice', key: null};
  };
  const color = (label: string, ground: 'paper' | 'dark' = 'paper') => colorOf(of(label), ground);
  return {of, at, color};
};
export type Cast = ReturnType<typeof castFor>;

// Direction words only: a chest badge tells left from right roughly and front from back badly, so a voice is a
// region, never a number. Positive azimuth is the wearer's left (direction.py).
export const side = (az: number) => (az > 12 ? 'left' : az < -12 ? 'right' : 'ahead');

export const firstName = (name: string) => name.split(' ')[0] || name;
