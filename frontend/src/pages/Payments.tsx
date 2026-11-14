import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { AttentionBadge, MethodBadge, PayStatusBadge } from '../components/payments/badges'
import { Badge, Button, Card, DemoBadge, Empty, ErrorNote, Field, PageHeader, Pagination, SearchBox, Seg, SkeletonRows, useLocalInput } from '../components/ui'
import { istTime, rupees } from '../lib/format'
import { rowKey, useAsync, useUrlState } from '../lib/hooks'
import { useDataScope } from '../lib/scope'
import { useIsOwner } from '../lib/auth'
import type { PaymentStatus } from '../types'

const PAGE = 20
const TABS: { value: '' | PaymentStatus; label: string }[] = [
  { value: '', label: 'All' }, { value: 'paid', label: 'Paid' }, { value: 'pending', label: 'Waiting' }, { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' }, { value: 'partially_refunded', label: 'Partly refunded' }, { value: 'refunded', label: 'Refunded' },
]

/** Every payment the shop has recorded, newest first. Orders that were paid before payments were tracked here have no row, and that is expected. */
export default function Payments() {
  const { includeDemo } = useDataScope()
  const owner = useIsOwner()
  const nav = useNavigate()
  const [f, set] = useUrlState({ q: '', status: '', method: '', since: '', until: '', attention: '', sort: 'newest', page: '1' })
  const [qLocal, setQLocal] = useLocalInput(f.q, (v) => set({ q: v }))
  const page = Math.max(1, Number(f.page) || 1)
  const res = useAsync(() => api.payments({
    status: f.status || undefined, method: f.method || undefined, q: f.q, since: f.since || undefined, until: f.until || undefined,
    include_synthetic: includeDemo, attention: f.attention === '1' ? true : undefined, sort: f.sort, limit: PAGE, offset: (page - 1) * PAGE,
  }), [f.status, f.method, f.q, f.since, f.until, f.attention, f.sort, page, includeDemo], 30000)
  const d = res.data
  const filtered = !!(f.q || f.status || f.method || f.since || f.until || f.attention)
  const dateBad = !!(f.since && f.until && f.since > f.until)
  const open = (id: number) => nav(`/payments/${id}`)

  return (
    <>
      <PageHeader title="Payments" description="Cash, UPI and Razorpay payments for your orders. A payment shows as paid only after a person recorded it or Razorpay confirmed it."
        actions={owner ? <Link className="btn secondary" to="/payment-analytics">Payment analytics</Link> : undefined} />
      <Card flush>
        <div className="toolbar">
          <SearchBox label="Search payments by payment number, bill number, customer or reference" placeholder="Payment, bill, customer or reference" value={qLocal} onChange={setQLocal} />
          <Field label="Way paid" htmlFor="p-m"><select id="p-m" value={f.method} onChange={(e) => set({ method: e.target.value })}><option value="">All ways</option><option value="cash">Cash</option><option value="upi">UPI</option><option value="razorpay">Razorpay</option></select></Field>
          <Field label="From" htmlFor="p-s"><input id="p-s" type="date" value={f.since} max={f.until || undefined} onChange={(e) => set({ since: e.target.value })} /></Field>
          <Field label="To" htmlFor="p-u" error={dateBad ? 'To is before From.' : null}><input id="p-u" type="date" value={f.until} min={f.since || undefined} onChange={(e) => set({ until: e.target.value })} /></Field>
          <Field label="Sort" htmlFor="p-o"><select id="p-o" value={f.sort} onChange={(e) => set({ sort: e.target.value })}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="amount_high">Highest amount</option><option value="amount_low">Lowest amount</option></select></Field>
          <label className="check"><input type="checkbox" checked={f.attention === '1'} onChange={(e) => set({ attention: e.target.checked ? '1' : '' })} />Needs a look</label>
        </div>
        <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--line)' }}>
          <Seg label="Payment status" value={f.status} onChange={(v) => set({ status: v })}
            options={TABS.map((t) => ({ value: t.value, label: t.label, count: d?.counts[t.value === '' ? 'all' : t.value] }))} />
        </div>
        <ErrorNote error={res.error} onRetry={res.reload} />
        {res.loading && !d ? <SkeletonRows rows={8} cols={6} /> : d && d.items.length === 0 ? (
          <Empty title={filtered ? 'No payments match these filters' : 'No payments recorded yet'} icon="wallet"
            action={filtered ? <Button variant="secondary" onClick={() => { setQLocal(''); set({ q: '', status: '', method: '', since: '', until: '', attention: '' }) }}>Clear filters</Button> : <Link className="btn" to="/orders">Open Orders</Link>}>
            {filtered ? 'Try a different search or clear the filters.' : 'Open an order and choose Take payment. Orders that were paid before payments were tracked here simply have no payment recorded.'}
          </Empty>
        ) : d && (
          <div className="table-wrap" style={{ opacity: res.loading ? 0.6 : 1, transition: 'opacity .15s' }}>
            <table className="tbl stack-sm">
              <thead><tr><th>Payment</th><th>Customer</th><th>Way paid</th><th>When (IST)</th><th className="num">Amount</th><th>Status</th><th aria-label="Open" /></tr></thead>
              <tbody>
                {d.items.map((p) => (
                  <tr key={p.id} className="clickable" tabIndex={0} onClick={() => open(p.id)} onKeyDown={(e) => rowKey(e, () => open(p.id))} aria-label={`Open payment ${p.code}`}>
                    <td><div className="cell-main"><b className="mono-id" style={{ color: 'var(--text)' }}>{p.code}{p.is_synthetic && <> <DemoBadge /></>}</b><span className="sub mono-id">{p.order_code}</span></div></td>
                    <td data-label="Customer" className="truncate" style={{ maxWidth: 180 }}>{p.customer_name}</td>
                    <td data-label="Way paid"><MethodBadge method={p.method} />{p.method === 'upi' && p.status !== 'pending' && !p.verified && <> <Badge tone="warn" title={p.verification_label}>Unverified</Badge></>}</td>
                    <td data-label="When" className="muted nowrap">{istTime(p.paid_at ?? p.created_at ?? '')}</td>
                    <td className="num"><b>{rupees(p.amount_paise)}</b>{p.refunded_paise > 0 && <div className="xs faint">{rupees(p.refunded_paise)} refunded</div>}</td>
                    <td><span className="row tight"><PayStatusBadge status={p.status} />{p.stale && <Badge tone="warn" title="Waiting longer than expected">Slow</Badge>}<AttentionBadge code={p.attention} /></span></td>
                    <td className="chev" aria-hidden>›</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {d && d.total > 0 && <Pagination page={page} pageSize={PAGE} total={d.total} noun="payments" onPage={(p) => set({ page: String(p) }, { keepPage: true })} />}
      </Card>
    </>
  )
}
