import { useMemo } from 'react'
import qrcode from 'qrcode-generator'
import { rupees } from '../../lib/format'
import type { UpiInstructions } from '../../types'
import { Badge } from '../ui'

/** The QR drawn as one SVG path from the library's module grid (no innerHTML). Dark modules on a white tile so phone cameras read it. */
export function QrSvg({ text, label, size = 220 }: { text: string; label: string; size?: number }) {
  const d = useMemo(() => {
    const q = qrcode(0, 'M')
    q.addData(text)
    q.make()
    const n = q.getModuleCount()
    let path = ''
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) path += `M${c + 4} ${r + 4}h1v1h-1z`
    return { path, n }
  }, [text])
  const box = d.n + 8
  return (
    <svg className="qr-svg" width={size} height={size} viewBox={`0 0 ${box} ${box}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <rect width={box} height={box} fill="#ffffff" />
      <path d={d.path} fill="#14181f" />
    </svg>
  )
}

/** What the customer scans, with the amount and the order it belongs to written next to it.
 *  Two kinds, and the screen says which: a QR made by Razorpay (the payment confirms itself) and a plain UPI QR (nothing confirms it until a person does). */
export function UpiQr({ upi }: { upi: UpiInstructions }) {
  const provider = upi.mode === 'provider'
  const hasQr = !!(upi.qr_image_url || upi.uri)
  return (
    <div className="upi-box">
      <div className="upi-qr">
        {upi.qr_image_url
          ? <img className="qr-svg" src={upi.qr_image_url} width={220} height={220} alt={`UPI QR code for ${rupees(upi.amount_paise)}, order ${upi.order_code}`} />
          : upi.uri
            ? <QrSvg text={upi.uri} label={`UPI QR code for ${rupees(upi.amount_paise)}, order ${upi.order_code}`} />
            : <div className="qr-missing muted small">No QR could be made.</div>}
      </div>
      <div className="upi-side">
        <Badge tone={provider ? 'info' : 'warn'} dot title={provider ? 'Razorpay tells this app when the money arrives.' : 'This app cannot see your bank. A person must confirm.'}>
          {provider ? 'Razorpay confirms this payment' : 'Not verified: a person must confirm'}
        </Badge>
        <dl className="kv compact">
          <dt>Amount</dt><dd><b className="amount">{rupees(upi.amount_paise)}</b></dd>
          <dt>Order</dt><dd>{upi.order_code}</dd>
          {upi.payee && (<><dt>Pay to</dt><dd>{upi.payee}</dd></>)}
          <dt>Reference</dt><dd className="mono-id">{upi.reference}</dd>
        </dl>
        {hasQr && <p className="small muted">{upi.instructions}</p>}
      </div>
    </div>
  )
}
