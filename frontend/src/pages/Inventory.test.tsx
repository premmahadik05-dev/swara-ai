import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Inventory from './Inventory'
import { ToastProvider } from '../components/Toast'
import { STAFF_USER, TestAuth } from '../test/auth'
import { captureDownloads, csvResponse, inventoryList, inventorySummary, json, mockRoutes, product } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })
const base = (over: Record<string, unknown> = {}) => ({
  'GET /api/inventory': inventoryList(),
  'GET /api/inventory/categories': [{ category: 'Grains & Flour', count: 12 }, { category: 'Dairy & Bakery', count: 9 }],
  'GET /api/analytics/inventory': inventorySummary(),
  ...over,
})
const renderIt = (path = '/inventory', user?: typeof STAFF_USER) => render(<TestAuth user={user}><MemoryRouter initialEntries={[path]}><ToastProvider><Inventory /></ToastProvider></MemoryRouter></TestAuth>)

describe('Inventory', () => {
  it('shows stock, status and the value at selling price, and says plainly that demo prices are placeholders', async () => {
    mockRoutes(base())
    renderIt()
    const row = (await screen.findByText('Basmati Rice')).closest('tr') as HTMLElement
    expect(within(row).getByText('Demo price')).toBeInTheDocument()
    expect(within(row).getByText('In stock')).toBeInTheDocument()
    expect(within(row).getByText('Curated staple')).toBeInTheDocument()
    expect(within(screen.getByText('Sugar').closest('tr') as HTMLElement).getByText('Shop price')).toBeInTheDocument()
    expect(screen.getByText('Running low', { selector: 'span.badge' })).toBeInTheDocument()
    expect(screen.getByText('₹1,84,500')).toBeInTheDocument()
    expect(screen.getByText(/65 items still use/)).toBeInTheDocument()
    expect(screen.getByText('Add a cost price to see value at cost')).toBeInTheDocument()   // no invented cost figure
  })

  it('keeps sorting available through a Sort select, because the column headers are hidden when the table stacks on a phone', async () => {
    const m = mockRoutes(base())
    renderIt()
    await screen.findByText('Basmati Rice')
    await userEvent.selectOptions(screen.getByLabelText('Sort by'), 'stock')
    await waitFor(() => expect(m.urls().some((u) => u.includes('sort=stock'))).toBe(true))
  })

  it('filters, sorts and pages on the server', async () => {
    const m = mockRoutes(base())
    renderIt()
    await screen.findByText('Basmati Rice')
    await userEvent.click(within(screen.getByRole('group', { name: 'Stock status' })).getByRole('button', { name: /Finished/ }))
    await waitFor(() => expect(m.urls().some((u) => u.startsWith('/api/inventory?') && u.includes('status=out'))).toBe(true))
    await userEvent.selectOptions(screen.getByLabelText('Source'), 'off_india')
    await waitFor(() => expect(m.urls().some((u) => u.includes('source=off_india') && u.includes('status=out'))).toBe(true))
    await userEvent.click(screen.getByRole('button', { name: 'Price' }))
    await waitFor(() => expect(m.urls().some((u) => u.includes('sort=price'))).toBe(true))
  })

  it('restocks by an amount, shows the new total before saving, and posts the quantity', async () => {
    const m = mockRoutes(base({ 'POST /api/products/2/restock': product({ id: 2, stock: 8 }) }))
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Restock Sugar' }))
    const dlg = await screen.findByRole('dialog', { name: /Restock Sugar/ })
    const save = within(dlg).getByRole('button', { name: 'Add stock' })
    expect(save).toBeDisabled()
    await userEvent.type(within(dlg).getByLabelText(/How much arrived/), '5')
    expect(within(dlg).getByText('New stock will be 8 kg.')).toBeInTheDocument()
    await userEvent.click(save)
    await waitFor(() => expect(m.calls.some((c) => c.method === 'POST' && c.url === '/api/products/2/restock')).toBe(true))
    expect(JSON.parse(m.calls.find((c) => c.method === 'POST')!.body!)).toEqual({ qty: '5' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('validates a new product before it can be submitted', async () => {
    mockRoutes(base())
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Add product' }))
    const dlg = await screen.findByRole('dialog', { name: 'Add product' })
    const submit = within(dlg).getByRole('button', { name: 'Add product' })
    expect(submit).toBeDisabled()
    await userEvent.type(within(dlg).getByLabelText('Name (English)'), 'Jaggery')
    await userEvent.type(within(dlg).getByLabelText('SKU'), 'a b')                      // spaces are not allowed
    await userEvent.type(within(dlg).getByLabelText(/Selling price/), '0')
    expect(within(dlg).getByText('Use 2–40 letters, numbers or dashes')).toBeInTheDocument()
    expect(within(dlg).getByText('Enter a price of at least ₹0.01')).toBeInTheDocument()
    expect(submit).toBeDisabled()
  })

  it('creates a product with an uppercased SKU and a price in paise', async () => {
    const m = mockRoutes(base({ 'POST /api/products': product({ id: 9, name_en: 'Jaggery' }) }))
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Add product' }))
    const dlg = await screen.findByRole('dialog', { name: 'Add product' })
    await userEvent.type(within(dlg).getByLabelText('Name (English)'), 'Jaggery')
    await userEvent.type(within(dlg).getByLabelText('SKU'), 'jag-1')
    await userEvent.type(within(dlg).getByLabelText(/Selling price/), '72.5')
    await userEvent.click(within(dlg).getByRole('button', { name: 'Add product' }))
    await waitFor(() => expect(m.calls.some((c) => c.method === 'POST' && c.url === '/api/products')).toBe(true))
    expect(JSON.parse(m.calls.find((c) => c.method === 'POST')!.body!)).toMatchObject({ sku: 'JAG-1', name_en: 'Jaggery', price_paise: 7250, unit: 'kg' })
  })

  it('shows the server reason when a product cannot be saved', async () => {
    mockRoutes(base({ 'POST /api/products': json({ detail: { code: 'DUPLICATE_SKU', message: 'SKU JAG-1 already exists.' } }, 409) }))
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Add product' }))
    const dlg = await screen.findByRole('dialog', { name: 'Add product' })
    await userEvent.type(within(dlg).getByLabelText('Name (English)'), 'Jaggery')
    await userEvent.type(within(dlg).getByLabelText('SKU'), 'JAG-1')
    await userEvent.type(within(dlg).getByLabelText(/Selling price/), '70')
    await userEvent.click(within(dlg).getByRole('button', { name: 'Add product' }))
    expect(await within(dlg).findByText('SKU JAG-1 already exists.')).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Add product' })).toBeInTheDocument()   // stays open so nothing typed is lost
  })

  it('shows a skeleton while loading, then an empty state with a way forward', async () => {
    mockRoutes(base({ 'GET /api/inventory': inventoryList([]) }))
    renderIt()
    expect(screen.getAllByRole('status', { name: 'Loading' }).length).toBeGreaterThan(0)
    expect(await screen.findByText('No products yet')).toBeInTheDocument()
  })

  describe('staff and export', () => {
    it('shows staff the stock but no Add, Restock or Edit, and says why', async () => {
      mockRoutes(base())
      renderIt('/inventory', STAFF_USER)
      const row = (await screen.findByText('Basmati Rice')).closest('tr') as HTMLElement
      expect(within(row).queryByRole('button', { name: /Restock/ })).toBeNull()
      expect(within(row).queryByRole('button', { name: /Edit/ })).toBeNull()
      expect(screen.queryByRole('button', { name: 'Add product' })).toBeNull()
      expect(screen.queryByRole('link', { name: 'Add from catalogue' })).toBeNull()
      expect(screen.getByText(/Only the shop owner can add products, change prices or restock/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument()      // looking is allowed, so is taking the list away
    })

    it('exports exactly what the filters show', async () => {
      const dl = captureDownloads()
      const m = mockRoutes(base({ 'GET /api/inventory/export.csv': () => csvResponse('SKU,Name\r\nRICE-BAS,Basmati Rice\r\n', 'swara-inventory-20261110.csv') }))
      renderIt('/inventory?status=low&category=Dairy%20%26%20Bakery&q=milk&sort=stock')
      await screen.findByText('Basmati Rice')
      await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
      expect(await screen.findByText('Saved swara-inventory-20261110.csv.')).toBeInTheDocument()
      const url = new URL('http://x' + m.urls().find((u) => u.startsWith('/api/inventory/export.csv'))!)
      expect(Object.fromEntries(url.searchParams)).toEqual({ q: 'milk', category: 'Dairy & Bakery', status: 'low', sort: 'stock' })
      expect(dl.saved[0].filename).toBe('swara-inventory-20261110.csv')
      dl.restore()
    })
  })
})
