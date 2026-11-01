import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {castFor} from '../lib/cast';
import {clamp} from '../lib/motion';
import {Chip, Receipt} from '../ui';
import {loadJP, theme} from '../theme';
import type {CastEntry, PersonLog, Translation} from '../lib/types';

// A lower third as a typeset caption card (paper/subtitles.html), one at a time in the bottom third
// (hud/subtitles.html): the words as said in serif italic, the English under them in sans, the speaker's colour as a
// rule down the left, the turn_kind as a dashed tag, and a receipt naming the recording, the turn and the span.
// The English is a subtitle for the viewer: until the badge's own translation arrived (its logged t_ms, usually
// right after the turn ended) the chip says so; from then on it is Muse Spark's line.
export type SubtitleTurn = {
  turn: number;
  speaker: string; // "1:C"
  name: string; // as logged
  color: string;
  start_ms: number;
  end_ms: number;
  text: string;
  english?: string | null;
  language?: string | null;
  kind?: string | null;
  translation_t_ms?: number | null;
  recording: string;
  named?: {name: string; t_ms: number} | null; // the name the log gave this voice later, if it had none yet
};

export type SubtitlesProps = {
  turns: SubtitleTurn[];
  startMs: number; // recording time at frame 0
  holdMs?: number; // how long a card stays after the turn ends, if nothing follows
  compact?: boolean;
};

const KIND_TAG: Record<string, string> = {
  ambient: 'ambient · not said to you',
  incidental: 'incidental',
  murmured: 'murmured · to himself',
};

export const SubtitleCard: React.FC<{t: SubtitleTurn; p: number; ms: number; compact?: boolean}> = ({t, p, ms, compact}) => {
  const isJP = t.language === 'Japanese' || /[぀-ヿ一-鿿]/.test(t.text);
  const jp = isJP ? loadJP() : null;
  const arrived = t.translation_t_ms == null || ms >= t.translation_t_ms;
  const tr = t.translation_t_ms != null ? `${(t.translation_t_ms / 1000).toFixed(1)} s` : '';
  return (
    <div
      style={{
        position: 'absolute',
        left: 96,
        bottom: 110,
        width: 1500,
        opacity: p,
        transform: `translateY(${(1 - p) * 22}px)`,
      }}
    >
      <div
        style={{
          position: 'relative',
          background: 'rgba(244,240,231,0.97)',
          border: `1.5px solid ${theme.rule}`,
          borderRadius: 26,
          padding: compact ? '28px 50px 26px 60px' : '34px 56px 30px 66px',
          boxShadow: '0 24px 60px rgba(0,0,0,0.45), 0 2px 8px rgba(0,0,0,0.2)',
          color: theme.ink,
        }}
      >
        <div style={{position: 'absolute', left: 22, top: 34, bottom: 34, width: 8, borderRadius: 6, background: t.color}} />
        <div style={{display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16, flexWrap: 'wrap'}}>
          <span style={{fontFamily: theme.sans, fontWeight: 700, fontSize: 30, color: t.color}}>{t.name}</span>
          {t.english ? (
            arrived ? (
              <Chip size={22}>Muse Spark · translated from {t.language}</Chip>
            ) : (
              <Chip kind="nomodel" size={22}>
                subtitle for viewers · Muse Spark's translation arrives at {tr}
              </Chip>
            )
          ) : (
            <Chip size={22}>Muse Voice Transcribe · the words</Chip>
          )}
          {t.kind && KIND_TAG[t.kind] ? (
            <Chip kind="nomodel" size={22}>
              {KIND_TAG[t.kind]}
            </Chip>
          ) : null}
        </div>
        <p
          style={{
            fontFamily: jp ? `${theme.serif}, ${jp}` : theme.serif,
            fontStyle: 'italic',
            fontWeight: 500,
            fontSize: compact ? 52 : 62,
            lineHeight: 1.16,
            margin: 0,
            color: theme.inkStrong,
            letterSpacing: '-0.005em',
          }}
        >
          {t.text}
        </p>
        {t.english ? (
          <p style={{fontFamily: theme.sans, fontSize: compact ? 36 : 42, lineHeight: 1.26, margin: '14px 0 0', color: arrived ? theme.ink : theme.inkSoft}}>
            <span style={{color: theme.accent, fontWeight: 700}}>→ </span>
            {t.english}
          </p>
        ) : null}
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 20, gap: 20}}>
          {t.english ? <Chip size={22}>Muse Voice Transcribe · the words</Chip> : <span />}
          <Receipt
            size={20}
            align="right"
            wrap
            style={{flex: 1}}
            parts={[
              t.recording,
              `turn ${t.turn}`,
              `${(t.start_ms / 1000).toFixed(1)}–${(t.end_ms / 1000).toFixed(1)} s`,
              ...(t.translation_t_ms != null ? [`translation logged ${tr}${arrived ? '' : ' · shown early'}`] : []),
              ...(t.named ? [`named ${t.named.name} at ${(t.named.t_ms / 1000).toFixed(1)} s`] : []),
              ...(t.kind ? [`turn_kind ${t.kind}`] : []),
            ]}
          />
        </div>
      </div>
    </div>
  );
};

export const Subtitles: React.FC<SubtitlesProps> = ({turns, startMs, holdMs = 900, compact}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ms = startMs + (frame / fps) * 1000;
  const FADE = 250;
  // one card at a time: a card ends at the next card's start, or holdMs after its own end
  const sorted = [...turns].sort((a, b) => a.start_ms - b.start_ms);
  let show: {t: SubtitleTurn; p: number} | null = null;
  sorted.forEach((t, i) => {
    const next = sorted[i + 1];
    const until = Math.min(t.end_ms + holdMs, next ? next.start_ms - 40 : Infinity);
    if (ms >= t.start_ms - FADE && ms <= until + FADE) {
      const pin = clamp((ms - (t.start_ms - FADE)) / FADE);
      const pout = clamp((until + FADE - ms) / FADE);
      show = {t, p: Math.min(pin, pout)};
    }
  });
  if (!show) return null;
  const {t, p} = show as {t: SubtitleTurn; p: number};
  return (
    <AbsoluteFill>
      <SubtitleCard t={t} p={p} ms={ms} compact={compact} />
    </AbsoluteFill>
  );
};

type RecLike = {
  id: string;
  cast: Record<string, CastEntry>;
  people_log?: PersonLog[];
  owner_event?: {t_ms: number; speakers: string[]} | null;
  turns: {turn: number; speaker: string; start_ms: number; end_ms: number; text: string; kind?: string | null; translation?: Translation | null}[];
};

// Build subtitle turns from a recording's turns: the name as the log had it when the turn ended, colours in order of
// appearance (tools/extract_data.py cast).
export const subtitleTurnsFromRec = (rec: RecLike, which: number[], translations?: Record<number, Translation | null>): SubtitleTurn[] => {
  const C = castFor(rec);
  return rec.turns
    .filter((t) => which.includes(t.turn))
    .map((t) => {
      const tr = translations ? (translations[t.turn] ?? null) : (t.translation ?? null);
      const then = C.at(t.speaker, t.end_ms);
      const final = C.of(t.speaker);
      const namedAt = then.name === final.name ? null : (rec.people_log ?? []).find((e) => e.type === 'person' && e.name === final.name && (e.speakers ?? []).includes(t.speaker));
      return {
        turn: t.turn,
        speaker: t.speaker,
        name: then.name,
        named: namedAt ? {name: final.name, t_ms: namedAt.t_ms} : null,
        color: C.color(t.speaker, 'paper'),
        start_ms: t.start_ms,
        end_ms: t.end_ms,
        text: t.text,
        english: tr?.english ?? null,
        language: tr?.language ?? null,
        kind: t.kind ?? null,
        translation_t_ms: tr?.t_ms ?? null,
        recording: rec.id,
      };
    });
};
