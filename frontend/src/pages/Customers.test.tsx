import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Customers from './Customers'
import { ToastProvider } from '../components/Toast'
import { STAFF_USER, TestAuth } from '../test/auth'
import { DataScopeProvider } from '../lib/scope'
import { captureDownloads, csvResponse, customer, json, mockRoutes, orderList } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })
const list = (items = [customer(), customer({ id: 6, name: 'Raj Shah', is_synthetic: false, orders: 0, spent_paise: 0, avg_basket_paise: 0, last_order_at: null, language: '' })]) => ({ total: items.length, page: 1, page_size: 20, items })
const detail = (over = {}) => ({ ...customer(), top_products: [{ product_id: 1, name: 'Rice', unit: 'kg', qty: 24, revenue_paise: 144000 }], language_mix: [{ language: 'gu', orders: 9 }, { language: 'hi', orders: 3 }], ...over })
const renderIt = (path = '/customers', user?: typeof STAFF_USER) => render(<TestAuth user={user}><MemoryRouter initialEntries={[path]}><DataScopeProvider><ToastProvider><Customers /></ToastProvider></DataScopeProvider></MemoryRouter></TestAuth>)

describe('Customers', () => {
  it('lists customers, marks demo ones, and does not invent figures for a customer with no orders', async () => {
    localStorage.setItem('swara.includeDemo', '1')   // these tests are about the demo-on state; the default for a shop is decided by its data (see shell.test)
    mockRoutes({ 'GET /api/customers': list() })
    renderIt()
    const meena = await screen.findByRole('row', { name: 'Open Meena Patel' })
    expect(within(meena).getByText('Demo')).toBeInTheDocument()
    expect(within(meena).getByText('₹5,400')).toBeInTheDocument()
    const raj = screen.getByRole('row', { name: 'Open Raj Shah' })
    expect(within(raj).queryByText('Demo')).toBeNull()
    expect(within(raj).getByText('Not set')).toBeInTheDocument()
    expect(within(raj).getByText('-')).toBeInTheDocument()                    // average bill: not ₹0
    expect(screen.getByText(/Demo Customer A–H/)).toBeInTheDocument()
  })

  it('hides the demo notice and passes the scope to the server when demo data is off', async () => {
    localStorage.setItem('swara.includeDemo', '0')
    const m = mockRoutes({ 'GET /api/customers': list([]) })
    renderIt()
    expect(await screen.findByText('No customers yet')).toBeInTheDocument()
    expect(screen.getByText(/Demo customers are hidden/)).toBeInTheDocument()
    expect(m.urls()[0]).toContain('include_synthetic=false')
    expect(screen.queryByText(/Demo Customer A–H/)).toBeNull()
  })

  it('opens a customer from the URL with their top products, language mix and recent orders', async () => {
    mockRoutes({ 'GET /api/customers': list(), 'GET /api/customers/5': detail(), 'GET /api/orders': orderList() })
    renderIt('/customers?open=5')
    const drawer = await screen.findByRole('dialog', { name: /Meena Patel/ })
    expect(await within(drawer).findByText('Rice')).toBeInTheDocument()
    expect(within(drawer).getByText('Gujarati · 9')).toBeInTheDocument()
    expect(within(drawer).getByText(/Demo customer\. The orders linked/)).toBeInTheDocument()
    expect(await within(drawer).findByRole('link', { name: 'SW-0001' })).toHaveAttribute('href', '/orders?open=1')
  })

  it('lets a customer\'s usual language be any of the eleven, or not set', async () => {
    mockRoutes({ 'GET /api/customers': list() })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'New customer' }))
    const dlg = await screen.findByRole('dialog', { name: 'New customer' })
    const options = within(dlg).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['Not set', 'Gujarati', 'Hindi', 'English', 'Hinglish', 'Marathi', 'Bengali', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Punjabi'])
  })

  it('validates the phone number before saving and posts a trimmed name', async () => {
    const m = mockRoutes({ 'GET /api/customers': list(), 'POST /api/customers': customer({ id: 9, name: 'Asha', is_synthetic: false }), 'GET /api/customers/9': detail({ id: 9, name: 'Asha' }), 'GET /api/orders': orderList([]) })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'New customer' }))
    const dlg = await screen.findByRole('dialog', { name: 'New customer' })
    const save = within(dlg).getByRole('button', { name: 'Add customer' })
    expect(save).toBeDisabled()
    await userEvent.type(within(dlg).getByLabelText('Name'), '  Asha ')
    await userEvent.type(within(dlg).getByLabelText(/Phone/), 'call me')
    expect(within(dlg).getByText('Use digits, spaces, + ( ) or -')).toBeInTheDocument()
    expect(save).toBeDisabled()
    await userEvent.clear(within(dlg).getByLabelText(/Phone/))
    await userEvent.type(within(dlg).getByLabelText(/Phone/), '98765 43210')
    await userEvent.click(save)
    await waitFor(() => expect(m.calls.some((c) => c.method === 'POST' && c.url === '/api/customers')).toBe(true))
    expect(JSON.parse(m.calls.find((c) => c.method === 'POST')!.body!)).toMatchObject({ name: 'Asha', phone: '98765 43210' })
  })

  it('keeps the form open and shows the reason when the server refuses', async () => {
    mockRoutes({ 'GET /api/customers': list(), 'POST /api/customers': json({ detail: { code: 'DUPLICATE', message: 'A customer with this phone already exists.' } }, 409) })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'New customer' }))
    const dlg = await screen.findByRole('dialog', { name: 'New customer' })
    await userEvent.type(within(dlg).getByLabelText('Name'), 'Asha')
    await userEvent.click(within(dlg).getByRole('button', { name: 'Add customer' }))
    expect(await within(dlg).findByText('A customer with this phone already exists.')).toBeInTheDocument()
  })

  it('closes the drawer with Escape and returns focus to the row that opened it', async () => {
    mockRoutes({ 'GET /api/customers': list(), 'GET /api/customers/5': detail(), 'GET /api/orders': orderList([]) })
    renderIt()
    const row = await screen.findByRole('row', { name: 'Open Meena Patel' })
    row.focus()
    await userEvent.keyboard('{Enter}')
    await screen.findByRole('dialog', { name: /Meena Patel/ })
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(row).toHaveFocus()
  })

  describe('staff and export', () => {
    it('shows staff the customers but no New customer, Edit or Export (a bulk file of phone numbers is the owner\'s)', async () => {
      mockRoutes({ 'GET /api/customers': list(), 'GET /api/customers/5': detail() })
      renderIt('/customers?open=5', STAFF_USER)
      expect(await screen.findByRole('row', { name: 'Open Meena Patel' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'New customer' })).toBeNull()
      expect(screen.queryByRole('button', { name: 'Export CSV' })).toBeNull()
      expect(screen.getByText(/Only the shop owner can add or edit them/)).toBeInTheDocument()
      const drawer = await screen.findByRole('dialog')
      await within(drawer).findByText('Rice')
      expect(within(drawer).queryByRole('button', { name: 'Edit details' })).toBeNull()
    })

    it('lets the owner export with the search, sort and demo scope that are on screen', async () => {
      const dl = captureDownloads()
      localStorage.setItem('swara.includeDemo', '0')
      const m = mockRoutes({ 'GET /api/customers': list(), 'GET /api/customers/export.csv': () => csvResponse('Name\r\nRaj Shah\r\n', 'swara-customers-20261110.csv') })
      renderIt('/customers?q=raj&sort=spent')
      await screen.findByRole('row', { name: 'Open Raj Shah' })
      await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
      expect(await screen.findByText('Saved swara-customers-20261110.csv.')).toBeInTheDocument()
      const url = new URL('http://x' + m.urls().find((u) => u.startsWith('/api/customers/export.csv'))!)
      expect(Object.fromEntries(url.searchParams)).toEqual({ q: 'raj', sort: 'spent', include_synthetic: 'false' })
      dl.restore()
    })
  })
})
