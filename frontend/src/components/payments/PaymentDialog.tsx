import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { istTime, rupees } from '../../lib/format'
import { METHOD_LONG, cashReceivedProblem, cashSuggestions, isPaid, newKey, openCheckout, rupeesToPaise, upiReferenceProblem, type CheckoutResponse } from '../../lib/payments'
import type { OrderPayments, PaymentConfig, PaymentDetail, PaymentMethod } from '../../types'
import { Icon } from '../Icons'
import { ConfirmDialog, Dialog } from '../Overlay'
import { Button, Field, Note, SkeletonCard } from '../ui'
import { METHOD_ICON, AttentionBadge } from './badges'
import { UpiQr } from './UpiQr'

const POLL_MS = 8000
type CheckoutState = 'idle' | 'opening' | 'open' | 'verifying' | 'closed' | 'declined'

/** Taking payment for one order: choose a way, then follow it through. Nothing here marks anything paid: the screen shows what the server says.
 *  Cash and a hand-confirmed UPI payment are recorded by a person; Razorpay is confirmed by the server from its signature check and Razorpay's own records. */
export function PaymentDialog({ orderId, onClose, onChanged }: { orderId: number; onClose: () => void; onChanged?: () => void }) {
  const [info, setInfo] = useState<OrderPayments | null>(null)
  const [cfg, setCfg] = useState<PaymentConfig | null>(null)
  const [pay, setPay] = useState<PaymentDetail | null>(null)
  const [loadErr, setLoadErr] = useState<string | null>(null)
  const [choice, setChoice] = useState<PaymentMethod>('cash')
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [cancelAsk, setCancelAsk] = useState(false)
  const [cash, setCash] = useState('')
  const [seen, setSeen] = useState(false)
  const [ref, setRef] = useState('')
  const [checkout, setCheckout] = useState<CheckoutState>('idle')
  const [declined, setDeclined] = useState<string | null>(null)
  const key = useRef<{ method: PaymentMethod; key: string } | null>(null)

  const load = useCallback(async () => {
    try {
      const [o, c] = await Promise.all([api.orderPayments(orderId), api.paymentConfig()])
      const id = o.summary.pending_payment_id ?? (isPaid(o.summary.status) ? o.summary.payment_id : null)
      const d = id ? await api.payment(id) : null
      // all three together: setting the order first would flash the "choose a way" screen for one round trip before an existing payment is resumed
      setInfo(o); setCfg(c); setPay(d)
      if (d?.method === 'cash' && d.status === 'pending') setCash((v) => v || String(d.amount_paise / 100))
      setLoadErr(null)
    } catch (e) { setLoadErr((e as Error).message) }
  }, [orderId])
  useEffect(() => { void load() }, [load])

  const take = (d: PaymentDetail) => {
    setPay(d); setErr(null)
    if (d.notice) setNotice(d.notice)
    onChanged?.()
  }
  const fail = (e: unknown) => setErr((e as Error).message || 'That did not work. Nothing was changed.')

  const run = async (name: string, fn: () => Promise<void>) => {
    setBusy(name); setErr(null)
    try { await fn() } catch (e) { fail(e) } finally { setBusy(null) }
  }

  const total = info?.total_paise ?? 0
  const start = () => run('start', async () => {
    if (!key.current || key.current.method !== choice) key.current = { method: choice, key: newKey() }
    const d = await api.startPayment(orderId, choice, key.current.key)
    key.current = null
    setNotice(null); setCheckout('idle'); setSeen(false); setRef('')
    setCash(String(d.amount_paise / 100))
    take(d)
  })
  const refresh = (quiet = false) => run(quiet ? 'poll' : 'refresh', async () => {
    if (!pay) return
    const d = await api.refreshPayment(pay.id)
    if (!quiet && !d.notice) setNotice(d.status === 'pending' ? 'Still waiting. Nothing has been received yet.' : null)
    take(d)
  })
  const cancel = () => run('cancel', async () => {
    if (!pay) return
    await api.cancelPayment(pay.id)
    setCancelAsk(false); setPay(null); setNotice(null); setCheckout('idle')
    onChanged?.(); await load()
  })

  // A payment that confirms itself (a Razorpay QR, or Checkout after it has been opened) is re-read now and then, until the server says it is no longer waiting.
  const watching = !!pay && pay.status === 'pending' && ((pay.method === 'upi' && pay.upi?.mode === 'provider') || (pay.method === 'razorpay' && checkout !== 'idle'))
  const refreshRef = useRef(refresh)
  refreshRef.current = refresh
  useEffect(() => {
    if (!watching) return
    const t = setInterval(() => { if (document.visibilityState !== 'hidden' && checkout !== 'open' && checkout !== 'verifying') void refreshRef.current(true) }, POLL_MS)
    return () => clearInterval(t)
  }, [watching, checkout])

  const verify = (r: CheckoutResponse) => {
    setCheckout('verifying')
    void run('verify', async () => {
      if (!pay) return
      try {
        const d = await api.verifyRazorpay(pay.id, { razorpay_order_id: r.razorpay_order_id, razorpay_payment_id: r.razorpay_payment_id, razorpay_signature: r.razorpay_signature })
        setCheckout('closed')
        take(d)
        if (d.status === 'pending') setNotice(d.notice ?? 'Razorpay has not confirmed this payment yet. This screen checks again by itself.')
      } catch (e) { setCheckout('closed'); throw e }
    })
  }
  const open = async () => {
    if (!pay?.checkout) return
    setErr(null); setDeclined(null); setCheckout('opening')
    try {
      await openCheckout(pay.checkout, {
        onResponse: verify,
        onFailed: (m) => { setDeclined(m); setCheckout('declined') },
        onDismiss: () => setCheckout((c) => (c === 'verifying' ? c : 'closed')),
      })
      setCheckout((c) => (c === 'opening' ? 'open' : c))
    } catch (e) { setCheckout('idle'); fail(e) }
  }

  const received = rupeesToPaise(cash)
  const change = pay && received !== null && received >= pay.amount_paise ? received - pay.amount_paise : 0
  const cashProblem = pay ? cashReceivedProblem(received, pay.amount_paise) : null
  const refProblem = ref.trim() ? upiReferenceProblem(ref) : null

  /* ---------------------------------------------------------------- body + footer for the step we are on */
  let body: React.ReactNode
  let footer: React.ReactNode = null
  const done = !!pay && isPaid(pay.status)
  const failed = !!pay && pay.status === 'failed'

  if (loadErr) {
    body = <Note tone="bad">{loadErr} <Button variant="link" onClick={() => void load()}>Try again</Button></Note>
  } else if (!info || !cfg) {
    body = <SkeletonCard lines={4} height={160} />
  } else if (done && pay) {
    body = (
      <div className="stack">
        <div className="pay-result ok" role="status">
          <span className="tick"><Icon name="check" size={22} /></span>
          <div><b>Payment received</b><div className="amount big">{rupees(pay.amount_paise)}</div></div>
        </div>
        {!pay.verified && <Note tone="warn"><b>Confirmed by hand.</b> {pay.verification_label}</Note>}
        <dl className="kv">
          <dt>Order</dt><dd>{pay.order_code}</dd>
          <dt>Way paid</dt><dd>{METHOD_LONG[pay.method]}</dd>
          <dt>Payment</dt><dd className="mono-id">{pay.code}</dd>
          {pay.provider_payment_id && (<><dt>Razorpay payment</dt><dd className="mono-id">{pay.provider_payment_id}</dd></>)}
          {pay.reference_note && (<><dt>UPI reference</dt><dd className="mono-id">{pay.reference_note}</dd></>)}
          {pay.method === 'cash' && pay.amount_received_paise != null && (<><dt>Cash received</dt><dd>{rupees(pay.amount_received_paise)}{pay.change_paise > 0 && <> · change {rupees(pay.change_paise)}</>}</dd></>)}
          {pay.paid_at && (<><dt>Paid</dt><dd>{istTime(pay.paid_at)} IST{pay.confirmed_by ? ` · ${pay.confirmed_by}` : ''}</dd></>)}
          <dt>Checked by</dt><dd>{pay.verification_label}</dd>
        </dl>
        <AttentionBadge code={pay.attention} />
      </div>
    )
    footer = (<>
      <Link className="btn secondary" to={`/payments/${pay.id}`} onClick={onClose}>Payment details</Link>
      <Link className="btn secondary" to={`/invoices/${pay.order_id}`} onClick={onClose}><Icon name="print" size={17} />Receipt</Link>
      <Button onClick={onClose} data-autofocus>Done</Button>
    </>)
  } else if (failed && pay) {
    body = (
      <div className="stack">
        <div className="pay-result bad" role="alert">
          <span className="tick"><Icon name="alert" size={22} /></span>
          <div><b>Payment did not go through</b><div className="muted">{pay.failure_reason || 'The payment failed. Nothing was charged to the customer, as far as Razorpay reports.'}</div></div>
        </div>
        <p className="muted small">The order is still open. Choose a way to try again.</p>
      </div>
    )
    footer = (<>
      <Button variant="secondary" onClick={onClose}>Close</Button>
      <Button onClick={() => { setPay(null); void load() }} data-autofocus>Try another way</Button>
    </>)
  } else if (pay && pay.status === 'pending') {
    const stale = pay.stale && <Note tone="warn">This payment has been waiting for more than {cfg.pending_minutes} minutes. Check its status, or cancel it and start again.</Note>
    const cancelBtn = <Button variant="ghost" onClick={() => (pay.method === 'cash' ? void cancel() : setCancelAsk(true))} disabled={!!busy}>Cancel payment</Button>
    if (pay.method === 'cash') {
      body = (
        <div className="stack">
          <div className="pay-sum"><span>Bill</span><b className="amount big">{rupees(pay.amount_paise)}</b></div>
          <Field label="Cash received (rupees)" htmlFor="cash-in" error={received !== null && cashProblem ? cashProblem : null} hint="Type what the customer handed over. The change is worked out for you.">
            <input id="cash-in" inputMode="decimal" autoComplete="off" value={cash} onChange={(e) => setCash(e.target.value)} data-autofocus />
          </Field>
          <div className="row tight" aria-label="Quick amounts">
            <Button size="sm" variant="secondary" onClick={() => setCash(String(pay.amount_paise / 100))}>Exact {rupees(pay.amount_paise)}</Button>
            {cashSuggestions(pay.amount_paise).map((v) => <Button key={v} size="sm" variant="secondary" onClick={() => setCash(String(v / 100))}>{rupees(v)}</Button>)}
          </div>
          <div className="pay-sum change" aria-live="polite"><span>Give back</span><b className="amount big">{rupees(change)}</b></div>
        </div>
      )
      footer = (<>{cancelBtn}<Button icon="check" onClick={() => run('cash', async () => { if (received !== null) take(await api.recordCash(pay.id, received)) })} loading={busy === 'cash'} disabled={!!cashProblem || !!busy}>Record cash received</Button></>)
    } else if (pay.method === 'upi' && pay.upi) {
      const provider = pay.upi.mode === 'provider'
      body = (
        <div className="stack">
          {stale}
          <UpiQr upi={pay.upi} />
          {provider ? (
            <Note tone="info"><span className="spinner" aria-hidden /> Waiting for Razorpay to confirm the payment. This screen checks by itself every few seconds.{' '}{notice}</Note>
          ) : (
            <div className="stack tight pay-confirm">
              <Note tone="warn"><b>This app cannot see the money.</b> The payment stays unconfirmed until someone checks the shop's bank or UPI app and confirms it here. A customer saying they paid is not proof.</Note>
              <label className="check"><input type="checkbox" checked={seen} onChange={(e) => setSeen(e.target.checked)} />I can see {rupees(pay.amount_paise)} from this customer in the bank or UPI app</label>
              <Field label="UPI reference (UTR) from the bank or UPI app" htmlFor="upi-ref" error={refProblem}>
                <input id="upi-ref" value={ref} onChange={(e) => setRef(e.target.value)} maxLength={40} autoComplete="off" placeholder="e.g. 412345678901" />
              </Field>
            </div>
          )}
        </div>
      )
      footer = provider
        ? (<>{cancelBtn}<Button variant="secondary" icon="refresh" onClick={() => void refresh()} loading={busy === 'refresh'}>Check status</Button></>)
        : (<>{cancelBtn}<Button icon="check" onClick={() => run('upi', async () => take(await api.confirmUpi(pay.id, ref.trim())))} loading={busy === 'upi'} disabled={!seen || !ref.trim() || !!refProblem || !!busy}>Confirm payment received</Button></>)
    } else if (pay.method === 'razorpay') {
      body = (
        <div className="stack">
          {stale}
          <div className="pay-sum"><span>Amount to pay</span><b className="amount big">{rupees(pay.amount_paise)}</b></div>
          {pay.checkout?.mode === 'test' && <Note tone="info"><b>Test mode.</b> No real money moves. Use Razorpay's test details in the Checkout window.</Note>}
          <p className="muted">Razorpay Checkout lets the customer pay with UPI, a card or netbanking. The payment counts only after this app has checked it with Razorpay.</p>
          {checkout === 'verifying' && <Note tone="info"><span className="spinner" aria-hidden /> Checking the payment with Razorpay...</Note>}
          {checkout === 'closed' && !notice && <Note tone="info">Checkout was closed. If the customer already paid, use Check status. Otherwise open Checkout again.</Note>}
          {checkout === 'declined' && declined && <Note tone="bad"><b>Razorpay says it failed.</b> {declined} The customer can try again inside Checkout.</Note>}
          {notice && <Note tone="info">{notice}</Note>}
        </div>
      )
      footer = (<>{cancelBtn}
        <Button variant="secondary" icon="refresh" onClick={() => void refresh()} loading={busy === 'refresh'} disabled={!!busy && busy !== 'refresh'}>Check status</Button>
        <Button variant="accent" icon="card" onClick={() => void open()} loading={checkout === 'opening'} disabled={!pay.checkout || checkout === 'verifying' || !!busy}>{checkout === 'idle' ? 'Open Razorpay Checkout' : 'Open Checkout again'}</Button></>)
    } else {
      body = <Note tone="bad">This payment is in a state this screen cannot continue. Open its details instead.</Note>
    }
  } else {
    // nothing started yet: choose
    const failedBefore = info.items.filter((p) => p.status === 'failed').sort((a, b) => b.id - a.id)[0]
    const opts: { m: PaymentMethod; title: string; text: string; ok: boolean; why: string | null }[] = [
      { m: 'cash', title: 'Cash', text: 'The customer pays at the counter or on delivery. You enter what you received.', ok: cfg.methods.cash.available, why: cfg.methods.cash.reason },
      { m: 'upi', title: 'UPI QR code', text: cfg.methods.upi.mode === 'provider' ? 'A QR made by Razorpay. The payment confirms itself.' : 'The shop\'s own UPI QR. You confirm it after checking the bank or UPI app.', ok: cfg.methods.upi.available, why: cfg.methods.upi.reason },
      { m: 'razorpay', title: 'Razorpay Checkout', text: 'UPI, cards and netbanking. Confirmed by Razorpay, never by the screen.', ok: cfg.methods.razorpay.available, why: cfg.methods.razorpay.reason },
    ]
    body = (
      <div className="stack">
        <div className="pay-sum"><span>{info.order_code}</span><b className="amount big">{rupees(total)}</b></div>
        {cfg.mode === 'test' && cfg.razorpay.enabled && <Note tone="info"><b>Test mode.</b> Razorpay payments here use test keys, so no real money moves.</Note>}
        {failedBefore && <Note tone="warn"><b>The last attempt failed.</b> {failedBefore.failure_reason || 'Choose a way to try again.'}</Note>}
        <div role="radiogroup" aria-label="How is the customer paying?" className="pay-options">
          {opts.map((o) => (
            <button key={o.m} type="button" role="radio" aria-checked={choice === o.m} disabled={!o.ok} className="pay-option" onClick={() => setChoice(o.m)}>
              <span className="po-ico"><Icon name={METHOD_ICON[o.m]} size={20} /></span>
              <span className="po-text"><b>{o.title}</b><span>{o.ok ? o.text : o.why}</span></span>
              <span className="po-dot" aria-hidden />
            </button>
          ))}
        </div>
      </div>
    )
    footer = (<><Button variant="secondary" onClick={onClose}>Not now</Button>
      <Button onClick={() => void start()} loading={busy === 'start'} disabled={!opts.find((o) => o.m === choice)?.ok || !!busy} icon="arrowRight" data-autofocus>Continue</Button></>)
  }

  return (
    <>
      <Dialog title="Take payment" subtitle={info ? `${info.order_code} · ${rupees(info.total_paise)}` : undefined} onClose={onClose} footer={footer}>
        <div className="pay-dialog">
          {err && <Note tone="bad">{err}</Note>}
          {body}
        </div>
      </Dialog>
      {cancelAsk && pay && (
        <ConfirmDialog title="Cancel this payment?" confirmLabel="Cancel payment" busy={busy === 'cancel'} onConfirm={() => void cancel()} onClose={() => setCancelAsk(false)}
          body={pay.method === 'razorpay'
            ? 'The order stays open and you can choose another way. If the customer has already started paying in Razorpay Checkout, a payment that goes through later is still recorded and flagged for you.'
            : pay.upi?.mode === 'provider'
              ? 'The order stays open and you can choose another way. The QR is closed at Razorpay where possible.'
              : 'The order stays open and you can choose another way. If the customer pays this QR anyway, the money will not be matched to this order automatically.'} />
      )}
    </>
  )
}
