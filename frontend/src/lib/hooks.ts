import { useSearchParams } from 'react-router-dom'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export interface AsyncState<T> {
  data: T | null
  error: ApiError | null
  /** true during the first load and every reload (data from the previous request stays visible meanwhile) */
  loading: boolean
  reload: () => void
}

/**
 * Load data on mount and when `deps` change; optionally poll. Ignores results from stale requests and keeps the previous
 * data on screen while the next request runs, so filters and pagination never flash to empty.
 * Polling pauses while the tab is hidden.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs?: number): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])

  const run = useCallback(() => {
    const id = ++seq.current
    setLoading(true)
    fnRef.current()
      .then((d) => { if (alive.current && id === seq.current) { setData(d); setError(null) } })
      .catch((e) => { if (alive.current && id === seq.current) setError(e instanceof ApiError ? e : new ApiError(0, 'ERROR', String(e?.message ?? e))) })
      .finally(() => { if (alive.current && id === seq.current) setLoading(false) })
  }, [])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(run, deps)
  useEffect(() => {
    if (!pollMs) return
    const t = setInterval(() => { if (typeof document === 'undefined' || document.visibilityState !== 'hidden') run() }, pollMs)
    return () => clearInterval(t)
  }, [pollMs, run])
  return { data, error, loading, reload: run }
}

/** A value that settles `ms` after the last change: used so typing in a search box makes one request, not one per key. */
export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function useMediaQuery(query: string): boolean {
  const get = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false)
  const [m, setM] = useState(get)
  useEffect(() => {
    if (!window.matchMedia) return
    const mq = window.matchMedia(query)
    const on = () => setM(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return m
}

/** Keyboard shortcut that ignores typing in inputs unless `allowInInput`. `combo` like 'mod+k' or '/'. */
export function useHotkey(combo: string, handler: (e: KeyboardEvent) => void, allowInInput = false) {
  const ref = useRef(handler)
  ref.current = handler
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const mod = combo.startsWith('mod+')
      const key = combo.replace('mod+', '')
      if (e.key.toLowerCase() !== key) return
      if (mod !== (e.metaKey || e.ctrlKey)) return
      if (!mod && (e.metaKey || e.ctrlKey || e.altKey)) return
      const el = e.target as HTMLElement | null
      const typing = !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))
      if (typing && !allowInInput) return
      ref.current(e)
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [combo, allowInInput])
}

/** Filter state kept in the URL (?q=...&page=2) so views are shareable and the back button works. Defaults are omitted. */
export function useUrlState<T extends Record<string, string>>(defaults: T): [T, (patch: Partial<T>, opts?: { keepPage?: boolean }) => void] {
  const [sp, setSp] = useSearchParams()
  const state = { ...defaults } as Record<string, string>
  for (const k of Object.keys(defaults)) { const v = sp.get(k); if (v !== null) state[k] = v }
  const set = useCallback((patch: Partial<T>, opts: { keepPage?: boolean } = {}) => {
    setSp((prev) => {
      const next = new URLSearchParams(prev)
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === defaults[k] || v === '') next.delete(k)
        else next.set(k, v as string)
      }
      if (!opts.keepPage && !('page' in patch)) next.delete('page')
      return next
    }, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setSp])
  return [state as T, set]
}

/**
 * Keyboard activation for a clickable table row (Enter or Space). The key press is consumed so it cannot continue on to
 * whatever receives focus next: opening a drawer moves focus to its Close button, and the same Enter would then press it.
 */
export function rowKey(e: React.KeyboardEvent, open: () => void) {
  if (e.target !== e.currentTarget) return
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() }
}
