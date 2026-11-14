import { METHOD_TEXT, PAY_STATUS_TEXT, PAY_STATUS_TONE, attentionText } from '../../lib/payments'
import type { OrderPaymentStatus, PaymentMethod } from '../../types'
import { Icon, type IconName } from '../Icons'
import { Badge } from '../ui'

export const METHOD_ICON: Record<PaymentMethod, IconName> = { cash: 'cash', upi: 'qr', razorpay: 'card' }

export function PayStatusBadge({ status, title }: { status: OrderPaymentStatus; title?: string }) {
  return <Badge tone={PAY_STATUS_TONE[status]} dot title={title}>{PAY_STATUS_TEXT[status]}</Badge>
}

export function MethodBadge({ method }: { method: PaymentMethod }) {
  return <span className="method-tag"><Icon name={METHOD_ICON[method]} size={14} />{METHOD_TEXT[method]}</span>
}

/** Shown only when the server raised a flag on the payment. */
export function AttentionBadge({ code }: { code: string | null | undefined }) {
  const t = attentionText(code)
  return t ? <Badge tone="warn" title={t.long}>{t.short}</Badge> : null
}
