import { useEffect, useState, type FormEvent } from 'react'

export type Session = 'checking' | 'in' | 'out'

/** Whether this browser holds the server key. The cookie is HttpOnly, so the page asks the API instead of looking. */
export function useSession(): [Session, (s: Session) => void] {
  const [session, setSession] = useState<Session>('checking')
  useEffect(() => {
    let alive = true
    fetch('/api/recordings')
      .then((r) => alive && setSession(r.status === 401 ? 'out' : 'in'))
      .catch(() => alive && setSession('in')) // the server is down: the list says so
    return () => {
      alive = false
    }
  }, [])
  return [session, setSession]
}

/** The server key, once: POST /login answers with an HttpOnly cookie that the API and the event stream accept. */
export function Login({ onIn }: { onIn: () => void }) {
  const [key, setKey] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: key.trim() }),
      })
      if (r.ok) {
        setKey('')
        onIn()
      } else {
        setError(r.status === 401 ? 'That key is wrong.' : r.status === 429 ? 'Too many tries. Wait a minute.' : `The server answered ${r.status}.`)
      }
    } catch {
      setError('Could not reach the server.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="list">
      <form className="card login" onSubmit={submit}>
        <h2>Server key</h2>
        <p className="soft">
          This server needs its key: <code>HALLWISE_TOKEN</code> in the repo's <code>.env</code>. This browser keeps it
          in a cookie afterwards.
        </p>
        <input
          type="password"
          name="token"
          aria-label="Server key"
          autoComplete="off"
          autoFocus
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
        <button className="primary" disabled={busy || !key.trim()}>
          {busy ? 'Checking…' : 'Open'}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  )
}
