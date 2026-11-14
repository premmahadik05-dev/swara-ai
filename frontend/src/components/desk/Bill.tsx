import { useEffect, useRef, useState, type ReactNode } from 'react'
import { fmtQty, itemName, rupees, unitLabel } from '../../lib/format'
import type { CartLine, CartView, Customer, Lang, Product } from '../../types'
import { Icon } from '../Icons'
import { Badge, Button, Empty } from '../ui'
import { CustomerPicker, ProductPicker } from './Pickers'

const stepOf = (unit: string) => (unit === 'kg' || unit === 'l' ? 0.5 : 1)

/** − qty + for one bill line. Typing a number commits on Enter or when the field loses focus. */
function Stepper({ line, busy, disabled, onSet }: { line: CartLine; busy: boolean; disabled: boolean; onSet: (qty: number) => void }) {
  const qty = Number(line.qty)
  const step = stepOf(line.unit)
  const [text, setText] = useState(fmtQty(qty))
  useEffect(() => { setText(fmtQty(qty)) }, [qty])
  const commit = () => {
    const n = Number(text)
    if (!Number.isFinite(n) || n < 0) { setText(fmtQty(qty)); return }
    if (n !== qty) onSet(n)
  }
  const name = line.name_en
  return (
    <div className="stepper" role="group" aria-label={`Quantity of ${name}`}>
      <button type="button" aria-label={`Decrease ${name}`} disabled={disabled || busy} onClick={() => onSet(Math.max(0, Math.round((qty - step) * 1000) / 1000))}><Icon name="minus" size={15} /></button>
      <input type="text" inputMode="decimal" aria-label={`${name} quantity in ${unitLabel(line.unit)}`} value={text} disabled={disabled || busy}
             onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit() } }} />
      <button type="button" aria-label={`Increase ${name}`} disabled={disabled || busy || qty + step > line.in_stock} onClick={() => onSet(Math.round((qty + step) * 1000) / 1000)}><Icon name="plus" size={15} /></button>
    </div>
  )
}

export interface BillProps {
  cart: CartView
  lang: Lang
  customer: Customer | null
  onCustomer: (c: Customer | null) => void
  onSetQty: (productId: number, qty: number) => void
  onAdd: (p: Product) => void
  busyLines: Set<number>
  /** the order is saved: show the bill read-only */
  locked: boolean
  footer: ReactNode
  note?: ReactNode
}

/** The running bill: a receipt that updates as the customer speaks and as the shopkeeper edits it. */
export function Bill({ cart, lang, customer, onCustomer, onSetQty, onAdd, busyLines, locked, footer, note }: BillProps) {
  const seen = useRef<Set<string>>(new Set())
  const [fresh, setFresh] = useState<Set<string>>(new Set())
  useEffect(() => {
    const now = new Set(cart.lines.map((l) => `${l.product_id}:${l.qty}`))
    const added = new Set([...now].filter((k) => !seen.current.has(k)))
    seen.current = now
    if (added.size && seen.current.size) {
      setFresh(added)
      const t = setTimeout(() => setFresh(new Set()), 1000)
      return () => clearTimeout(t)
    }
  }, [cart])

  return (
    <section className="card bill" aria-label="Bill">
      <div className="bill-head">
        <h2 className="h3">Bill</h2>
        <span className="muted small" aria-live="polite">{cart.lines.length} {cart.lines.length === 1 ? 'item' : 'items'}</span>
      </div>
      <div className="bill-meta">
        <CustomerPicker value={customer} onChange={onCustomer} disabled={locked} />
        {!locked && <ProductPicker onAdd={onAdd} />}
      </div>
      <div className="bill-lines">
        {cart.lines.length === 0 ? (
          <Empty title="Nothing on the bill yet" icon="cart">Say or type an order, or search for an item above. Each line appears here as it is understood.</Empty>
        ) : cart.lines.map((l) => {
          const isFresh = fresh.has(`${l.product_id}:${l.qty}`)
          return (
            <div key={l.product_id} className={`bl${isFresh ? ' new' : ''}${busyLines.has(l.product_id) ? ' busy' : ''}`}>
              <div className="nm">
                <b title={l.name_en}>{itemName(l, lang)}</b>
                <span className="faint xs">
                  {rupees(l.unit_price_paise)} / {unitLabel(l.unit)}
                  {l.assumed && <> · <Badge tone="warn" title="The customer said a general word like 'oil'. The shop's default item was used. Change it if that is wrong.">default pick</Badge></>}
                </span>
              </div>
              {locked ? <span className="small muted nowrap">{fmtQty(l.qty)} {unitLabel(l.unit)}</span>
                : <Stepper line={l} busy={busyLines.has(l.product_id)} disabled={false} onSet={(q) => onSetQty(l.product_id, q)} />}
              <div className="row nowrap tight" style={{ justifyContent: 'flex-end' }}>
                <span className="amt">{rupees(l.line_total_paise)}</span>
                {!locked && <Button variant="ghost" size="sm" iconOnly icon="x" aria-label={`Remove ${l.name_en}`} disabled={busyLines.has(l.product_id)} onClick={() => onSetQty(l.product_id, 0)} />}
              </div>
            </div>
          )
        })}
      </div>
      <div className="bill-foot">
        {note}
        <div className="bill-total"><span className="muted">Total</span><span className="big" aria-live="polite" aria-atomic="true">{rupees(cart.total_paise)}</span></div>
        <div className="row between nowrap">{footer}</div>
      </div>
    </section>
  )
}
