import { useEffect, useState } from 'react'
import { bearing, mmss, nameFor, type State } from './model'
import { Login, useSession } from './Login'
import { SoundField } from './SoundField'
import { useRecording, useRecordings } from './useRecording'

type Theme = 'system' | 'light' | 'dark'
const THEMES: Theme[] = ['system', 'light', 'dark']

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

/** Sun, moon, or half-disc for "follow the system". */
function ThemeIcon({ theme }: { theme: Theme }) {
  const stroke = 'currentColor'
  if (theme === 'light')
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="1.8" strokeLinecap="round">
        <circle cx="12" cy="12" r="4.2" />
        <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" />
      </svg>
    )
  if (theme === 'dark')
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="1.8" strokeLinejoin="round">
        <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
      </svg>
    )
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="1.8">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 3.5v17A8.5 8.5 0 0 0 12 3.5z" fill={stroke} />
    </svg>
  )
}

export default function App() {
  const [theme, setTheme] = useTheme()
  const [session, setSession] = useSession()
  const hash = useHash()
  const match = /^#\/r\/([^/]+)/.exec(hash)
  const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]
  return (
    <>
      <header className="top">
        <a href="#/" className="brand">
          <span className="mark" aria-hidden="true" />
          <h1>Hallwise</h1>
        </a>
        <nav className="nav">
          <a href="#/" className={match ? '' : 'current'}>Recordings</a>
        </nav>
        <span className="spacer" />
        <button className="icon" onClick={() => setTheme(next)} title={`Paper: ${theme} — click for ${next}`} aria-label="Appearance">
          <ThemeIcon theme={theme} />
        </button>
      </header>
      {session === 'out' ? (
        <Login onIn={() => setSession('in')} />
      ) : session === 'checking' ? null : match ? (
        <Dashboard id={match[1]} />
      ) : (
        <RecordingList onOut={() => setSession('out')} />
      )}
    </>
  )
}

function RecordingList({ onOut }: { onOut: () => void }) {
  const rows = useRecordings(onOut)
  return (
    <main className="list">
      <h2>Recordings</h2>
      {!rows.length && <p className="empty">Nothing recorded yet. Start the badge app and this list fills in.</p>}
      {rows.map((r) => (
        <a key={r.id} className="card row" href={`#/r/${r.id}`}>
          <span>
            <span className={`dot${r.live ? ' live' : ''}`} /> &nbsp;
            <span className="title">{r.event || 'Untitled recording'}</span>
            {r.venue && <small> · {r.venue}</small>}
          </span>
          <small>
            {new Date(r.started * 1000).toLocaleString()} · {r.device || 'unknown device'} · {r.layout}
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
      <div className="subhead">
        <span className={`dot${status === 'live' ? ' live' : ''}`} />
        <span className="title">{state.event || id}</span>
        <span className="soft">
          {state.venue && `${state.venue} · `}
          {status === 'live' ? 'live' : status === 'ended' ? 'finished' : status} · {mmss(state.tMs)}
        </span>
      </div>
      <main className="layout">
        <div className="column">
          <Transcript state={state} />
        </div>
        <div className="column">
          <section className="card">
            <h2>Where everyone is</h2>
            <SoundField state={state} />
          </section>
          <People state={state} />
          <Promises state={state} />
          <Suspects state={state} />
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
        const rel = b === null ? null : b - (state.yaw ?? 0) // 0 = straight ahead of the badge, positive = left
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
          const tr = state.translations[l.turn]
          return (
            <div className={`line ${cls}`} key={l.turn}>
              <span className="who">{who}</span>
              <span>
                {l.text}
                <span className="t">{mmss(l.startMs)}</span>
                {cls === 'filtered' && <span className="t">filtered</span>}
                {tr && (
                  <div className="translation">
                    {tr.english} <span className="t">translated from {tr.language}</span>
                  </div>
                )}
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
