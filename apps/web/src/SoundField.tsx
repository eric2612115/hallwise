import { bearing, personForSpeaker, type State } from './model'

/** The room from above: the badge in the middle, each speaker where their voice came from. */
export function SoundField({ state }: { state: State }) {
  const size = 300
  const c = size / 2
  const r = 118
  const yaw = state.yaw ?? 0
  const activeSpeaker = state.lastSpeaker && state.lastSpeaker.untilMs >= state.tMs ? state.lastSpeaker.speaker : null
  const speakers = Object.entries(state.speakerAzimuth).filter(([k]) => !state.ownerSpeakers.includes(k))

  // Room coordinates: azimuth 0 = the badge's x axis (to the wearer's right), 90 = straight ahead.
  const point = (az: number, radius: number) => ({
    x: c + radius * Math.cos((az * Math.PI) / 180),
    y: c - radius * Math.sin((az * Math.PI) / 180),
  })
  const facing = point(yaw + 90, 34)

  // One icon per person (mean over their labels); unnamed labels get their own small icon.
  const placed = new Map<string, { az: number; label: string; active: boolean }>()
  for (const [speaker, az] of speakers) {
    const person = personForSpeaker(state, speaker)
    const key = person?.key ?? speaker
    const b = person ? bearing(state, person) ?? az : az
    const prev = placed.get(key)
    placed.set(key, {
      az: b,
      label: person?.name ?? speaker,
      active: (prev?.active ?? false) || speaker === activeSpeaker,
    })
  }

  return (
    <svg viewBox={`0 0 ${size} ${size}`} width="100%" style={{ maxWidth: 360, display: 'block', margin: '0 auto' }}>
      <circle cx={c} cy={c} r={r + 22} fill="none" stroke="var(--rule)" />
      <circle cx={c} cy={c} r={r / 2 + 11} fill="none" stroke="var(--rule)" strokeDasharray="3 5" />
      {/* the badge and where it faces */}
      <line x1={c} y1={c} x2={facing.x} y2={facing.y} stroke="var(--ink-soft)" strokeWidth={2} strokeLinecap="round" />
      <circle cx={c} cy={c} r={9} fill="var(--ink)" />
      <text x={c} y={c + 24} textAnchor="middle" fontSize={11} fill="var(--ink-soft)">you</text>
      {[...placed.entries()].map(([key, p]) => {
        const at = point(p.az, r)
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
              {p.label.slice(0, 2)}
            </text>
            <text x={at.x} y={at.y + 28} textAnchor="middle" fontSize={11} fill="var(--ink-soft)">
              {p.label.split(' ')[0]}
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
