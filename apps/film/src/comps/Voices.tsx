import React, {useMemo} from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {castFor, side} from '../lib/cast';
import {clamp, lerp, prng, seg} from '../lib/motion';
import {Chip, Corner, Eyebrow, Frame, Receipt} from '../ui';
import {theme} from '../theme';
import type {ProofData, Turn} from '../lib/types';
import {turnAt} from './Room';

// Radar / voices (spec 5.5): soft wedges around the wearer (hud softWedge), a seeded particle stream from the live
// region to the badge, the three-row "where the sound came from, 100 ms at a time" strip from win400, and the side
// view on the right (blueprint: UP axis, dashed threshold, code constants). Words only, "?" for low confidence, both
// panels PENDING the FOA comparison. Every value is recomputed with direction.py (the xray sidecar).
export type VoicesProps = {data: ProofData; startMs: number; endMs: number; seed?: number};

const rad = (d: number) => (d * Math.PI) / 180;

export const Voices: React.FC<VoicesProps> = ({data, startMs, endMs, seed = 99}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const r = data.rec3f3e;
  const code = data.code;
  const C = castFor(r);
  const t = frame / fps;
  const playMs = startMs + (frame / durationInFrames) * (endMs - startMs);
  const live = turnAt(r, playMs);
  const nameAt = (spk: string) => C.at(spk, playMs);
  const headP = seg(frame, 0, Math.round(fps * 0.5));

  // one region per guest voice heard so far: the confidence-weighted circular mean of its turns that have ended by
  // the play time (as direction.SpeakerPositions does); nothing the badge has not heard yet is drawn
  const regions = useMemo(() => {
    const by: Record<string, Turn[]> = {};
    for (const tt of r.turns) if (tt.end_ms <= playMs) (by[tt.speaker] = by[tt.speaker] || []).push(tt);
    const out: {spk: string; az: number; spread: number; conf: number; level: number; n: number; dist: number}[] = [];
    let loud = -99;
    for (const [spk, ts] of Object.entries(by)) {
      if (C.of(spk).p === 'owner') continue;
      let c = 0,
        s = 0,
        wt = 0,
        lv = 0;
      for (const tt of ts) {
        const k = Math.max(tt.conf3d ?? 0, 0.05);
        c += k * Math.cos(rad(tt.az ?? 0));
        s += k * Math.sin(rad(tt.az ?? 0));
        wt += k;
        lv += tt.level_db ?? -60;
      }
      const R = Math.hypot(c, s) / wt;
      out.push({spk, az: (Math.atan2(s, c) * 180) / Math.PI, spread: R < 1 ? (Math.sqrt(-2 * Math.log(Math.max(R, 1e-6))) * 180) / Math.PI : 0, conf: wt / ts.length, level: lv / ts.length, n: ts.length, dist: 0});
      loud = Math.max(loud, lv / ts.length);
    }
    return out.map((g) => ({...g, dist: clamp(0.44 + ((loud - g.level) / 18) * 0.5, 0.36, 1)}));
  }, [r, Math.floor(playMs / 500)]);

  // the top view: ahead is up, the wearer's left is on the left of the picture (a positive azimuth)
  const CX = 530,
    CY = 300,
    R0 = 236;
  const pt = (az: number, rr: number) => [CX - Math.sin(rad(az)) * rr, CY - Math.cos(rad(az)) * rr];
  const wedge = (az: number, half: number, r0: number, r1: number) => {
    const [x0, y0] = pt(az - half, r0),
      [x1, y1] = pt(az + half, r0),
      [x2, y2] = pt(az + half, r1),
      [x3, y3] = pt(az - half, r1);
    return `M${x0} ${y0} A${r0} ${r0} 0 0 0 ${x1} ${y1} L${x2} ${y2} A${r1} ${r1} 0 0 1 ${x3} ${y3} Z`;
  };

  // particles: sound travelling from the live region to the badge (hud/voices.html), seeded so every render agrees
  const PART = useMemo(() => {
    const rnd = prng(seed);
    return Array.from({length: 140}, () => ({phase: rnd() * 1.6, life: 1.2 + rnd() * 0.6, j: (rnd() - 0.5) * 0.5, z: rnd()}));
  }, [seed]);
  const W4 = r.win400;
  const gate = (i: number) => (W4.level_db[i] ?? -99) > -45 && (W4.conf3d[i] ?? 0) >= code.WEARER_MIN_CONFIDENCE;
  const idxAt = (ms: number) => clamp(Math.round((ms - W4.t_ms[0]) / 100), 0, W4.t_ms.length - 1);

  const labels = regions.map((g) => ({...g, labAz: g.az}));
  const ordered = [...labels].sort((a, b) => a.labAz - b.labAz);
  for (let pass = 0; pass < 6; pass++)
    for (let i = 1; i < ordered.length; i++) {
      const gap = ordered[i].labAz - ordered[i - 1].labAz;
      if (gap < 22) {
        ordered[i].labAz += (22 - gap) / 2;
        ordered[i - 1].labAz -= (22 - gap) / 2;
      }
    }

  // the lanes strip: where the sound came from, 100 ms at a time (win400, conf >= 0.3, level > -45 dB)
  const LW = 1060,
    LH = 96;
  const laneY = (b: string) => (b === 'left' ? 16 : b === 'ahead' ? 48 : 80);

  // the side view (blueprint): UP axis, the dashed threshold, the wearer above it, guests near level
  const SW = 554,
    SH = 520,
    bx = 150,
    by = 360;
  const ray = (deg: number, len: number) => [bx + 31 + Math.cos(rad(deg)) * len, by - 23 - Math.sin(rad(deg)) * len];
  const [tx, ty] = ray(code.WEARER_MIN_ELEVATION, 300);
  const med = r.wearer?.medians ?? {},
    found = r.wearer?.found?.[0];

  return (
    <Frame>
      <div style={{position: 'absolute', left: 96, top: 58, right: 96, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 30, opacity: headP}}>
        <div style={{flex: 1}}>
          <Eyebrow size={22}>Voices around the wearer · left and right are rough, front and back unreliable</Eyebrow>
          <h1 style={{fontFamily: theme.serif, fontWeight: 500, fontSize: 58, lineHeight: 1.04, letterSpacing: '-0.012em', margin: '8px 0 0', color: theme.inkStrong, whiteSpace: 'nowrap'}}>Each voice is a region, never a number.</h1>
        </div>
        <div style={{display: 'flex', gap: 12}}>
          <Chip kind="code">code · direction.py</Chip>
          <Chip kind="pending" size={20}>
            pending · FOA comparison
          </Chip>
        </div>
      </div>

      {/* top view */}
      <div style={{position: 'absolute', left: 96, top: 214, width: 1060}}>
        <svg width={1060} height={590} viewBox="0 0 1060 590" style={{overflow: 'visible', display: 'block'}}>
          <defs>
            <filter id="vx-soft" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation={20} />
            </filter>
          </defs>
          {[0.33, 0.66, 1].map((k) => (
            <circle key={k} cx={CX} cy={CY} r={R0 * k} fill="none" stroke={theme.inkSoft} strokeWidth={k === 1 ? 2 : 1.5} strokeDasharray={k === 1 ? undefined : '8 10'} opacity={k === 1 ? 0.6 : 0.4} />
          ))}
          <line x1={CX - R0 - 24} y1={CY} x2={CX + R0 + 24} y2={CY} stroke={theme.rule} strokeWidth={1.5} />
          <text x={CX - R0 - 36} y={CY + 8} textAnchor="end" fontFamily={theme.mono} fontSize={20} fill={theme.inkSoft} letterSpacing="0.06em">
            LEFT
          </text>
          <text x={CX + R0 + 36} y={CY + 8} fontFamily={theme.mono} fontSize={20} fill={theme.inkSoft} letterSpacing="0.06em">
            RIGHT
          </text>
          <text x={CX} y={CY - R0 - 18} textAnchor="middle" fontFamily={theme.mono} fontSize={20} fill={theme.inkSoft} opacity={0.55} letterSpacing="0.06em">
            AHEAD · UNRELIABLE
          </text>
          <text x={CX} y={CY + R0 + 34} textAnchor="middle" fontFamily={theme.mono} fontSize={20} fill={theme.inkSoft} opacity={0.55} letterSpacing="0.06em">
            BEHIND · UNRELIABLE
          </text>
          {regions.map((g, i) => {
            const isLive = live?.speaker === g.spk;
            const half = clamp(Math.max(g.spread, 10) + (1 - g.conf) * 26, 14, 56);
            const rr = R0 * g.dist;
            const col = C.color(g.spk, 'paper');
            const q = seg(frame, Math.round(fps * 0.3) + i * 3, Math.round(fps * 0.5));
            return (
              <g key={g.spk} opacity={q}>
                {isLive ? <path d={wedge(g.az, half * 1.6, rr - 110, rr + 110)} fill={col} opacity={0.12} filter="url(#vx-soft)" style={{mixBlendMode: 'multiply'}} /> : null}
                <path d={wedge(g.az, half, rr - 60, rr + 60)} fill={col} opacity={(isLive ? 0.3 : 0.18) + 0.35 * g.conf} filter="url(#vx-soft)" style={{mixBlendMode: 'multiply'}} />
              </g>
            );
          })}
          {/* labels on two stacks with leaders */}
          {(() => {
            const left = ordered.filter((g) => g.az > 0).sort((a, b) => pt(a.az, R0 * a.dist)[1] - pt(b.az, R0 * b.dist)[1]);
            const right = ordered.filter((g) => g.az <= 0).sort((a, b) => pt(a.az, R0 * a.dist)[1] - pt(b.az, R0 * b.dist)[1]);
            const stack = (items: typeof ordered, xText: number, anchor: 'start' | 'end') => {
              let y = 70;
              return items.map((g) => {
                const [x, yy] = pt(g.az, R0 * g.dist);
                y = Math.max(y, yy - 40);
                const ly = y;
                y += 40;
                const col = C.color(g.spk, 'paper');
                const sp = r.speaker_positions[g.spk];
                const low = (sp && sp.t_ms <= playMs && sp.low_confidence) || g.conf < code.WEARER_MIN_CONFIDENCE;
                const isLive = live?.speaker === g.spk;
                return (
                  <g key={g.spk} opacity={isLive ? 1 : 0.75}>
                    <path d={`M${xText + (anchor === 'end' ? 10 : -10)} ${ly - 8} L ${x} ${yy}`} fill="none" stroke={col} strokeWidth={2} strokeDasharray="5 7" opacity={0.75} />
                    <text x={xText} y={ly} textAnchor={anchor} fontFamily={theme.sans} fontSize={26} fontWeight={700} fill={col}>
                      {nameAt(g.spk).name}
                      {low ? '?' : ''}
                    </text>
                  </g>
                );
              });
            };
            return (
              <>
                {stack(left, 150, 'end')}
                {stack(right, 1060 - 150, 'start')}
              </>
            );
          })()}
          {/* particles */}
          {PART.map((p, i) => {
            const born = Math.floor((t - p.phase) / p.life) * p.life + p.phase;
            const age = t - born;
            if (age < 0) return null;
            const k = age / p.life;
            const ms = clamp(startMs + born * ((endMs - startMs) / (durationInFrames / fps)), startMs, endMs);
            const ii = idxAt(ms);
            if (!gate(ii)) return null;
            const az = W4.az_room[ii] ?? 0;
            const lt = turnAt(r, ms);
            const c = lt ? C.color(lt.speaker, 'paper') : theme.inkSoft;
            const own = lt ? C.of(lt.speaker).p === 'owner' : false;
            const r0 = own ? 70 : R0 * 0.8 + p.z * 90;
            const th = own ? rad(0) + p.j * 1.2 * 57 : clamp(az, -80, 80) + p.j * 0.35 * 57;
            const rr = lerp(r0, 20, 1 - Math.pow(1 - k, 3));
            const [x, y] = pt(th, rr);
            return <circle key={i} cx={x} cy={y - (own ? (1 - k) * 50 : 0)} r={1.2 + p.z * 2} fill={c} opacity={(1 - k) * 0.85} />;
          })}
          <circle cx={CX} cy={CY} r={15} fill={theme.ink} />
          <rect x={CX - 9} y={CY - 2} width={18} height={26} rx={3} fill={theme.paper} stroke={theme.ink} strokeWidth={2.5} />
          <text x={CX + 28} y={CY + 32} fontFamily={theme.sans} fontSize={24} fontWeight={700} fill={theme.ink}>
            you
          </text>
        </svg>
        {/* the lanes */}
        <div style={{marginTop: 4}}>
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline'}}>
            <Eyebrow size={18}>where the sound came from, 100 ms at a time</Eyebrow>
            <Receipt size={17} parts={[`${(playMs / 1000).toFixed(1)} s`, live ? `${nameAt(live.speaker).name} · turn ${live.turn}` : 'room', 'win400', `conf ≥ ${code.WEARER_MIN_CONFIDENCE}`]} />
          </div>
          <svg width={LW} height={LH} viewBox={`0 0 ${LW} ${LH}`} style={{display: 'block', marginTop: 4}}>
            {['left', 'ahead', 'right'].map((b) => (
              <g key={b}>
                <line x1={70} x2={LW} y1={laneY(b)} y2={laneY(b)} stroke={theme.rule} strokeWidth={1.5} />
                <text x={0} y={laneY(b) + 6} fontFamily={theme.mono} fontSize={16} fill={theme.inkSoft} letterSpacing="0.06em">
                  {b.toUpperCase()}
                </text>
              </g>
            ))}
            {W4.t_ms.map((ms, i) => {
              if (ms < startMs || ms > endMs || !gate(i)) return null;
              const x = 70 + ((ms - startMs) / (endMs - startMs)) * (LW - 70);
              const lt = turnAt(r, ms);
              const c = lt ? C.color(lt.speaker, 'paper') : theme.inkSoft;
              const y = laneY(side(W4.az_room[i] ?? 0));
              return <circle key={i} cx={x} cy={y + Math.sin(i * 1.7) * 3} r={2.4} fill={c} opacity={ms <= playMs ? 0.45 + 0.5 * (W4.conf3d[i] ?? 0) : 0.12} />;
            })}
            <line x1={70 + ((playMs - startMs) / (endMs - startMs)) * (LW - 70)} x2={70 + ((playMs - startMs) / (endMs - startMs)) * (LW - 70)} y1={4} y2={LH - 4} stroke={theme.live} strokeWidth={2} />
          </svg>
        </div>
      </div>

      {/* side view */}
      <div style={{position: 'absolute', left: 1270, top: 214, width: SW}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 16, height: 60}}>
          <h3 style={{fontFamily: theme.serif, fontWeight: 500, fontSize: 36, margin: 0}}>Your voice, from above</h3>
          <Chip kind="pending" size={18}>
            pending
          </Chip>
        </div>
        <svg width={SW} height={SH} viewBox={`0 0 ${SW} ${SH}`} style={{overflow: 'visible', display: 'block'}}>
          <defs>
            <filter id="vx-soft2" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation={18} />
            </filter>
          </defs>
          <circle cx={bx - 10} cy={by - 230} r={50} fill="none" stroke={theme.ink} strokeWidth={2.5} />
          <path d={`M${bx - 24} ${by - 182} C ${bx - 20} ${by - 140}, ${bx - 60} ${by - 130}, ${bx - 70} ${by - 60} L ${bx - 76} ${by + 150}`} fill="none" stroke={theme.ink} strokeWidth={2.5} strokeLinecap="round" />
          <path d={`M${bx + 4} ${by - 180} C ${bx + 16} ${by - 150}, ${bx + 40} ${by - 116}, ${bx + 36} ${by - 40} L ${bx + 30} ${by + 150}`} fill="none" stroke={theme.ink} strokeWidth={2.5} strokeLinecap="round" />
          <rect x={bx + 20} y={by - 40} width={22} height={34} rx={4} fill={theme.paper} stroke={theme.ink} strokeWidth={3} />
          <line x1={bx + 31} y1={by - 23} x2={bx + 31 + 330} y2={by - 23} stroke={theme.rule} strokeWidth={1.5} />
          <line x1={bx + 31} y1={by - 23} x2={bx + 31} y2={by - 23 - 300} stroke={theme.inkSoft} strokeWidth={1.5} opacity={0.5} />
          <polygon points={`${bx + 27},${by - 23 - 300} ${bx + 35},${by - 23 - 300} ${bx + 31},${by - 23 - 310}`} fill={theme.inkSoft} opacity={0.6} />
          <text x={bx + 42} y={by - 23 - 300} fontFamily={theme.mono} fontSize={18} fill={theme.inkSoft} letterSpacing="0.06em">
            UP
          </text>
          <line x1={bx + 31} y1={by - 23} x2={tx} y2={ty} stroke={theme.inkSoft} strokeWidth={2} strokeDasharray="8 10" />
          <text x={tx + 6} y={ty - 10} textAnchor="end" fontFamily={theme.mono} fontSize={16} fill={theme.inkSoft} letterSpacing="0.06em">
            wearer threshold · code constant
          </text>
          {Object.entries(med).map(([spk, m]) => {
            const own = spk === found;
            const gi = Object.keys(med).filter((k) => k !== found).indexOf(spk);
            const col = C.color(spk, 'paper');
            const [x, y] = ray(m, own ? 200 : 230);
            return (
              <g key={spk}>
                <ellipse cx={x} cy={y} rx={own ? 105 : 100} ry={own ? 46 : 34} fill={col} opacity={own ? 0.4 : 0.5} filter="url(#vx-soft2)" transform={`rotate(${-m} ${x} ${y})`} style={{mixBlendMode: 'multiply'}} />
                {own ? (
                  <text x={x - 70} y={y - 62} fontFamily={theme.sans} fontSize={26} fontWeight={700} fill={theme.ink}>
                    you ← wearer · from above
                  </text>
                ) : (
                  <text x={x + 70 + (gi % 2 ? 40 : -40)} y={y + (gi % 2 ? 66 : -50)} textAnchor="middle" fontFamily={theme.sans} fontSize={26} fontWeight={700} fill={col}>
                    {nameAt(spk).short}
                    {(r.speaker_positions[spk]?.low_confidence ?? false) ? '?' : ''}
                  </text>
                )}
              </g>
            );
          })}
          <text x={bx + 31 + 200} y={by - 23 + 34} textAnchor="middle" fontFamily={theme.mono} fontSize={17} fill={theme.inkSoft} letterSpacing="0.06em">
            guests, near level
          </text>
        </svg>
        <Receipt size={19} wrap parts={['per-turn median elevation · Wearer re-run offline', `found ${found ?? '—'} (you)`, `rule: median ≥ ${code.WEARER_MIN_ELEVATION}°, +${code.WEARER_MARGIN}° over every other voice, ≥ ${code.WEARER_MIN_TURNS} turns`, `owner event ${((r.owner_event?.t_ms ?? 0) / 1000).toFixed(1)} s · ${r.owner_event?.source === 'transcript' ? 'Muse Spark, from the transcript' : r.owner_event?.source}`]} style={{display: 'block', marginTop: 6, lineHeight: 1.35}} />
      </div>
      <Corner name="voices" parts={[r.id, `${r.channels} ch ${r.layout}`, `${r.sample_rate / 1000} kHz`, 'recomputed with direction.py', 'xray.json · win400']} left={96} />
    </Frame>
  );
};
