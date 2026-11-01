import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {castFor, side} from '../lib/cast';
import {clamp, fmt, lin, sdb, seg} from '../lib/motion';
import {Chip, ChipKind, Kept, Receipt, Struck} from '../ui';
import {hexA, theme} from '../theme';
import type {ProofData, Turn} from '../lib/types';

// The X-ray freeze (spec 5.1): the frozen frame underneath, paper cards rising column by column, one 54 px caption
// per beat, a chip on every card saying who did it (a Meta model or Hallwise code), and a receipt that lets anyone
// check the value. Eleven beats, then the notification card the owner actually saw lands last, bottom-right.
//
// It is a composite: the sound beats and the French turn come from the 4-channel rehearsal frozen at `freezeMs`;
// the recall, the hook, the retired comparison come from run 51b4 on its own clock; the edge and the check from the
// aside take; the page from a saved one-pager. The stamp says so, and every card's receipt names its source.
// Everything tied to the frozen moment (regions, names) is a function of t: nothing the badge had not heard by
// `freezeMs` is drawn.
export type XRayProps = {
  data: ProofData;
  freezeMs: number; // where the footage froze (the end of "One page with numbers tomorrow.")
  beatSeconds?: number; // 0.85 s per beat (spec 4)
  transparent?: boolean; // no frame underneath: for a ProRes 4444 overlay
  beats?: number[]; // which beats to show, 1..12 (the fallback without 4 and 5 while the FOA comparison is PENDING)
};

const N = 12;

// ---- small svg helpers
const area = (arr: (number | null)[], w: number, h: number, lo: number, hi: number, step = 2, from = 0, to = arr.length) => {
  const n = arr.length;
  let d = `M${(from / n) * w} ${h}`;
  for (let i = from; i < to; i += step) {
    const v = arr[i] == null ? lo : clamp(arr[i] as number, lo, hi);
    d += ` L${((i / n) * w).toFixed(1)} ${(h - ((v - lo) / (hi - lo)) * h).toFixed(1)}`;
  }
  return d + ` L${(Math.min(to, n) / n) * w} ${h} Z`;
};

const Lab: React.FC<{x: number; y: number; on?: boolean; anchor?: 'start' | 'middle' | 'end'; children: React.ReactNode; size?: number}> = ({x, y, on, anchor = 'start', children, size = 14}) => (
  <text x={x} y={y} textAnchor={anchor} fontFamily={theme.mono} fontSize={size} fill={on ? theme.accent : theme.inkSoft} letterSpacing="0.06em">
    {children}
  </text>
);

type Body = (w: number, h: number, p: number, frame: number, at: number) => React.ReactNode;

export const XRay: React.FC<XRayProps> = ({data, freezeMs, beatSeconds = 0.85, transparent, beats}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const STEP = Math.round(fps * beatSeconds);
  const LAND = Math.round(fps * 0.45);
  const r = data.rec3f3e;
  const win = r.window;
  const run = data.run1;
  const acc = data.accent;
  const op = data.onepager;
  const res = data.research;
  const code = data.code;
  const C3 = castFor(r);
  const C51 = castFor(run);
  const show = beats ?? Array.from({length: N}, (_, i) => i + 1);
  const order = show; // beat numbers in landing order
  const landed = Math.min(order.length, Math.floor(frame / STEP) + 1); // how many have landed (the first lands at frame 0)
  const all = frame >= order.length * STEP + STEP * 0.5;
  const current = landed; // 1-based index into order
  const fz = (freezeMs / 1000).toFixed(1);
  const runId = `run ${run.id.slice(-4)}`;

  // ---- the window shown by the sound beats
  const sx = (ms: number, w: number) => ((ms - win.t0) / (win.t1 - win.t0)) * w;
  const turnsIn = r.turns.filter((t) => t.end_ms > win.t0 && t.start_ms < win.t1);
  const playhead = (w: number, h: number) => <line x1={sx(freezeMs, w)} y1={-4} x2={sx(freezeMs, w)} y2={h + 4} stroke={theme.live} strokeWidth={2} />;
  const col = (t: Turn) => C3.color(t.speaker, 'paper');

  // 01 four channels: the envelope of each channel, coloured by whoever is speaking (hud drawChannels)
  const b1: Body = (w, h, p) => {
    const rows = r.channel_names;
    const rh = h / rows.length;
    const tw = w - 34 - 40;
    const n = win.rms_db[rows[0]].length;
    const upto = Math.floor(n * clamp(p * 1.6));
    return (
      <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} style={{overflow: 'visible'}}>
        {rows.map((c, i) => {
          const y = i * rh;
          const arr = win.rms_db[c];
          return (
            <g key={c} transform={`translate(34 ${y})`}>
              <path d={area(arr, tw, rh - 3, -62, -14, 2, 0, upto)} fill={theme.inkSoft} opacity={0.28} />
              {turnsIn.map((t) => {
                const i0 = clamp(Math.floor((t.start_ms - win.t0) / win.step_ms), 0, n);
                const i1 = clamp(Math.ceil((t.end_ms - win.t0) / win.step_ms), 0, Math.min(n, upto));
                if (i1 <= i0) return null;
                return <path key={t.turn} d={area(arr, tw, rh - 3, -62, -14, 2, i0, i1)} fill={col(t)} opacity={i === 0 ? 0.9 : 0.6} />;
              })}
              <Lab x={-34} y={rh - 6} on={i === 0}>
                {c}
              </Lab>
            </g>
          );
        })}
        <g transform="translate(34 0)">{playhead(tw, h)}</g>
        {/* the W channel peels off toward the transcriber */}
        <path d={`M${34 + tw} ${rh / 2} C ${34 + tw + 18} ${rh / 2}, ${34 + tw + 18} ${h - 8}, ${w} ${h - 8}`} fill="none" stroke={theme.accent} strokeWidth={2} strokeDasharray={200} strokeDashoffset={200 - 200 * clamp((p - 0.5) * 2)} />
        <circle cx={w} cy={h - 8} r={4} fill={theme.accent} opacity={clamp((p - 0.8) * 5)} />
      </svg>
    );
  };

  // 02 the leveler's gain ribbon, coloured by who is speaking (hud drawGain); the axis is the leveler's own cap
  const CAP = code.leveler.max_boost_db;
  const youIn = turnsIn.filter((t) => C3.of(t.speaker).p === 'owner' && t.gain_db != null).map((t) => t.gain_db as number);
  const guestsIn = turnsIn.filter((t) => C3.of(t.speaker).p !== 'owner' && t.gain_db != null).map((t) => t.gain_db as number);
  const mean = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
  const b2: Body = (w, h, p) => {
    const g = win.gain_db;
    const top = 16,
      bot = h - 16;
    const yOf = (v: number) => bot - ((clamp(v, -CAP, CAP) + CAP) / (2 * CAP)) * (bot - top);
    const zero = yOf(0);
    const tw = w - 34;
    const n = g.length;
    const upto = Math.floor(n * clamp(p * 1.6));
    return (
      <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} style={{overflow: 'visible'}}>
        <line x1={34} y1={zero} x2={w} y2={zero} stroke={theme.rule} strokeWidth={1.5} />
        <g transform={`translate(34 ${top})`}>
          <path d={area(g, tw, bot - top, -CAP, CAP, 2, 0, upto)} fill={theme.inkSoft} opacity={0.22} />
          {turnsIn.map((t) => {
            const i0 = clamp(Math.floor((t.start_ms - win.t0) / win.step_ms), 0, n);
            const i1 = clamp(Math.ceil((t.end_ms - win.t0) / win.step_ms), 0, Math.min(n, upto));
            if (i1 <= i0) return null;
            let d = `M${(i0 / n) * tw} ${zero - top}`;
            for (let i = i0; i < i1; i++) d += ` L${((i / n) * tw).toFixed(1)} ${(yOf(g[i] ?? 0) - top).toFixed(1)}`;
            d += ` L${(i1 / n) * tw} ${zero - top} Z`;
            return <path key={t.turn} d={d} fill={col(t)} opacity={0.85} />;
          })}
          {playhead(tw, bot - top)}
        </g>
        {[CAP, 0, -CAP].map((v) => (
          <g key={v}>
            <line x1={28} x2={34} y1={yOf(v)} y2={yOf(v)} stroke={theme.inkSoft} strokeWidth={1.5} />
            <Lab x={24} y={yOf(v) + 4} anchor="end" size={12}>
              {v > 0 ? `+${v}` : v}
            </Lab>
          </g>
        ))}
        <Lab x={w} y={11} anchor="end" size={12} on>
          you {sdb(mean(youIn))} · guests {sdb(Math.min(...guestsIn))} … {sdb(Math.max(...guestsIn))}
        </Lab>
        <Lab x={w} y={h - 1} anchor="end" size={11}>
          target {code.leveler.target_db} dBFS · {code.leveler.ratio}:1 · cap ±{CAP} dB · 10 ms steps
        </Lab>
      </svg>
    );
  };

  // 03 names expected: the count, the two accuracy strips (without / with hints), and one voice's two readings
  const fr = acc.rows.find((x) => x.id === 'fr_f') ?? acc.rows[0];
  const said = (s: string) => {
    const m = s.match(/I['’]m (.*?)\. /);
    return m ? m[1] : s;
  };
  const b3: Body = (w, h, p) => {
    const cell = (w - 92) / acc.voices;
    const strip = (y: number, key: 'nohints' | 'hints', label: string) => (
      <g key={key}>
        <Lab x={0} y={y + 9} on={key === 'hints'}>
          {label}
        </Lab>
        {acc.rows.map((row, i) => {
          const v = row[key].name;
          const on = i < acc.voices * clamp(p * 1.4);
          return <rect key={row.id} x={92 + i * cell} y={y} width={cell - 2} height={10} rx={2} fill={v === 'yes' ? theme.accent : v === 'no' ? theme.rule : theme.inkSoft} opacity={on ? (v === 'yes' ? 0.95 : 0.55) : 0.15} />;
        })}
      </g>
    );
    return (
      <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} style={{overflow: 'visible'}}>
        <text x={0} y={30} fontFamily={theme.serif} fontSize={34} fontWeight={600} fill={theme.inkStrong}>
          {acc.name_nohints} → {acc.name_hints}
        </text>
        <text x={150} y={30} fontFamily={theme.sans} fontSize={17} fill={theme.ink}>
          of {acc.voices} names right, {acc.accents.length} accents
        </text>
        {strip(40, 'nohints', 'no hints')}
        {strip(54, 'hints', 'hints')}
        <Lab x={0} y={80}>
          no hints
        </Lab>
        <text x={92} y={80} fontFamily={theme.serif} fontStyle="italic" fontSize={17} fill={theme.inkSoft}>
          {said(fr.nohints.text)}
        </text>
        <Lab x={0} y={98} on>
          hints
        </Lab>
        <text x={92} y={98} fontFamily={theme.serif} fontStyle="italic" fontSize={17} fill={theme.accent}>
          {said(fr.hints.text)}
        </text>
        <Lab x={w} y={h - 1} anchor="end" size={10.5}>
          hints: up to {code.hints.MAX_HINT_NAMES} names + {code.hints.MAX_HINT_COMPANIES} companies (people index) · not logged
        </Lab>
      </svg>
    );
  };

  // 04 voices as soft regions, as the badge had them at the freeze: only turns that had ended by then, the
  // confidence-weighted circular mean of each guest's turns (as direction.SpeakerPositions does), the width from
  // their spread; the name is the one logged by then, else "a voice"; words only, never a degree
  const regions = (() => {
    const by: Record<string, Turn[]> = {};
    for (const t of r.turns) if (t.end_ms <= freezeMs) (by[t.speaker] = by[t.speaker] || []).push(t);
    const out: {spk: string; az: number; spread: number; conf: number; level: number; n: number; first: number}[] = [];
    let loud = -99;
    for (const [spk, ts] of Object.entries(by)) {
      if (C3.at(spk, freezeMs).p === 'owner') continue;
      let c = 0,
        s = 0,
        wt = 0,
        lv = 0;
      for (const t of ts) {
        const k = Math.max(t.conf3d ?? 0, 0.05);
        c += k * Math.cos(((t.az ?? 0) * Math.PI) / 180);
        s += k * Math.sin(((t.az ?? 0) * Math.PI) / 180);
        wt += k;
        lv += t.level_db ?? -60;
      }
      const R = Math.hypot(c, s) / wt;
      out.push({spk, az: (Math.atan2(s, c) * 180) / Math.PI, spread: R < 1 ? (Math.sqrt(-2 * Math.log(Math.max(R, 1e-6))) * 180) / Math.PI : 0, conf: wt / ts.length, level: lv / ts.length, n: ts.length, first: Math.min(...ts.map((t) => t.start_ms))});
      loud = Math.max(loud, lv / ts.length);
    }
    return out.map((g) => ({...g, dist: clamp(0.44 + ((loud - g.level) / 18) * 0.5, 0.36, 1)}));
  })();
  // the check that no region leaks from after the freeze (tools/extract_data.py keeps the same list in at_freeze)
  const leak = regions.filter((g) => g.first > freezeMs);
  if (leak.length) throw new Error(`X-ray: a region's first turn is after the freeze: ${leak.map((g) => g.spk).join(', ')}`);
  if (freezeMs === r.freeze_ms) {
    const want = r.at_freeze.regions.join(',');
    const have = regions.map((g) => g.spk).sort().join(',');
    if (want !== have) throw new Error(`X-ray: regions at the freeze differ from extract_data.py (${have} vs ${want})`);
  }
  const b4: Body = (w, h, p) => {
    const cx = w * 0.3,
      cy = h + 6,
      R0 = h - 4;
    const pt = (a: number, q: number) => [cx - Math.sin(a) * q, cy - Math.cos(a) * q];
    const legend = [...regions].sort((a, b) => b.az - a.az);
    return (
      <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} style={{overflow: 'visible'}}>
        <defs>
          <filter id="xr-soft" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation={9} />
          </filter>
        </defs>
        <path d={`M${cx - R0} ${cy} A${R0} ${R0} 0 0 1 ${cx + R0} ${cy}`} fill="none" stroke={theme.inkSoft} strokeWidth={2} opacity={0.6} />
        <path d={`M${cx - R0 * 0.5} ${cy} A${R0 * 0.5} ${R0 * 0.5} 0 0 1 ${cx + R0 * 0.5} ${cy}`} fill="none" stroke={theme.inkSoft} strokeWidth={2} strokeDasharray="8 10" opacity={0.5} />
        <Lab x={cx - R0 - 8} y={cy - 2} anchor="end">
          left
        </Lab>
        <Lab x={cx + R0 + 8} y={cy - 2}>
          right
        </Lab>
        {regions.map((g, i) => {
          const q = clamp(p * 1.3 - i * 0.08);
          const half = clamp(Math.max(g.spread, 10) + (1 - g.conf) * 26, 14, 56);
          const rr = R0 * g.dist;
          const a0 = ((g.az - half) * Math.PI) / 180,
            a1 = ((g.az + half) * Math.PI) / 180;
          const [x0, y0] = pt(a0, rr - 22),
            [x1, y1] = pt(a1, rr - 22),
            [x2, y2] = pt(a1, rr + 22),
            [x3, y3] = pt(a0, rr + 22);
          return <path key={g.spk} opacity={q} d={`M${x0} ${y0} A${rr - 22} ${rr - 22} 0 0 0 ${x1} ${y1} L${x2} ${y2} A${rr + 22} ${rr + 22} 0 0 1 ${x3} ${y3} Z`} fill={C3.color(g.spk, 'paper')} fillOpacity={0.25 + 0.4 * g.conf} filter="url(#xr-soft)" style={{mixBlendMode: 'multiply'}} />;
        })}
        <circle cx={cx} cy={cy - 2} r={7} fill={theme.ink} />
        <Lab x={cx + 12} y={cy - 2}>
          you
        </Lab>
        {legend.map((g, i) => {
          const sp = r.speaker_positions[g.spk];
          const low = (sp && sp.t_ms <= freezeMs && sp.low_confidence) || g.conf < code.WEARER_MIN_CONFIDENCE;
          const c = C3.at(g.spk, freezeMs);
          const y = 14 + i * Math.min(20, (h - 30) / Math.max(legend.length, 1));
          const x = w * 0.6;
          return (
            <g key={g.spk} opacity={clamp(p * 1.3 - i * 0.08)}>
              <circle cx={x} cy={y - 5} r={5} fill={C3.color(g.spk, 'paper')} />
              <text x={x + 12} y={y} fontFamily={theme.sans} fontSize={15} fontWeight={700} fill={C3.color(g.spk, 'paper')}>
                {c.short}
                {low ? '?' : ''}
              </text>
              <Lab x={x + 12 + (c.short.length + (low ? 1 : 0)) * 8.6 + 8} y={y} size={12}>
                {side(g.az)}
              </Lab>
            </g>
          );
        })}
        <Lab x={w * 0.6} y={h - 14} size={10.5}>
          {regions.length} voices by {fz} s · ? = unsure
        </Lab>
      </svg>
    );
  };

  // 05 your voice, from above (blueprint's side view): an UP axis, the dashed wearer threshold (a code constant),
  // the wearer's blob above it, guests near level; no degrees anywhere. On this rehearsal the owner was found from
  // the transcript (Muse Spark); the Wearer medians are a re-run offline, on a mix that places the owner high.
  const b5: Body = (w, h, p) => {
    const bx = 64,
      by = h - 24;
    const med = r.wearer?.medians ?? {};
    const found = r.wearer?.found?.[0];
    const ray = (deg: number, len: number) => [bx + Math.cos((deg * Math.PI) / 180) * len, by - Math.sin((deg * Math.PI) / 180) * len];
    const [tx, ty] = ray(code.WEARER_MIN_ELEVATION, h - 26);
    return (
      <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} style={{overflow: 'visible'}}>
        <defs>
          <filter id="xr-soft2" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation={8} />
          </filter>
        </defs>
        <line x1={bx} y1={by} x2={bx} y2={4} stroke={theme.inkSoft} strokeWidth={1.5} opacity={0.5} />
        <polygon points={`${bx - 4},10 ${bx + 4},10 ${bx},2`} fill={theme.inkSoft} opacity={0.6} />
        <Lab x={bx - 10} y={12} anchor="end" size={12}>
          up
        </Lab>
        <line x1={bx} y1={by} x2={w - 10} y2={by} stroke={theme.rule} strokeWidth={1.5} />
        <line x1={bx} y1={by} x2={tx} y2={ty} stroke={theme.inkSoft} strokeWidth={2} strokeDasharray="8 10" pathLength={100} strokeDashoffset={100 - 100 * clamp(p * 1.4)} />
        <Lab x={w - 10} y={12} anchor="end" size={12}>
          dashed: wearer threshold · code constant
        </Lab>
        <Lab x={w - 10} y={h - 1} anchor="end" size={10.5}>
          Wearer re-run offline · this mix places the owner high
        </Lab>
        {Object.entries(med).map(([spk, m], i) => {
          const own = spk === found;
          const q = clamp(p * 1.3 - i * 0.1);
          const [x, y] = ray(m, own ? h - 44 : w * 0.42);
          return (
            <g key={spk} opacity={q}>
              <ellipse cx={x} cy={y} rx={own ? 30 : 56} ry={own ? 16 : 11} fill={C3.color(spk, 'paper')} fillOpacity={0.5} filter="url(#xr-soft2)" transform={`rotate(${-m} ${x} ${y})`} style={{mixBlendMode: 'multiply'}} />
              {own ? (
                <text x={x + 44} y={y + 2} fontFamily={theme.sans} fontSize={16} fontWeight={700} fill={theme.ink}>
                  you ← wearer · from above
                </text>
              ) : null}
            </g>
          );
        })}
        <rect x={bx - 7} y={by - 12} width={12} height={18} rx={2} fill={theme.paper} stroke={theme.ink} strokeWidth={2} />
        <Lab x={w - 10} y={by - 30} anchor="end" size={12}>
          guests, near level
        </Lab>
        <Lab x={bx + 12} y={h - 13} size={10.5}>
          rule: median ≥ {code.WEARER_MIN_ELEVATION}°, {code.WEARER_MARGIN}° above every other voice, ≥ {code.WEARER_MIN_TURNS} turns
        </Lab>
      </svg>
    );
  };

  // ---- rows for the word and check cards
  const Rows: React.FC<{children: React.ReactNode; gap?: number}> = ({children, gap = 5}) => <div style={{display: 'flex', flexDirection: 'column', gap, fontSize: 15.5, lineHeight: 1.22}}>{children}</div>;
  const Row: React.FC<{mark: React.ReactNode; markColor?: string; src?: React.ReactNode; children: React.ReactNode; p?: number; lines?: number; soft?: boolean}> = ({mark, markColor, src, children, p = 1, lines = 2, soft}) => (
    <div style={{display: 'flex', alignItems: 'baseline', gap: 10, opacity: p, transform: `translateY(${(1 - p) * 6}px)`, color: soft ? theme.inkSoft : theme.ink}}>
      <span style={{fontWeight: 700, width: 20, flex: 'none', color: markColor ?? theme.ink}}>{mark}</span>
      <span style={{flex: 1, minWidth: 0, display: '-webkit-box', WebkitLineClamp: lines, WebkitBoxOrient: 'vertical', overflow: 'hidden'}}>{children}</span>
      {src ? <span style={{fontFamily: theme.mono, fontSize: 11.5, lineHeight: 1.25, color: theme.inkSoft, marginLeft: 'auto', flex: 'none', maxWidth: '40%', textAlign: 'right', overflowWrap: 'anywhere', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden'}}>{src}</span> : null}
    </div>
  );
  const I: React.FC<{children: React.ReactNode}> = ({children}) => <i style={{fontFamily: theme.serif}}>{children}</i>;
  const K: React.FC<{children: React.ReactNode}> = ({children}) => <span style={{fontFamily: theme.mono, fontSize: 13.5, color: theme.inkSoft, marginRight: 6}}>{children}</span>;
  const s1 = (ms: number, d = 1) => `${(ms / 1000).toFixed(d)} s`;

  // 06 a known name, instantly (recall.py, no model call), from run 51b4 on its own clock
  const ph = run.person_history.find((x) => x.key.startsWith('kenji') && x.provisional);
  const phConfirmed = run.person_history.find((x) => x.key.startsWith('kenji') && !x.provisional);
  const kt = run.turns.find((t) => t.turn === ph?.turn);
  const b6: Body = (_w, _h, p) =>
    ph && kt ? (
      <Rows>
        <Row mark="●" markColor={C51.color(kt.speaker, 'paper')} src={`${runId} · turn ${kt.turn}`} p={clamp(p * 1.5)}>
          <I>“{kt.text}”</I>
        </Row>
        <Row mark="◎" markColor={theme.accent} src={`person_history ${s1(ph.t_ms)}`} p={clamp(p * 1.5 - 0.3)}>
          <b>met before</b> · matched: {ph.matched} · {ph.encounters.map((e) => e.event).join(', ')}
        </Row>
        <Row mark="✓" markColor={theme.accent} src={phConfirmed ? s1(phConfirmed.t_ms) : ''} p={clamp(p * 1.5 - 0.6)} lines={1}>
          provisional, then confirmed by the next Muse Spark run
        </Row>
      </Rows>
    ) : null;

  // 07 Chloé's colleague · Oct 23, from the log, not a model (hooks.py); the hook fired in run 51b4 at 80.6 s
  const hook = run.hooks.find((hh) => hh.title.startsWith('Chloé'))!;
  const evq = data.evidence.chloe;
  const hookLabel = Object.entries(run.cast).find(([, c]) => c.key === hook.person_key)?.[0] ?? '';
  const hookPerson = hookLabel ? C51.at(hookLabel, hook.t_ms) : {name: run.people_final[hook.person_key]?.name ?? hook.person_key};
  const hookColor = hookLabel ? C51.color(hookLabel, 'paper') : theme.accent;
  const b7: Body = (_w, _h, p) => {
    const q = evq.turn.text;
    const idx = q.indexOf('My colleague');
    const before = idx >= 0 ? q.slice(0, idx) : q;
    const mid = idx >= 0 ? q.slice(idx).split(' ').slice(0, 3).join(' ') : '';
    const after = idx >= 0 ? q.slice(idx + mid.length) : '';
    return (
      <Rows>
        <Row mark={evq.date} markColor={theme.inkSoft} p={clamp(p * 1.5)} src={`evidence ${evq.id.slice(-4)} · turn ${evq.turn.turn}`}>
          <I>
            “{before}
            <Kept p={clamp(p * 2 - 0.6)} color={hookColor}>
              {mid}
            </Kept>
            {after}”
          </I>
        </Row>
        <Row mark="→" markColor={theme.accent} src={`${runId} · hook ${s1(hook.t_ms)}`} p={clamp(p * 1.5 - 0.4)}>
          <b>{hook.title}</b> · on <span style={{color: hookColor, fontWeight: 700}}>{hookPerson.name}</span>, the voice that just said her name
        </Row>
      </Rows>
    );
  };

  // 08 each model's output, labelled, each with the log it comes from
  const t11 = r.turns.find((t) => t.turn === 11)!;
  const onePager = r.promises['one-pager-to-margot-lefevre'];
  const coffee = r.promises['coffee-to-kenji-watanabe-hoshizora-robotics'];
  const sparkEdge = data.aside.spark.kept_edges[0];
  const sparkRecord = data.aside.spark.calls.find((c) => c.name === 'hallwise_record');
  const finderCall = data.aside.finder.c_final.calls[0];
  const finderEdge = finderCall.kept.find((e) => e.said === data.aside.aside_turn) ?? finderCall.kept[0];
  const LRow: React.FC<{chip: string; p: number; children: React.ReactNode; soft?: boolean}> = ({chip, p, children, soft}) => (
    <div style={{display: 'grid', gridTemplateColumns: 'auto minmax(0,1fr)', gap: '4px 10px', alignItems: 'center', fontSize: 14.5, lineHeight: 1.2, opacity: p, transform: `translateY(${(1 - p) * 6}px)`}}>
      <Chip size={11.5} style={{padding: '1px 8px 2px'}}>
        {chip}
      </Chip>
      <div style={{display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden', color: soft ? theme.inkSoft : theme.ink}}>{children}</div>
    </div>
  );
  const b8: Body = (_w, _h, p) => (
    <div style={{display: 'flex', flexDirection: 'column', gap: 3}}>
      <LRow chip="Muse Voice Transcribe" p={clamp(p * 1.6)}>
        <K>{r.id.slice(-4)} · turn {t11.turn} · {t11.speaker}</K>
        <I>{t11.text}</I>
      </LRow>
      <LRow chip="Muse Spark" p={clamp(p * 1.6 - 0.2)}>
        <K>translation {s1(t11.translation?.t_ms ?? 0)}</K>
        {t11.translation?.english} <K>promise</K>
        {onePager?.what} · {onePager?.due}
      </LRow>
      <LRow chip="Muse Spark" p={clamp(p * 1.6 - 0.4)}>
        <K>promise corrected {s1(coffee.replaced_at ?? coffee.t_ms)}</K>
        coffee · <Struck p={clamp(p * 2 - 0.9)}>{coffee.replaces}</Struck> <b>{coffee.due}</b> · its own <K>replaces</K>field, no code check
      </LRow>
      <LRow chip="Muse Spark" p={clamp(p * 1.6 - 0.55)}>
        <K>edge · record call</K>
        <I>“{sparkEdge.said}”</I> · act: {sparkEdge.act} <K>{fmt(sparkRecord?.total_tokens ?? 0)} tokens</K>
      </LRow>
      <LRow chip="Muse Spark Open" p={clamp(p * 1.6 - 0.7)}>
        <K>edge · finder call {finderCall.call}</K>
        <I>“{finderEdge.said}”</I> · {finderCall.seconds} s · {fmt(finderCall.usage.total_tokens)} tokens · {finderCall.kept.length} of {finderCall.raw} kept
      </LRow>
      <LRow chip="SAM 3.1" p={clamp(p * 1.6 - 0.85)} soft>
        <K>photo</K>no photo this evening; faces are found only when one is taken
      </LRow>
    </div>
  );

  // 09 the code strikes what isn't backed: the edge finder's edge the check dropped (said joins two turns), the one
  // it kept (her words in one turn of her own voice), and the retired comparison's withdrawn confirmation
  const dropped = data.aside.finder.c.calls[0].dropped[0];
  const droppedCall = data.aside.finder.c.calls[0];
  const dis = run.disagreement!;
  const conf = run.confirmed.find((c) => c.key === dis.key)!;
  const rm = run.confirmed_removed[0];
  const sr5 = run.second_runs.find((s) => s.disagreed > 0) ?? run.second_runs[run.second_runs.length - 1];
  const disLabel = Object.entries(run.cast).find(([, c]) => c.key === dis.key)?.[0] ?? '';
  const disName = disLabel ? C51.at(disLabel, dis.t_ms).name : (run.people_final[dis.key]?.name ?? dis.key);
  const droppedShort = dropped.said.length > 70 ? dropped.said.slice(0, 38).trimEnd() + ' … / ' + dropped.said.slice(dropped.said.indexOf(' / ') + 3) : dropped.said;
  const b9: Body = (_w, _h, p, fr_, at) => {
    const strike1 = seg(fr_, at + Math.round(fps * 0.4), Math.round(fps * 0.35));
    const strike2 = seg(fr_, at + Math.round(fps * 0.65), Math.round(fps * 0.3));
    return (
      <Rows gap={4}>
        <Row mark="✕" markColor={theme.live} src={`${data.aside.finder.c.file.replace('.txt', '')} call ${droppedCall.call} · joins turns ${dropped.turns.join('+')} · raw ${droppedCall.raw} → kept ${droppedCall.kept.length}`} p={clamp(p * 1.5)}>
          <Struck p={strike1} multiline>
            <I>“{droppedShort}”</I>
          </Struck>
        </Row>
        <Row mark="✓" markColor={theme.accent} src={`${data.aside.finder.c_final.file.replace('.txt', '')} call ${finderCall.call} · raw ${finderCall.raw} → kept ${finderCall.kept.length}`} p={clamp(p * 1.5 - 0.25)}>
          <I>“{finderEdge.said}”</I> · in turn {finderEdge.turns[finderEdge.turns.length - 1]}, her own voice →{' '}
          <Kept p={clamp(p * 2 - 0.5)}>
            <b>kept</b>
          </Kept>
        </Row>
        <Row mark="✕" markColor={theme.live} src={`${run.id.slice(-4)} · disagreement ${s1(dis.t_ms)} · retired comparison`} p={clamp(p * 1.5 - 0.5)}>
          <Struck p={strike2}>{disName} · {dis.a.text} · confirmed</Struck> · “{dis.a.text}” vs “{dis.b.text}”
        </Row>
      </Rows>
    );
  };

  // 10 research: no source, no line (research.py ground); the app's own partial wording, by line
  const L = data.app_labels;
  const b10: Body = (_w, _h, p) => (
    <Rows gap={4}>
      {res.findings.map((f, i) => (
        <Row key={f.kind} mark="✓" markColor={theme.accent} src={f.source.replace('https://', '')} p={clamp(p * 1.6 - i * 0.2)} lines={1}>
          <K>{f.kind}</K>
          {f.text}
        </Row>
      ))}
      <Row mark="—" markColor={theme.live} src={`status ${res.status} · “${(data.decoy?.title ?? 'a same-name page').split('|')[0].trim()}” (same name) is not in it`} p={clamp(p * 1.6 - 0.5)} lines={1}>
        <K>profile</K>nothing public ties Julien to Corvane
      </Row>
      <Row mark="!" markColor={theme.live} src={L.partial_note_source.split(' · ')[0]} p={clamp(p * 1.6 - 0.7)} lines={1}>
        <b>{L.partial_note}</b>
      </Row>
    </Rows>
  );

  // 11 the deck, rebuilt: 12 slide bars → one page of figures, each tied to its slide (onepager.numbers)
  const lit = new Set(op.links.flatMap((l) => l.slides));
  const b11: Body = (w, h, p) => {
    const px = 12 * 12 + 44;
    return (
      <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} style={{overflow: 'visible'}}>
        {op.deck_slides.map((_, i) => (
          <rect key={i} x={i * 12} y={h / 2 - 20} width={9} height={40} rx={2} fill={lit.has(i) && p > 0.5 ? theme.accent : theme.rule} opacity={clamp(p * 3 - i * 0.1)} />
        ))}
        <path d={`M${12 * 12 + 2} ${h / 2} L ${12 * 12 + 24} ${h / 2}`} stroke={theme.ink} strokeWidth={2.5} strokeLinecap="round" opacity={clamp(p * 2 - 0.5)} />
        <polygon points={`${12 * 12 + 24},${h / 2 - 5} ${12 * 12 + 33},${h / 2} ${12 * 12 + 24},${h / 2 + 5}`} fill={theme.ink} opacity={clamp(p * 2 - 0.5)} />
        <Lab x={0} y={h - 1} size={10.5}>
          LiveRebuild · not yet live
        </Lab>
        <g opacity={clamp(p * 2 - 0.8)}>
          <rect x={px} y={1} width={w - px} height={h - 2} rx={4} fill="#fff" stroke={theme.rule} />
          <Lab x={px + 10} y={h - 7} size={11}>
            {op.page.figures.length} figures, each tied to a slide · {op.model}
          </Lab>
          {op.page.figures.map((f, i) => {
            const c = i % 3,
              row = Math.floor(i / 3),
              cw = (w - px - 16) / 3;
            return (
              <text key={i} x={px + 10 + c * cw} y={26 + row * 25} fontFamily={theme.serif} fontSize={20} fontWeight={600} fill={theme.accent}>
                {f.value}
              </text>
            );
          })}
        </g>
      </svg>
    );
  };

  type Beat = {n: number; title: string; cap: string; body: Body; h: number; chips: [ChipKind, string][]; rec: React.ReactNode[]};
  const BEATS: Beat[] = [
    {n: 1, title: 'Four channels in', cap: 'Four channels in. The original is kept.', body: b1, h: 72, chips: [['code', 'code · recording.py'], ['code', `W → transcriber · ${code.ASR_RATE / 1000} kHz`]], rec: [r.id.slice(-4), `audio.wav · ${r.channels} ch ${r.layout} · ${r.sample_rate / 1000} kHz`]},
    {n: 2, title: 'Levelled for the transcriber', cap: 'Levelled for the transcriber: you down, far guests up.', body: b2, h: 84, chips: [['code', 'code · leveler.py']], rec: [r.id.slice(-4), 'xray.json lev · re-run offline on audio.wav']},
    {n: 3, title: 'Names expected before anyone speaks', cap: 'Names expected before anyone speaks.', body: b3, h: 108, chips: [['model', 'Muse Voice Transcribe'], ['code', 'code · recording.py']], rec: [acc.file, `${acc.voices} voices · ${acc.accents.length} accents`]},
    {n: 4, title: 'Voices placed as soft regions', cap: 'Voices placed as soft regions, never degrees.', body: b4, h: 92, chips: [['code', 'code · direction.py'], ['pending', 'pending · FOA']], rec: [r.id.slice(-4), `speaker_position ≤ ${fz} s`, 'recomputed from audio.wav']},
    {n: 5, title: 'Your voice, from above', cap: 'Your own voice, found because it comes from above.', body: b5, h: 92, chips: [['model', 'Muse Spark'], ['code', 'code · direction.py'], ['pending', 'pending']], rec: [r.id.slice(-4), `owner ${s1(r.owner_event?.t_ms ?? 0)} · from the transcript`]},
    {n: 6, title: 'A known name, instantly', cap: 'A known name, instantly, with no model.', body: b6, h: 104, chips: [['code', 'code · recall.py'], ['nomodel', 'no model call']], rec: [`${runId} · its own clock`, 'person_history → confirmed']},
    {n: 7, title: 'Chloé’s colleague · Oct 23', cap: 'Chloé’s colleague · Oct 23, from the log, not a model.', body: b7, h: 82, chips: [['code', 'code · hooks.py']], rec: [`${runId} · hook ${s1(hook.t_ms)}`, `evidence ${evq.id} · turn ${evq.turn.turn}`]},
    {n: 8, title: 'Each model’s output, labelled', cap: 'Each model’s output, labelled.', body: b8, h: 142, chips: [['code', 'code · events.jsonl']], rec: [`${r.id.slice(-4)} · turn ${t11.turn}`, `aside take · ${data.aside.spark.files[1]} · ${data.aside.finder.c_final.file} call ${finderCall.call}`]},
    {n: 9, title: 'The code strikes what isn’t backed', cap: 'The code strikes what the transcript doesn’t back.', body: b9, h: 116, chips: [['code', 'code · extract.py · kept_edges']], rec: ['logged by finder_check.py', 'take_edges → kept_edges · no check event yet']},
    {n: 10, title: 'Research: no source, no line', cap: 'Research: no source, no line.', body: b10, h: 112, chips: [['model', 'Muse Spark · web search'], ['code', 'code · ground']], rec: [`${res.corpus ? 'corpus run · ' : ''}${fmt(res.tokens)} tokens`, `note: ${L.partial_note_source.split(' · ')[1]}`]},
    {n: 11, title: 'The deck, rebuilt', cap: 'The deck, rebuilt. Every number held to the slides.', body: b11, h: 70, chips: [['model', 'Muse Spark'], ['code', 'code · onepager.py']], rec: [`saved page → ${run.id.slice(-4)}`, `${op.dropped.length} dropped · ${op.seconds} s · ${fmt(op.usage.total_tokens)} tokens`]},
  ];

  // columns: Sound → Words → Checks → action; the fallback (a shorter list) re-flows into the same three columns
  const DEFAULT_COL: Record<number, number> = {1: 0, 2: 0, 4: 0, 5: 0, 3: 1, 6: 1, 7: 1, 8: 1, 9: 2, 10: 2, 11: 2};
  const cards = order.filter((n) => n !== 12);
  const colOf = (n: number) => {
    if (!beats) return DEFAULT_COL[n];
    const per = Math.ceil(cards.length / 3);
    return Math.min(2, Math.floor(cards.indexOf(n) / per));
  };
  const colW = (1824 - 56) / 3;
  const inner = colW - 36;
  const heads = [['Sound', '→'], ['Words', '→'], ['Checks → action', '']];
  const indexOf = (n: number) => order.indexOf(n); // landing index, -1 if hidden
  const beatState = (n: number) => {
    const i = indexOf(n);
    if (i < 0) return {visible: false, at: 0, p: 0, lit: false, done: false};
    const at = i * STEP;
    const p = seg(frame, at, LAND);
    const isLit = !all && i === current - 1;
    return {visible: i < landed, at, p, lit: isLit, done: !isLit && i < landed};
  };
  const pendingShown = order.includes(4) || order.includes(5);

  const capBeat = all ? null : order[current - 1];
  const caption = all
    ? 'The machinery, from three takes: sound, words, checks, action.'
    : capBeat === 12
      ? 'The buzz. What the owner saw; everything above is why.'
      : (BEATS.find((b) => b.n === capBeat)?.cap ?? '');
  const capN = all ? `${order.length} / ${order.length}` : `${String(current).padStart(2, '0')} / ${order.length}`;
  const capP = all ? 1 : seg(frame, (current - 1) * STEP, Math.round(fps * 0.3));
  const dark = theme.darkInk;

  // the buzz card (beat 12)
  const s12 = beatState(12);
  const ring = s12.visible ? lin(frame, s12.at, Math.round(fps * 0.9)) : 0;

  return (
    <AbsoluteFill style={{backgroundColor: transparent ? 'transparent' : undefined, fontFamily: theme.sans}}>
      {/* stamp: a composite of three takes and a saved page, and the frame says which is which */}
      <div style={{position: 'absolute', left: 48, top: 30, display: 'flex', alignItems: 'center', gap: 16}}>
        <span style={{fontFamily: theme.mono, fontSize: 21, letterSpacing: '0.18em', textTransform: 'uppercase', color: dark, padding: '5px 13px', border: `2px solid ${dark}`, borderRadius: 8}}>X-ray</span>
        <div>
          <Receipt dark size={18} parts={[r.id, `frozen at ${fz} s`, `${r.event} · ${r.venue}`]} style={{display: 'block'}} />
          <Receipt dark size={14} parts={['composite', `+ ${runId} on its own clock`, 'the aside take', 'a saved page', 'each card names its source']} style={{display: 'block', marginTop: 2}} />
        </div>
      </div>
      <div style={{position: 'absolute', right: 48, top: 34, display: 'flex', gap: 10, alignItems: 'center'}}>
        <Chip dark size={17}>
          a Meta model
        </Chip>
        <Chip dark kind="code" size={17}>
          Hallwise code
        </Chip>
        {pendingShown ? (
          <Chip kind="pending" size={17}>
            pending · FOA comparison
          </Chip>
        ) : null}
      </div>
      {/* caption */}
      <p style={{position: 'absolute', left: 48, top: 90, right: 48, fontFamily: theme.serif, fontWeight: 500, fontSize: 54, lineHeight: 1.05, letterSpacing: '-0.012em', color: dark, margin: 0, whiteSpace: 'nowrap', opacity: capP, transform: `translateY(${(1 - capP) * 10}px)`}}>
        <span style={{fontFamily: theme.mono, fontWeight: 500, fontSize: 26, letterSpacing: '0.1em', color: theme.darkInkSoft, marginRight: 18, verticalAlign: '0.5em'}}>{capN}</span>
        {caption}
      </p>
      {/* columns */}
      <div style={{position: 'absolute', left: 48, top: 182, right: 48, display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 28}}>
        {heads.map((hd, c) => (
          <div key={c}>
            <div style={{fontFamily: theme.mono, fontSize: 18, letterSpacing: '0.16em', textTransform: 'uppercase', color: theme.darkInkSoft, paddingBottom: 6, borderBottom: `1.5px solid ${theme.darkRule}`, marginBottom: 12, display: 'flex', justifyContent: 'space-between'}}>
              <span>{hd[0]}</span>
              <span>{hd[1]}</span>
            </div>
            <div style={{display: 'flex', flexDirection: 'column', gap: 10}}>
              {cards
                .filter((n) => colOf(n) === c)
                .map((n) => BEATS.find((b) => b.n === n)!)
                .map((b) => {
                  const s = beatState(b.n);
                  const shown = indexOf(b.n) + 1; // numbered in landing order, so a shorter cut still counts 01, 02, ...
                  if (!s.visible) return <div key={b.n} style={{height: b.h + 86, opacity: 0}} />;
                  return (
                    <div
                      key={b.n}
                      style={{
                        position: 'relative',
                        background: theme.paperRaised,
                        border: `1.5px solid ${theme.rule}`,
                        borderRadius: 18,
                        padding: '11px 18px 9px',
                        color: theme.ink,
                        opacity: s.p * (s.done ? 0.86 : 1),
                        transform: `translateY(${(1 - s.p) * 18}px) scale(${s.lit ? 1.02 : 1})`,
                        boxShadow: s.lit ? `0 0 0 3px ${theme.paperRaised}, 0 0 0 6px ${theme.darkAccent}, 0 18px 48px rgba(0,0,0,0.3)` : '0 2px 0 rgba(42,38,34,0.04), 0 18px 48px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.08)',
                        zIndex: s.lit ? 2 : 1,
                      }}
                    >
                      <p style={{fontFamily: theme.serif, fontWeight: 500, fontSize: 22, lineHeight: 1.1, margin: '0 0 5px', color: theme.inkStrong, display: 'flex', alignItems: 'baseline', gap: 12}}>
                        <span style={{fontFamily: theme.mono, fontWeight: 500, fontSize: 17, color: theme.inkSoft, letterSpacing: '0.08em'}}>{String(shown).padStart(2, '0')}</span>
                        {b.title}
                      </p>
                      <div style={{height: b.h, position: 'relative'}}>{b.body(inner, b.h, s.p, frame, s.at)}</div>
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginTop: 6}}>
                        <span style={{display: 'flex', gap: 6, flex: 'none'}}>
                          {b.chips.map(([k, t], i) => (
                            <Chip key={i} kind={k} size={12.5}>
                              {t}
                            </Chip>
                          ))}
                        </span>
                        <Receipt size={12} lines={2} parts={b.rec} style={{flex: 1, minWidth: 0, textAlign: 'right', lineHeight: 1.25}} />
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        ))}
      </div>
      {/* 12: the buzz, what the owner saw, lands last bottom-right (hud); the app's own strings, the run's own name */}
      {s12.visible ? (
        <div style={{position: 'absolute', right: 48, bottom: 98, width: colW}}>
          {[0, 1].map((k) => {
            const q = ring <= 0 || ring >= 1 ? 0 : clamp((ring - k * 0.18) / (1 - k * 0.18));
            if (!q) return null;
            const rr = 120 + q * 420;
            return <div key={k} style={{position: 'absolute', left: colW / 2 - rr, top: 80 - rr, width: rr * 2, height: rr * 2, borderRadius: '50%', border: `2px solid ${hexA(theme.darkLive, 0.5 * (1 - q))}`, pointerEvents: 'none'}} />;
          })}
          <div
            style={{
              position: 'relative',
              display: 'grid',
              gridTemplateColumns: '54px minmax(0, 1fr)',
              gap: 16,
              padding: '14px 20px 12px 16px',
              borderRadius: 24,
              background: 'rgba(244,240,231,0.98)',
              border: `1.5px solid ${theme.rule}`,
              boxShadow: s12.lit ? `0 0 0 3px ${theme.paperRaised}, 0 0 0 6px ${theme.darkAccent}, 0 18px 48px rgba(0,0,0,0.35)` : '0 14px 40px rgba(0,0,0,0.35)',
              opacity: s12.p,
              transform: `translateY(${(1 - s12.p) * 26}px)`,
              color: theme.ink,
            }}
          >
            <div style={{width: 54, height: 54, borderRadius: 14, background: theme.ink, color: theme.paper, display: 'grid', placeItems: 'center', fontFamily: theme.serif, fontWeight: 600, fontSize: 32}}>H</div>
            <div style={{minWidth: 0}}>
              <div style={{display: 'flex', justifyContent: 'space-between', fontFamily: theme.mono, fontSize: 15, letterSpacing: '0.1em', textTransform: 'uppercase', color: theme.inkSoft, marginBottom: 4}}>
                <span>Hallwise · on the badge</span>
                <span>now</span>
              </div>
              <p style={{fontFamily: theme.serif, fontWeight: 600, fontSize: 29, lineHeight: 1.1, color: theme.inkStrong, margin: 0}}>{L.rebuilt_headline}</p>
              <p style={{fontSize: 21, lineHeight: 1.25, margin: '4px 0 0', opacity: clamp(s12.p * 1.5 - 0.3)}}>{L.rebuilt_subline}</p>
              <div style={{marginTop: 7}}>
                <Chip kind="code" size={12.5}>
                  ios/Sources/{L.rebuilt_source}
                </Chip>
              </div>
              <Receipt size={12} lines={2} parts={[`${op.slides.length} slides → 1 page · ${op.page.figures.length} figures`, `name: ${run.id.slice(-4)} person event · cued page (onepager.find_person)`]} style={{display: 'block', marginTop: 5, lineHeight: 1.25}} />
            </div>
          </div>
        </div>
      ) : null}
      {/* tape */}
      <div style={{position: 'absolute', left: 48, right: 48, bottom: 24, display: 'flex', alignItems: 'center', gap: 10}}>
        {order.map((n, i) => (
          <span key={n} style={{height: 8, flex: 1, borderRadius: 4, background: i < landed ? (i === current - 1 && !all ? theme.darkAccent : dark) : theme.darkRule}} />
        ))}
        <Receipt dark size={17} style={{marginLeft: 12, flex: 'none'}} parts={[all ? 'composed frame' : `t = ${(frame / fps).toFixed(1)} s`, 'every value from a log, a sidecar, the finder check or a saved page']} />
      </div>
    </AbsoluteFill>
  );
};
