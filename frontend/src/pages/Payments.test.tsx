import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Payments from './Payments'
import { DataScopeProvider } from '../lib/scope'
import { ToastProvider } from '../components/Toast'
import { STAFF_USER, TestAuth } from '../test/auth'
import { mockRoutes, payment } from '../test/fixtures'
import type { Payment, PaymentList } from '../types'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })
const Where = () => { const l = useLocation(); return <div data-testid="where">{l.pathname}{l.search}</div> }
const renderIt = (path = '/payments', user?: typeof STAFF_USER) => render(
  <TestAuth user={user}><MemoryRouter initialEntries={[path]}><DataScopeProvider><ToastProvider>
    <Routes><Route path="/payments" element={<Payments />} /><Route path="/payments/:id" element={<Where />} /><Route path="/payment-analytics" element={<Where />} /></Routes>
  </ToastProvider></DataScopeProvider></MemoryRouter></TestAuth>,
)
const list = (items: Payment[], over: Partial<PaymentList> = {}): PaymentList => ({
  total: items.length, limit: 20, offset: 0, counts: { all: items.length, pending: 1, paid: 2, failed: 0, cancelled: 0, partially_refunded: 0, refunded: 0 }, items, ...over,
})
const PAID_CASH = payment({ id: 1, code: 'PAY-261111-0001', status: 'paid', method: 'cash', verified: true, order_code: 'SW-0001', paid_at: '2026-11-11T13:00:00' })
const MANUAL_UPI = payment({ id: 2, code: 'PAY-261111-0002', status: 'paid', method: 'upi', provider: 'manual', verified: false, verification: 'manual', verification_label: 'Confirmed by hand. Not verified by a payment provider.', order_code: 'SW-0002', customer_name: 'Meena Shah', paid_at: '2026-11-11T13:05:00', amount_paise: 4500 })
const WAITING = payment({ id: 3, code: 'PAY-261111-0003', status: 'pending', method: 'razorpay', provider: 'razorpay', order_code: 'SW-0003', stale: true })
const FLAGGED = payment({ id: 4, code: 'PAY-261111-0004', status: 'paid', method: 'razorpay', provider: 'razorpay', verified: true, attention: 'amount_mismatch', refunded_paise: 5000, order_code: 'SW-0004' })

describe('Payments history', () => {
  it('lists payments with way paid, status and server counts, and marks a hand-confirmed UPI payment as unverified', async () => {
    mockRoutes({ 'GET /api/payments': list([PAID_CASH, MANUAL_UPI, WAITING, FLAGGED]) })
    renderIt()
    const cash = await screen.findByRole('row', { name: 'Open payment PAY-261111-0001' })
    expect(within(cash).getByText('Cash')).toBeInTheDocument()
    expect(within(cash).getByText('Paid')).toBeInTheDocument()
    expect(within(cash).getByText('₹172')).toBeInTheDocument()
    const upi = screen.getByRole('row', { name: 'Open payment PAY-261111-0002' })
    expect(within(upi).getByText('Unverified')).toBeInTheDocument()
    const waiting = screen.getByRole('row', { name: 'Open payment PAY-261111-0003' })
    expect(within(waiting).getByText('Waiting for payment')).toBeInTheDocument()
    expect(within(waiting).getByText('Slow')).toBeInTheDocument()
    const flagged = screen.getByRole('row', { name: 'Open payment PAY-261111-0004' })
    expect(within(flagged).getByText('Amount differs')).toBeInTheDocument()
    expect(within(flagged).getByText('₹50 refunded')).toBeInTheDocument()
    const seg = screen.getByRole('group', { name: 'Payment status' })
    expect(within(seg).getByRole('button', { name: /Paid\s*2/ })).toBeInTheDocument()
  })

  it('sends the filters to the server and keeps them in the address', async () => {
    const m = mockRoutes({ 'GET /api/payments': list([PAID_CASH]) })
    renderIt()
    await screen.findByRole('row', { name: 'Open payment PAY-261111-0001' })
    await userEvent.click(screen.getByRole('button', { name: /^Failed/ }))
    await waitFor(() => expect(m.urls().some((u) => u.includes('status=failed'))).toBe(true))
    await userEvent.selectOptions(screen.getByLabelText('Way paid'), 'upi')
    await waitFor(() => expect(m.urls().some((u) => u.includes('method=upi') && u.includes('status=failed'))).toBe(true))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Needs a look' }))
    await waitFor(() => expect(m.urls().some((u) => u.includes('attention=true'))).toBe(true))
    expect(m.urls().every((u) => u.includes('limit=20'))).toBe(true)
  })

  it('debounces the search into one request', async () => {
    const m = mockRoutes({ 'GET /api/payments': list([PAID_CASH]) })
    renderIt()
    await screen.findByRole('row', { name: 'Open payment PAY-261111-0001' })
    const before = m.calls.length
    await userEvent.type(screen.getByRole('searchbox', { name: /Search payments/ }), 'meena')
    await waitFor(() => expect(m.urls().some((u) => u.includes('q=meena'))).toBe(true))
    expect(m.calls.length - before).toBe(1)
  })

  it('opens the details when a row is clicked', async () => {
    mockRoutes({ 'GET /api/payments': list([PAID_CASH]) })
    renderIt()
    await userEvent.click(await screen.findByRole('row', { name: 'Open payment PAY-261111-0001' }))
    expect(await screen.findByTestId('where')).toHaveTextContent('/payments/1')
  })

  it('explains an empty history without calling orders "unpaid"', async () => {
    mockRoutes({ 'GET /api/payments': list([], { counts: { all: 0, pending: 0, paid: 0, failed: 0, cancelled: 0, partially_refunded: 0, refunded: 0 } }) })
    renderIt()
    expect(await screen.findByText('No payments recorded yet')).toBeInTheDocument()
    expect(screen.getByText(/paid before payments were tracked here simply have no payment recorded/)).toBeInTheDocument()
    expect(screen.queryByText(/unpaid/i)).not.toBeInTheDocument()
  })

  it('offers to clear filters when nothing matches', async () => {
    mockRoutes({ 'GET /api/payments': list([]) })
    renderIt('/payments?q=zzz')
    expect(await screen.findByText('No payments match these filters')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument()
  })

  it('shows the link to payment analytics to the owner only', async () => {
    mockRoutes({ 'GET /api/payments': list([PAID_CASH]) })
    const { unmount } = renderIt()
    expect(await screen.findByRole('link', { name: 'Payment analytics' })).toBeInTheDocument()
    unmount()
    mockRoutes({ 'GET /api/payments': list([PAID_CASH]) })
    renderIt('/payments', STAFF_USER)
    await screen.findByRole('row', { name: 'Open payment PAY-261111-0001' })
    expect(screen.queryByRole('link', { name: 'Payment analytics' })).not.toBeInTheDocument()
  })

  it('warns about a date range that runs backwards', async () => {
    mockRoutes({ 'GET /api/payments': list([PAID_CASH]) })
    renderIt('/payments?since=2026-11-10&until=2026-11-01')
    expect(await screen.findByText('To is before From.')).toBeInTheDocument()
  })
})
