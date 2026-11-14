import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ExportButton } from '../components/ExportButton'
import { PrintBillButton } from '../components/PrintBill'
import { PayStatusBadge, MethodBadge } from '../components/payments/badges'
import { PaymentDialog } from '../components/payments/PaymentDialog'
import { ConfirmDialog, Drawer } from '../components/Overlay'
import { useToast } from '../components/Toast'
import { Badge, Button, Card, DemoBadge, Empty, ErrorNote, Field, Note, PageHeader, Pagination, SearchBox, Seg, SkeletonRows, useLocalInput } from '../components/ui'
import { LANG_LATIN, fmtQty, istTime, plural, rupees, unitLabel } from '../lib/format'
import { useIsOwner } from '../lib/auth'
import { LANG_META } from '../lib/languages'
import { rowKey, useAsync, useUrlState } from '../lib/hooks'
import { useDataScope } from '../lib/scope'
import type { Order } from '../types'

const PAGE = 20
const statusTone = { confirmed: 'info', fulfilled: 'ok', cancelled: 'bad' } as const
const statusText = { confirmed: 'Confirmed', fulfilled: 'Fulfilled', cancelled: 'Cancelled' } as const
const line = (i: Order['items'][number]) => `${i.name} × ${fmtQty(i.qty)} ${unitLabel(i.unit)}`
/** What was ordered, with quantities: the first two lines, then "+N more". The full list is in the hover text and in the order drawer. */
const summary = (o: Order) => o.items.slice(0, 2).map(line).join(', ') + (o.items.length > 2 ? ` +${o.items.length - 2} more` : '')

function OrderDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { toast } = useToast()
  const owner = useIsOwner()
  const res = useAsync(() => api.order(id), [id])
  const shop = useAsync(() => api.health(), [])
  const [confirm, setConfirm] = useState<'cancelled' | null>(null)
  const [busy, setBusy] = useState(false)
  const [paying, setPaying] = useState(false)
  const o = res.data
  const pay = o?.payment
  const heldMoney = pay ? Math.max(0, pay.paid_paise - pay.refunded_paise) : 0   // collected and not refunded: the server will not cancel the order while this is more than zero

  const change = async (s: 'fulfilled' | 'cancelled') => {
    if (!o) return
    setBusy(true)
    try {
      await api.setOrderStatus(o.id, s)
      toast(s === 'cancelled' ? `${o.code} cancelled. Stock returned to the shelf.` : `${o.code} marked fulfilled.`, 'ok')
      setConfirm(null); res.reload(); onChanged()
    } catch (e) { toast((e as Error).message, 'bad'); setConfirm(null) } finally { setBusy(false) }
  }

  return (
    <>
      <Drawer title={o ? o.code : 'Order'} subtitle={o ? istTime(o.created_at) + ' IST' : undefined} onClose={onClose}
        footer={o && owner && o.status === 'confirmed' ? (<>
          <Button variant="danger" onClick={() => setConfirm('cancelled')} disabled={busy || heldMoney > 0} title={heldMoney > 0 ? 'Refund the payment first' : undefined}>Cancel order</Button>
          <Button onClick={() => void change('fulfilled')} loading={busy} icon="check">Mark fulfilled</Button>
        </>) : undefined}>
        <ErrorNote error={res.error} onRetry={res.reload} />
        {!o && !res.error && <SkeletonRows rows={5} cols={3} />}
        {o && (
          <div className="stack">
            <div className="row">
              <Badge tone={statusTone[o.status]} dot>{statusText[o.status]}</Badge>
              {o.is_synthetic && <DemoBadge />}
              <Badge>{o.channel === 'voice' ? 'Spoken' : 'Typed'}</Badge>
              <Badge tone="info">{LANG_LATIN[o.language] ?? o.language}</Badge>
              <span style={{ marginLeft: 'auto' }}><PrintBillButton order={o} shopName={shop.data?.store_name ?? 'SWARA AI'} /></span>
            </div>
            <dl className="kv">
              <dt>Customer</dt><dd>{o.customer_id ? <Link to={`/customers?open=${o.customer_id}`}>{o.customer_name}</Link> : o.customer_name}</dd>
              <dt>Items</dt><dd>{plural(o.items.length, 'line')}</dd>
              {o.session_id && <><dt>Conversation</dt><dd><Link to="/live" className="mono-id">{o.session_id.slice(0, 8)}</Link></dd></>}
            </dl>
            <div className="card">
              <div className="table-wrap">
                <table className="tbl compact">
                  <thead><tr><th>Item</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">Amount</th></tr></thead>
                  <tbody>
                    {o.items.map((i) => (
                      <tr key={i.product_id}><td>{i.name}</td><td className="num">{fmtQty(i.qty)} {unitLabel(i.unit)}</td><td className="num muted">{rupees(i.unit_price_paise)}</td><td className="num"><b>{rupees(i.line_total_paise)}</b></td></tr>
                    ))}
                  </tbody>
                  <tfoot><tr><td colSpan={3} style={{ padding: '12px 14px', fontWeight: 600 }}>Total</td><td className="num" style={{ padding: '12px 14px', fontSize: 16, fontWeight: 650 }}>{rupees(o.total_paise)}</td></tr></tfoot>
                </table>
              </div>
            </div>
            <section className="pay-strip" aria-label="Payment">
              <div className="grow">
                <div className="row tight"><b>Payment</b><PayStatusBadge status={pay?.status ?? 'none'} />{pay?.method && pay.status !== 'pending' && pay.status !== 'failed' && <MethodBadge method={pay.method} />}</div>
                <div className="muted small">
                  {!pay || pay.status === 'none' ? 'No payment is recorded in SWARA AI for this order. Orders from before payments were tracked here show this.'
                    : pay.status === 'pending' ? 'A payment was started and is waiting.'
                    : pay.status === 'failed' ? 'The last attempt failed. You can try again.'
                    : pay.status === 'cancelled' ? 'The last payment was cancelled.'
                    : `${rupees(pay.paid_paise)} collected${pay.refunded_paise ? `, ${rupees(pay.refunded_paise)} refunded` : ''}.`}
                </div>
              </div>
              <div className="row tight">
                {pay?.payment_id && <Link className="btn secondary small" to={`/payments/${pay.payment_id}`}>Details</Link>}
                {pay && (pay.status === 'paid' || pay.status === 'partially_refunded' || pay.status === 'refunded') && <Link className="btn secondary small" to={`/invoices/${o.id}`}>Receipt</Link>}
                {o.status !== 'cancelled' && !(pay && (pay.status === 'paid' || pay.status === 'partially_refunded' || pay.status === 'refunded')) && (
                  <Button size="sm" icon="wallet" onClick={() => setPaying(true)}>{pay?.status === 'pending' ? 'Continue payment' : 'Take payment'}</Button>
                )}
              </div>
            </section>
            {heldMoney > 0 && o.status === 'confirmed' && <Note tone="warn">{rupees(heldMoney)} was collected for this order. {owner ? 'Refund it from the payment page before cancelling the order.' : 'Only the shop owner can refund it, and it must be refunded before the order can be cancelled.'}</Note>}
            {o.status === 'cancelled' && <p className="muted small">This order was cancelled and its stock was returned to the shelf.</p>}
            {!owner && o.status === 'confirmed' && <p className="muted small">Only the shop owner can mark an order fulfilled or cancel it.</p>}
          </div>
        )}
      </Drawer>
      {confirm && o && (
        <ConfirmDialog title={`Cancel ${o.code}?`} confirmLabel="Cancel order" busy={busy} onClose={() => setConfirm(null)} onConfirm={() => void change('cancelled')}
          body={<>Stock for {plural(o.items.length, 'item')} goes back to the shelf and the sale ({rupees(o.total_paise)}) stops counting in reports.{pay?.status === 'pending' ? ' The payment that is still waiting is cancelled too.' : ''} This cannot be undone.</>} />
      )}
      {paying && o && <PaymentDialog orderId={o.id} onClose={() => setPaying(false)} onChanged={() => { res.reload(); onChanged() }} />}
    </>
  )
}

export default function Orders() {
  const { includeDemo } = useDataScope()
  const [f, set] = useUrlState({ q: '', status: '', channel: '', language: '', sort: 'newest', page: '1', open: '' })
  const [qLocal, setQLocal] = useLocalInput(f.q, (v) => set({ q: v }))
  const page = Math.max(1, Number(f.page) || 1)
  const res = useAsync(() => api.orders({ status: f.status, channel: f.channel, language: f.language, q: f.q, sort: f.sort, include_synthetic: includeDemo, limit: PAGE, offset: (page - 1) * PAGE }),
    [f.status, f.channel, f.language, f.q, f.sort, page, includeDemo])
  const d = res.data
  const counts = d?.counts
  const openId = Number(f.open) || null
  const filtered = !!(f.q || f.channel || f.language || f.status)

  return (
    <>
      <PageHeader title="Orders" description="Every confirmed bill, from voice and typed orders. Open one to see its items or to mark it fulfilled or cancelled."
        actions={<>
          <ExportButton what="orders" fetchFile={() => api.exportOrders({ status: f.status, channel: f.channel, language: f.language, q: f.q, sort: f.sort, include_synthetic: includeDemo })} />
          <Link className="btn" to="/order">New order</Link>
        </>} />
      <Card flush>
        <div className="toolbar">
          <SearchBox label="Search orders by bill number or customer" placeholder="Bill number or customer" value={qLocal} onChange={setQLocal} />
          <Field label="Taken by" htmlFor="o-ch"><select id="o-ch" value={f.channel} onChange={(e) => set({ channel: e.target.value })}><option value="">Voice and typed</option><option value="voice">Voice</option><option value="text">Typed</option></select></Field>
          <Field label="Language" htmlFor="o-lg"><select id="o-lg" value={f.language} onChange={(e) => set({ language: e.target.value })}><option value="">All languages</option>{LANG_META.map((l) => <option key={l.key} value={l.key}>{l.name}</option>)}</select></Field>
          <Field label="Sort" htmlFor="o-so"><select id="o-so" value={f.sort} onChange={(e) => set({ sort: e.target.value })}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="total_high">Highest total</option><option value="total_low">Lowest total</option></select></Field>
        </div>
        <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--line)' }}>
          <Seg label="Order status" value={f.status} onChange={(v) => set({ status: v })} options={[
            { value: '', label: 'All', count: counts?.all }, { value: 'confirmed', label: 'Confirmed', count: counts?.confirmed },
            { value: 'fulfilled', label: 'Fulfilled', count: counts?.fulfilled }, { value: 'cancelled', label: 'Cancelled', count: counts?.cancelled }]} />
        </div>
        <ErrorNote error={res.error} onRetry={res.reload} />
        {res.loading && !d ? <SkeletonRows rows={8} cols={6} /> : d && d.items.length === 0 ? (
          <Empty title={filtered ? 'No orders match these filters' : 'No orders yet'} icon="orders"
            action={filtered ? <Button variant="secondary" onClick={() => { setQLocal(''); set({ q: '', status: '', channel: '', language: '' }) }}>Clear filters</Button> : <Link className="btn" to="/order">Take an order</Link>}>
            {filtered ? 'Try a different search or clear the filters.' : includeDemo ? 'Orders you take on the Order desk appear here.' : 'Demo data is switched off, so only orders you took are listed. Take one on the Order desk.'}
          </Empty>
        ) : d && (
          <div className="table-wrap" style={{ opacity: res.loading ? 0.6 : 1, transition: 'opacity .15s' }}>
            <table className="tbl stack-sm">
              <thead><tr><th>Order</th><th>Customer</th><th>Products and quantity</th><th>Language and channel</th><th>When (IST)</th><th className="num">Total</th><th>Status</th><th>Payment</th><th aria-label="Open" /></tr></thead>
              <tbody>
                {d.items.map((o) => (
                  <tr key={o.id} className="clickable" tabIndex={0} onClick={() => set({ open: String(o.id) }, { keepPage: true })}
                      onKeyDown={(e) => rowKey(e, () => set({ open: String(o.id) }, { keepPage: true }))} aria-label={`Open ${o.code}`}>
                    <td><b className="mono-id" style={{ color: 'var(--text)' }}>{o.code}{o.is_synthetic && <> <DemoBadge /></>}</b></td>
                    <td data-label="Customer" className="truncate" style={{ maxWidth: 160 }}>{o.customer_name}</td>
                    <td data-label="Items" className="muted truncate" style={{ maxWidth: 300 }} title={o.items.map(line).join('\n')}>{summary(o)}</td>
                    <td data-label="Language"><span className="row tight"><Badge>{o.channel === 'voice' ? 'Voice' : 'Typed'}</Badge><Badge tone="info">{LANG_LATIN[o.language] ?? o.language}</Badge></span></td>
                    <td data-label="When" className="muted nowrap">{istTime(o.created_at)}</td>
                    <td className="num"><b>{rupees(o.total_paise)}</b></td>
                    <td><Badge tone={statusTone[o.status]} dot>{statusText[o.status]}</Badge></td>
                    <td data-label="Payment">{o.payment && o.payment.status !== 'none' ? <PayStatusBadge status={o.payment.status} /> : <span className="faint small" title="No payment is recorded in SWARA AI for this order">Not recorded</span>}</td>
                    <td className="chev" aria-hidden>›</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {d && d.total > 0 && <Pagination page={page} pageSize={PAGE} total={d.total} noun="orders" onPage={(p) => set({ page: String(p) }, { keepPage: true })} />}
      </Card>
      {openId && <OrderDrawer id={openId} onClose={() => set({ open: '' }, { keepPage: true })} onChanged={res.reload} />}
    </>
  )
}
