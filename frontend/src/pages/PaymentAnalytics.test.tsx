import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PaymentAnalytics from './PaymentAnalytics'
import { DataScopeProvider } from '../lib/scope'
import { STAFF_USER, TestAuth } from '../test/auth'
import { mockRoutes, paymentAnalytics } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })
const renderIt = (user?: typeof STAFF_USER) => render(<TestAuth user={user}><MemoryRouter><DataScopeProvider><PaymentAnalytics /></DataScopeProvider></MemoryRouter></TestAuth>)

describe('PaymentAnalytics', () => {
  it('shows totals added up from payment records, with manual UPI called out as not verified', async () => {
    localStorage.setItem('swara.includeDemo', '0')
    const m = mockRoutes({ 'GET /api/payments/analytics': paymentAnalytics() })
    renderIt()
    const collected = await screen.findByRole('group', { name: 'Collected' })
    expect(within(collected).getByText('₹900')).toBeInTheDocument()
    expect(within(collected).getByText(/₹50 refunded, ₹850 kept/)).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Cash' })).getByText('₹500')).toBeInTheDocument()
    const upi = screen.getByRole('group', { name: 'UPI' })
    expect(within(upi).getByText('₹300')).toBeInTheDocument()
    expect(within(upi).getByText(/confirmed by hand, not verified by a provider/)).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Razorpay' })).getByText('₹100')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Waiting' })).getByText('₹120')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Failed' })).getByText('2 payments')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Refunds' })).getByText(/1 refund \(₹20\) waiting for Razorpay/)).toBeInTheDocument()
    expect(screen.getByText('Only payments you recorded')).toBeInTheDocument()
    expect(m.urls()[0]).toContain('days=30')
    expect(m.urls()[0]).toContain('include_synthetic=false')
    expect(screen.getByRole('link', { name: 'Show them' })).toHaveAttribute('href', '/payments?attention=1')
  })

  it('offers the numbers as a table too, for the trend and for the way-paid split', async () => {
    mockRoutes({ 'GET /api/payments/analytics': paymentAnalytics() })
    renderIt()
    await screen.findByRole('group', { name: 'Collected' })
    const trend = screen.getByRole('region', { name: 'Collected over time' })
    await userEvent.click(within(trend).getByRole('button', { name: 'Table' }))
    const table = within(trend).getByRole('table')
    expect(within(table).getAllByText('₹500').length).toBeGreaterThan(0)
    expect(within(table).getByText('9 Nov')).toBeInTheDocument()
    await userEvent.click(within(trend).getByRole('button', { name: 'Monthly' }))
    expect(within(within(trend).getByRole('table')).getByText('Nov 2026')).toBeInTheDocument()
    const split = screen.getByRole('region', { name: 'Way paid' })
    await userEvent.click(within(split).getByRole('button', { name: 'Table' }))
    expect(within(split).getByText('56%')).toBeInTheDocument()
  })

  it('asks the server again when the period or the demo scope changes', async () => {
    const m = mockRoutes({ 'GET /api/payments/analytics': paymentAnalytics() })
    renderIt()
    await screen.findByRole('group', { name: 'Collected' })
    await userEvent.click(screen.getByRole('button', { name: 'Last 90 days' }))
    await waitFor(() => expect(m.urls().some((u) => u.includes('days=90'))).toBe(true))
  })

  it('says so when there is nothing in the period', async () => {
    const z = paymentAnalytics()
    mockRoutes({ 'GET /api/payments/analytics': paymentAnalytics({ kpis: { ...z.kpis, paid_count: 0, pending_count: 0, failed_count: 0, refund_count: 0, collected_paise: 0, cash_paise: 0, upi_paise: 0, razorpay_paise: 0, refunds_paise: 0, net_paise: 0, average_paise: 0, pending_paise: 0, failed_paise: 0, upi_manual_paise: 0, refunds_waiting_count: 0, refunds_waiting_paise: 0, needs_attention: 0 } }) })
    renderIt()
    expect(await screen.findByText('No payments in this period')).toBeInTheDocument()
  })

  it('is for the owner only: staff are told so and nothing is requested', async () => {
    const m = mockRoutes({})
    renderIt(STAFF_USER)
    expect(await screen.findByText('Only the shop owner can open this page')).toBeInTheDocument()
    expect(m.calls).toHaveLength(0)
  })
})
