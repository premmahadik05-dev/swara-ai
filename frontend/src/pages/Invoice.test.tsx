import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Invoice from './Invoice'
import { invoice, json, mockRoutes } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); document.body.classList.remove('printing-invoice') })
const renderIt = () => render(<MemoryRouter initialEntries={['/invoices/12']}><Routes><Route path="/invoices/:orderId" element={<Invoice />} /></Routes></MemoryRouter>)

describe('Invoice', () => {
  it('shows the number, shop, customer, items, totals and the payment that was recorded', async () => {
    mockRoutes({ 'GET /api/orders/12/invoice': invoice() })
    renderIt()
    const doc = (await screen.findAllByRole('article', { name: 'Invoice INV-2026-000001' }))[0]
    expect(within(doc).getByText('Patel Kirana (demo)')).toBeInTheDocument()
    expect(within(doc).getByText('Walk-in customer')).toBeInTheDocument()
    expect(within(doc).getByText('Rice')).toBeInTheDocument()
    expect(within(doc).getAllByText('₹172').length).toBeGreaterThan(0)
    expect(within(doc).getByText('Paid', { selector: 'dd' })).toBeInTheDocument()
    expect(within(doc).getByText('PAY-261111-0007')).toBeInTheDocument()
    // a cash payment is recorded by a person; it is not "unverified", and the page adds nothing to what the server's label says
    expect(within(doc).getByText('Cash recorded by Test Owner')).toBeInTheDocument()
    expect(doc.textContent ?? '').not.toMatch(/not verified/i)
  })

  it('says once, in the server\'s words, that a hand-confirmed UPI payment was not verified by a provider', async () => {
    const label = 'Confirmed by Test Owner. Not verified by a payment provider'
    mockRoutes({ 'GET /api/orders/12/invoice': invoice({ payment: { status: 'paid', method: 'upi', provider: 'manual', reference: 'PAY-261111-0008', provider_payment_id: null, paid_at: '2026-11-11T13:04:00', amount_paise: 17200, refunded_paise: 0, verified: false, label } }) })
    renderIt()
    const doc = (await screen.findAllByRole('article', { name: 'Invoice INV-2026-000001' }))[0]
    expect(within(doc).getByText(label)).toBeInTheDocument()
    expect((doc.textContent ?? '').match(/not verified/gi)).toHaveLength(1)
  })

  it('makes no tax claim: it repeats the server note and never says GST invoice without "not"', async () => {
    mockRoutes({ 'GET /api/orders/12/invoice': invoice() })
    const { container } = renderIt()
    await screen.findAllByRole('article')
    expect(screen.getAllByText(/is not a GST tax invoice/).length).toBeGreaterThan(0)
    const text = container.textContent ?? ''
    for (const m of text.matchAll(/GST/g)) expect(text.slice(Math.max(0, m.index! - 12), m.index! + 20)).toMatch(/not a GST/)
    expect(text).not.toMatch(/GSTIN|CGST|SGST|IGST/)
  })

  it('says plainly when no payment is recorded, and flags a cancelled or demo order', async () => {
    mockRoutes({ 'GET /api/orders/12/invoice': invoice({ payment: null, order_status: 'cancelled', is_synthetic: true }) })
    renderIt()
    await screen.findAllByRole('article')
    expect(screen.getAllByText('No payment is recorded for this order in SWARA AI.').length).toBeGreaterThan(0)
    expect(screen.getAllByText('This order was cancelled.').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Generated demo data. This is not a real sale.').length).toBeGreaterThan(0)
  })

  it('shows a discount line only when there is one', async () => {
    mockRoutes({ 'GET /api/orders/12/invoice': invoice({ discount_paise: 1200, subtotal_paise: 18400, total_paise: 17200 }) })
    renderIt()
    await screen.findAllByRole('article')
    expect(screen.getAllByText('Discount').length).toBeGreaterThan(0)
    expect(screen.getAllByText('-₹12').length).toBeGreaterThan(0)
  })

  it('prints only the invoice: marks the page for printing, names the file after the invoice number, then puts both back', async () => {
    mockRoutes({ 'GET /api/orders/12/invoice': invoice() })
    document.title = 'Invoice · SWARA AI'
    let during = { cls: false, title: '' }
    vi.stubGlobal('print', () => { during = { cls: document.body.classList.contains('printing-invoice'), title: document.title }; window.dispatchEvent(new Event('afterprint')) })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: /Print or save as PDF/ }))
    expect(during).toEqual({ cls: true, title: 'INV-2026-000001' })
    await waitFor(() => expect(document.body.classList.contains('printing-invoice')).toBe(false))
    expect(document.title).toBe('Invoice · SWARA AI')
  })

  it('shows the server message when the invoice cannot be made', async () => {
    mockRoutes({ 'GET /api/orders/12/invoice': () => json({ detail: { code: 'NOT_FOUND', message: 'No such order.' } }, 404) })
    renderIt()
    expect(await screen.findByText(/No such order\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Print or save as PDF/ })).toBeDisabled()
  })
})
