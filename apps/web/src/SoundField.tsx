import { bearing, distance, personForSpeaker, type State } from './model'

/** The room from above: the badge in the middle, each speaker where their voice came from. */
export function SoundField({ state }: { state: State }) {
  const size = 300
  const c = size / 2
  const r = 118
  const yaw = state.yaw ?? 0
  const activeSpeaker = state.lastSpeaker && state.lastSpeaker.untilMs >= state.tMs ? state.lastSpeaker.speaker : null
  const speakers = Object.entries(state.speakerAzimuth).filter(([k]) => !state.ownerSpeakers.includes(k))

  // Room coordinates (ambisonics convention): azimuth 0 = where the badge faced at the start, up on this map;
  // positive = to the left. The badge now faces room azimuth `yaw`.
  const point = (az: number, radius: number) => ({
    x: c - radius * Math.sin((az * Math.PI) / 180),
    y: c - radius * Math.cos((az * Math.PI) / 180),
  })
  const facing = point(yaw, 34)

  // One icon per person (mean over their labels); unnamed voices are faint dots.
  const placed = new Map<string, { az: number; d: number; label: string; named: boolean; active: boolean }>()
  for (const [speaker, az] of speakers) {
    const person = personForSpeaker(state, speaker)
    const key = person?.key ?? speaker
    const b = person ? bearing(state, person) ?? az : az
    const prev = placed.get(key)
    placed.set(key, {
      az: b,
      d: distance(state, person ? person.speakers : [speaker]),
      label: person?.name ?? '',
      named: !!person,
      active: (prev?.active ?? false) || speaker === activeSpeaker,
    })
  }

  // Close voices on the inner ring, far ones at the edge; named neighbours within 20° stagger in and out so
  // their labels stay readable when three people stand on one side.
  const radii = new Map<string, number>()
  for (const [key, p] of placed) radii.set(key, r * (0.64 + 0.36 * p.d))
  const named = [...placed.entries()].filter(([, p]) => p.named).sort((a, b) => a[1].az - b[1].az)
  let push = false
  named.forEach(([key, p], i) => {
    if (i === 0) return
    const gap = Math.abs(p.az - named[i - 1][1].az)
    push = gap < 20 ? !push : false
    if (push) radii.set(key, (radii.get(key) ?? r) + 26)
  })

  return (
    <svg viewBox={`0 0 ${size} ${size}`} width="100%" style={{ maxWidth: 360, display: 'block', margin: '0 auto' }}>
      <circle cx={c} cy={c} r={r + 22} fill="none" stroke="var(--rule)" />
      <circle cx={c} cy={c} r={r / 2 + 11} fill="none" stroke="var(--rule)" strokeDasharray="3 5" />
      {/* the badge and where it faces */}
      <line x1={c} y1={c} x2={facing.x} y2={facing.y} stroke="var(--ink-soft)" strokeWidth={2} strokeLinecap="round" />
      <circle cx={c} cy={c} r={9} fill="var(--ink)" />
      <text x={c} y={c + 24} textAnchor="middle" fontSize={11} fill="var(--ink-soft)">you</text>
      {[...placed.entries()].map(([key, p]) => {
        const at = point(p.az, radii.get(key) ?? r)
        if (!p.named)
          return (
            <circle key={key} cx={at.x} cy={at.y} r={p.active ? 7 : 4} fill={p.active ? 'var(--accent)' : 'var(--rule)'} />
          )
        const words = p.label.split(' ')
        const initials = words.length >= 2 ? words.slice(0, 2).map((w) => w[0]).join('') : p.label.slice(0, 2)
        return (
          <g key={key}>
            <circle
              cx={at.x}
              cy={at.y}
              r={p.active ? 15 : 11}
              fill={p.active ? 'var(--accent)' : 'var(--paper-deep)'}
              stroke={p.active ? 'var(--accent)' : 'var(--ink-soft)'}
              strokeWidth={1.5}
            />
            <text
              x={at.x}
              y={at.y + 4}
              textAnchor="middle"
              fontSize={11}
              fill={p.active ? 'var(--paper)' : 'var(--ink)'}
              fontFamily="var(--serif)"
            >
              {initials}
            </text>
            <text x={at.x} y={at.y + 28} textAnchor="middle" fontSize={11} fill="var(--ink-soft)">
              {words[0]}
            </text>
          </g>
        )
      })}
      {!placed.size && (
        <text x={c} y={c - 40} textAnchor="middle" fontSize={12} fill="var(--ink-soft)" fontStyle="italic">
          {state.layout === 'foa' ? 'listening…' : 'no direction on this recording'}
        </text>
      )}
    </svg>
  )
}
