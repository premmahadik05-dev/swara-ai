import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { Button, Empty, ErrorNote, Note, PageHeader, SkeletonCard } from '../components/ui'
import { fmtQty, istTime, rupees, unitLabel } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { METHOD_LONG, PAY_STATUS_TEXT } from '../lib/payments'
import type { InvoiceData } from '../types'

const PRINTING = 'printing-invoice'

/** The invoice as a document. The same markup is shown on screen and printed. It states only what is recorded: no tax is worked out or claimed. */
function InvoiceDoc({ inv }: { inv: InvoiceData }) {
  const p = inv.payment
  return (
    <article className="invoice-doc" aria-label={`Invoice ${inv.number}`}>
      <header className="inv-head">
        <div><h2 className="inv-shop">{inv.shop.name}</h2><div className="inv-kind">Invoice</div></div>
        <dl className="inv-meta">
          <dt>Invoice no.</dt><dd>{inv.number}</dd>
          <dt>Issued</dt><dd>{inv.issued_at ? `${istTime(inv.issued_at)} IST` : '-'}</dd>
          <dt>Order</dt><dd>{inv.order_code}</dd>
          {inv.ordered_at && (<><dt>Ordered</dt><dd>{istTime(inv.ordered_at)} IST</dd></>)}
        </dl>
      </header>
      {inv.order_status === 'cancelled' && <p className="inv-flag">This order was cancelled.</p>}
      {inv.is_synthetic && <p className="inv-flag">Generated demo data. This is not a real sale.</p>}
      <section className="inv-block"><div className="inv-label">Billed to</div><div><b>{inv.customer.name}</b>{inv.customer.phone ? <> · {inv.customer.phone}</> : null}</div></section>
      <table className="inv-table">
        <thead><tr><th>Item</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">Amount</th></tr></thead>
        <tbody>
          {inv.items.map((i, n) => (
            <tr key={n}><td>{i.name}</td><td className="num">{fmtQty(i.qty)} {unitLabel(i.unit)}</td><td className="num">{rupees(i.unit_price_paise)}</td><td className="num">{rupees(i.line_total_paise)}</td></tr>
          ))}
        </tbody>
        <tfoot>
          <tr><td colSpan={3}>Subtotal</td><td className="num">{rupees(inv.subtotal_paise)}</td></tr>
          {inv.discount_paise > 0 && <tr><td colSpan={3}>Discount</td><td className="num">-{rupees(inv.discount_paise)}</td></tr>}
          <tr className="inv-total"><td colSpan={3}>Total</td><td className="num">{rupees(inv.total_paise)}</td></tr>
        </tfoot>
      </table>
      <section className="inv-block">
        <div className="inv-label">Payment</div>
        {p ? (
          <dl className="inv-pay">
            <dt>Status</dt><dd>{PAY_STATUS_TEXT[p.status]}</dd>
            <dt>Way paid</dt><dd>{METHOD_LONG[p.method]}</dd>
            <dt>Reference</dt><dd>{p.reference}{p.provider_payment_id ? ` · ${p.provider_payment_id}` : ''}</dd>
            {p.paid_at && (<><dt>Paid</dt><dd>{istTime(p.paid_at)} IST</dd></>)}
            <dt>Amount</dt><dd>{rupees(p.amount_paise)}{p.refunded_paise > 0 ? ` (${rupees(p.refunded_paise)} refunded)` : ''}</dd>
            <dt>Checked by</dt><dd>{p.label}</dd>
          </dl>
        ) : <div>No payment is recorded for this order in SWARA AI.</div>}
      </section>
      <p className="inv-note">{inv.tax_note}</p>
    </article>
  )
}

/** Invoice for one order. Opening it issues the invoice number once; opening it again shows the same one. */
export default function Invoice() {
  const { orderId } = useParams()
  const oid = Number(orderId)
  const res = useAsync(() => (Number.isFinite(oid) ? api.invoice(oid) : Promise.reject(new Error('That invoice address is not valid.'))), [oid])
  const inv = res.data
  useEffect(() => () => document.body.classList.remove(PRINTING), [])

  const print = () => {
    if (!inv) return
    const title = document.title
    const done = () => { document.body.classList.remove(PRINTING); document.title = title }
    document.body.classList.add(PRINTING)
    document.title = inv.number   // the name a "save as PDF" file starts with
    window.addEventListener('afterprint', done, { once: true })
    window.print()
  }

  return (
    <>
      <PageHeader title={inv ? `Invoice ${inv.number}` : 'Invoice'} description="A printable bill with the payment recorded for the order. It can be saved as a PDF from the print window."
        actions={<>
          <Link className="btn secondary" to={`/orders?open=${oid}`}>Back to order</Link>
          <Button icon="print" onClick={print} disabled={!inv}>Print or save as PDF</Button>
        </>} />
      <div className="stack">
        <ErrorNote error={res.error} onRetry={res.reload} />
        {res.loading && !inv && <SkeletonCard lines={8} height={320} />}
        {!inv && !res.loading && !res.error && <Empty title="Invoice not found" icon="orders" />}
        {inv && (
          <>
            <Note tone="info">{inv.tax_note}</Note>
            <div className="invoice-sheet"><InvoiceDoc inv={inv} /></div>
            {createPortal(<div className="print-invoice" aria-hidden><InvoiceDoc inv={inv} /></div>, document.body)}
          </>
        )}
      </div>
    </>
  )
}
