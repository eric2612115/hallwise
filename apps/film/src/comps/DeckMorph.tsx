import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {firstName} from '../lib/cast';
import {clamp, fmt, lerp, seg} from '../lib/motion';
import {Chip, Corner, Eyebrow, Frame, Receipt} from '../ui';
import {theme} from '../theme';
import type {ProofData} from '../lib/types';

// The deck morph (spec 5.4): the twelve slides as small paper cards; the ones a figure comes from stay lit, the rest
// fold away; the one page rises on the right; dotted teal leaders draw from each source slide to its figure's dot,
// over the page at low opacity, and the figures count up. "← slide N" under each figure, REBUILT IN 3.77 s as a big
// mono readout, and the NUMBERS CHECKED chip on the page itself (blueprint grafts). Every number is onepager.numbers'
// own verdict (tools/extract_data.py); the name is the rebuilt event's (the run's person the cued page landed on).
export type DeckMorphProps = {data: ProofData; seconds?: number};

const S = {cols: 3, gx: 262, gy: 164, w: 236, h: 150, left: 96, top: 250};
const PAGE = {left: 1020, top: 250, w: 804, h: 700};

export const DeckMorph: React.FC<DeckMorphProps> = ({data, seconds = 4.5}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const op = data.onepager;
  const rb = data.rebuilt;
  const pg = op.page;
  const total = seconds * fps;
  const t = clamp(frame / (total * 0.82)); // 0: the deck as it was; 1: the page, every figure tied to its slide
  const lit = new Set(op.links.flatMap((l) => l.slides));
  const headP = seg(frame, 0, Math.round(fps * 0.5));
  const k2 = seg(frame, total * 0.3, Math.round(fps * 0.6));
  const k3 = seg(frame, total * 0.52, Math.round(fps * 0.6)); // leaders
  const count = seg(frame, total * 0.3 + Math.round(fps * 0.25), Math.round(fps * 0.4)); // figures count up as the page lands

  // figure positions inside the page (3 x 2 grid), for the leaders: the dot sits just left of each figure
  const figPos = (i: number) => {
    const c = i % 3,
      row = Math.floor(i / 3);
    const x = PAGE.left + 44 + c * ((PAGE.w - 88 + 22) / 3);
    const y = PAGE.top + 32 + 46 * 1.2 + 26 * 1.2 + 20 + 18 + row * 118 + 28;
    return [x, y];
  };
  const countUp = (v: string) => {
    // "24 of 25" / "410" / "5-8": count each integer up from 0
    return v.replace(/\d+/g, (m) => String(Math.round(parseInt(m, 10) * count)));
  };

  return (
    <Frame>
      <div style={{position: 'absolute', left: 96, top: 58, right: 96, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 30, opacity: headP}}>
        <div style={{flex: 1}}>
          <Eyebrow style={{whiteSpace: 'nowrap'}}>
            The deck, rebuilt for {firstName(rb.name)} · “{rb.shape || rb.acts[0]}”
          </Eyebrow>
          <h1 style={{fontFamily: theme.serif, fontWeight: 500, fontSize: 52, lineHeight: 1.04, letterSpacing: '-0.012em', margin: '8px 0 0', color: theme.inkStrong, whiteSpace: 'nowrap'}}>Twelve slides, folded into one page. Numbers first.</h1>
        </div>
        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 12, flex: 'none', maxWidth: 560}}>
          <div style={{display: 'flex', gap: 12}}>
            <Chip>Muse Spark</Chip>
            <Chip kind="code">code · onepager.py</Chip>
          </div>
          <Receipt size={18} lines={2} align="right" parts={[op.file, op.deck, `cued into run ${data.run1.id.slice(-4)} for ${rb.name}`]} />
        </div>
      </div>

      {/* the slides */}
      <div style={{position: 'absolute', left: S.left, top: S.top, width: 760, height: 660}}>
        {op.deck_slides.map((s, i) => {
          const x0 = (i % S.cols) * S.gx,
            y0 = Math.floor(i / S.cols) * S.gy;
          const k = seg(frame, total * 0.12 + i * 2, Math.round(fps * 0.6));
          const isLit = lit.has(i);
          const sc = lerp(1, isLit ? 1 : 0.82, k);
          const o = lerp(1, isLit ? 1 : 0.42, k);
          const litNow = isLit && k > 0.6;
          return (
            <div
              key={i}
              style={{
                position: 'absolute',
                left: x0,
                top: y0,
                width: S.w,
                height: S.h,
                padding: '16px 18px',
                borderRadius: 14,
                background: theme.paperRaised,
                border: `1.5px solid ${litNow ? theme.accent : theme.rule}`,
                boxShadow: litNow ? '0 0 0 3px rgba(47,127,114,0.18), 0 6px 18px rgba(42,38,34,0.10)' : '0 6px 18px rgba(42,38,34,0.10)',
                transform: `scale(${sc})`,
                opacity: o * headP,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{fontFamily: theme.mono, fontSize: 17, color: theme.inkSoft, letterSpacing: '0.06em'}}>slide {i + 1}</div>
                <div style={{fontFamily: theme.serif, fontSize: 24, fontWeight: 500, lineHeight: 1.12, color: theme.inkStrong}}>{s.title}</div>
              </div>
              <div style={{display: 'flex', flexWrap: 'wrap', gap: 5}}>
                {s.numbers.slice(0, 6).map((n) => (
                  <span key={n} style={{fontFamily: theme.mono, fontSize: 15, padding: '1px 7px', borderRadius: 6, background: theme.paperDeep, color: theme.ink}}>
                    {n}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* the page */}
      <div
        style={{
          position: 'absolute',
          left: PAGE.left,
          top: PAGE.top,
          width: PAGE.w,
          height: PAGE.h,
          padding: '32px 44px 26px',
          borderRadius: 10,
          background: '#FFFFFF',
          color: theme.inkStrong,
          boxShadow: '0 30px 70px rgba(42,38,34,0.22), 0 2px 8px rgba(42,38,34,0.12)',
          opacity: k2,
          transform: `translateX(${lerp(60, 0, k2)}px) scale(${lerp(0.96, 1, k2)})`,
        }}
      >
        <div style={{position: 'absolute', right: 24, top: 22}}>
          <Chip kind="kept" size={16} style={{opacity: count}}>
            numbers checked · dropped {op.dropped.length}
          </Chip>
        </div>
        <p style={{fontFamily: theme.serif, fontSize: 46, fontWeight: 600, margin: 0, letterSpacing: '-0.01em'}}>{pg.title}</p>
        <p style={{fontFamily: theme.serif, fontStyle: 'italic', fontSize: 26, margin: '4px 0 20px', color: '#3a3530'}}>{pg.lede}</p>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px 22px', borderTop: '1.5px solid #e4ded2', borderBottom: '1.5px solid #e4ded2', padding: '18px 0'}}>
          {pg.figures.map((f, i) => (
            <div key={i} style={{height: 102}}>
              <div style={{fontFamily: theme.serif, fontSize: 50, fontWeight: 600, lineHeight: 1, letterSpacing: '-0.02em', color: theme.accent, fontVariantNumeric: 'tabular-nums'}}>{countUp(f.value)}</div>
              <div style={{fontSize: 17, lineHeight: 1.25, marginTop: 6, color: theme.ink}}>{f.label}</div>
              <div style={{fontFamily: theme.mono, fontSize: 13, marginTop: 4, color: theme.accent, opacity: k3}}>← slide {op.links[i].slides.map((s) => s + 1).join(', ')}</div>
            </div>
          ))}
        </div>
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 28px', marginTop: 16}}>
          {pg.sections.map((s) => (
            <div key={s.heading}>
              <p style={{fontFamily: theme.serif, fontWeight: 600, fontSize: 20, margin: '0 0 3px'}}>{s.heading}</p>
              {s.points.slice(0, 2).map((pt) => (
                <p key={pt} style={{margin: 0, fontSize: 15.5, lineHeight: 1.3, color: '#3a3530'}}>
                  {pt}
                </p>
              ))}
            </div>
          ))}
        </div>
        <p style={{marginTop: 14, fontFamily: theme.serif, fontStyle: 'italic', fontSize: 19, color: '#3a3530'}}>{pg.close}</p>
      </div>

      {/* leaders, over the page at low opacity: every figure, tied to the slide that states its numbers, ending on
          the figure's own dot */}
      <svg viewBox="0 0 1920 1080" style={{position: 'absolute', inset: 0, width: 1920, height: 1080, pointerEvents: 'none'}}>
        {op.links.map((l, i) => {
          if (!l.slides.length) return null;
          const si = l.slides[0];
          const sx = S.left + (si % S.cols) * S.gx + S.w,
            sy = S.top + Math.floor(si / S.cols) * S.gy + S.h / 2;
          const [fx, fy] = figPos(i);
          const x1 = fx - 10;
          return (
            <g key={i} opacity={k3}>
              <path d={`M${sx} ${sy} C ${sx + 140} ${sy}, ${x1 - 140} ${fy}, ${x1} ${fy}`} fill="none" stroke={theme.accent} strokeWidth={2.5} strokeDasharray="6 8" pathLength={100} strokeDashoffset={100 - 100 * k3} opacity={0.35} />
              <circle cx={x1} cy={fy} r={5} fill={theme.accent} />
            </g>
          );
        })}
      </svg>
      <div style={{position: 'absolute', left: 96, bottom: 84, width: 820, display: 'flex', alignItems: 'center', gap: 18, opacity: headP}}>
        <Chip kind="code">rule</Chip>
        <p style={{margin: 0, fontFamily: theme.serif, fontStyle: 'italic', fontSize: 25, lineHeight: 1.3, color: theme.ink}}>Every number on the page must be one the slides state; a line with the reader's own words is dropped. One retry, then the failing lines are cut.</p>
      </div>
      <div style={{position: 'absolute', right: 96, bottom: 40, textAlign: 'right', opacity: k2}}>
        <div style={{fontFamily: theme.mono, fontSize: 44, fontWeight: 500, letterSpacing: '0.06em', color: theme.inkStrong, lineHeight: 1}}>
          REBUILT IN {op.seconds} <span style={{fontSize: 28, color: theme.inkSoft}}>s</span>
        </div>
        <Receipt size={19} style={{display: 'block', marginTop: 10}} parts={[`${op.slides.length} slides → 1 page`, `${pg.figures.length} figures`, `${op.dropped.length} lines dropped`, `retried: ${op.retried}`, op.model, `${fmt(op.usage.total_tokens)} tokens`]} />
      </div>
      <Corner name="deck" parts={[`t = ${t.toFixed(2)}`]} left={96} />
    </Frame>
  );
};
