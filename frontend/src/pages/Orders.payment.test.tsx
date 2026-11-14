import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Orders from './Orders'
import { ToastProvider } from '../components/Toast'
import { STAFF_USER, TestAuth } from '../test/auth'
import { DataScopeProvider } from '../lib/scope'
import { mockRoutes, order, orderList, paymentConfig } from '../test/fixtures'
import type { OrderPaymentSummary } from '../types'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear() })
const renderIt = (path = '/orders', user?: typeof STAFF_USER) => render(
  <TestAuth user={user}><MemoryRouter initialEntries={[path]}><DataScopeProvider><ToastProvider><Orders /></ToastProvider></DataScopeProvider></MemoryRouter></TestAuth>,
)
const NONE: OrderPaymentSummary = { status: 'none', paid_paise: 0, refunded_paise: 0, method: null, payment_id: null, pending_payment_id: null }
const PAID: OrderPaymentSummary = { status: 'paid', paid_paise: 17200, refunded_paise: 0, method: 'cash', payment_id: 7, pending_payment_id: null }

describe('Orders and payments', () => {
  it('shows "Not recorded" for an order that never had a payment, including old responses with no payment field at all', async () => {
    mockRoutes({ 'GET /api/orders': orderList([order(), order({ id: 2, code: 'SW-0002', payment: NONE })]) })
    renderIt()
    for (const code of ['SW-0001', 'SW-0002']) expect(within(await screen.findByRole('row', { name: `Open ${code}` })).getByText('Not recorded')).toBeInTheDocument()
    expect(screen.queryByText(/unpaid/i)).not.toBeInTheDocument()
  })

  it('shows the payment status on each row', async () => {
    mockRoutes({ 'GET /api/orders': orderList([order({ payment: PAID }), order({ id: 2, code: 'SW-0002', payment: { ...NONE, status: 'pending', pending_payment_id: 3 } })]) })
    renderIt()
    expect(within(await screen.findByRole('row', { name: 'Open SW-0001' })).getByText('Paid')).toBeInTheDocument()
    expect(within(screen.getByRole('row', { name: 'Open SW-0002' })).getByText('Waiting for payment')).toBeInTheDocument()
  })

  it('offers Take payment in the order drawer when nothing is recorded, and opens the payment window', async () => {
    mockRoutes({
      'GET /api/orders': orderList(), 'GET /api/orders/1': order({ payment: NONE }), 'GET /api/health': { store_name: 'Patel Kirana' },
      'GET /api/orders/1/payments': { order_id: 1, order_code: 'SW-0001', total_paise: 17200, summary: NONE, items: [] },
      'GET /api/payments/config': paymentConfig(),
    })
    renderIt('/orders?open=1')
    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByText(/No payment is recorded in SWARA AI for this order/)).toBeInTheDocument()
    await userEvent.click(within(drawer).getByRole('button', { name: 'Take payment' }))
    const pay = (await screen.findAllByRole('dialog')).find((d) => within(d).queryByRole('radiogroup'))
    expect(pay).toBeTruthy()
  })

  it('says "Continue payment" while one is waiting', async () => {
    mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/1': order({ payment: { ...NONE, status: 'pending', pending_payment_id: 3 } }), 'GET /api/health': { store_name: 'x' } })
    renderIt('/orders?open=1')
    expect(await screen.findByRole('button', { name: 'Continue payment' })).toBeInTheDocument()
  })

  it('shows a paid order with its receipt and details, and no Take payment button', async () => {
    mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/1': order({ payment: PAID }), 'GET /api/health': { store_name: 'x' } })
    renderIt('/orders?open=1')
    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByText('₹172 collected.')).toBeInTheDocument()
    expect(within(drawer).getByRole('link', { name: 'Receipt' })).toHaveAttribute('href', '/invoices/1')
    expect(within(drawer).getByRole('link', { name: 'Details' })).toHaveAttribute('href', '/payments/7')
    expect(within(drawer).queryByRole('button', { name: 'Take payment' })).not.toBeInTheDocument()
  })

  it('keeps Cancel order off while money collected has not been refunded, and says why', async () => {
    mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/1': order({ payment: PAID }), 'GET /api/health': { store_name: 'x' } })
    renderIt('/orders?open=1')
    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByRole('button', { name: 'Cancel order' })).toBeDisabled()
    expect(within(drawer).getByText(/Refund it from the payment page before cancelling/)).toBeInTheDocument()
  })

  it('lets the order be cancelled again once the money was refunded', async () => {
    mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/1': order({ payment: { ...PAID, status: 'refunded', refunded_paise: 17200 } }), 'GET /api/health': { store_name: 'x' } })
    renderIt('/orders?open=1')
    expect(await screen.findByRole('button', { name: 'Cancel order' })).toBeEnabled()
  })

  it('tells staff that only the owner can refund', async () => {
    mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/1': order({ payment: PAID }), 'GET /api/health': { store_name: 'x' } })
    renderIt('/orders?open=1', STAFF_USER)
    expect(await screen.findByText(/Only the shop owner can refund it/)).toBeInTheDocument()
  })

  it('warns that a waiting payment is cancelled together with the order', async () => {
    mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/1': order({ payment: { ...NONE, status: 'pending', pending_payment_id: 3 } }), 'GET /api/health': { store_name: 'x' } })
    renderIt('/orders?open=1')
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel order' }))
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('The payment that is still waiting is cancelled too.')
  })
})
