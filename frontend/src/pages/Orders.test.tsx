import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Orders from './Orders'
import { ToastProvider } from '../components/Toast'
import { STAFF_USER, TestAuth } from '../test/auth'
import { DataScopeProvider } from '../lib/scope'
import { captureDownloads, csvResponse, json, mockRoutes, order, orderList } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); document.body.classList.remove('printing-bill') })
const renderIt = (path = '/orders', user?: typeof STAFF_USER) => render(
  <TestAuth user={user}><MemoryRouter initialEntries={[path]}><DataScopeProvider><ToastProvider><Orders /></ToastProvider></DataScopeProvider></MemoryRouter></TestAuth>,
)

describe('Orders', () => {
  it('lists orders with server-side status counts, a demo marker and a readable summary of the items', async () => {
    mockRoutes({ 'GET /api/orders': orderList() })
    renderIt()
    const row = (await screen.findByRole('row', { name: 'Open SW-0001' }))
    expect(within(row).getByText('₹172')).toBeInTheDocument()
    expect(within(row).getByText('Rice × 2 kg, Milk × 1 L')).toBeInTheDocument()
    expect(within(row).getByText('Walk-in customer')).toBeInTheDocument()
    expect(within(screen.getByRole('row', { name: 'Open SW-0002' })).getByText('Demo')).toBeInTheDocument()
    const seg = screen.getByRole('group', { name: 'Order status' })
    expect(within(seg).getByRole('button', { name: /Fulfilled\s*1/ })).toBeInTheDocument()
  })

  it('sends filters to the server rather than filtering the visible page, and the demo switch is part of the request', async () => {
    localStorage.setItem('swara.includeDemo', '1')   // these tests are about the demo-on state; the default for a shop is decided by its data (see shell.test)
    const m = mockRoutes({ 'GET /api/orders': orderList() })
    renderIt()
    await screen.findByRole('row', { name: 'Open SW-0001' })
    await userEvent.click(screen.getByRole('button', { name: /Fulfilled/ }))
    await waitFor(() => expect(m.urls().some((u) => u.includes('status=fulfilled'))).toBe(true))
    await userEvent.selectOptions(screen.getByLabelText('Taken by'), 'voice')
    await waitFor(() => expect(m.urls().some((u) => u.includes('channel=voice') && u.includes('status=fulfilled'))).toBe(true))
    expect(m.urls().every((u) => u.includes('include_synthetic=true'))).toBe(true)
  })

  it('debounces the search box into a single request', async () => {
    const m = mockRoutes({ 'GET /api/orders': orderList() })
    renderIt()
    await screen.findByRole('row', { name: 'Open SW-0001' })
    const before = m.calls.length
    await userEvent.type(screen.getByRole('searchbox', { name: /Search orders/ }), 'meena')
    await waitFor(() => expect(m.urls().some((u) => u.includes('q=meena'))).toBe(true))
    expect(m.calls.length - before).toBe(1)
  })

  it('explains an empty result and offers to clear the filters', async () => {
    mockRoutes({ 'GET /api/orders': orderList([], 0) })
    renderIt('/orders?q=zzz')
    expect(await screen.findByText('No orders match these filters')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument()
  })

  it('opens an order from the URL (deep link) and shows its lines and the total', async () => {
    mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/1': order() })
    renderIt('/orders?open=1')
    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByText('Rice')).toBeInTheDocument()
    expect(within(drawer).getByText('₹172', { selector: 'td' })).toBeInTheDocument()
    expect(within(drawer).getByRole('button', { name: 'Mark fulfilled' })).toBeInTheDocument()
  })

  it('asks before cancelling, says what will happen to stock, and only then calls the API', async () => {
    let status = 'confirmed'
    const m = mockRoutes({
      'GET /api/orders': () => orderList([order({ status: status as 'confirmed' })]),
      'GET /api/orders/1': () => order({ status: status as 'confirmed' }),
      'POST /api/orders/1/status': () => { status = 'cancelled'; return order({ status: 'cancelled' }) },
    })
    renderIt('/orders?open=1')
    const drawer = await screen.findByRole('dialog', { name: /SW-0001/ })
    await userEvent.click(await within(drawer).findByRole('button', { name: 'Cancel order' }))
    expect(m.calls.some((c) => c.method === 'POST')).toBe(false)           // nothing yet
    const confirm = await screen.findByRole('alertdialog')
    expect(within(confirm).getByText(/goes back to the shelf/)).toBeInTheDocument()
    await userEvent.click(within(confirm).getByRole('button', { name: 'Cancel order' }))
    await waitFor(() => expect(m.calls.some((c) => c.method === 'POST' && c.url === '/api/orders/1/status')).toBe(true))
    expect(JSON.parse(m.calls.find((c) => c.method === 'POST')!.body!)).toEqual({ status: 'cancelled' })
    expect(await screen.findByText(/cancelled\. Stock returned to the shelf/)).toBeInTheDocument()
  })

  it('shows the server message when a status change is refused', async () => {
    mockRoutes({
      'GET /api/orders': orderList(), 'GET /api/orders/1': order(),
      'POST /api/orders/1/status': json({ detail: { code: 'BAD_STATE', message: 'Only a confirmed order can be fulfilled.' } }, 409),
    })
    renderIt('/orders?open=1')
    await userEvent.click(await screen.findByRole('button', { name: 'Mark fulfilled' }))
    expect(await screen.findByText('Only a confirmed order can be fulfilled.')).toBeInTheDocument()
  })

  it('shows a retryable error when the list cannot load', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('x')))
    renderIt()
    expect(await screen.findByText(/Cannot reach the SWARA AI server/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  describe('for staff', () => {
    it('offers no way to fulfil or cancel an order, because the server would refuse it, and says why', async () => {
      mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/1': order() })
      renderIt('/orders?open=1', STAFF_USER)
      const drawer = await screen.findByRole('dialog')
      expect(await within(drawer).findByText('Rice')).toBeInTheDocument()
      expect(within(drawer).queryByRole('button', { name: 'Mark fulfilled' })).toBeNull()
      expect(within(drawer).queryByRole('button', { name: 'Cancel order' })).toBeNull()
      expect(within(drawer).getByText('Only the shop owner can mark an order fulfilled or cancel it.')).toBeInTheDocument()
      expect(within(drawer).getByRole('button', { name: 'Print bill' })).toBeInTheDocument()
    })
  })

  it('can filter by any of the eleven languages, and sends the chosen one to the server', async () => {
    const m = mockRoutes({ 'GET /api/orders': orderList() })
    renderIt()
    await screen.findByRole('row', { name: 'Open SW-0001' })
    const select = screen.getByLabelText('Language')
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['All languages', 'Gujarati', 'Hindi', 'English', 'Hinglish', 'Marathi', 'Bengali', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Punjabi'])
    await userEvent.selectOptions(select, 'bn')
    await waitFor(() => expect(m.urls().some((u) => u.startsWith('/api/orders') && u.includes('language=bn'))).toBe(true))
  })

  describe('export', () => {
    it('downloads the orders for the filters on screen and says what was saved', async () => {
      localStorage.setItem('swara.includeDemo', '1')   // these tests are about the demo-on state; the default for a shop is decided by its data (see shell.test)
      const dl = captureDownloads()
      const m = mockRoutes({
        'GET /api/orders': orderList(),
        'GET /api/orders/export.csv': () => csvResponse('Bill,Date (IST)\r\nSW-0001,2026-11-10 10:30\r\n', 'swara-orders-20261110.csv'),
      })
      renderIt('/orders?status=fulfilled&language=hi')
      await screen.findByRole('row', { name: 'Open SW-0001' })
      await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
      expect(await screen.findByText('Saved swara-orders-20261110.csv.')).toBeInTheDocument()
      const url = m.urls().find((u) => u.startsWith('/api/orders/export.csv'))!
      expect(url).toContain('status=fulfilled')
      expect(url).toContain('language=hi')
      expect(url).toContain('include_synthetic=true')
      expect(dl.saved).toHaveLength(1)
      expect(dl.saved[0].filename).toBe('swara-orders-20261110.csv')
      expect(await dl.saved[0].blob.text()).toContain('SW-0001')
      dl.restore()
    })

    it('says when the file holds only the first rows', async () => {
      const dl = captureDownloads()
      mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/export.csv': () => csvResponse('Bill\r\n', 'swara-orders-20261110.csv', true) })
      renderIt()
      await screen.findByRole('row', { name: 'Open SW-0001' })
      await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
      expect(await screen.findByText(/holds the first rows only/)).toBeInTheDocument()
      dl.restore()
    })

    it('shows the reason and saves nothing when the server refuses', async () => {
      const dl = captureDownloads()
      mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/export.csv': () => json({ detail: 'Sign in to continue.' }, 500) })
      renderIt()
      await screen.findByRole('row', { name: 'Open SW-0001' })
      await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
      expect(await screen.findByText('Sign in to continue.')).toBeInTheDocument()
      expect(dl.saved).toHaveLength(0)
      dl.restore()
    })
  })

  describe('print bill', () => {
    it('puts the shop name, the lines and the total on the printed page, and prints only the bill', async () => {
      const print = vi.spyOn(window, 'print').mockImplementation(() => undefined)
      mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/1': order({ customer_name: 'Meena Patel' }), 'GET /api/health': { store_name: 'Shah Kirana & Stores', status: 'ok' } })
      renderIt('/orders?open=1')
      const button = await screen.findByRole('button', { name: 'Print bill' })
      await waitFor(() => expect(document.querySelector('.print-bill h1')?.textContent).toBe('Shah Kirana & Stores'))
      const bill = document.querySelector('.print-bill') as HTMLElement
      expect(bill.parentElement).toBe(document.body)                       // a direct child of <body>, so the print stylesheet can hide everything else
      expect(within(bill).getByText(/Bill SW-0001/)).toBeInTheDocument()
      expect(within(bill).getByText(/Customer: Meena Patel/)).toBeInTheDocument()
      expect(within(bill).getByText('Rice')).toBeInTheDocument()
      expect(within(bill).getByText('₹172', { selector: 'tfoot td' })).toBeInTheDocument()
      expect(within(bill).queryByText(/not a real sale/)).toBeNull()
      await userEvent.click(button)
      expect(print).toHaveBeenCalledTimes(1)
      expect(document.body.classList.contains('printing-bill')).toBe(true)
      window.dispatchEvent(new Event('afterprint'))
      expect(document.body.classList.contains('printing-bill')).toBe(false)
    })

    it('marks a demo order as not a real sale, and a cancelled one as cancelled', async () => {
      mockRoutes({ 'GET /api/orders': orderList(), 'GET /api/orders/2': order({ id: 2, code: 'SW-0002', is_synthetic: true, status: 'cancelled' }), 'GET /api/health': { store_name: 'Shah Kirana', status: 'ok' } })
      renderIt('/orders?open=2')
      await screen.findByRole('button', { name: 'Print bill' })
      await waitFor(() => expect(document.querySelector('.print-bill')).not.toBeNull())
      const bill = document.querySelector('.print-bill') as HTMLElement
      expect(within(bill).getByText('Generated demo data. This is not a real sale.')).toBeInTheDocument()
      expect(within(bill).getByText(/CANCELLED/)).toBeInTheDocument()
    })
  })
})
