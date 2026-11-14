import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useDebounced } from '../lib/hooks'
import { Icon } from './Icons'

/** Search-as-you-type picker (ARIA combobox). Arrow keys move, Enter picks, Escape closes; one request per pause in typing. */
export function Combobox<T>({ label, placeholder, search, itemKey, renderOption, isDisabled, onSelect, extra, emptyText = 'No matches', hint, autoFocus, initialLoad = false, clearOnSelect = true, disabled }: {
  label: string
  placeholder?: string
  search: (q: string) => Promise<T[]>
  itemKey: (t: T) => string | number
  renderOption: (t: T) => ReactNode
  isDisabled?: (t: T) => boolean
  onSelect: (t: T) => void
  /** extra rows shown above the results (e.g. "Walk-in customer") */
  extra?: { key: string; node: ReactNode; onPick: () => void }[]
  emptyText?: string
  hint?: string
  autoFocus?: boolean
  initialLoad?: boolean
  clearOnSelect?: boolean
  disabled?: boolean
}) {
  const [q, setQ] = useState('')
  const dq = useDebounced(q.trim(), 200)
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<T[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(false)
  const [active, setActive] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const id = useId()
  const searchRef = useRef(search)
  searchRef.current = search

  useEffect(() => {
    if (!open) return
    if (!dq && !initialLoad) { setItems([]); return }
    let live = true
    setBusy(true)
    searchRef.current(dq).then((r) => { if (live) { setItems(r); setErr(false) } }).catch(() => { if (live) setErr(true) }).finally(() => { if (live) setBusy(false) })
    return () => { live = false }
  }, [dq, open, initialLoad])

  useEffect(() => {
    if (!open) return
    const on = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', on)
    return () => document.removeEventListener('mousedown', on)
  }, [open])

  const rows = [...(extra ?? []).map((e) => ({ kind: 'extra' as const, key: e.key, node: e.node, pick: e.onPick, disabled: false })),
    ...items.map((t) => ({ kind: 'item' as const, key: String(itemKey(t)), node: renderOption(t), pick: () => onSelect(t), disabled: !!isDisabled?.(t) }))]
  // With something typed, Enter should pick the first match, not a pinned row such as "Walk-in customer" that sits above the matches.
  useEffect(() => { setActive(dq.trim() && items.length ? (extra?.length ?? 0) : 0) }, [items, dq])  // eslint-disable-line react-hooks/exhaustive-deps

  const choose = (i: number) => {
    const r = rows[i]
    if (!r || r.disabled) return
    r.pick()
    if (clearOnSelect) setQ('')
    setOpen(false)
  }
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((a) => Math.min(rows.length - 1, a + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(0, a - 1)) }
    else if (e.key === 'Enter' && open && rows.length) { e.preventDefault(); choose(active) }
    else if (e.key === 'Escape' && open) { e.stopPropagation(); setOpen(false) }
  }

  return (
    <div className="picker" ref={box}>
      <div className="search">
        <Icon name="search" size={16} />
        <input type="text" role="combobox" aria-label={label} aria-expanded={open} aria-controls={`${id}-list`} aria-autocomplete="list" autoComplete="off" spellCheck={false}
               aria-activedescendant={open && rows[active] ? `${id}-${active}` : undefined} placeholder={placeholder} value={q} autoFocus={autoFocus} disabled={disabled}
               onFocus={() => setOpen(true)} onClick={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true) }} onKeyDown={onKey} />
        {busy && <span className="spinner clear" style={{ right: 10, width: 14, height: 14 }} aria-hidden />}
      </div>
      {open && (rows.length > 0 || dq || hint || err) && (
        <div className="picker-list" id={`${id}-list`} role="listbox" aria-label={label}>
          {rows.map((r, i) => (
            <div key={r.key} id={`${id}-${i}`} role="option" aria-selected={i === active} aria-disabled={r.disabled || undefined}
                 className={`picker-opt${i === active ? ' on' : ''}`} onMouseMove={() => setActive(i)} onMouseDown={(e) => e.preventDefault()} onClick={() => choose(i)}>
              {r.node}
            </div>
          ))}
          {!busy && !err && dq && items.length === 0 && <div className="picker-opt" aria-live="polite" style={{ cursor: 'default', color: 'var(--text-2)' }}>{emptyText}</div>}
          {!dq && hint && rows.length === 0 && <div className="picker-opt" style={{ cursor: 'default', color: 'var(--text-3)' }}>{hint}</div>}
          {err && <div className="picker-opt" role="alert" style={{ cursor: 'default', color: 'var(--bad)' }}>Could not load results. Is the backend running?</div>}
        </div>
      )}
    </div>
  )
}
