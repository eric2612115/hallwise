import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {castFor} from '../lib/cast';
import {clamp, prng} from '../lib/motion';
import {hexA, theme} from '../theme';
import {Grain} from '../ui';
import type {Rec3} from '../lib/types';

// Stand-in footage: a dark room with soft light pools, a LIVE slate, and the four badge channels breathing at the
// bottom left, coloured by whoever is speaking (hud/xray.html drawChannels). The levels are the real 20 ms RMS of
// audio.wav from the xray sidecar, so the meter moves with the badge audio under it.
export type RoomProps = {
  rec: Rec3;
  startMs: number; // what recording time frame 0 is
  frozen?: number; // 0..1: desaturate, darken, blur (the X-ray freeze)
  meter?: boolean;
  slate?: boolean;
  holdFrom?: number; // frame after which the recording time stops advancing (the freeze)
};

export const turnAt = (rec: Rec3, ms: number) => rec.turns.find((t) => ms >= t.start_ms && ms <= t.end_ms) ?? null;

export const Bokeh: React.FC<{seed?: number; n?: number; drift?: number}> = ({seed = 7, n = 9, drift = 0}) => {
  const pools = useMemo(() => {
    const r = prng(seed);
    const cols = ['#E89A5C', '#B8862B', '#E8E2D6', '#C8702F', '#7FA3E0', '#B08AD8'];
    return Array.from({length: n}, (_, i) => ({
      size: 160 + r() * 420,
      x: r() * 1920,
      y: 120 + r() * 800,
      c: cols[Math.floor(r() * cols.length)],
      a: 0.10 + r() * 0.16,
      ph: r() * Math.PI * 2,
      i,
    }));
  }, [seed, n]);
  return (
    <AbsoluteFill style={{filter: 'blur(70px)', overflow: 'hidden'}}>
      {pools.map((p) => (
        <div
          key={p.i}
          style={{
            position: 'absolute',
            width: p.size,
            height: p.size,
            left: p.x - p.size / 2 + Math.sin(drift * 0.4 + p.ph) * 30,
            top: p.y - p.size / 2 + Math.cos(drift * 0.3 + p.ph) * 18,
            borderRadius: '50%',
            background: hexA(p.c, p.a),
          }}
        />
      ))}
    </AbsoluteFill>
  );
};


export const FoaMeter: React.FC<{rec: Rec3; ms: number; width?: number}> = ({rec, ms, width = 420}) => {
  const C = castFor(rec);
  const w = rec.window;
  const rowH = 30;
  const traceMs = 2500;
  const i1 = Math.floor((ms - w.t0) / w.step_ms);
  const i0 = Math.max(0, i1 - traceMs / w.step_ms);
  const CH = rec.channel_names;
  const n = w.rms_db[CH[0]].length;
  if (i1 < 0 || i0 >= n) return null;
  const norm = (db: number | null) => clamp(((db ?? -70) + 62) / 44);
  const tw = width - 36;
  return (
    <div style={{position: 'absolute', left: 48, top: 96, width, fontFamily: theme.mono}}>
      <div style={{fontSize: 15, letterSpacing: '0.16em', textTransform: 'uppercase', color: theme.darkInkSoft, marginBottom: 8}}>
        the badge · {rec.channels} channels · {rec.layout.toUpperCase()}
      </div>
      <svg width={width} height={rowH * 4} style={{overflow: 'visible', display: 'block'}}>
        {CH.map((c, ci) => {
          const y0 = ci * rowH;
          const pts: string[] = [];
          const segs: {x0: number; x1: number; col: string}[] = [];
          let cur: {x0: number; x1: number; col: string} | null = null;
          for (let i = i0; i <= Math.min(i1, n - 1); i++) {
            const x = ((i - i0) / (traceMs / w.step_ms)) * tw + 36;
            const y = y0 + rowH - 4 - norm(w.rms_db[c][i]) * (rowH - 8);
            pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
            const t = turnAt(rec, w.t0 + i * w.step_ms);
            const col = t ? C.color(t.speaker, 'dark') : theme.darkInkSoft;
            if (cur && cur.col === col) cur.x1 = x;
            else {
              cur = {x0: x, x1: x, col};
              segs.push(cur);
            }
          }
          const path = `M36,${y0 + rowH - 4} L${pts.join(' L')} L${36 + tw},${y0 + rowH - 4} Z`;
          return (
            <g key={c}>
              <text x={0} y={y0 + rowH - 8} fill={ci === 0 ? theme.darkAccent : theme.darkInkSoft} fontSize={16} fontWeight={500}>
                {c}
              </text>
              <line x1={36} x2={36 + tw} y1={y0 + rowH - 4} y2={y0 + rowH - 4} stroke={hexA(theme.darkInk, 0.12)} />
              <defs>
                <clipPath id={`clip-${c}`}>
                  <path d={path} />
                </clipPath>
              </defs>
              <g clipPath={`url(#clip-${c})`}>
                {segs.map((s, k) => (
                  <rect key={k} x={s.x0} y={y0} width={Math.max(1, s.x1 - s.x0 + 1)} height={rowH} fill={hexA(s.col, ci === 0 ? 0.85 : 0.55)} />
                ))}
              </g>
            </g>
          );
        })}
      </svg>
    </div>
  );
};

export const Room: React.FC<RoomProps> = ({rec, startMs, frozen = 0, meter = true, slate = true, holdFrom}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ms = startMs + (Math.min(frame, holdFrom ?? Infinity) / fps) * 1000;
  const hud = 1 - frozen;
  const live = turnAt(rec, ms);
  const C = castFor(rec);
  return (
    <AbsoluteFill style={{backgroundColor: theme.dark, overflow: 'hidden'}}>
      <AbsoluteFill style={{filter: frozen > 0 ? `saturate(${1 - 0.75 * frozen}) brightness(${1 - 0.3 * frozen}) blur(${6 * frozen}px)` : undefined}}>
        <Bokeh drift={frame / fps} />
        <Grain dark />
        <AbsoluteFill
          style={{
            backgroundImage: `linear-gradient(${hexA(theme.darkInk, 0.035)} 1px, transparent 1px), linear-gradient(90deg, ${hexA(theme.darkInk, 0.035)} 1px, transparent 1px)`,
            backgroundSize: '96px 96px',
            maskImage: 'radial-gradient(ellipse at 50% 50%, black 30%, transparent 80%)',
          }}
        />
        {slate ? (
          <div style={{position: 'absolute', left: 48, top: 40, opacity: hud, display: 'flex', alignItems: 'center', gap: 14, fontFamily: theme.mono, fontSize: 20, letterSpacing: '0.06em', color: theme.darkInkSoft}}>
            <span style={{width: 12, height: 12, borderRadius: '50%', background: theme.darkLive, boxShadow: `0 0 0 ${4 + 3 * Math.sin(frame / 6)}px ${hexA(theme.darkLive, 0.2)}`}} />
            <span style={{color: theme.darkInk}}>LIVE</span>
            <span>·</span>
            <span>{rec.event}</span>
            <span>·</span>
            <span>{rec.id}</span>
            <span>·</span>
            <span>{(ms / 1000).toFixed(1)} s</span>
            {live ? (
              <>
                <span>·</span>
                <span style={{color: C.color(live.speaker, 'dark')}}>{C.at(live.speaker, ms).name} · turn {live.turn}</span>
              </>
            ) : null}
          </div>
        ) : null}
        {slate ? (
          <div style={{position: 'absolute', right: 48, top: 36, opacity: hud, display: 'flex', alignItems: 'center', gap: 14}}>
            <span style={{width: 34, height: 34, borderRadius: '50%', background: theme.darkInk, color: theme.dark, display: 'grid', placeItems: 'center', fontFamily: theme.serif, fontWeight: 600, fontSize: 20}}>H</span>
            <span style={{fontFamily: theme.serif, fontWeight: 600, fontSize: 24, color: theme.darkInk}}>Hallwise</span>
          </div>
        ) : null}
        {meter ? (
          <div style={{opacity: hud}}>
            <FoaMeter rec={rec} ms={ms} />
          </div>
        ) : null}
      </AbsoluteFill>
      <AbsoluteFill style={{background: `rgba(0,0,0,${0.35 * frozen})`}} />
    </AbsoluteFill>
  );
};
