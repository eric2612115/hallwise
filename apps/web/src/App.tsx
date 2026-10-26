import { useEffect, useState } from 'react'
import { bearing, mmss, nameFor, type State } from './model'
import { SoundField } from './SoundField'
import { useRecording, useRecordings } from './useRecording'

type Theme = 'system' | 'light' | 'dark'

function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem('theme') as Theme) || 'system'
    } catch {
      return 'system'
    }
  })
  useEffect(() => {
    if (theme === 'system') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
    try {
      localStorage.setItem('theme', theme)
    } catch {
      /* private mode */
    }
  }, [theme])
  return [theme, setTheme]
}

function useHash(): string {
  const [hash, setHash] = useState(location.hash)
  useEffect(() => {
    const on = () => setHash(location.hash)
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  }, [])
  return hash
}

export default function App() {
  const [theme, setTheme] = useTheme()
  const hash = useHash()
  const match = /^#\/r\/([^/]+)/.exec(hash)
  return (
    <>
      <header className="top">
        <a href="#/"><h1>Hallwise</h1></a>
        <span className="soft">who you met · what you owe them</span>
        <span className="spacer" />
        <select value={theme} onChange={(e) => setTheme(e.target.value as Theme)} aria-label="Appearance">
          <option value="system">Paper: system</option>
          <option value="light">Paper: light</option>
          <option value="dark">Paper: dark</option>
        </select>
      </header>
      {match ? <Dashboard id={match[1]} /> : <RecordingList />}
    </>
  )
}

function RecordingList() {
  const rows = useRecordings()
  return (
    <main className="list">
      <h2>Recordings</h2>
      {!rows.length && <p className="empty">Nothing recorded yet. Start the badge app and this list fills in.</p>}
      {rows.map((r) => (
        <a key={r.id} className="card" href={`#/r/${r.id}`}>
          <span>
            <span className={`dot${r.live ? ' live' : ''}`} /> &nbsp;{r.id}
          </span>
          <small>
            {r.device || 'unknown device'} · {r.layout} · {new Date(r.started * 1000).toLocaleString()}
          </small>
        </a>
      ))}
    </main>
  )
}

function Dashboard({ id }: { id: string }) {
  const { state, status } = useRecording(id)
  return (
    <>
      <div className="top" style={{ position: 'static', borderTop: 0 }}>
        <span className={`dot${status === 'live' ? ' live' : ''}`} />
        <span className="soft">
          {status === 'live' ? 'live' : status === 'ended' ? 'finished' : status} · {mmss(state.tMs)} · {id}
        </span>
      </div>
      <main className="layout">
        <div className="column">
          <Transcript state={state} />
        </div>
        <div className="column">
          <People state={state} />
          <Promises state={state} />
          <Suspects state={state} />
          <section className="card">
            <h2>Where everyone is</h2>
            <SoundField state={state} />
          </section>
          {state.topics.length > 0 && (
            <section className="card">
              <h2>The room is talking about</h2>
              <div className="topics">{state.topics.join('  ·  ')}</div>
            </section>
          )}
        </div>
      </main>
    </>
  )
}

function People({ state }: { state: State }) {
  return (
    <section className="card">
      <h2>People</h2>
      {!state.people.length && <div className="empty">Nobody yet</div>}
      {state.people.map((p) => {
        const b = bearing(state, p)
        const rel = b === null ? null : b - (state.yaw ?? 0) - 90 // 0 = straight ahead of the badge
        return (
          <div className="person" key={p.key}>
            <div className="arrow" style={rel === null ? { opacity: 0.35 } : { transform: `rotate(${-rel}deg)` }}>
              {rel === null ? '·' : '↑'}
            </div>
            <div>
              <div className="name">{p.name}</div>
              <small>{[p.company, p.role].filter(Boolean).join(' · ')}</small>
              <div className="tags">
                {p.language && <span className="tag">{p.language}</span>}
                {p.introducedBy && <span className="tag">via {nameFor(state, p.introducedBy)}</span>}
              </div>
            </div>
          </div>
        )
      })}
    </section>
  )
}

function Promises({ state }: { state: State }) {
  if (!state.promises.length) return null
  return (
    <section className="card">
      <h2>You owe · they owe</h2>
      {state.promises.map((p) => (
        <div className="promise" key={p.key}>
          <div>{p.what}</div>
          <div className="meta">
            <span>{p.owedBy === 'owner' ? `→ ${nameFor(state, p.owedTo)}` : `${nameFor(state, p.owedBy)} → you`}</span>
            {p.replaces && <s>{p.replaces}</s>}
            {p.due && <span className="due">{p.due}</span>}
          </div>
        </div>
      ))}
    </section>
  )
}

function Suspects({ state }: { state: State }) {
  if (!state.suspects.length) return null
  return (
    <section className="card">
      <h2>Check these words</h2>
      {state.suspects.map((w) => (
        <div className="suspect" key={`${w.turn}-${w.heard}`}>
          <s>{w.heard}</s>
          <span className="soft">→</span>
          <strong>{w.likely}</strong>
          <small>turn {w.turn}</small>
        </div>
      ))}
    </section>
  )
}

function Transcript({ state }: { state: State }) {
  return (
    <section className="card">
      <h2>Transcript</h2>
      <div className="transcript">
        {!state.lines.length && <div className="empty">Waiting for the first words…</div>}
        {state.lines.map((l) => {
          const kind = state.turnKinds[l.turn] ?? 'conversation'
          const who = state.ownerSpeakers.includes(l.speaker)
            ? 'You'
            : (state.people.find((p) => p.speakers.includes(l.speaker))?.name.split(' ')[0] ?? l.speaker)
          const cls = kind === 'incidental' || kind === 'noise' ? 'filtered' : kind === 'ambient' || kind === 'stage' ? 'ambient' : ''
          return (
            <div className={`line ${cls}`} key={l.turn}>
              <span className="who">{who}</span>
              <span>
                {l.text}
                <span className="t">{mmss(l.startMs)}</span>
                {cls === 'filtered' && <span className="t">filtered</span>}
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
