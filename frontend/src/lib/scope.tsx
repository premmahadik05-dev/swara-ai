import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

const KEY = 'swara.includeDemo'
/** The person's own choice, or null when they have never touched the switch. */
const read = (): boolean | null => { try { const v = localStorage.getItem(KEY); return v === '1' ? true : v === '0' ? false : null } catch { return null } }

interface Scope {
  includeDemo: boolean
  setIncludeDemo: (v: boolean) => void
  /** True once the app knows which set of records to show (the person chose, or the shop's data decided). */
  resolved: boolean
  /** Used by the app shell: the shop's own default, applied only while the person has made no choice. */
  setAutoDefault: (v: boolean) => void
}

/**
 * Whether screens include the generated demo orders and customers. One switch for the whole app (top bar), so every
 * number on every screen is computed over the same set of records and is labelled the same way.
 *
 * Default: real records only. Demo records are shown by default only for a shop that has recorded no orders of its own,
 * so a brand-new install still has something to look at, and a shop in use never sees generated figures unless it turns them on.
 * The person's explicit choice always wins over that default.
 */
const Ctx = createContext<Scope>({ includeDemo: true, setIncludeDemo: () => undefined, resolved: true, setAutoDefault: () => undefined })
export const useDataScope = () => useContext(Ctx)

export function DataScopeProvider({ children }: { children: ReactNode }) {
  const [explicit, setExplicit] = useState<boolean | null>(read)
  const [auto, setAuto] = useState<boolean | null>(null)
  const setIncludeDemo = useCallback((v: boolean) => {
    setExplicit(v)
    try { localStorage.setItem(KEY, v ? '1' : '0') } catch { /* private mode */ }
  }, [])
  const value = useMemo<Scope>(() => ({
    includeDemo: explicit ?? auto ?? false, setIncludeDemo, resolved: explicit !== null || auto !== null, setAutoDefault: setAuto,
  }), [explicit, auto, setIncludeDemo])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
