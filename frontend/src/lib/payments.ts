import { rupees } from './format'
import type { OrderPaymentStatus, OrderPaymentSummary, PaymentCheckout, PaymentMethod, PaymentStatus } from '../types'

/* Words and tones for payments, kept in one place so every screen says the same thing.
   "Not recorded" is for an order that has no payment in this app. It does not mean unpaid: shops took cash before payments existed here. */
export const PAY_STATUS_TEXT: Record<OrderPaymentStatus, string> = {
  none: 'Not recorded', pending: 'Waiting for payment', paid: 'Paid', failed: 'Failed', cancelled: 'Cancelled', partially_refunded: 'Partly refunded', refunded: 'Refunded',
}
export const PAY_STATUS_TONE: Record<OrderPaymentStatus, 'ok' | 'warn' | 'bad' | 'info' | 'plain' | undefined> = {
  none: undefined, pending: 'warn', paid: 'ok', failed: 'bad', cancelled: undefined, partially_refunded: 'info', refunded: 'info',
}
export const METHOD_TEXT: Record<PaymentMethod, string> = { cash: 'Cash', upi: 'UPI', razorpay: 'Razorpay' }
export const METHOD_LONG: Record<PaymentMethod, string> = { cash: 'Cash', upi: 'UPI QR code', razorpay: 'Razorpay (UPI, cards, netbanking)' }
export const REFUND_STATUS_TEXT = { pending: 'Waiting for Razorpay', processed: 'Refunded', failed: 'Failed' } as const

/** What the Orders list shows in its Payment column. */
export function orderPaymentLabel(s: OrderPaymentSummary | undefined): { text: string; tone: (typeof PAY_STATUS_TONE)[OrderPaymentStatus] } {
  const st: OrderPaymentStatus = s?.status ?? 'none'
  const method = s?.method && (st === 'paid' || st === 'partially_refunded' || st === 'refunded') ? ` · ${METHOD_TEXT[s.method]}` : ''
  return { text: PAY_STATUS_TEXT[st] + method, tone: PAY_STATUS_TONE[st] }
}

/** Same rule as the server: 4 to 40 letters or digits. The server stays the judge; this only saves a round trip. */
export const upiReferenceProblem = (v: string): string | null =>
  /^[A-Za-z0-9\-_/ ]{4,40}$/.test(v.replace(/\s+/g, ' ').trim()) ? null : 'Enter the UPI reference from your bank or UPI app (4 to 40 letters or digits).'

export const isPaid = (s: PaymentStatus | OrderPaymentStatus | undefined) => s === 'paid' || s === 'partially_refunded' || s === 'refunded'

/** "1,234.50", "₹ 500", "500" to whole paise. Returns null for anything that is not a plain amount with at most two decimals. */
export function rupeesToPaise(text: string): number | null {
  const t = text.replace(/[₹,\s]/g, '')
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(t)) return null
  const [whole, frac = ''] = t.split('.')
  return Number(whole) * 100 + Number((frac + '00').slice(0, 2))
}

/** A fresh request key. Sending the same key again returns the same payment, so a double tap or a retry never starts two. */
export function newKey(): string {
  const c = globalThis.crypto
  if (c?.randomUUID) return c.randomUUID()
  return 'k-' + Math.random().toString(36).slice(2) + Date.now().toString(36)
}

/* ------------------------------------------------------------------ Razorpay Checkout
   The browser only ever holds the PUBLIC key id and the Razorpay order id the server made. Whatever Checkout reports is sent to the server, which
   checks the signature with the key secret and asks Razorpay about the payment. A "success" in this file never marks anything paid by itself. */
const CHECKOUT_SRC = 'https://checkout.razorpay.com/v1/checkout.js'

export interface CheckoutResponse { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string }
interface RazorpayInstance { open: () => void; on: (event: string, cb: (r: { error?: { description?: string; reason?: string; code?: string } }) => void) => void }
type RazorpayCtor = new (options: Record<string, unknown>) => RazorpayInstance
declare global { interface Window { Razorpay?: RazorpayCtor } }

let loading: Promise<RazorpayCtor> | null = null
export function loadCheckout(): Promise<RazorpayCtor> {
  if (window.Razorpay) return Promise.resolve(window.Razorpay)
  if (loading) return loading
  loading = new Promise<RazorpayCtor>((resolve, reject) => {
    const s = document.createElement('script')
    s.src = CHECKOUT_SRC
    s.async = true
    s.onload = () => (window.Razorpay ? resolve(window.Razorpay) : reject(new Error('Razorpay Checkout did not start.')))
    s.onerror = () => { loading = null; s.remove(); reject(new Error('Could not load Razorpay Checkout. Check the internet connection. Nothing was charged.')) }
    document.head.appendChild(s)
  })
  return loading
}

export interface CheckoutHandlers {
  onResponse: (r: CheckoutResponse) => void
  onFailed: (message: string) => void
  onDismiss: () => void
}
export async function openCheckout(c: PaymentCheckout, h: CheckoutHandlers): Promise<void> {
  const Razorpay = await loadCheckout()
  const rz = new Razorpay({
    key: c.key_id, order_id: c.provider_order_id, amount: c.amount_paise, currency: c.currency, name: c.name, description: c.description,
    handler: (r: CheckoutResponse) => h.onResponse(r),
    modal: { ondismiss: () => h.onDismiss(), confirm_close: true },
    theme: { color: '#c9a459' },
  })
  rz.on('payment.failed', (r) => h.onFailed(r.error?.description || r.error?.reason || 'The payment did not go through.'))
  rz.open()
}

/** The server's "needs a look" flags, in the words the owner reads. */
export const ATTENTION_TEXT: Record<string, { short: string; long: string }> = {
  amount_mismatch: { short: 'Amount differs', long: 'Razorpay reported an amount that does not match the bill. It was not marked paid. Check it in the Razorpay dashboard.' },
  late_payment: { short: 'Paid late', long: 'Money arrived after this payment had already failed or been cancelled. It is now recorded as paid.' },
  duplicate_collection: { short: 'Collected twice', long: 'More than one payment was collected for this order. Refund the extra one.' },
  order_cancelled: { short: 'Order cancelled', long: 'Money was collected for an order that is cancelled. Refund it, or reopen the sale by talking to the customer.' },
  refund_mismatch: { short: 'Refund differs', long: 'Razorpay reported a refund amount that differs from the one asked for. The recorded amount was corrected to fit.' },
}
export const attentionText = (code: string | null | undefined) => (code ? ATTENTION_TEXT[code] ?? { short: 'Needs a look', long: 'This payment needs a look.' } : null)

/** Smallest few round amounts a customer might hand over for a bill, for the cash screen. */
/** The same rule the server applies to cash received (payments service, confirm_cash): not less than the bill, and not more than twenty times the bill plus ₹1,000 (an obvious slip, such as extra digits).
 *  The server is the one that decides; this only stops the button before a request that would be refused. Returns the reason, or null. */
export function cashReceivedProblem(receivedPaise: number | null, billPaise: number): string | null {
  if (receivedPaise === null) return 'Enter the amount as rupees, for example 500 or 499.50.'
  if (receivedPaise < billPaise) return `That is less than the bill of ${rupees(billPaise)}.`
  if (receivedPaise > billPaise * 20 + 100_000) return 'That amount looks wrong. Check it and try again.'
  return null
}

export function cashSuggestions(totalPaise: number): number[] {
  const out: number[] = []
  for (const step of [1000, 5000, 10000, 50000, 200000]) {
    const v = Math.ceil(totalPaise / step) * step
    if (v > totalPaise && !out.includes(v)) out.push(v)
    if (out.length === 3) break
  }
  return out
}
