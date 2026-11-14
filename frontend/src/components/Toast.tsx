import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Icon } from './Icons'
import { Button } from './ui'

type Kind = 'info' | 'ok' | 'bad'
interface T { id: number; text: string; kind: Kind }
const Ctx = createContext<{ toast: (text: string, kind?: Kind) => void }>({ toast: () => undefined })
export const useToast = () => useContext(Ctx)

/** Short confirmations (4 s) and errors (8 s). Announced politely to screen readers; the close button is keyboard reachable. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<T[]>([])
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())
  const dismiss = useCallback((id: number) => {
    setItems((s) => s.filter((x) => x.id !== id))
    const t = timers.current.get(id)
    if (t) { clearTimeout(t); timers.current.delete(id) }
  }, [])
  const toast = useCallback((text: string, kind: Kind = 'info') => {
    const id = Date.now() + Math.random()
    setItems((s) => [...s.slice(-3), { id, text, kind }])
    timers.current.set(id, setTimeout(() => dismiss(id), kind === 'bad' ? 8000 : 4000))
  }, [dismiss])
  useEffect(() => { const m = timers.current; return () => m.forEach(clearTimeout) }, [])
  const value = useMemo(() => ({ toast }), [toast])
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite" aria-relevant="additions">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <Icon name={t.kind === 'ok' ? 'check' : t.kind === 'bad' ? 'alert' : 'info'} size={17} />
            <span className="msg">{t.text}</span>
            <Button variant="ghost" size="sm" iconOnly icon="x" aria-label="Dismiss notification" onClick={() => dismiss(t.id)} />
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}
