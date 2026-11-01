import React from 'react';
import {AbsoluteFill} from 'remotion';
import {hexA, theme} from '../theme';

// ---------- the frame: paper or dark, with grain and a vignette (paper.css .frame/.grain/.vignette)
const GRAIN = `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 1.4 -0.35'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")`;

export const Grain: React.FC<{dark?: boolean}> = ({dark}) => (
  <AbsoluteFill style={{backgroundImage: GRAIN, opacity: dark ? 0.16 : 0.13, mixBlendMode: dark ? 'screen' : 'multiply', pointerEvents: 'none'}} />
);

export const Vignette: React.FC<{dark?: boolean}> = ({dark}) => (
  <AbsoluteFill
    style={{
      background: dark
        ? 'radial-gradient(ellipse at 50% 40%, transparent 45%, rgba(0,0,0,0.55) 140%)'
        : 'radial-gradient(ellipse at 50% 40%, transparent 55%, rgba(42,38,34,0.10) 150%)',
      pointerEvents: 'none',
    }}
  />
);

export const Frame: React.FC<{dark?: boolean; transparent?: boolean; children?: React.ReactNode; style?: React.CSSProperties}> = ({dark, transparent, children, style}) => (
  <AbsoluteFill
    style={{
      backgroundColor: transparent ? 'transparent' : dark ? theme.dark : theme.paper,
      color: dark ? theme.darkInk : theme.ink,
      fontFamily: theme.sans,
      overflow: 'hidden',
      ...style,
    }}
  >
    {transparent ? null : <Grain dark={dark} />}
    {children}
    {transparent ? null : <Vignette dark={dark} />}
  </AbsoluteFill>
);

// ---------- chips: who did it. A Meta model is an ink pill with a dot; Hallwise code is a teal outlined pill in
// mono with a square mark; PENDING is ochre dashed; NO MODEL CALL the same shape in ink-soft; kept/struck verdicts.
export type ChipKind = 'model' | 'code' | 'pending' | 'nomodel' | 'kept' | 'struck' | 'live';

export const Chip: React.FC<{kind?: ChipKind; size?: number; dark?: boolean; children: React.ReactNode; style?: React.CSSProperties}> = ({
  kind = 'model',
  size = 26,
  dark,
  children,
  style,
}) => {
  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: size * 0.45,
    padding: `${size * 0.27}px ${size * 0.75}px ${size * 0.3}px`,
    borderRadius: 999,
    fontSize: size,
    lineHeight: 1.2,
    fontWeight: 600,
    letterSpacing: '0.01em',
    whiteSpace: 'nowrap',
    verticalAlign: 'middle',
    border: `2px solid ${dark ? theme.darkInk : theme.ink}`,
    color: dark ? theme.darkInk : theme.ink,
    background: dark ? 'transparent' : theme.paperRaised,
    fontFamily: theme.sans,
    ...style,
  };
  const dot = (extra: React.CSSProperties = {}) => <span style={{width: size * 0.46, height: size * 0.46, borderRadius: '50%', background: 'currentColor', flex: 'none', ...extra}} />;
  if (kind === 'code') {
    const c = dark ? theme.darkAccent : theme.accent;
    return (
      <span style={{...base, fontFamily: theme.mono, fontWeight: 500, borderColor: c, color: c, background: 'transparent'}}>
        {dot({width: size * 0.5, height: size * 0.5, borderRadius: 3, background: 'transparent', border: '2.5px solid currentColor'})}
        {children}
      </span>
    );
  }
  if (kind === 'pending' || kind === 'nomodel') {
    const c = kind === 'pending' ? theme.pending : dark ? theme.darkInkSoft : theme.inkSoft;
    return (
      <span style={{...base, fontFamily: theme.mono, fontWeight: 500, border: `2px dashed ${c}`, color: c, background: 'transparent', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: size * 0.85}}>
        {children}
      </span>
    );
  }
  if (kind === 'kept' || kind === 'struck' || kind === 'live') {
    const c = kind === 'kept' ? (dark ? theme.darkAccent : theme.accent) : dark ? theme.darkLive : theme.live;
    return (
      <span style={{...base, borderColor: c, color: c, background: 'transparent'}}>
        <span style={{fontWeight: 700}}>{kind === 'kept' ? '✓' : kind === 'struck' ? '✕' : '●'}</span>
        {children}
      </span>
    );
  }
  return (
    <span style={base}>
      {dot()}
      {children}
    </span>
  );
};

// ---------- receipt: the line that lets anyone check the value. It is never cut with an ellipsis: `lines` lets it
// wrap to that many lines (breaking anywhere, so a long id still shows whole), `wrap` to as many as it needs.
export const Receipt: React.FC<{parts: React.ReactNode[]; size?: number; dark?: boolean; wrap?: boolean; lines?: number; style?: React.CSSProperties; align?: 'left' | 'right'}> = ({
  parts,
  size = 24,
  dark,
  wrap,
  lines,
  style,
  align = 'left',
}) => (
  <span
    style={{
      fontFamily: theme.mono,
      fontSize: size,
      lineHeight: 1.3,
      color: dark ? theme.darkInkSoft : theme.inkSoft,
      letterSpacing: '0.005em',
      whiteSpace: wrap || lines ? 'normal' : 'nowrap',
      overflow: wrap ? 'visible' : 'hidden',
      overflowWrap: lines ? 'anywhere' : undefined,
      display: lines ? '-webkit-box' : undefined,
      WebkitLineClamp: lines,
      WebkitBoxOrient: lines ? 'vertical' : undefined,
      textOverflow: wrap || lines ? 'clip' : 'ellipsis',
      textAlign: align,
      ...style,
    }}
  >
    {parts.map((p, i) => (
      <React.Fragment key={i}>
        {i > 0 ? <span style={{opacity: 0.55, margin: '0 0.45em'}}>·</span> : null}
        {p}
      </React.Fragment>
    ))}
  </span>
);

export const B: React.FC<{children: React.ReactNode; dark?: boolean}> = ({children, dark}) => <b style={{fontWeight: 500, color: dark ? theme.darkInk : theme.ink}}>{children}</b>;

// ---------- cards: typeset paper over the frozen frame
export const Card: React.FC<{children: React.ReactNode; style?: React.CSSProperties; lit?: boolean; flat?: boolean}> = ({children, style, lit, flat}) => (
  <div
    style={{
      position: 'relative',
      background: flat ? theme.paper : theme.paperRaised,
      border: `1.5px solid ${theme.rule}`,
      borderRadius: 22,
      boxShadow: flat
        ? 'none'
        : lit
          ? `0 0 0 3px ${theme.paperRaised}, 0 0 0 6px ${theme.darkAccent}, 0 18px 48px rgba(0,0,0,0.3)`
          : '0 2px 0 rgba(42,38,34,0.04), 0 18px 48px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.08)',
      padding: '30px 36px',
      color: theme.ink,
      ...style,
    }}
  >
    {children}
  </div>
);

export const CardTitle: React.FC<{n?: string; children: React.ReactNode; size?: number; style?: React.CSSProperties}> = ({n, children, size = 34, style}) => (
  <p style={{fontFamily: theme.serif, fontWeight: 500, fontSize: size, lineHeight: 1.1, margin: `0 0 ${size * 0.4}px`, color: theme.inkStrong, display: 'flex', alignItems: 'baseline', gap: 14, ...style}}>
    {n ? <span style={{fontFamily: theme.mono, fontWeight: 500, fontSize: size * 0.65, color: theme.inkSoft, letterSpacing: '0.08em'}}>{n}</span> : null}
    {children}
  </p>
);

export const Eyebrow: React.FC<{children: React.ReactNode; dark?: boolean; size?: number; style?: React.CSSProperties}> = ({children, dark, size = 26, style}) => (
  <div style={{fontFamily: theme.mono, fontSize: size, letterSpacing: '0.12em', textTransform: 'uppercase', color: dark ? theme.darkInkSoft : theme.inkSoft, ...style}}>{children}</div>
);

// ---------- a corner mark on every frame: the page's name and the recording it draws on
export const Corner: React.FC<{name: string; parts: React.ReactNode[]; dark?: boolean; left?: number}> = ({name, parts, dark, left = 48}) => (
  <div style={{position: 'absolute', left, bottom: 36, display: 'flex', alignItems: 'center', gap: 18}}>
    <span style={{width: 40, height: 40, borderRadius: '50%', display: 'grid', placeItems: 'center', background: dark ? theme.darkInk : theme.ink, color: dark ? theme.dark : theme.paper, fontFamily: theme.serif, fontWeight: 600, fontSize: 22}}>H</span>
    <span style={{fontFamily: theme.serif, fontWeight: 600, fontSize: 26, letterSpacing: '0.01em', color: dark ? theme.darkInk : theme.ink}}>Hallwise</span>
    <Receipt parts={[name, ...parts]} dark={dark} style={{marginLeft: 6}} />
  </div>
);

// ---------- verdict marks
// The hand-drawn red stroke that never hides the words: one stroke across the whole claim, drawn left to right
// with p in 0..1 (spec 4, strike). The claim is kept on one line, and the stroke is a bar sized from that line's
// own box (rotate -1.6 deg, at least 4 px), so it can never break into pieces the way a path over a wrapped box
// did. `multiline` is for a claim that must wrap: the same text is laid over itself with a line-through on every
// line, revealed left to right.
export const Struck: React.FC<{p: number; children: React.ReactNode; color?: string; thick?: number; multiline?: boolean; style?: React.CSSProperties}> = ({p, children, color = theme.live, thick = 0.09, multiline, style}) => {
  const faded = p > 0.5 ? theme.inkSoft : 'inherit';
  if (multiline) {
    return (
      <span style={{display: 'inline-grid', color: faded, ...style}}>
        <span style={{gridArea: '1 / 1'}}>{children}</span>
        <span aria-hidden style={{gridArea: '1 / 1', color: 'transparent', textDecoration: 'line-through', textDecorationColor: color, textDecorationThickness: `max(${thick}em, 4px)`, clipPath: `inset(0 ${100 - 100 * p}% 0 0)`, pointerEvents: 'none'}}>
          {children}
        </span>
      </span>
    );
  }
  return (
    <span style={{position: 'relative', display: 'inline-block', whiteSpace: 'nowrap', color: faded, ...style}}>
      {children}
      <span aria-hidden style={{position: 'absolute', left: '-2%', top: '52%', height: `max(${thick}em, 4px)`, width: `${104 * p}%`, background: color, borderRadius: 3, transform: 'translateY(-50%) rotate(-1.6deg)', transformOrigin: 'left center', pointerEvents: 'none', opacity: 0.94}} />
    </span>
  );
};

// The teal underline on the words that were found, drawn in over p.
export const Kept: React.FC<{p: number; children: React.ReactNode; color?: string}> = ({p, children, color = theme.accent}) => (
  <span style={{position: 'relative', display: 'inline', color}}>
    {children}
    <span style={{position: 'absolute', left: 0, bottom: '-0.12em', height: '0.1em', minHeight: 4, width: `${p * 100}%`, background: color, borderRadius: 2}} />
  </span>
);

// A speaker swatch
export const Sw: React.FC<{color: string; size?: number}> = ({color, size = 0.62}) => (
  <span style={{display: 'inline-block', width: `${size}em`, height: `${size}em`, borderRadius: '50%', background: color, verticalAlign: '-0.02em', marginRight: '0.3em'}} />
);

export {hexA, theme};
