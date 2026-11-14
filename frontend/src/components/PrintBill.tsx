import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { fmtQty, istTime, rupees, unitLabel } from '../lib/format'
import type { Order } from '../types'
import { Button } from './ui'

const PRINTING = 'printing-bill'

/** A plain, receipt-style bill for one order. It is only ever on paper: on screen it is hidden, and while printing it is the only thing shown. */
function Bill({ order, shopName }: { order: Order; shopName: string }) {
  return createPortal(
    <div className="print-bill" aria-hidden>
      <h1>{shopName}</h1>
      <p className="pb-meta">Bill {order.code}<br />{istTime(order.created_at)} IST<br />Customer: {order.customer_name}</p>
      {order.status === 'cancelled' && <p className="pb-flag">CANCELLED. Stock was returned to the shelf.</p>}
      {order.is_synthetic && <p className="pb-flag">Generated demo data. This is not a real sale.</p>}
      <table>
        <thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead>
        <tbody>
          {order.items.map((i) => (
            <tr key={i.product_id}><td>{i.name}</td><td>{fmtQty(i.qty)} {unitLabel(i.unit)}</td><td>{rupees(i.unit_price_paise)}</td><td>{rupees(i.line_total_paise)}</td></tr>
          ))}
        </tbody>
        <tfoot><tr><td colSpan={3}>Total</td><td>{rupees(order.total_paise)}</td></tr></tfoot>
      </table>
      <p className="pb-foot">Thank you. Prices are as entered by the shop; this bill shows no tax breakdown.</p>
    </div>,
    document.body,
  )
}

/** "Print bill": opens the browser's print dialog showing only this order's bill (it can also be saved as a PDF from there). */
export function PrintBillButton({ order, shopName }: { order: Order; shopName: string }) {
  useEffect(() => () => document.body.classList.remove(PRINTING), [])
  const print = () => {
    const done = () => document.body.classList.remove(PRINTING)
    document.body.classList.add(PRINTING)
    window.addEventListener('afterprint', done, { once: true })
    window.print()
  }
  return (
    <>
      <Button size="sm" variant="secondary" icon="print" onClick={print} title="Print this bill, or save it as a PDF from the print window">Print bill</Button>
      <Bill order={order} shopName={shopName} />
    </>
  )
}
