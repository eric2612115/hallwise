import React from 'react';
import {shotlist, Beat, poseAt, trailAt, Pose, Device} from './data';
import {P, pt, floorTransform, theme, S} from './proj';

const deg = Math.PI / 180;

// Per-device label placement, to keep labels off the furniture and each other.
const LABEL: Record<string, {dx: number; dy: number; dz?: number; anchor: 'start' | 'middle' | 'end'}> = {
  'TV': {dx: 0, dy: 0, dz: 1.9, anchor: 'middle'},
  'Mac-0': {dx: 0.25, dy: 0.0, dz: 0.3, anchor: 'start'},
  'Phone-L': {dx: 0.18, dy: 0.05, dz: 1.15, anchor: 'start'},
  'Mac-1': {dx: 0, dy: 0.42, anchor: 'middle'},
  'Mac-2': {dx: 0, dy: 0.42, anchor: 'middle'},
  'Mac-3': {dx: 0, dy: 0.48, anchor: 'middle'},
  'iPhone-K': {dx: 0.0, dy: 0.42, anchor: 'middle'},
};

const halo: React.CSSProperties = {paintOrder: 'stroke', stroke: theme.paper, strokeWidth: 4, strokeLinejoin: 'round'};

const Box: React.FC<{x0: number; y0: number; x1: number; y1: number; h: number; label: string; id: string}> = ({x0, y0, x1, y1, h, label, id}) => {
  const top = `${pt(x0, y0, h)} ${pt(x1, y0, h)} ${pt(x1, y1, h)} ${pt(x0, y1, h)}`;
  const bottom = `${pt(x0, y0)} ${pt(x1, y0)} ${pt(x1, y1)} ${pt(x0, y1)}`;
  const lp = id === 'table' ? P(x0 + 0.1, y1 - 0.12, h) : P(x0 + 0.1, y1 - 0.1, h);
  return (
    <g>
      <polygon points={bottom} fill="none" stroke={theme.inkFaint} strokeWidth={1} />
      {[[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(([x, y], i) => (
        <line key={i} x1={P(x, y, 0).sx} y1={P(x, y, 0).sy} x2={P(x, y, h).sx} y2={P(x, y, h).sy} stroke={theme.inkSoft} strokeWidth={1.2} />
      ))}
      <polygon points={top} fill={theme.paperDeep} fillOpacity={0.85} stroke={theme.ink} strokeWidth={1.4} />
      <text x={lp.sx} y={lp.sy - 4} fontSize={12} fill={theme.inkSoft} fontFamily={theme.sans} style={halo}>{label}</text>
    </g>
  );
};

const DeviceGlyph: React.FC<{d: Device; active: boolean; t: number; muted: boolean}> = ({d, active, t, muted}) => {
  const color = active ? theme.sound : theme.inkSoft;
  const lab = LABEL[d.id] ?? {dx: 0, dy: 0.35, anchor: 'middle' as const};
  const lp = P(d.x + lab.dx, d.y + lab.dy, lab.dz ?? 0);
  let glyph: React.ReactNode;
  if (d.kind === 'laptop') {
    glyph = (
      <g>
        <g transform={floorTransform(d.x, d.y, d.z)}>
          <rect x={-0.18} y={-0.12} width={0.36} height={0.24} fill={theme.panel} stroke={color} strokeWidth={1.3} vectorEffect="non-scaling-stroke" />
        </g>
        <polygon points={`${pt(d.x - 0.18, d.y - 0.12, d.z)} ${pt(d.x + 0.18, d.y - 0.12, d.z)} ${pt(d.x + 0.18, d.y - 0.12, d.z + 0.24)} ${pt(d.x - 0.18, d.y - 0.12, d.z + 0.24)}`}
          fill={active ? theme.sound : '#3a3631'} fillOpacity={active ? 0.9 : 0.75} stroke={color} strokeWidth={1.3} />
      </g>
    );
  } else if (d.kind === 'phone') {
    glyph = (
      <g>
        <line x1={P(d.x, d.y, 0).sx} y1={P(d.x, d.y, 0).sy} x2={P(d.x, d.y, d.z).sx} y2={P(d.x, d.y, d.z).sy} stroke={theme.inkFaint} strokeWidth={1} strokeDasharray="2 3" />
        <circle cx={P(d.x, d.y, 0).sx} cy={P(d.x, d.y, 0).sy} r={2.5} fill={theme.inkFaint} />
        <polygon points={`${pt(d.x - 0.05, d.y, d.z)} ${pt(d.x + 0.05, d.y, d.z)} ${pt(d.x + 0.05, d.y, d.z + 0.2)} ${pt(d.x - 0.05, d.y, d.z + 0.2)}`}
          fill={active ? theme.sound : '#3a3631'} fillOpacity={active ? 0.95 : 0.8} stroke={color} strokeWidth={1.5} />
      </g>
    );
  } else {
    const w = d.w ?? 3;
    glyph = (
      <polygon points={`${pt(d.x - w / 2, d.y, d.z - 0.35)} ${pt(d.x + w / 2, d.y, d.z - 0.35)} ${pt(d.x + w / 2, d.y, d.z + 0.35)} ${pt(d.x - w / 2, d.y, d.z + 0.35)}`}
        fill={active ? theme.sound : '#3a3631'} fillOpacity={active ? 0.55 : 0.7} stroke={color} strokeWidth={1.5} />
    );
  }
  return (
    <g>
      {active && !muted && (
        <g transform={floorTransform(d.x, d.y, 0)}>
          <circle cx={0} cy={0} r={0.55} fill="url(#glow)" />
          {[0, 1, 2].map((i) => {
            const ph = ((t * 0.8 + i / 3) % 1 + 1) % 1;
            return <circle key={i} cx={0} cy={0} r={0.15 + ph * 1.1} fill="none" stroke={theme.sound} strokeOpacity={0.85 * (1 - ph)} strokeWidth={2} vectorEffect="non-scaling-stroke" />;
          })}
        </g>
      )}
      {glyph}
      <text x={lp.sx} y={lp.sy} fontSize={13} fontWeight={600} fill={active ? theme.sound : theme.ink} fontFamily={theme.sans} textAnchor={lab.anchor} style={halo}>{d.label}</text>
      {active && muted && <text x={lp.sx} y={lp.sy + 14} fontSize={11} fill={theme.cold} fontFamily={theme.sans} textAnchor={lab.anchor} style={halo}>muted in post</text>}
    </g>
  );
};

const FaceTick: React.FC<{x: number; y: number; face: number; color: string}> = ({x, y, face, color}) => (
  <g transform={floorTransform(x, y, 0)}>
    <g transform={`rotate(${face})`}>
      <polygon points="0.42,0 0.26,-0.09 0.26,0.09" fill={color} fillOpacity={0.9} />
    </g>
  </g>
);

const Figure: React.FC<{p: Pose; color: string; name: string; frame: number; role: 'eric' | 'friend' | 'camera'; surfaceZ: number; badgeGlow: number}> = ({p, color, name, frame, role, surfaceZ, badgeGlow}) => {
  const sw = 3.2;
  const common = {stroke: color, strokeWidth: sw, strokeLinecap: 'round' as const, fill: 'none'};
  const fx = Math.cos(p.face * deg), fy = Math.sin(p.face * deg);
  const swing = p.moving ? Math.sin(frame * 0.45) * 0.14 : 0;

  if (p.pose === 'lie') {
    const z = surfaceZ;
    const head = P(p.x - 0.75, p.y, z + 0.14);
    const sh = P(p.x - 0.55, p.y, z + 0.1), hip = P(p.x + 0.2, p.y, z + 0.1);
    const f1 = P(p.x + 0.9, p.y - 0.1, z + 0.08), f2 = P(p.x + 0.9, p.y + 0.1, z + 0.08);
    const hand = P(p.x - 0.62, p.y, z + 0.55);
    return (
      <g>
        <line x1={sh.sx} y1={sh.sy} x2={hip.sx} y2={hip.sy} {...common} />
        <line x1={hip.sx} y1={hip.sy} x2={f1.sx} y2={f1.sy} {...common} />
        <line x1={hip.sx} y1={hip.sy} x2={f2.sx} y2={f2.sy} {...common} />
        <line x1={sh.sx} y1={sh.sy} x2={hand.sx} y2={hand.sy} {...common} strokeWidth={2.4} />
        <circle cx={head.sx} cy={head.sy} r={10} fill={theme.paper} {...common} />
        {/* the phone held over his face */}
        <rect x={hand.sx - 7} y={hand.sy - 10} width={14} height={20} rx={2} fill="#FFF3DA" stroke={theme.ink} strokeWidth={1.5} />
        <text x={head.sx - 14} y={head.sy - 22} fontSize={13} fontWeight={700} fill={color} fontFamily={theme.sans} style={halo}>{name}</text>
      </g>
    );
  }

  const sit = p.pose === 'sit';
  const zHip = sit ? surfaceZ : 0.85, zSh = sit ? surfaceZ + 0.55 : 1.4, zHead = sit ? surfaceZ + 0.78 : 1.63;
  const feet = P(p.x, p.y, 0), hip = P(p.x, p.y, zHip), sh = P(p.x, p.y, zSh), head = P(p.x, p.y, zHead);
  const l1 = sit ? P(p.x + 0.35 * fx, p.y + 0.35 * fy, 0) : P(p.x - 0.13 + swing, p.y, 0);
  const l2 = sit ? P(p.x + 0.42 * fx, p.y + 0.42 * fy, 0) : P(p.x + 0.13 - swing, p.y, 0);
  const knee = sit ? P(p.x + 0.3 * fx, p.y + 0.3 * fy, surfaceZ) : null;

  let arms: React.ReactNode;
  let gear: React.ReactNode = null;
  if (role === 'camera' && p.look) {
    const a = Math.atan2(p.look.y - p.y, p.look.x - p.x);
    const hx = p.x + 0.32 * Math.cos(a), hy = p.y + 0.32 * Math.sin(a);
    const hand = P(hx, hy, p.topDown ? 1.95 : 1.15);
    const top = P(hx, hy, p.topDown ? 2.25 : 1.55);
    arms = (
      <g>
        <line x1={P(p.x, p.y, 1.38).sx} y1={P(p.x, p.y, 1.38).sy} x2={hand.sx - 4} y2={hand.sy} {...common} strokeWidth={2.4} />
        <line x1={P(p.x, p.y, 1.38).sx} y1={P(p.x, p.y, 1.38).sy} x2={hand.sx + 4} y2={hand.sy} {...common} strokeWidth={2.4} />
      </g>
    );
    gear = (
      <g>
        <line x1={hand.sx} y1={hand.sy} x2={top.sx} y2={top.sy} stroke={color} strokeWidth={2.4} />
        <circle cx={hand.sx} cy={hand.sy} r={3.5} fill={color} />
        {p.topDown ? (
          <rect x={top.sx - 10} y={top.sy - 5} width={20} height={10} rx={2} fill={color} stroke={theme.paper} strokeWidth={1} />
        ) : (
          <rect x={top.sx - 5} y={top.sy - 11} width={10} height={22} rx={2} fill={color} stroke={theme.paper} strokeWidth={1} />
        )}
      </g>
    );
  } else {
    const a1 = P(p.x - 0.25, p.y, zSh - 0.4), a2 = P(p.x + 0.25, p.y, zSh - 0.4);
    arms = (
      <g>
        <line x1={sh.sx} y1={sh.sy - 2} x2={a1.sx} y2={a1.sy} {...common} strokeWidth={2.4} />
        <line x1={sh.sx} y1={sh.sy - 2} x2={a2.sx} y2={a2.sy} {...common} strokeWidth={2.4} />
      </g>
    );
  }

  const chest = P(p.x + 0.06 * fx, p.y + 0.06 * fy, sit ? surfaceZ + 0.4 : 1.22);
  return (
    <g>
      <FaceTick x={p.x} y={p.y} face={p.face} color={color} />
      <ellipse cx={feet.sx} cy={feet.sy} rx={9} ry={4} fill={color} fillOpacity={0.18} />
      {knee ? (
        <>
          <polyline points={`${hip.sx},${hip.sy} ${knee.sx},${knee.sy} ${l1.sx},${l1.sy}`} {...common} />
          <polyline points={`${hip.sx},${hip.sy} ${knee.sx + 3},${knee.sy} ${l2.sx},${l2.sy}`} {...common} />
        </>
      ) : (
        <>
          <line x1={hip.sx} y1={hip.sy} x2={l1.sx} y2={l1.sy} {...common} />
          <line x1={hip.sx} y1={hip.sy} x2={l2.sx} y2={l2.sy} {...common} />
        </>
      )}
      <line x1={hip.sx} y1={hip.sy} x2={sh.sx} y2={sh.sy} {...common} />
      {arms}
      <circle cx={head.sx} cy={head.sy} r={10} fill={theme.paper} {...common} />
      <circle cx={head.sx + 5 * fx} cy={head.sy + 2.2 * fy} r={2} fill={color} />
      {gear}
      {role === 'eric' && (
        <g>
          {badgeGlow > 0 && [0, 1].map((i) => {
            const ph = ((badgeGlow * 1.6 + i / 2) % 1 + 1) % 1;
            return <circle key={i} cx={chest.sx} cy={chest.sy} r={9 + ph * 26} fill="none" stroke={theme.eric} strokeOpacity={0.9 * (1 - ph)} strokeWidth={2} />;
          })}
          <rect x={chest.sx - 5} y={chest.sy - 7} width={10} height={14} rx={1.5} fill={badgeGlow > 0 ? '#FFD37A' : '#FFF3DA'} stroke={theme.ink} strokeWidth={1.3} />
        </g>
      )}
      <text x={head.sx} y={head.sy - 17} fontSize={13} fontWeight={700} fill={color} fontFamily={theme.sans} textAnchor="middle" style={halo}>{name}</text>
    </g>
  );
};

const ViewCone: React.FC<{p: Pose}> = ({p}) => {
  if (!p.look) return null;
  if (p.topDown) {
    const top = P(p.look.x, p.look.y, 2.2);
    const base = P(p.look.x, p.look.y, 0);
    return (
      <g>
        <g transform={floorTransform(p.look.x, p.look.y, 0)}>
          <circle cx={0} cy={0} r={0.75} fill={theme.camera} fillOpacity={0.12} stroke={theme.camera} strokeWidth={1.5} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
        </g>
        <line x1={top.sx} y1={top.sy} x2={base.sx} y2={base.sy} stroke={theme.camera} strokeWidth={1.2} strokeDasharray="3 3" />
        <text x={base.sx} y={base.sy + 46} fontSize={11} fill={theme.camera} fontFamily={theme.sans} textAnchor="middle" style={halo}>top-down</text>
      </g>
    );
  }
  const a = Math.atan2(p.look.y - p.y, p.look.x - p.x);
  const dist = Math.hypot(p.look.x - p.x, p.look.y - p.y);
  const L = Math.min(dist + 0.7, 4.2);
  const half = 20 * deg;
  const arc = Array.from({length: 9}, (_, i) => {
    const ang = a - half + (2 * half * i) / 8;
    return pt(p.x + L * Math.cos(ang), p.y + L * Math.sin(ang), 0);
  }).join(' ');
  return (
    <g>
      <polygon points={`${pt(p.x, p.y, 0)} ${arc}`} fill={theme.camera} fillOpacity={0.11} stroke={theme.camera} strokeOpacity={0.7} strokeWidth={1.2} strokeDasharray="4 3" />
      <line x1={P(p.x, p.y, 1.5).sx} y1={P(p.x, p.y, 1.5).sy} x2={P(p.look.x, p.look.y, 1.2).sx} y2={P(p.look.x, p.look.y, 1.2).sy} stroke={theme.camera} strokeOpacity={0.55} strokeWidth={1} strokeDasharray="2 4" />
      <circle cx={P(p.look.x, p.look.y, 1.2).sx} cy={P(p.look.x, p.look.y, 1.2).sy} r={4} fill="none" stroke={theme.camera} strokeWidth={1.5} />
    </g>
  );
};

const Trail: React.FC<{pts: {x: number; y: number}[]; color: string; dash: string; width: number}> = ({pts, color, dash, width}) => {
  if (pts.length < 2) return null;
  return <polyline points={pts.map((q) => pt(q.x, q.y, 0)).join(' ')} fill="none" stroke={color} strokeWidth={width} strokeDasharray={dash} strokeOpacity={0.85} strokeLinejoin="round" />;
};

const surfaceFor = (x: number, y: number) => {
  for (const o of shotlist.plan.objects) {
    if (x >= o.x0 - 0.3 && x <= o.x1 + 0.3 && y >= o.y0 - 0.3 && y <= o.y1 + 0.3) return o.h;
  }
  return 0;
};

export const Apartment: React.FC<{t: number; beat: Beat; frame: number}> = ({t, beat, frame}) => {
  const {plan} = shotlist;
  const eric = poseAt(shotlist.keyframes.eric, t);
  const friend = poseAt(shotlist.keyframes.friend, t);
  const cam = poseAt(shotlist.keyframes.camera, t);
  const frozen = !!beat.xray;
  const silence = !!beat.silence;

  // Which devices sound right now (the real files on the timeline), plus the hall bed on the TV.
  const active = new Set<string>();
  for (const a of shotlist.audio) if (a.kind === 'guest' && t >= a.at && t < a.at + a.duration) active.add(a.device);
  const bedOn = t >= shotlist.hallBed.on && t < shotlist.hallBed.off;
  if (bedOn) active.add('TV');
  for (const p of beat.plays) if (p.placeholder && t >= p.t && t < p.t + p.length) active.add(p.device);

  // Badge glow for 1.6 s after a buzz; callouts for buzz/ring events.
  let badgeGlow = 0;
  const callouts: {x: number; y: number; z: number; text: string; color: string; age: number}[] = [];
  for (const b of shotlist.beats) {
    for (const e of b.events ?? []) {
      const age = t - e.t;
      if (age < 0 || age > 2.2) continue;
      if (e.kind === 'buzz') badgeGlow = Math.max(badgeGlow, age < 1.6 ? age : 0);
      if (e.kind === 'click') continue;
      if (e.device === 'badge') callouts.push({x: eric.x, y: eric.y, z: 2.15, text: e.label, color: theme.eric, age});
      else {
        const d = plan.devices.find((dd) => dd.id === e.device);
        if (d) callouts.push({x: d.x, y: d.y, z: d.z + 0.55, text: e.label, color: theme.sound, age});
      }
    }
  }
  // "met before" rings: around the device whose guest was just named.
  const ringFor = (id: string) => shotlist.beats.some((b) => (b.events ?? []).some((e) => e.kind === 'ring' && e.device !== 'badge' && t >= e.t && t < e.t + 2.2 && (e.label.includes('Siddharth') ? id === 'Mac-3' : e.label.includes('Kenji') || e.label.includes('coffee') ? id === 'iPhone-K' : false)));

  const reached = (m: {x: number; y: number}) => shotlist.keyframes.eric.some((k) => k.t <= t && Math.abs(k.x - m.x) < 1e-6 && Math.abs(k.y - m.y) < 1e-6);

  const partition = plan.rooms.filter((r) => r.door);
  const WALL_H = 0.55;

  return (
    <svg width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0, filter: frozen ? 'grayscale(0.85)' : undefined}}>
      <defs>
        <radialGradient id="glow">
          <stop offset="0%" stopColor={theme.sound} stopOpacity={0.45} />
          <stop offset="100%" stopColor={theme.sound} stopOpacity={0} />
        </radialGradient>
      </defs>

      {/* floors */}
      {plan.rooms.map((r) => (
        <polygon key={r.id} points={`${pt(r.x0, r.y0)} ${pt(r.x1, r.y0)} ${pt(r.x1, r.y1)} ${pt(r.x0, r.y1)}`}
          fill={r.id === 'living' ? '#EDE7D9' : r.id === 'friend' ? '#E9E9DE' : '#EDE3DC'} stroke="none" />
      ))}
      {/* room labels */}
      {plan.rooms.map((r) => {
        const lp = P(r.x0 + 0.25, r.y1 - 0.3);
        return <text key={r.id} x={lp.sx} y={lp.sy} fontSize={13} letterSpacing={2} fill={theme.inkFaint} fontFamily={theme.sans} fontWeight={700}>{r.label}</text>;
      })}
      {/* outer walls, low, wireframe */}
      {(() => {
        const b = plan.bounds as unknown as {x0: number; y0: number; x1: number; y1: number};
        const corners: [number, number][] = [[b.x0, b.y0], [b.x1, b.y0], [b.x1, b.y1], [b.x0, b.y1]];
        return (
          <g>
            <polygon points={corners.map(([x, y]) => pt(x, y, 0)).join(' ')} fill="none" stroke={theme.ink} strokeWidth={2.2} />
            <polygon points={corners.map(([x, y]) => pt(x, y, WALL_H)).join(' ')} fill="none" stroke={theme.inkFaint} strokeWidth={1} />
            {corners.map(([x, y], i) => <line key={i} x1={P(x, y, 0).sx} y1={P(x, y, 0).sy} x2={P(x, y, WALL_H).sx} y2={P(x, y, WALL_H).sy} stroke={theme.inkSoft} strokeWidth={1.2} />)}
          </g>
        );
      })()}
      {/* partitions: the wall at x = 4 with its two doors, and the wall between the two left rooms */}
      {partition.map((r) => {
        const d = r.door!;
        const x = r.x1;
        return (
          <g key={r.id}>
            <line x1={P(x, r.y0).sx} y1={P(x, r.y0).sy} x2={P(x, d.from).sx} y2={P(x, d.from).sy} stroke={theme.ink} strokeWidth={2.2} />
            <line x1={P(x, d.to).sx} y1={P(x, d.to).sy} x2={P(x, r.y1).sx} y2={P(x, r.y1).sy} stroke={theme.ink} strokeWidth={2.2} />
            <line x1={P(x, r.y0, WALL_H).sx} y1={P(x, r.y0, WALL_H).sy} x2={P(x, d.from, WALL_H).sx} y2={P(x, d.from, WALL_H).sy} stroke={theme.inkFaint} strokeWidth={1} />
            <line x1={P(x, d.to, WALL_H).sx} y1={P(x, d.to, WALL_H).sy} x2={P(x, r.y1, WALL_H).sx} y2={P(x, r.y1, WALL_H).sy} stroke={theme.inkFaint} strokeWidth={1} />
            {[d.from, d.to].map((y, i) => <line key={i} x1={P(x, y, 0).sx} y1={P(x, y, 0).sy} x2={P(x, y, WALL_H).sx} y2={P(x, y, WALL_H).sy} stroke={theme.inkSoft} strokeWidth={1.2} />)}
            {/* door leaf, open into the living room */}
            <line x1={P(x, d.from).sx} y1={P(x, d.from).sy} x2={P(x + 0.7, d.from + 0.35).sx} y2={P(x + 0.7, d.from + 0.35).sy} stroke={theme.inkSoft} strokeWidth={1.4} />
            <text x={P(x + 0.1, d.to + 0.32).sx} y={P(x + 0.1, d.to + 0.32).sy} fontSize={11} fill={theme.inkFaint} fontFamily={theme.sans} style={halo}>{d.label}</text>
          </g>
        );
      })}
      <line x1={P(0, 4).sx} y1={P(0, 4).sy} x2={P(4, 4).sx} y2={P(4, 4).sy} stroke={theme.ink} strokeWidth={2.2} />

      {/* camera spots */}
      {plan.cameraSpots.filter((c) => c.id !== 'K2b').map((c) => {
        const q = P(c.x, c.y, 0);
        return (
          <g key={c.id}>
            <rect x={q.sx - 4} y={q.sy - 4} width={8} height={8} fill="none" stroke={theme.camera} strokeWidth={1.3} transform={`rotate(45 ${q.sx} ${q.sy})`} />
            <text x={q.sx + 8} y={q.sy + 4} fontSize={11} fontWeight={700} fill={theme.camera} fontFamily={theme.sans} style={halo}>{c.id}</text>
          </g>
        );
      })}

      {/* trails */}
      <Trail pts={trailAt(shotlist.keyframes.camera, t)} color={theme.camera} dash="2 5" width={1.6} />
      <Trail pts={trailAt(shotlist.keyframes.friend, t)} color={theme.friend} dash="2 4" width={1.8} />
      <Trail pts={trailAt(shotlist.keyframes.eric, t)} color={theme.eric} dash="7 5" width={2.6} />

      {/* furniture */}
      {plan.objects.map((o) => <Box key={o.id} {...o} />)}

      {/* Eric's numbered marks */}
      {plan.marks.map((m) => {
        const q = P(m.x, m.y, 0);
        const on = reached(m);
        const dx = m.id === 'B' || m.id === 'C' ? -14 : 14;
        return (
          <g key={m.id}>
            <circle cx={q.sx} cy={q.sy} r={11} fill={on ? theme.eric : theme.paper} stroke={theme.eric} strokeWidth={2} />
            <text x={q.sx} y={q.sy + 4.5} fontSize={12} fontWeight={700} fill={on ? '#fff' : theme.eric} fontFamily={theme.mono} textAnchor="middle">{m.n}</text>
            <text x={q.sx + dx} y={q.sy + 4} fontSize={11} fill={theme.inkSoft} fontFamily={theme.sans} textAnchor={dx < 0 ? 'end' : 'start'} style={halo}>{m.label}</text>
          </g>
        );
      })}

      {/* view cone under the figures */}
      <ViewCone p={cam} />

      {/* devices */}
      {plan.devices.map((d) => <DeviceGlyph key={d.id} d={d} active={active.has(d.id)} t={t} muted={silence && d.id === 'TV'} />)}
      {plan.devices.filter((d) => ringFor(d.id)).map((d) => (
        <g key={d.id + 'ring'} transform={floorTransform(d.x, d.y, 0)}>
          <circle cx={0} cy={0} r={0.5} fill="none" stroke={theme.friend} strokeWidth={3} vectorEffect="non-scaling-stroke" />
        </g>
      ))}

      {/* people, painted back to front by y */}
      {[{p: friend, color: theme.friend, name: 'FRIEND', role: 'friend' as const}, {p: cam, color: theme.camera, name: 'CAMERA', role: 'camera' as const}, {p: eric, color: theme.eric, name: 'ERIC', role: 'eric' as const}]
        .sort((a, b) => a.p.y - b.p.y)
        .map((f) => <Figure key={f.name} p={f.p} color={f.color} name={f.name} frame={frozen ? 0 : frame} role={f.role} surfaceZ={surfaceFor(f.p.x, f.p.y)} badgeGlow={f.role === 'eric' ? badgeGlow : 0} />)}

      {/* callouts */}
      {callouts.map((c, i) => {
        const q = P(c.x, c.y, c.z);
        const w = Math.min(560, c.text.length * 7.6 + 24);
        const x = Math.max(50, Math.min(1190 - w, q.sx - w / 2));
        const op = c.age > 1.7 ? Math.max(0, 1 - (c.age - 1.7) / 0.5) : 1;
        return (
          <g key={i} opacity={op}>
            <line x1={q.sx} y1={q.sy + 8} x2={q.sx} y2={q.sy + 30} stroke={c.color} strokeWidth={1.5} />
            <rect x={x} y={q.sy - 22} width={w} height={30} rx={6} fill={theme.panel} stroke={c.color} strokeWidth={1.5} />
            <text x={x + 12} y={q.sy - 2} fontSize={14} fontWeight={600} fill={c.color} fontFamily={theme.sans}>{c.text}</text>
          </g>
        );
      })}

      {/* silence / X-ray state */}
      {(silence || frozen) && (
        <g>
          <rect x={30} y={82} width={1170} height={740} fill={frozen ? '#1E2E5C' : 'none'} fillOpacity={0.14} stroke={theme.cold} strokeWidth={3} rx={8} />
          <rect x={44} y={94} width={frozen ? 330 : 190} height={30} rx={6} fill={theme.cold} />
          <text x={58} y={115} fontSize={15} fontWeight={700} fill="#fff" fontFamily={theme.sans} letterSpacing={1}>{frozen ? 'X-RAY · FREEZE-FRAME (POST)' : 'SILENCE (POST)'}</text>
          {frozen && <line x1={30} y1={82 + ((t * 120) % 740)} x2={1200} y2={82 + ((t * 120) % 740)} stroke={theme.cold} strokeOpacity={0.5} strokeWidth={1.5} />}
        </g>
      )}
    </svg>
  );
};
