import { useEffect, useState } from 'react'
import { errorMessage, getJson } from './api'

interface Resource<T> {
  path: string | null
  data: T | null
  loading: boolean
  error: string | null
  receivedAt: number | null
}

export function useResource<T>(path: string | null, refresh: number, poll = false): Resource<T> {
  const [state, setState] = useState<Resource<T>>({ path: null, data: null, loading: !!path, error: null, receivedAt: null })
  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    let timer: number | undefined
    const read = async () => {
      setState(previous => ({ path, data: previous.path === path ? previous.data : null, loading: true, error: previous.path === path ? previous.error : null, receivedAt: previous.path === path ? previous.receivedAt : null }))
      try {
        const data = await getJson<T>(path, controller.signal)
        if (!controller.signal.aborted) setState({ path, data, loading: false, error: null, receivedAt: Date.now() })
      } catch (error) {
        if (!controller.signal.aborted) setState(previous => ({ ...previous, path, loading: false, error: errorMessage(error) }))
      } finally {
        if (poll && !controller.signal.aborted) timer = window.setTimeout(() => void read(), 15_000)
      }
    }
    void read()
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [path, refresh, poll])
  if (!path || state.path !== path) return { path, data: null, loading: !!path, error: null, receivedAt: null }
  return state
}

export function useNow() {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 5_000)
    return () => window.clearInterval(timer)
  }, [])
  return now
}
