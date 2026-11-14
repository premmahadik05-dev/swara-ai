import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PaymentDialog } from './PaymentDialog'
import { ToastProvider } from '../Toast'
import { json, mockRoutes, payment, paymentConfig } from '../../test/fixtures'
import type { OrderPayments, PaymentDetail } from '../../types'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); delete (window as { Razorpay?: unknown }).Razorpay })

const NONE = { status: 'none', paid_paise: 0, refunded_paise: 0, method: null, payment_id: null, pending_payment_id: null } as const
const orderPayments = (over: Partial<OrderPayments> = {}): OrderPayments => ({ order_id: 12, order_code: 'SW-261111-0012', total_paise: 17200, summary: NONE, items: [], ...over })
const renderIt = (onClose = vi.fn(), onChanged = vi.fn()) => render(
  <MemoryRouter><ToastProvider><PaymentDialog orderId={12} onClose={onClose} onChanged={onChanged} /></ToastProvider></MemoryRouter>,
)
const body = (m: { calls: { method: string; url: string; body: string | null }[] }, key: string) => {
  const c = m.calls.find((x) => `${x.method} ${x.url}` === key)
  return c?.body ? JSON.parse(c.body) : null
}
const paid = (over: Partial<PaymentDetail> = {}) => payment({ status: 'paid', verified: true, verification: 'cash', verification_label: 'Cash recorded by Test Owner', paid_at: '2026-11-11T13:04:00', confirmed_by: 'Test Owner', ...over })

describe('PaymentDialog: choosing a way', () => {
  it('lists the three ways, turns off the ones that are not set up and says why', async () => {
    mockRoutes({ 'GET /api/orders/12/payments': orderPayments(), 'GET /api/payments/config': paymentConfig() })
    renderIt()
    const group = await screen.findByRole('radiogroup', { name: 'How is the customer paying?' })
    expect(within(group).getByRole('radio', { name: /Cash/ })).toBeEnabled()
    const rz = within(group).getByRole('radio', { name: /Razorpay Checkout/ })
    expect(rz).toBeDisabled()
    expect(rz).toHaveTextContent('Razorpay keys are not set')
    expect(within(group).getByRole('radio', { name: /UPI QR code/ })).toBeDisabled()
    expect(within(group).getByRole('radio', { name: /UPI QR code/ })).toHaveTextContent("Add the shop's UPI ID in Settings")
  })

  it('says nothing about test keys when no Razorpay keys are set', async () => {
    mockRoutes({ 'GET /api/orders/12/payments': orderPayments(), 'GET /api/payments/config': paymentConfig() })
    renderIt()
    await screen.findByRole('radiogroup')
    expect(screen.queryByText(/Test mode\./)).not.toBeInTheDocument()
  })

  it('tells the person about a test-mode setup and about a failed earlier attempt', async () => {
    mockRoutes({
      'GET /api/orders/12/payments': orderPayments({ items: [payment({ id: 5, status: 'failed', failure_reason: 'The card was declined.' })], summary: { ...NONE, status: 'failed' } }),
      'GET /api/payments/config': paymentConfig({ razorpay: true }),
    })
    renderIt()
    expect(await screen.findByText(/The last attempt failed\./)).toBeInTheDocument()
    expect(screen.getByText('The card was declined.', { exact: false })).toBeInTheDocument()
    expect(screen.getByText(/Test mode\./)).toBeInTheDocument()
  })
})

describe('PaymentDialog: resuming', () => {
  it('shows a skeleton, not the choose-a-way screen, while it fetches an existing payment', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((r) => { release = r })
    mockRoutes({
      'GET /api/orders/12/payments': orderPayments({ summary: { ...NONE, status: 'pending', pending_payment_id: 7 } }),
      'GET /api/payments/config': paymentConfig(),
      'GET /api/payments/7': async () => { await gate; return payment({ id: 7, method: 'cash', status: 'pending' }) },
    })
    renderIt()
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Take payment' })).toBeInTheDocument())
    await new Promise((r) => setTimeout(r, 30))
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Continue' })).not.toBeInTheDocument()
    release()
    expect(await screen.findByLabelText('Cash received (rupees)')).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
  })
})

describe('PaymentDialog: cash', () => {
  const setup = () => {
    let state: PaymentDetail | null = null
    const m = mockRoutes({
      'GET /api/orders/12/payments': () => orderPayments({ summary: state ? { ...NONE, status: state.status === 'paid' ? 'paid' : 'pending', pending_payment_id: state.status === 'pending' ? state.id : null } : NONE }),
      'GET /api/payments/config': paymentConfig(),
      'POST /api/orders/12/payments': () => { state = payment(); return json(state, 201) },
      'POST /api/payments/7/cash': (_u: URL, init: RequestInit) => { const b = JSON.parse(String(init.body)); state = paid({ method: 'cash', amount_received_paise: b.received_paise, change_paise: b.received_paise - 17200 }); return state },
    })
    return m
  }

  it('starts a cash payment with a request key, works out the change and records it', async () => {
    const m = setup()
    const onChanged = vi.fn()
    renderIt(vi.fn(), onChanged)
    await userEvent.click(await screen.findByRole('radio', { name: /Cash/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    const started = body(m, 'POST /api/orders/12/payments')
    expect(started.method).toBe('cash')
    expect(started.idempotency_key).toMatch(/.{8,}/)
    expect(started.amount_paise).toBeUndefined()   // the amount is never sent: the server charges the order's own total

    const input = await screen.findByLabelText('Cash received (rupees)')
    expect(input).toHaveValue('172')
    await userEvent.clear(input)
    await userEvent.type(input, '500')
    expect(screen.getByText('Give back').parentElement).toHaveTextContent('₹328')
    await userEvent.click(screen.getByRole('button', { name: 'Record cash received' }))
    expect(await screen.findByText('Payment received')).toBeInTheDocument()
    expect(body(m, 'POST /api/payments/7/cash')).toEqual({ received_paise: 50000 })
    expect(screen.getByText(/Cash received/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Receipt/ })).toHaveAttribute('href', '/invoices/12')
    expect(onChanged).toHaveBeenCalled()
  })

  it('will not record less than the bill and says so', async () => {
    setup()
    renderIt()
    await userEvent.click(await screen.findByRole('radio', { name: /Cash/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    const input = await screen.findByLabelText('Cash received (rupees)')
    await userEvent.clear(input)
    await userEvent.type(input, '100')
    expect(screen.getByText('That is less than the bill of ₹172.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Record cash received' })).toBeDisabled()
    await userEvent.clear(input)
    await userEvent.type(input, 'abc')
    expect(screen.getByRole('button', { name: 'Record cash received' })).toBeDisabled()
  })

  it('stops an amount the server would call a slip (over twenty times the bill plus 1,000 rupees) before it is sent', async () => {
    setup()
    renderIt()
    await userEvent.click(await screen.findByRole('radio', { name: /Cash/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    const input = await screen.findByLabelText('Cash received (rupees)')
    await userEvent.clear(input)
    await userEvent.type(input, '99999')
    expect(screen.getByText('That amount looks wrong. Check it and try again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Record cash received' })).toBeDisabled()
  })

  it('shows the server message when recording fails, and does not show the payment as received', async () => {
    mockRoutes({
      'GET /api/orders/12/payments': orderPayments({ summary: { ...NONE, status: 'pending', pending_payment_id: 7 } }),
      'GET /api/payments/config': paymentConfig(),
      'GET /api/payments/7': payment(),
      'POST /api/payments/7/cash': () => json({ detail: { code: 'NOT_PENDING', message: 'That payment is no longer waiting.' } }, 409),
    })
    renderIt()
    await screen.findByLabelText('Cash received (rupees)')
    await userEvent.click(screen.getByRole('button', { name: 'Record cash received' }))
    expect(await screen.findByText('That payment is no longer waiting.')).toBeInTheDocument()
    expect(screen.queryByText('Payment received')).not.toBeInTheDocument()
  })

  it('resumes a payment that is already waiting instead of starting a second one', async () => {
    const m = mockRoutes({
      'GET /api/orders/12/payments': orderPayments({ summary: { ...NONE, status: 'pending', pending_payment_id: 7 } }),
      'GET /api/payments/config': paymentConfig(),
      'GET /api/payments/7': payment(),
    })
    renderIt()
    expect(await screen.findByLabelText('Cash received (rupees)')).toBeInTheDocument()
    expect(m.calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('shows an already-paid order as paid without offering to take payment again', async () => {
    mockRoutes({
      'GET /api/orders/12/payments': orderPayments({ summary: { status: 'paid', paid_paise: 17200, refunded_paise: 0, method: 'cash', payment_id: 7, pending_payment_id: null } }),
      'GET /api/payments/config': paymentConfig(),
      'GET /api/payments/7': paid(),
    })
    renderIt()
    expect(await screen.findByText('Payment received')).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
  })

  it('asks before cancelling a waiting non-cash payment, then returns to the choice', async () => {
    let cancelled = false
    mockRoutes({
      'GET /api/orders/12/payments': () => orderPayments({ summary: cancelled ? NONE : { ...NONE, status: 'pending', pending_payment_id: 7 } }),
      'GET /api/payments/config': paymentConfig({ vpa: 'patelstore@okhdfcbank' }),
      'GET /api/payments/7': payment({ method: 'upi', provider: 'manual', upi: { mode: 'manual', verified_by_provider: false, uri: 'upi://pay?pa=x', qr_image_url: null, payee: 'patelstore@okhdfcbank', amount_paise: 17200, reference: 'PAY-1', order_code: 'SW-1', instructions: 'Scan.' } }),
      'POST /api/payments/7/cancel': () => { cancelled = true; return payment({ status: 'cancelled', method: 'upi' }) },
    })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel payment' }))
    const confirm = await screen.findByRole('alertdialog')
    expect(confirm).toHaveTextContent(/order stays open/i)
    await userEvent.click(within(confirm).getByRole('button', { name: 'Cancel payment' }))
    expect(await screen.findByRole('radiogroup')).toBeInTheDocument()
  })
})

describe('PaymentDialog: UPI QR confirmed by hand', () => {
  const upiPending = () => payment({ method: 'upi', provider: 'manual', upi: { mode: 'manual', verified_by_provider: false, uri: 'upi://pay?pa=patelstore%40okhdfcbank&am=172.00', qr_image_url: null, payee: 'patelstore@okhdfcbank', amount_paise: 17200, reference: 'PAY-261111-0007', order_code: 'SW-261111-0012', instructions: 'Scan.' } })

  it('shows the QR as unverified and keeps Confirm off until someone has looked at the bank and typed the reference', async () => {
    const m = mockRoutes({
      'GET /api/orders/12/payments': orderPayments({ summary: { ...NONE, status: 'pending', pending_payment_id: 7 } }),
      'GET /api/payments/config': paymentConfig({ vpa: 'patelstore@okhdfcbank' }),
      'GET /api/payments/7': upiPending(),
      'POST /api/payments/7/confirm-upi': () => payment({ ...upiPending(), status: 'paid', verified: false, verification: 'manual', verification_label: 'Confirmed by hand by Test Owner. Not verified by a payment provider.', reference_note: 'UTR412345', paid_at: '2026-11-11T13:09:00' }),
    })
    renderIt()
    expect(await screen.findByText('Not verified: a person must confirm')).toBeInTheDocument()
    expect(screen.getByText(/cannot see the money/)).toBeInTheDocument()
    const confirm = screen.getByRole('button', { name: 'Confirm payment received' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/UPI reference/), 'UTR412345')
    expect(confirm).toBeDisabled()   // still not enough: nobody has said they looked
    await userEvent.click(screen.getByRole('checkbox', { name: /I can see ₹172/ }))
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)
    expect(await screen.findByText('Payment received')).toBeInTheDocument()
    expect(body(m, 'POST /api/payments/7/confirm-upi')).toEqual({ reference: 'UTR412345' })
    expect(screen.getByText(/Confirmed by hand\./)).toBeInTheDocument()   // the result keeps saying it was not provider-verified
  })

  it('rejects an obviously wrong reference before sending it', async () => {
    mockRoutes({
      'GET /api/orders/12/payments': orderPayments({ summary: { ...NONE, status: 'pending', pending_payment_id: 7 } }),
      'GET /api/payments/config': paymentConfig({ vpa: 'patelstore@okhdfcbank' }),
      'GET /api/payments/7': upiPending(),
    })
    renderIt()
    await userEvent.click(await screen.findByRole('checkbox'))
    await userEvent.type(screen.getByLabelText(/UPI reference/), 'ab')
    expect(screen.getByText(/4 to 40 letters or digits/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm payment received' })).toBeDisabled()
  })
})

describe('PaymentDialog: Razorpay Checkout', () => {
  class FakeRazorpay {
    static last: FakeRazorpay | null = null
    options: Record<string, unknown>
    handlers: Record<string, (r: unknown) => void> = {}
    constructor(options: Record<string, unknown>) { this.options = options; FakeRazorpay.last = this }
    on(ev: string, cb: (r: unknown) => void) { this.handlers[ev] = cb }
    open() { /* the real one shows a window; the test calls the handlers by hand */ }
  }
  const rzPending = () => payment({
    id: 9, method: 'razorpay', provider: 'razorpay', provider_order_id: 'order_TEST1',
    checkout: { key_id: 'rzp_test_PLACEHOLDER01', provider_order_id: 'order_TEST1', amount_paise: 17200, currency: 'INR', name: 'Patel Kirana', description: 'Bill SW-261111-0012', mode: 'test' },
  })
  const setup = (verify: () => unknown) => {
    ;(window as unknown as { Razorpay: unknown }).Razorpay = FakeRazorpay
    return mockRoutes({
      'GET /api/orders/12/payments': orderPayments({ summary: { ...NONE, status: 'pending', pending_payment_id: 9 } }),
      'GET /api/payments/config': paymentConfig({ razorpay: true }),
      'GET /api/payments/9': rzPending(),
      'POST /api/payments/9/razorpay/verify': verify,
    })
  }

  it('opens Checkout with the public key and the server-made order only, and nothing secret', async () => {
    setup(() => rzPending())
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Open Razorpay Checkout' }))
    await waitFor(() => expect(FakeRazorpay.last).not.toBeNull())
    const o = FakeRazorpay.last!.options
    expect(o.key).toBe('rzp_test_PLACEHOLDER01')
    expect(o.order_id).toBe('order_TEST1')
    expect(o.amount).toBe(17200)
    expect(JSON.stringify(o)).not.toMatch(/secret/i)
    expect(screen.getByText(/No real money moves/)).toBeInTheDocument()
  })

  it('sends what Checkout returned to the server and shows paid only because the server says paid', async () => {
    const m = setup(() => payment({ ...rzPending(), checkout: undefined, status: 'paid', verified: true, verification: 'signature', verification_label: 'Verified with Razorpay', provider_payment_id: 'pay_TEST1', paid_at: '2026-11-11T13:09:00' }))
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Open Razorpay Checkout' }))
    await waitFor(() => expect(FakeRazorpay.last).not.toBeNull())
;(FakeRazorpay.last!.options.handler as (r: unknown) => void)({ razorpay_payment_id: 'pay_TEST1', razorpay_order_id: 'order_TEST1', razorpay_signature: 'sig' })
    expect(await screen.findByText('Payment received')).toBeInTheDocument()
    expect(body(m, 'POST /api/payments/9/razorpay/verify')).toEqual({ razorpay_order_id: 'order_TEST1', razorpay_payment_id: 'pay_TEST1', razorpay_signature: 'sig' })
    expect(screen.getByText('pay_TEST1')).toBeInTheDocument()
  })

  it('does not call the payment paid when Checkout says success but the server does not agree yet', async () => {
    setup(() => payment({ ...rzPending(), notice: 'Razorpay has not confirmed this payment yet.' }))
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Open Razorpay Checkout' }))
    await waitFor(() => expect(FakeRazorpay.last).not.toBeNull())
;(FakeRazorpay.last!.options.handler as (r: unknown) => void)({ razorpay_payment_id: 'pay_X', razorpay_order_id: 'order_TEST1', razorpay_signature: 'sig' })
    expect(await screen.findByText('Razorpay has not confirmed this payment yet.')).toBeInTheDocument()
    expect(screen.queryByText('Payment received')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Checkout again' })).toBeInTheDocument()
  })

  it('shows the server refusal of a bad signature and still does not show a payment', async () => {
    setup(() => json({ detail: { code: 'BAD_SIGNATURE', message: 'The payment confirmation could not be verified. Nothing was recorded as paid.' } }, 400))
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Open Razorpay Checkout' }))
    await waitFor(() => expect(FakeRazorpay.last).not.toBeNull())
;(FakeRazorpay.last!.options.handler as (r: unknown) => void)({ razorpay_payment_id: 'pay_X', razorpay_order_id: 'order_TEST1', razorpay_signature: 'forged' })
    expect(await screen.findByText(/Nothing was recorded as paid/)).toBeInTheDocument()
    expect(screen.queryByText('Payment received')).not.toBeInTheDocument()
  })

  it('reports a declined payment and a closed window without marking anything', async () => {
    setup(() => rzPending())
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Open Razorpay Checkout' }))
    await waitFor(() => expect(FakeRazorpay.last).not.toBeNull())
    FakeRazorpay.last!.handlers['payment.failed']({ error: { description: 'Your bank declined the payment.' } })
    expect(await screen.findByText(/Your bank declined the payment\./)).toBeInTheDocument()
    expect(screen.queryByText('Payment received')).not.toBeInTheDocument()
    ;(FakeRazorpay.last!.options.modal as { ondismiss: () => void }).ondismiss()
    expect(screen.getByRole('button', { name: 'Open Checkout again' })).toBeInTheDocument()
  })

  it('shows a clear message when the Checkout script cannot be loaded', async () => {
    setup(() => rzPending())
    delete (window as { Razorpay?: unknown }).Razorpay
    const origAppend = document.head.appendChild.bind(document.head)
    vi.spyOn(document.head, 'appendChild').mockImplementation(((el: Node) => { if ((el as HTMLScriptElement).src?.includes('checkout.razorpay.com')) { setTimeout(() => (el as HTMLScriptElement).onerror?.(new Event('error')), 0); return el } return origAppend(el) }) as typeof document.head.appendChild)
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Open Razorpay Checkout' }))
    expect(await screen.findByText(/Could not load Razorpay Checkout\. Check the internet connection\. Nothing was charged\./)).toBeInTheDocument()
  })
})

describe('PaymentDialog: Razorpay QR (confirms itself)', () => {
  it('says it is waiting for Razorpay and gives a Check status button that asks the server', async () => {
    const qr = payment({ method: 'upi', provider: 'razorpay_qr', upi: { mode: 'provider', verified_by_provider: true, uri: null, qr_image_url: 'https://rzp.example/q.png', payee: null, amount_paise: 17200, reference: 'PAY-1', order_code: 'SW-1', instructions: 'Scan.' } })
    const m = mockRoutes({
      'GET /api/orders/12/payments': orderPayments({ summary: { ...NONE, status: 'pending', pending_payment_id: 7 } }),
      'GET /api/payments/config': paymentConfig({ razorpay: true, qr: true }),
      'GET /api/payments/7': qr,
      'POST /api/payments/7/refresh': () => ({ ...qr, notice: undefined }),
    })
    renderIt()
    expect(await screen.findByText(/Waiting for Razorpay to confirm the payment/)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()   // nobody confirms this one by hand
    await userEvent.click(screen.getByRole('button', { name: 'Check status' }))
    await waitFor(() => expect(m.calls.some((c) => c.url === '/api/payments/7/refresh' && c.method === 'POST')).toBe(true))
    expect(screen.queryByText('Payment received')).not.toBeInTheDocument()
  })
})
