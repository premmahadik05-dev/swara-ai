import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useIsOwner } from '../lib/auth'
import { useDebounced } from '../lib/hooks'
import type { SearchResults } from '../types'
import { Icon, type IconName } from './Icons'

interface Item { key: string; group: string; icon: IconName; title: string; subtitle?: string; to: string; ownerOnly?: boolean }

const PAGES: Item[] = [
  { key: 'p-dash', group: 'Go to', icon: 'dashboard', title: 'Dashboard', to: '/dashboard' },
  { key: 'p-order', group: 'Go to', icon: 'mic', title: 'Order desk', subtitle: 'Take an order by voice or typing', to: '/order' },
  { key: 'p-orders', group: 'Go to', icon: 'orders', title: 'Orders', to: '/orders' },
  { key: 'p-pay', group: 'Go to', icon: 'wallet', title: 'Payments', subtitle: 'Cash, UPI and Razorpay payments', to: '/payments' },
  { key: 'p-payana', group: 'Go to', icon: 'cash', title: 'Payment analytics', subtitle: 'Owner only: money collected by way paid', to: '/payment-analytics', ownerOnly: true },
  { key: 'p-cust', group: 'Go to', icon: 'users', title: 'Customers', to: '/customers' },
  { key: 'p-inv', group: 'Go to', icon: 'box', title: 'Inventory', to: '/inventory' },
  { key: 'p-cat', group: 'Go to', icon: 'catalogue', title: 'Catalogue', subtitle: 'Open Food Facts reference products', to: '/catalogue' },
  { key: 'p-ana', group: 'Go to', icon: 'chart', title: 'Analytics', to: '/analytics' },
  { key: 'p-perf', group: 'Go to', icon: 'trend', title: 'AI performance', to: '/performance' },
  { key: 'p-diag', group: 'Go to', icon: 'clock', title: 'Voice diagnostics', subtitle: 'Owner only: response time by step', to: '/diagnostics', ownerOnly: true },
  { key: 'p-live', group: 'Go to', icon: 'chat', title: 'Conversations', to: '/live' },
  { key: 'p-noise', group: 'Go to', icon: 'wave', title: 'Noise lab', to: '/noise' },
  { key: 'p-set', group: 'Go to', icon: 'gear', title: 'Settings', to: '/settings' },
]

function toItems(r: SearchResults): Item[] {
  const q = encodeURIComponent(r.query)
  const out: Item[] = []
  r.products.forEach((h) => out.push({ key: `pr${h.id}`, group: 'Products in your shop', icon: 'box', title: h.title, subtitle: h.subtitle, to: `/inventory?q=${encodeURIComponent(h.title)}` }))
  r.customers.forEach((h) => out.push({ key: `cu${h.id}`, group: 'Customers', icon: 'user', title: h.title, subtitle: h.subtitle, to: `/customers?open=${h.id}` }))
  r.orders.forEach((h) => out.push({ key: `or${h.id}`, group: 'Orders', icon: 'orders', title: h.title, subtitle: h.subtitle, to: `/orders?open=${h.id}` }))
  r.catalog.forEach((h) => out.push({ key: `ca${h.id}`, group: 'Catalogue (reference)', icon: 'catalogue', title: h.title, subtitle: h.subtitle, to: `/catalogue?open=${h.id}` }))
  if ((r.catalog_total ?? 0) > r.catalog.length) out.push({ key: 'ca-all', group: 'Catalogue (reference)', icon: 'arrowRight', title: `See all ${r.catalog_total!.toLocaleString('en-IN')} catalogue matches`, to: `/catalogue?q=${q}` })
  return out
}

/** Ctrl/⌘+K search across products, customers, orders and the catalogue, plus quick navigation. */
export function CommandPalette({ onClose }: { onClose: () => void }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const dq = useDebounced(q.trim(), 200)
  const [res, setRes] = useState<SearchResults | null>(null)
  const [err, setErr] = useState(false)
  const [busy, setBusy] = useState(false)
  const [active, setActive] = useState(0)
  const listId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const prev = useRef<HTMLElement | null>(null)

  useEffect(() => {
    prev.current = document.activeElement as HTMLElement | null
    inputRef.current?.focus()
    const o = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = o; prev.current?.focus?.() }
  }, [])

  useEffect(() => {
    if (dq.length < 2) { setRes(null); setErr(false); setBusy(false); return }
    let live = true
    setBusy(true)
    api.search(dq, 5).then((r) => { if (live) { setRes(r); setErr(false) } }).catch(() => { if (live) setErr(true) }).finally(() => { if (live) setBusy(false) })
    return () => { live = false }
  }, [dq])

  const owner = useIsOwner()
  const items = useMemo<Item[]>(() => {
    const pageList = PAGES.filter((p) => !p.ownerOnly || owner)
    if (q.trim().length < 2) return pageList
    const server = res ? toItems(res) : []
    const pages = pageList.filter((p) => p.title.toLowerCase().includes(q.trim().toLowerCase()))
    return [...pages, ...server]
  }, [q, res, owner])
  useEffect(() => { setActive(0) }, [items.length, dq])

  const go = (it: Item) => { onClose(); nav(it.to) }
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(0, a - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (items[active]) go(items[active]) }
    else if (e.key === 'Escape') { e.preventDefault(); onClose() }
    else if (e.key === 'Tab') { e.preventDefault() }
  }
  useEffect(() => { document.getElementById(`${listId}-${active}`)?.scrollIntoView?.({ block: 'nearest' }) }, [active, listId])

  let lastGroup = ''
  return createPortal(
    <>
      <div className="scrim" onMouseDown={onClose} aria-hidden />
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search" onKeyDown={onKey}>
        <div className="palette-in">
          <Icon name="search" size={18} />
          <input ref={inputRef} type="text" role="combobox" aria-expanded="true" aria-controls={listId} aria-activedescendant={items[active] ? `${listId}-${active}` : undefined}
                 aria-label="Search products, customers, orders" placeholder="Search products, customers, orders, catalogue…" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" spellCheck={false} />
          {busy ? <span className="spinner" aria-hidden /> : <kbd>Esc</kbd>}
        </div>
        <div className="palette-list" id={listId} role="listbox" aria-label="Results">
          {err && <div className="palette-empty">Search is not available right now. Is the backend running?</div>}
          {!err && q.trim().length >= 2 && !busy && items.length === 0 && <div className="palette-empty">Nothing matches “{q.trim()}”. Try a product name, a customer name or an order number.</div>}
          {items.map((it, i) => {
            const head = it.group !== lastGroup
            lastGroup = it.group
            return (
              <div key={it.key} role="presentation">
                {head && <div className="palette-group" role="presentation">{it.group}</div>}
                <div id={`${listId}-${i}`} role="option" aria-selected={i === active} className={`palette-item${i === active ? ' on' : ''}`} onMouseMove={() => setActive(i)} onClick={() => go(it)}>
                  <Icon name={it.icon} size={17} />
                  <span className="grow truncate"><b>{it.title}</b>{it.subtitle && <span className="faint"> · {it.subtitle}</span>}</span>
                  {i === active && <kbd>↵</kbd>}
                </div>
              </div>
            )
          })}
        </div>
        <div className="palette-foot"><span><kbd>↑</kbd> <kbd>↓</kbd> to move</span><span><kbd>↵</kbd> to open</span><span><kbd>Esc</kbd> to close</span></div>
      </div>
    </>,
    document.body,
  )
}
