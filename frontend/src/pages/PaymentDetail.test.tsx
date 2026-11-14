import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PaymentDetail from './PaymentDetail'
import { ToastProvider } from '../components/Toast'
import { STAFF_USER, TestAuth } from '../test/auth'
import { json, mockRoutes, payment } from '../test/fixtures'
import type { PaymentDetail as Detail } from '../types'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })
const renderIt = (user?: typeof STAFF_USER) => render(
  <TestAuth user={user}><MemoryRouter initialEntries={['/payments/7']}><ToastProvider>
    <Routes><Route path="/payments/:id" element={<PaymentDetail />} /></Routes>
  </ToastProvider></MemoryRouter></TestAuth>,
)
const PAID = (over: Partial<Detail> = {}) => payment({
  status: 'paid', method: 'razorpay', provider: 'razorpay', verified: true, verification: 'webhook', verification_label: 'Confirmed by Razorpay', provider_payment_id: 'pay_TEST1', provider_order_id: 'order_TEST1',
  paid_at: '2026-11-11T13:04:00', confirmed_by: null, refundable_paise: 17200,
  events: [
    { id: 1, source: 'system', type: 'created', message: 'Payment started', status_before: null, status_after: 'pending', signature_ok: null, actor: 'Test Owner', created_at: '2026-11-11T13:00:00' },
    { id: 2, source: 'webhook', type: 'payment.captured', message: 'Razorpay reports the payment as captured', status_before: 'pending', status_after: 'paid', signature_ok: true, actor: null, created_at: '2026-11-11T13:04:00' },
  ], ...over,
})

describe('PaymentDetail', () => {
  it('shows the amount, how it was checked, the Razorpay references and the activity in order', async () => {
    mockRoutes({ 'GET /api/payments/7': PAID() })
    renderIt()
    expect(await screen.findByRole('heading', { name: 'PAY-261111-0007' })).toBeInTheDocument()
    expect(screen.getByText('Confirmed by Razorpay')).toBeInTheDocument()
    expect(screen.getByText('pay_TEST1')).toBeInTheDocument()
    expect(screen.getByText('order_TEST1')).toBeInTheDocument()
    expect(screen.getByText('Payment started')).toBeInTheDocument()
    expect(screen.getByText(/signature checked/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Receipt/ })).toHaveAttribute('href', '/invoices/12')
  })

  it('says a hand-confirmed UPI payment is unverified', async () => {
    mockRoutes({ 'GET /api/payments/7': PAID({ method: 'upi', provider: 'manual', verified: false, verification: 'manual', verification_label: 'Confirmed by hand by Test Owner. Not verified by a payment provider.', reference_note: 'UTR412345', provider_payment_id: null, provider_order_id: null }) })
    renderIt()
    expect(await screen.findByText('Unverified')).toBeInTheDocument()
    expect(screen.getByText('UTR412345')).toBeInTheDocument()
  })

  it('does not call cash "unverified": a person recorded it, and no provider was ever involved', async () => {
    mockRoutes({ 'GET /api/payments/7': PAID({ method: 'cash', verified: false, verification: 'cash', verification_label: 'Cash recorded by Test Owner' }) })
    renderIt()
    expect(await screen.findByText('Cash recorded by Test Owner')).toBeInTheDocument()
    expect(screen.queryByText('Unverified')).not.toBeInTheDocument()
  })

  it('explains a flag the server raised', async () => {
    mockRoutes({ 'GET /api/payments/7': PAID({ attention: 'amount_mismatch', status: 'pending', verified: false, paid_at: null, refundable_paise: 0 }) })
    renderIt()
    expect(await screen.findByText(/did not match|does not match the bill/i)).toBeInTheDocument()
    expect(screen.getAllByText('Amount differs').length).toBeGreaterThan(0)
  })

  it('shows why a payment failed', async () => {
    mockRoutes({ 'GET /api/payments/7': payment({ status: 'failed', failure_reason: 'Your bank declined the payment.', failure_code: 'BAD_REQUEST_ERROR', refundable_paise: 0 }) })
    renderIt()
    expect(await screen.findByText(/Your bank declined the payment\./)).toBeInTheDocument()
  })

  it('lets the owner refund part of it, asks first, and sends a request key', async () => {
    let detail = PAID()
    const m = mockRoutes({
      'GET /api/payments/7': () => detail,
      'POST /api/payments/7/refunds': () => { detail = PAID({ status: 'partially_refunded', refunded_paise: 5000, refundable_paise: 12200, refunds: [{ id: 1, code: 'REF-261111-0001', payment_id: 7, kind: 'provider', amount_paise: 5000, status: 'pending', reason: 'Item returned', provider_refund_id: 'rfnd_1', speed_processed: null, failure_reason: null, label: 'Razorpay refund', initiated_by: 'Test Owner', created_at: '2026-11-11T13:10:00', processed_at: null }] }); return json({ ...detail.refunds[0], payment: detail }, 201) },
    })
    renderIt()
    const amount = await screen.findByLabelText('Refund amount (rupees)')
    await userEvent.clear(amount)
    await userEvent.type(amount, '50')
    await userEvent.type(screen.getByLabelText('Reason'), 'Item returned')
    await userEvent.click(screen.getByRole('button', { name: 'Refund' }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveTextContent(/until Razorpay confirms it/)
    expect(m.calls.some((c) => c.method === 'POST')).toBe(false)   // nothing is sent before the person confirms
    await userEvent.click(within(ask).getByRole('button', { name: 'Refund' }))
    expect(await screen.findByText('REF-261111-0001')).toBeInTheDocument()
    const sent = JSON.parse(m.calls.find((c) => c.method === 'POST')!.body!)
    expect(sent).toMatchObject({ amount_paise: 5000, reason: 'Item returned' })
    expect(sent.idempotency_key).toMatch(/.{8,}/)
    expect(screen.getByText('Waiting for Razorpay')).toBeInTheDocument()   // not "Refunded": the provider has not confirmed it
  })

  it('will not refund more than what is left, or without a reason', async () => {
    mockRoutes({ 'GET /api/payments/7': PAID({ refundable_paise: 12200 }) })
    renderIt()
    const amount = await screen.findByLabelText('Refund amount (rupees)')
    await userEvent.clear(amount)
    await userEvent.type(amount, '500')
    expect(screen.getByText('The most that can be refunded is ₹122.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refund' })).toBeDisabled()
    await userEvent.clear(amount)
    await userEvent.type(amount, '10')
    expect(screen.getByRole('button', { name: 'Refund' })).toBeDisabled()   // no reason yet
  })

  it('shows staff the refunds but no refund form', async () => {
    mockRoutes({ 'GET /api/payments/7': PAID() })
    renderIt(STAFF_USER)
    await screen.findByRole('heading', { name: 'PAY-261111-0007' })
    expect(screen.queryByLabelText('Refund amount (rupees)')).not.toBeInTheDocument()
    expect(screen.getByText('Only the shop owner can refund a payment.')).toBeInTheDocument()
  })

  it('checks a waiting refund with Razorpay and reports what it said', async () => {
    const refund = { id: 1, code: 'REF-261111-0001', payment_id: 7, kind: 'provider' as const, amount_paise: 5000, status: 'pending' as const, reason: 'Item returned', provider_refund_id: 'rfnd_1', speed_processed: null, failure_reason: null, label: 'Razorpay refund', initiated_by: 'Test Owner', created_at: '2026-11-11T13:10:00', processed_at: null }
    const m = mockRoutes({
      'GET /api/payments/7': PAID({ status: 'partially_refunded', refunded_paise: 0, refundable_paise: 12200, refunds: [refund] }),
      'POST /api/refunds/1/refresh': () => ({ ...refund, notice: 'Razorpay has not confirmed this refund yet.' }),
    })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Check status' }))
    expect(await screen.findByText('Razorpay has not confirmed this refund yet.')).toBeInTheDocument()
    expect(m.calls.some((c) => c.url === '/api/refunds/1/refresh')).toBe(true)
  })

  it('reaches Razorpay only on request: a Check with Razorpay button for provider payments', async () => {
    const m = mockRoutes({ 'GET /api/payments/7': PAID(), 'POST /api/payments/7/refresh': () => ({ ...PAID(), notice: 'No change. Razorpay has nothing new.' }) })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Check with Razorpay' }))
    await waitFor(() => expect(m.calls.some((c) => c.url === '/api/payments/7/refresh')).toBe(true))
  })

  it('does not offer Check with Razorpay for cash', async () => {
    mockRoutes({ 'GET /api/payments/7': payment({ status: 'paid', method: 'cash', provider: 'none', verified: true, verification: 'cash', verification_label: 'Cash recorded' , paid_at: '2026-11-11T13:04:00', amount_received_paise: 20000, change_paise: 2800, refundable_paise: 17200 }) })
    renderIt()
    await screen.findByRole('heading', { name: 'PAY-261111-0007' })
    expect(screen.queryByRole('button', { name: 'Check with Razorpay' })).not.toBeInTheDocument()
    expect(screen.getByText(/change ₹28/)).toBeInTheDocument()
  })

  it('shows the server message when the payment is not found', async () => {
    mockRoutes({ 'GET /api/payments/7': () => json({ detail: { code: 'NOT_FOUND', message: 'No such payment.' } }, 404) })
    renderIt()
    expect(await screen.findByText(/No such payment\./)).toBeInTheDocument()
  })
})
