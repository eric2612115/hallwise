import React from 'react';
import {shotlist, fmtTime, partLabel} from './data';
import {theme} from './proj';

const X = 40, W = 1840, BAR_Y = 992, BAR_H = 30;
const xOf = (s: number) => X + (s / shotlist.duration) * W;

export const TimelineStrip: React.FC<{t: number}> = ({t}) => {
  // Part brackets.
  const parts: {id: string; start: number; end: number}[] = [];
  for (const b of shotlist.beats) {
    const last = parts[parts.length - 1];
    if (last && last.id === b.part) last.end = b.end;
    else parts.push({id: b.part, start: b.start, end: b.end});
  }
  // Markers: the surprises and the silences.
  const markers: {t: number; label: string; color: string}[] = [];
  for (const b of shotlist.beats) {
    for (const e of b.events ?? []) {
      if (e.kind === 'buzz') markers.push({t: e.t, label: b.key === 'names' ? 'buzz · Chloé' : b.key === 'waiter' ? 'buzz · one page' : b.key === 'invite' ? 'buzz · invite' : 'buzz · connector', color: theme.eric});
      if (e.kind === 'ring') markers.push({t: e.t, label: e.label.includes('coffee') ? 'Friday' : e.label.includes('Siddharth') ? 'ring · Siddharth' : 'ring · Kenji', color: theme.friend});
    }
    if (b.silence) markers.push({t: b.start, label: b.name.replace(/\.$/, ''), color: theme.cold});
    if (b.key === 'itdoes' || b.key === 'stop') markers.push({t: b.start, label: b.name, color: theme.inkSoft});
    if (b.key === 'chloe') markers.push({t: b.start, label: 'the call with Chloé', color: theme.eric});
    if (b.key === 'out') markers.push({t: b.start + (b.hot_at ?? 0), label: 'the room hits', color: theme.hot});
  }
  markers.sort((a, b) => a.t - b.t);

  return (
    <svg width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0, fontFamily: theme.sans}}>
      {parts.map((p, i) => (
        <g key={i}>
          <line x1={xOf(p.start) + 2} y1={975} x2={xOf(p.end) - 2} y2={975} stroke={theme.inkFaint} strokeWidth={1} />
          <line x1={xOf(p.start) + 2} y1={970} x2={xOf(p.start) + 2} y2={980} stroke={theme.inkFaint} strokeWidth={1} />
          <line x1={xOf(p.end) - 2} y1={970} x2={xOf(p.end) - 2} y2={980} stroke={theme.inkFaint} strokeWidth={1} />
          <text x={(xOf(p.start) + xOf(p.end)) / 2} y={966} fontSize={11} letterSpacing={2} fontWeight={700} fill={theme.inkSoft} textAnchor="middle">{partLabel(p.id).toUpperCase()}</text>
        </g>
      ))}
      {shotlist.beats.map((b) => {
        const x0 = xOf(b.start), x1 = xOf(b.end);
        const past = t >= b.end, now = t >= b.start && t < b.end;
        const op = past || now ? 0.95 : 0.4;
        const col = (hot: boolean) => (hot ? theme.hot : theme.cold);
        const split = b.hot_at !== undefined ? xOf(b.start + b.hot_at) : null;
        return (
          <g key={b.id}>
            {split ? (
              <>
                <rect x={x0} y={BAR_Y} width={split - x0 - 1} height={BAR_H} fill={col(false)} opacity={op} />
                <rect x={split} y={BAR_Y} width={x1 - split - 1} height={BAR_H} fill={col(true)} opacity={op} />
              </>
            ) : (
              <rect x={x0} y={BAR_Y} width={Math.max(1, x1 - x0 - 1)} height={BAR_H} fill={col(b.temp === 'hot')} opacity={op} />
            )}
            {b.silence && <rect x={x0} y={BAR_Y} width={Math.max(1, x1 - x0 - 1)} height={BAR_H} fill="url(#hatch)" opacity={0.5} />}
            {x1 - x0 > 24 && <text x={(x0 + x1) / 2} y={BAR_Y + 20} fontSize={12} fontWeight={700} fill="#fff" fontFamily={theme.mono} textAnchor="middle">{b.id}</text>}
            {now && <rect x={x0} y={BAR_Y - 3} width={Math.max(1, x1 - x0 - 1)} height={BAR_H + 6} fill="none" stroke={theme.ink} strokeWidth={1.5} />}
          </g>
        );
      })}
      <defs>
        <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke="#fff" strokeWidth="2" />
        </pattern>
      </defs>
      {(() => {
        // Pack the marker labels into rows so none overlaps its neighbour.
        const rowEnd: number[] = [];
        return markers.map((m) => {
          const x = xOf(m.t);
          const w = m.label.length * 6.4 + 12;
          let row = rowEnd.findIndex((e) => e < x - 2);
          if (row < 0) { row = rowEnd.length; rowEnd.push(0); }
          rowEnd[row] = x + w;
          return {...m, row};
        });
      })().map((m, i) => {
        const x = xOf(m.t);
        const row = m.row;
        const y = BAR_Y + BAR_H + 14 + row * 17;
        return (
          <g key={i}>
            <line x1={x} y1={BAR_Y + BAR_H} x2={x} y2={y - 9} stroke={m.color} strokeWidth={1} />
            <circle cx={x} cy={y - 9} r={2.5} fill={m.color} />
            <text x={x + 5} y={y - 4} fontSize={11} fill={m.color} fontWeight={600}>{m.label}</text>
          </g>
        );
      })}
      {/* minute ticks */}
      {[0, 30, 60, 90, 120, 150, 180].map((s) => (
        <g key={s}>
          <line x1={xOf(s)} y1={BAR_Y - 6} x2={xOf(s)} y2={BAR_Y} stroke={theme.inkSoft} strokeWidth={1} />
          <text x={xOf(s)} y={BAR_Y - 9} fontSize={10} fill={theme.inkFaint} fontFamily={theme.mono} textAnchor={s === 0 ? 'start' : s === 180 ? 'end' : 'middle'}>{fmtTime(s).replace('.0', '')}</text>
        </g>
      ))}
      {/* playhead */}
      <line x1={xOf(t)} y1={BAR_Y - 10} x2={xOf(t)} y2={BAR_Y + BAR_H + 8} stroke={theme.ink} strokeWidth={2.5} />
      <polygon points={`${xOf(t) - 6},${BAR_Y - 16} ${xOf(t) + 6},${BAR_Y - 16} ${xOf(t)},${BAR_Y - 8}`} fill={theme.ink} />
    </svg>
  );
};
