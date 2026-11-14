import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { Icon } from '../components/Icons'
import { AttentionBadge, MethodBadge, PayStatusBadge } from '../components/payments/badges'
import { PaymentDialog } from '../components/payments/PaymentDialog'
import { ConfirmDialog } from '../components/Overlay'
import { useToast } from '../components/Toast'
import { Badge, Button, Card, DemoBadge, Empty, ErrorNote, Field, Note, PageHeader, SkeletonCard } from '../components/ui'
import { useIsOwner } from '../lib/auth'
import { istTime, rupees } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { METHOD_LONG, REFUND_STATUS_TEXT, attentionText, newKey, rupeesToPaise } from '../lib/payments'
import type { PaymentDetail as Detail, PaymentRefund } from '../types'

const SOURCE_TEXT = { webhook: 'Razorpay', checkout: 'Checkout', user: 'Shop team', system: 'System' } as const

function RefundRow({ r, owner, onChanged }: { r: PaymentRefund; owner: boolean; onChanged: () => void }) {
  const { toast } = useToast()
  const [busy, setBusy] = useState(false)
  const check = async () => {
    setBusy(true)
    try { const x = await api.refreshRefund(r.id); toast(x.notice ?? (x.status === 'pending' ? 'Razorpay has not confirmed this refund yet.' : 'Refund updated.'), x.status === 'failed' ? 'bad' : 'info'); onChanged() }
    catch (e) { toast((e as Error).message, 'bad') } finally { setBusy(false) }
  }
  return (
    <li className="refund-row">
      <div className="grow">
        <div className="row tight"><b>{rupees(r.amount_paise)}</b>
          <Badge tone={r.status === 'processed' ? 'ok' : r.status === 'failed' ? 'bad' : 'warn'} dot>{REFUND_STATUS_TEXT[r.status]}</Badge>
          <span className="mono-id">{r.code}</span></div>
        <div className="muted small">{r.reason}</div>
        <div className="faint xs">{r.label}{r.initiated_by ? ` · by ${r.initiated_by}` : ''}{r.created_at ? ` · ${istTime(r.created_at)} IST` : ''}{r.provider_refund_id ? ` · ${r.provider_refund_id}` : ''}</div>
        {r.failure_reason && <div className="small bad-text">{r.failure_reason}</div>}
      </div>
      {owner && r.status === 'pending' && r.kind === 'provider' && <Button size="sm" variant="secondary" icon="refresh" onClick={() => void check()} loading={busy}>Check status</Button>}
    </li>
  )
}

function RefundForm({ p, onDone }: { p: Detail; onDone: () => void }) {
  const { toast } = useToast()
  const [amount, setAmount] = useState(String(p.refundable_paise / 100))
  const [reason, setReason] = useState('')
  const [ask, setAsk] = useState(false)
  const [busy, setBusy] = useState(false)
  const key = useState(newKey)[0]
  const paise = rupeesToPaise(amount)
  const problem = paise === null ? 'Enter an amount in rupees, for example 120 or 49.50.' : paise < 1 ? 'The amount must be more than zero.' : paise > p.refundable_paise ? `The most that can be refunded is ${rupees(p.refundable_paise)}.` : null
  const send = async () => {
    if (paise === null) return
    setBusy(true)
    try {
      const r = await api.refund(p.id, { amountPaise: paise, reason: reason.trim(), idempotencyKey: key })
      toast(r.status === 'processed' ? `Refund of ${rupees(paise)} recorded.` : `Refund of ${rupees(paise)} requested. It is not complete until Razorpay confirms it.`, r.status === 'failed' ? 'bad' : 'ok')
      setAsk(false); onDone()
    } catch (e) { toast((e as Error).message, 'bad'); setAsk(false) } finally { setBusy(false) }
  }
  const provider = p.provider === 'razorpay'
  return (
    <form className="stack tight" onSubmit={(e) => { e.preventDefault(); if (!problem && reason.trim()) setAsk(true) }}>
      <Field label="Refund amount (rupees)" htmlFor="rf-a" error={amount && problem ? problem : null} hint={`Up to ${rupees(p.refundable_paise)} can still be refunded.`}>
        <input id="rf-a" inputMode="decimal" autoComplete="off" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </Field>
      <Field label="Reason" htmlFor="rf-r" hint="Kept with the refund for your records."><input id="rf-r" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} autoComplete="off" placeholder="e.g. Item returned" /></Field>
      <div className="row"><Button type="submit" variant="danger" icon="undo" disabled={!!problem || !reason.trim() || busy}>Refund</Button></div>
      {ask && (
        <ConfirmDialog title={`Refund ${paise !== null ? rupees(paise) : ''}?`} tone="primary" confirmLabel="Refund" busy={busy} onConfirm={() => void send()} onClose={() => setAsk(false)}
          body={provider
            ? 'This asks Razorpay to send the money back to the customer. It shows as waiting until Razorpay confirms it, and it cannot be undone once Razorpay accepts it.'
            : 'You return this money to the customer yourself, by hand. This only records that you did. It cannot be undone.'} />
      )}
    </form>
  )
}

export default function PaymentDetail() {
  const { id } = useParams()
  const pid = Number(id)
  const owner = useIsOwner()
  const { toast } = useToast()
  const res = useAsync(() => api.payment(pid), [pid])
  const [busy, setBusy] = useState(false)
  const [resume, setResume] = useState(false)
  const p = res.data

  if (!Number.isFinite(pid)) return <Empty title="That payment address is not valid" icon="wallet" action={<Link className="btn" to="/payments">All payments</Link>} />
  if (res.error && !p) return (
    <>
      <PageHeader title="Payment" />
      <ErrorNote error={res.error} onRetry={res.reload} />
      <div className="row" style={{ marginTop: 12 }}><Link className="btn secondary" to="/payments">All payments</Link></div>
    </>
  )
  if (!p) return <SkeletonCard lines={6} height={260} />

  const check = async () => {
    setBusy(true)
    try { const d = await api.refreshPayment(p.id); toast(d.notice ?? (d.status === p.status ? 'No change. Razorpay has nothing new.' : 'Updated from Razorpay.'), 'info'); res.reload() }
    catch (e) { toast((e as Error).message, 'bad') } finally { setBusy(false) }
  }
  const att = attentionText(p.attention)
  const canRefund = owner && p.refundable_paise > 0 && (p.status === 'paid' || p.status === 'partially_refunded')

  return (
    <>
      <PageHeader title={p.code} description={<>For order <Link to={`/orders?open=${p.order_id}`}>{p.order_code}</Link> · {p.customer_name}</>}
        meta={<><PayStatusBadge status={p.status} /><MethodBadge method={p.method} />{p.is_synthetic && <DemoBadge />}<AttentionBadge code={p.attention} /></>}
        actions={<>
          <Link className="btn secondary" to="/payments">All payments</Link>
          {(p.status !== 'pending') && <Link className="btn secondary" to={`/invoices/${p.order_id}`}><Icon name="print" size={17} />Receipt</Link>}
          {p.status === 'pending' && <Button onClick={() => setResume(true)} icon="wallet">Continue payment</Button>}
          {(p.status === 'pending' || p.method === 'razorpay') && p.provider !== 'none' && p.provider !== 'manual' && <Button variant="secondary" icon="refresh" onClick={() => void check()} loading={busy}>Check with Razorpay</Button>}
        </>} />
      <div className="stack">
        {att && <Note tone="warn"><b>{att.short}.</b> {att.long}</Note>}
        {p.status === 'failed' && <Note tone="bad"><b>Failed.</b> {p.failure_reason || 'The payment did not go through.'}{p.failure_code ? ` (${p.failure_code})` : ''}</Note>}
        <div className="pay-grid">
          <Card title="Payment">
            <dl className="kv">
              <dt>Amount</dt><dd><b className="amount big">{rupees(p.amount_paise)}</b></dd>
              <dt>Status</dt><dd><PayStatusBadge status={p.status} /></dd>
              <dt>Way paid</dt><dd>{METHOD_LONG[p.method]}{p.provider_method ? ` · ${p.provider_method}` : ''}</dd>
              <dt>Checked by</dt><dd>{p.verification_label}{p.verification === 'manual' && !p.verified && p.status !== 'pending' && p.status !== 'failed' && p.status !== 'cancelled' && <> <Badge tone="warn">Unverified</Badge></>}</dd>
              {p.amount_received_paise != null && (<><dt>Cash received</dt><dd>{rupees(p.amount_received_paise)}{p.change_paise > 0 && <> · change {rupees(p.change_paise)}</>}</dd></>)}
              {p.reference_note && (<><dt>UPI reference</dt><dd className="mono-id">{p.reference_note}</dd></>)}
              {p.provider_payment_id && (<><dt>Razorpay payment</dt><dd className="mono-id">{p.provider_payment_id}</dd></>)}
              {p.provider_order_id && (<><dt>Razorpay order</dt><dd className="mono-id">{p.provider_order_id}</dd></>)}
              <dt>Started</dt><dd>{p.created_at ? `${istTime(p.created_at)} IST` : '-'}{p.created_by ? ` · ${p.created_by}` : ''}</dd>
              {p.paid_at && (<><dt>Paid</dt><dd>{istTime(p.paid_at)} IST{p.confirmed_by ? ` · ${p.confirmed_by}` : ''}</dd></>)}
              {p.refunded_paise > 0 && (<><dt>Refunded</dt><dd>{rupees(p.refunded_paise)} of {rupees(p.amount_paise)}</dd></>)}
            </dl>
          </Card>
          <Card title="Refunds" description={p.refunds.length ? undefined : 'No refunds on this payment.'}>
            {p.refunds.length > 0 && <ul className="list-rows refunds">{p.refunds.map((r) => <RefundRow key={r.id} r={r} owner={owner} onChanged={res.reload} />)}</ul>}
            {canRefund && <div style={{ marginTop: p.refunds.length ? 16 : 0 }}><RefundForm key={p.refunded_paise} p={p} onDone={res.reload} /></div>}
            {!owner && (p.status === 'paid' || p.status === 'partially_refunded') && <p className="muted small">Only the shop owner can refund a payment.</p>}
          </Card>
        </div>
        <Card title="Activity" description="Everything that changed this payment, oldest first.">
          {p.events.length === 0 ? <p className="muted">Nothing recorded yet.</p> : (
            <ol className="pay-events">
              {p.events.map((e) => (
                <li key={e.id}>
                  <div className="row tight"><b>{e.message}</b></div>
                  <div className="faint xs">
                    {e.created_at ? `${istTime(e.created_at)} IST` : ''} · {SOURCE_TEXT[e.source]}{e.actor ? ` · ${e.actor}` : ''}
                    {e.status_before && e.status_after && e.status_before !== e.status_after ? ` · ${e.status_before} to ${e.status_after}` : ''}
                    {e.signature_ok === true ? ' · signature checked' : ''}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
      {resume && <PaymentDialog orderId={p.order_id} onClose={() => setResume(false)} onChanged={res.reload} />}
    </>
  )
}
