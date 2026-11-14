import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { CustomerForm } from '../components/CustomerForm'
import { ExportButton } from '../components/ExportButton'
import { Drawer } from '../components/Overlay'
import { Avatar, Badge, Button, Card, DemoBadge, Empty, ErrorNote, Field, Note, PageHeader, Pagination, SearchBox, SkeletonRows, useLocalInput } from '../components/ui'
import { LANG_LATIN, ago, fmtQty, istTime, rupees, unitLabel, wholeRupees } from '../lib/format'
import { useIsOwner } from '../lib/auth'
import { rowKey, useAsync, useUrlState } from '../lib/hooks'
import { useDataScope } from '../lib/scope'
import type { Customer } from '../types'

const PAGE = 20
const statusTone = { confirmed: 'info', fulfilled: 'ok', cancelled: 'bad' } as const

function CustomerDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const res = useAsync(() => api.customer(id), [id])
  const orders = useAsync(() => api.orders({ customer_id: id, limit: 5 }), [id])
  const owner = useIsOwner()
  const [editing, setEditing] = useState(false)
  const c = res.data
  return (
    <>
      <Drawer title={c?.name ?? 'Customer'} subtitle={c ? <span className="row tight">{c.is_synthetic && <DemoBadge title="A placeholder customer generated for the demo. Not a real person." />}{c.language && <Badge tone="info">{LANG_LATIN[c.language] ?? c.language}</Badge>}{c.phone && <span>{c.phone}</span>}</span> : undefined}
        onClose={onClose} footer={c && owner ? <Button variant="secondary" icon="edit" onClick={() => setEditing(true)}>Edit details</Button> : undefined}>
        <ErrorNote error={res.error} onRetry={res.reload} />
        {!c && !res.error && <SkeletonRows rows={5} cols={2} />}
        {c && (
          <div className="stack">
            {c.is_synthetic && <Note tone="warn">Demo customer. The orders linked to this record were generated for the demo, so these totals are not real purchases.</Note>}
            <div className="stat-pair">
              <div><div className="l">Orders</div><div className="v">{c.orders}</div></div>
              <div><div className="l">Total spent</div><div className="v">{wholeRupees(c.spent_paise)}</div></div>
              <div><div className="l">Average bill</div><div className="v">{wholeRupees(c.avg_basket_paise)}</div></div>
              <div><div className="l">Last order</div><div className="v" style={{ fontSize: 15 }}>{ago(c.last_order_at)}</div></div>
            </div>
            {c.notes && <div className="prov"><h3>Notes</h3><p style={{ margin: 0 }}>{c.notes}</p></div>}
            <Card title="Buys most often" description="By amount spent">
              {c.top_products.length === 0 ? <p className="muted small" style={{ margin: 0 }}>No purchases yet.</p> : (
                <ul className="list-rows">{c.top_products.map((p) => <li key={p.product_id}><span className="grow truncate">{p.name}</span><span className="muted small nowrap">{fmtQty(p.qty)} {unitLabel(p.unit)}</span><b className="nowrap">{rupees(p.revenue_paise)}</b></li>)}</ul>
              )}
            </Card>
            {c.language_mix.length > 0 && (
              <div className="row tight"><span className="muted small">Orders by language:</span>{c.language_mix.map((l) => <Badge key={l.language} tone="info">{LANG_LATIN[l.language] ?? l.language} · {l.orders}</Badge>)}</div>
            )}
            <Card title="Recent orders" actions={<Link className="btn secondary small" to={`/orders?q=${encodeURIComponent(c.name)}`}>All orders</Link>} flush>
              {!orders.data ? <SkeletonRows rows={3} cols={3} /> : orders.data.items.length === 0 ? <p className="muted small" style={{ padding: '4px 20px 16px', margin: 0 }}>No orders linked to this customer yet.</p> : (
                <table className="tbl compact"><tbody>
                  {orders.data.items.map((o) => <tr key={o.id}><td><Link to={`/orders?open=${o.id}`} className="mono-id">{o.code}</Link></td><td className="muted nowrap">{istTime(o.created_at)}</td><td className="num"><b>{rupees(o.total_paise)}</b></td><td><Badge tone={statusTone[o.status]}>{o.status}</Badge></td></tr>)}
                </tbody></table>
              )}
            </Card>
          </div>
        )}
      </Drawer>
      {editing && c && <CustomerForm initial={c} onClose={() => setEditing(false)} onDone={() => { setEditing(false); res.reload(); onChanged() }} />}
    </>
  )
}

export default function Customers() {
  const { includeDemo } = useDataScope()
  const [f, set] = useUrlState({ q: '', sort: 'recent', page: '1', open: '' })
  const [qLocal, setQLocal] = useLocalInput(f.q, (v) => set({ q: v }))
  const owner = useIsOwner()
  const [creating, setCreating] = useState(false)
  const page = Math.max(1, Number(f.page) || 1)
  const res = useAsync(() => api.customers({ q: f.q, sort: f.sort, include_synthetic: includeDemo, page, page_size: PAGE }), [f.q, f.sort, page, includeDemo])
  const d = res.data
  const openId = Number(f.open) || null

  return (
    <>
      <PageHeader title="Customers" description="People who buy from the shop. Pick a customer on the Order desk and their bills are linked here automatically."
        actions={owner ? <>
          <ExportButton what="customers" fetchFile={() => api.exportCustomers({ q: f.q, sort: f.sort, include_synthetic: includeDemo })} />
          <Button icon="plus" onClick={() => setCreating(true)}>New customer</Button>
        </> : undefined} />
      <div className="stack">
        {!owner && <Note tone="info"><b>You are signed in as staff.</b> You can look at customers and pick one when you take an order. Only the shop owner can add or edit them.</Note>}
        {includeDemo && <Note tone="warn">Customers named <b>Demo Customer A–H</b> are placeholders created for the demo, and their orders are generated. No real person's data is stored in this project.</Note>}
        <Card flush>
          <div className="toolbar">
            <SearchBox label="Search customers" placeholder="Name or phone" value={qLocal} onChange={setQLocal} />
            <Field label="Sort by" htmlFor="cu-so"><select id="cu-so" value={f.sort} onChange={(e) => set({ sort: e.target.value })}><option value="recent">Most recent order</option><option value="spent">Most spent</option><option value="orders">Most orders</option><option value="name">Name</option></select></Field>
          </div>
          <ErrorNote error={res.error} onRetry={res.reload} />
          {res.loading && !d ? <SkeletonRows rows={7} cols={6} /> : d && d.items.length === 0 ? (
            <Empty title={f.q ? 'No customers match' : 'No customers yet'} icon="users"
              action={f.q ? <Button variant="secondary" onClick={() => setQLocal('')}>Clear search</Button> : owner ? <Button onClick={() => setCreating(true)}>Add a customer</Button> : undefined}>
              {f.q ? 'Check the spelling, or search by phone number.' : includeDemo ? 'Add your first customer, or reseed the demo data.' : 'Demo customers are hidden. Add your first customer to start linking orders.'}
            </Empty>
          ) : d && (
            <div className="table-wrap" style={{ opacity: res.loading ? 0.6 : 1, transition: 'opacity .15s' }}>
              <table className="tbl stack-sm">
                <thead><tr><th>Customer</th><th>Language</th><th className="num">Orders</th><th className="num">Spent</th><th className="num">Average bill</th><th>Last order</th><th aria-label="Open" /></tr></thead>
                <tbody>
                  {d.items.map((c: Customer) => (
                    <tr key={c.id} className="clickable" tabIndex={0} onClick={() => set({ open: String(c.id) }, { keepPage: true })} onKeyDown={(e) => rowKey(e, () => set({ open: String(c.id) }, { keepPage: true }))} aria-label={`Open ${c.name}`}>
                      <td><div className="cell-user"><Avatar name={c.name} /><div className="cell-main"><b>{c.name}{c.is_synthetic && <> <DemoBadge title="Placeholder customer generated for the demo." /></>}</b><span className="faint xs">{c.phone || 'No phone'}</span></div></div></td>
                      <td data-label="Language">{c.language ? <Badge tone="info">{LANG_LATIN[c.language] ?? c.language}</Badge> : <span className="faint">Not set</span>}</td>
                      <td className="num" data-label="Orders">{c.orders}</td>
                      <td className="num" data-label="Spent"><b>{wholeRupees(c.spent_paise)}</b></td>
                      <td className="num muted" data-label="Average bill">{c.orders ? wholeRupees(c.avg_basket_paise) : '-'}</td>
                      <td className="muted nowrap" data-label="Last order">{ago(c.last_order_at)}</td>
                      <td className="chev" aria-hidden>›</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {d && d.total > 0 && <Pagination page={page} pageSize={PAGE} total={d.total} noun="customers" onPage={(p) => set({ page: String(p) }, { keepPage: true })} />}
        </Card>
      </div>
      {openId && <CustomerDrawer id={openId} onClose={() => set({ open: '' }, { keepPage: true })} onChanged={res.reload} />}
      {creating && <CustomerForm onClose={() => setCreating(false)} onDone={(c) => { setCreating(false); res.reload(); set({ open: String(c.id) }, { keepPage: true }) }} />}
    </>
  )
}
