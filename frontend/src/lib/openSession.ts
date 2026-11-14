/**
 * The order desk remembers which bill is open in this browser tab, so a reload, a slip to another page or a dropped connection does not lose the
 * customer's order: the bill itself lives on the server, and this only remembers its id. sessionStorage is per tab and ends when the tab closes,
 * so two counters (two tabs) never pick up each other's bill.
 */
const KEY = 'swara.openSession'
const MAX_AGE_MS = 6 * 60 * 60 * 1000

export function saveOpenSession(id: string): void {
  try { sessionStorage.setItem(KEY, JSON.stringify({ id, at: Date.now() })) } catch { /* private mode: nothing is remembered */ }
}

export function loadOpenSession(): string | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const v = JSON.parse(raw) as { id?: unknown; at?: unknown }
    if (typeof v.id !== 'string' || !/^[A-Za-z0-9_-]{1,40}$/.test(v.id) || typeof v.at !== 'number' || Date.now() - v.at > MAX_AGE_MS) { sessionStorage.removeItem(KEY); return null }
    return v.id
  } catch { return null }
}

export function clearOpenSession(): void {
  try { sessionStorage.removeItem(KEY) } catch { /* nothing to clear */ }
}
