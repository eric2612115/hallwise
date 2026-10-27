import { useEffect, useState } from 'react'
import { empty, reduce, type Event, type State } from './model'

export type Status = 'connecting' | 'live' | 'ended' | 'error'

/** Follow one recording: everything so far, then live events until it ends. */
export function useRecording(id: string): { state: State; status: Status } {
  const [state, setState] = useState<State>(empty)
  const [status, setStatus] = useState<Status>('connecting')

  useEffect(() => {
    setState(empty)
    setStatus('connecting')
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/events/${id}`)
    let current = empty
    ws.onmessage = (m) => {
      const e = JSON.parse(m.data) as Event
      current = reduce(current, e)
      setState(current)
      if (e.type === 'recording_end') setStatus('ended')
      else if (status !== 'ended') setStatus('live')
    }
    ws.onerror = () => setStatus('error')
    ws.onclose = () => setStatus((prev) => (prev === 'live' ? 'ended' : prev))
    return () => ws.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  return { state, status }
}

export interface RecordingMeta {
  id: string
  started: number
  device: string
  layout: string
  event?: string
  venue?: string
  live: boolean
}

/** Every recording, polled; `onOut` when the server stops taking this browser's key (a new key, a restart). */
export function useRecordings(onOut: () => void): RecordingMeta[] {
  const [list, setList] = useState<RecordingMeta[]>([])
  useEffect(() => {
    let alive = true
    const load = () =>
      fetch('/api/recordings')
        .then((r) => {
          if (r.status === 401) {
            onOut()
            throw new Error('unauthorized')
          }
          return r.json()
        })
        .then((rows: RecordingMeta[]) => alive && setList(rows))
        .catch(() => undefined)
    load()
    const timer = setInterval(load, 5000)
    return () => {
      alive = false
      clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return list
}
