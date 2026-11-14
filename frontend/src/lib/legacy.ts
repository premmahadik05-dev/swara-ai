/**
 * Settings saved under the previous product name are carried over once, so nobody loses the Demo data
 * switch and the sidebar choice. The old keys are removed after the move.
 * (This is the only place the old name still appears in the front end, on purpose.)
 */
const OLD = 'dukaanmitra.'
const NEW = 'swara.'
const NAMES: { store: () => Storage; name: string }[] = [
  { store: () => localStorage, name: 'includeDemo' },
  { store: () => localStorage, name: 'sidebar' },
]

export function migrateLegacyStorage(): void {
  // The shared admin token was replaced by real accounts; make sure none is left lying in this browser.
  for (const k of ['swara.adminToken', OLD + 'adminToken']) { try { sessionStorage.removeItem(k) } catch { /* ignore */ } }
  // There is no dark theme any more. A theme choice saved by an earlier build is deleted so nothing reads it.
  for (const k of ['swara.theme', OLD + 'theme']) { try { localStorage.removeItem(k) } catch { /* ignore */ } }
  for (const { store, name } of NAMES) {
    try {
      const s = store()
      const old = s.getItem(OLD + name)
      if (old === null) continue
      if (s.getItem(NEW + name) === null) s.setItem(NEW + name, old)
      s.removeItem(OLD + name)
    } catch { /* storage unavailable (private mode): nothing to move */ }
  }
}
