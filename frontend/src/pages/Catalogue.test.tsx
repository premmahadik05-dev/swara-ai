import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Catalogue from './Catalogue'
import { ToastProvider } from '../components/Toast'
import { STAFF_USER, TestAuth } from '../test/auth'
import { json, mockRoutes, product } from '../test/fixtures'
import type { CatalogDetail, CatalogItem } from '../types'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

const item = (over: Partial<CatalogItem> = {}): CatalogItem => ({
  id: 10, ean: '8901058000290', name: 'Maggi 2-Minute Noodles', brand: 'Maggi', category: 'Packaged Foods', pack_size: 70, pack_unit: 'g', pack_label: '70 g',
  display_name: 'Maggi 2-Minute Noodles 70 g', last_modified: '2024-03-02T00:00:00Z', source_id: 'off_india', provenance: 'sourced + transformed', in_shop: false, ...over,
})
const detail = (over: Partial<CatalogDetail> = {}): CatalogDetail => ({
  ...item(), name_raw: 'MAGGI 2-minute noodles &amp; masala', quantity_raw: '70g', off_categories_raw: 'en:noodles,en:instant-noodles', transforms: ['name:cleaned', 'qty:g->kg', 'cat:name'],
  split: 'train', suggested_aliases: ['maggi', 'maggi noodles'], ...over,
})
const base = (over: Record<string, unknown> = {}) => ({
  'GET /api/catalog': { total: 2, page: 1, page_size: 24, items: [item(), item({ id: 11, ean: '8901063010116', name: 'Parle-G Biscuits', brand: '', category: 'Biscuits', pack_label: '56 g', in_shop: true })] },
  'GET /api/catalog/facets': { total: 5325, categories: [{ name: 'Packaged Foods', count: 3000 }, { name: 'Biscuits', count: 800 }], brands: [{ name: 'Maggi', count: 12 }] },
  'GET /api/catalog/source': {
    rows_loaded: 5325, manifest_found: true, title: 'Open Food Facts, India', origin: 'Open Food Facts', licence: 'ODbL 1.0', retrieved_on: '2026-11-10', snapshot_date: '2026-07-05',
    attribution: 'Contains information from Open Food Facts', raw_rows: 6000, limitations: ['Contains no prices.', 'Categories are assigned by rules and are about 90% accurate.'],
  },
  ...over,
})
const renderIt = (path = '/catalogue', user?: typeof STAFF_USER) => render(<TestAuth user={user}><MemoryRouter initialEntries={[path]}><ToastProvider><Catalogue /></ToastProvider></MemoryRouter></TestAuth>)

describe('Catalogue', () => {
  it('states where the data came from, its licence, and that it has no prices', async () => {
    mockRoutes(base())
    renderIt()
    expect(await screen.findByText('Open Food Facts, India')).toBeInTheDocument()
    expect(screen.getByText(/5,325 packaged-food products/)).toBeInTheDocument()
    expect(screen.getByText(/licence ODbL 1.0/)).toBeInTheDocument()
    expect(screen.getByText('no prices and no stock')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Source and limits' }))
    expect(screen.getByText('Contains no prices.')).toBeInTheDocument()
    expect(screen.getByText(/Categories are assigned by rules/)).toBeInTheDocument()
  })

  it('labels unbranded items honestly and tells apart those already in the shop', async () => {
    mockRoutes(base())
    renderIt()
    const parle = (await screen.findByText('Parle-G Biscuits')).closest('tr') as HTMLElement
    expect(within(parle).getByText('Unbranded')).toBeInTheDocument()
    expect(within(parle).getByText('In your shop')).toBeInTheDocument()
    const maggi = screen.getByText('Maggi 2-Minute Noodles').closest('tr') as HTMLElement
    expect(within(maggi).getByRole('button', { name: 'Add to shop' })).toBeInTheDocument()
  })

  it('shows what the source said next to what the cleaning script changed, in plain words', async () => {
    mockRoutes(base({ 'GET /api/catalog/10': detail() }))
    renderIt('/catalogue?open=10')
    const drawer = await screen.findByRole('dialog', { name: /Maggi 2-Minute Noodles 70 g/ })
    expect(await within(drawer).findByText('MAGGI 2-minute noodles &amp; masala')).toBeInTheDocument()   // raw text shown as published
    expect(within(drawer).getAllByText('sourced').length).toBeGreaterThan(0)
    expect(within(drawer).getAllByText('transformed').length).toBeGreaterThan(0)
    expect(within(drawer).getByText(/Tidied the name/)).toBeInTheDocument()
    expect(within(drawer).getByText(/Read the pack size from the source text and converted it \(g → kg\)/)).toBeInTheDocument()
    expect(within(drawer).getByText(/Assigned the shop category from words in the product name/)).toBeInTheDocument()
  })

  it('will not add an item without the shopkeeper\'s own price, then sends rupees as paise', async () => {
    const m = mockRoutes(base({ 'GET /api/catalog/10': detail(), 'POST /api/catalog/10/import': product({ id: 77, name_en: 'Maggi 2-Minute Noodles 70 g' }) }))
    renderIt('/catalogue?open=10')
    const drawer = await screen.findByRole('dialog')
    const add = await within(drawer).findByRole('button', { name: 'Add to my shop' })
    expect(add).toBeDisabled()
    expect(within(drawer).getByText(/the catalogue has no prices/)).toBeInTheDocument()
    await userEvent.type(within(drawer).getByLabelText('Your selling price (₹)'), '14')
    await userEvent.type(within(drawer).getByLabelText('Packs in stock now'), '24')
    await userEvent.click(add)
    await waitFor(() => expect(m.calls.some((c) => c.method === 'POST')).toBe(true))
    expect(JSON.parse(m.calls.find((c) => c.method === 'POST')!.body!)).toMatchObject({ price_paise: 1400, stock: 24, cost_paise: null })
  })

  it('rejects an absurd price before it reaches the server', async () => {
    mockRoutes(base({ 'GET /api/catalog/10': detail() }))
    renderIt('/catalogue?open=10')
    const drawer = await screen.findByRole('dialog')
    await userEvent.type(await within(drawer).findByLabelText('Your selling price (₹)'), '999999999')
    expect(within(drawer).getByText(/Enter a price between/)).toBeInTheDocument()
    expect(within(drawer).getByRole('button', { name: 'Add to my shop' })).toBeDisabled()
  })

  it('points to Inventory instead of offering a second import when the item is already in the shop', async () => {
    mockRoutes(base({ 'GET /api/catalog/11': detail({ id: 11, ean: '8901063010116', in_shop: true, display_name: 'Parle-G Biscuits 56 g' }) }))
    renderIt('/catalogue?open=11')
    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByText('This product is in your shop.')).toBeInTheDocument()
    expect(within(drawer).queryByRole('button', { name: 'Add to my shop' })).toBeNull()
    expect(within(drawer).getByRole('link', { name: 'Inventory' })).toHaveAttribute('href', '/inventory?q=8901063010116')
  })

  it('shows the server reason if the import is refused', async () => {
    mockRoutes(base({ 'GET /api/catalog/10': detail(), 'POST /api/catalog/10/import': json({ detail: { code: 'ALREADY_IMPORTED', message: 'This product is already in your shop.' } }, 409) }))
    renderIt('/catalogue?open=10')
    const drawer = await screen.findByRole('dialog')
    await userEvent.type(await within(drawer).findByLabelText('Your selling price (₹)'), '14')
    await userEvent.click(within(drawer).getByRole('button', { name: 'Add to my shop' }))
    expect(await within(drawer).findByText('This product is already in your shop.')).toBeInTheDocument()
  })

  it('filters by category on the server, and the empty state offers to clear', async () => {
    const m = mockRoutes(base({ 'GET /api/catalog': (u: URL) => (u.searchParams.get('q') === 'zzz' ? { total: 0, page: 1, page_size: 24, items: [] } : base()['GET /api/catalog']) }))
    renderIt()
    await screen.findByText('Parle-G Biscuits')
    await userEvent.click(within(screen.getByRole('group', { name: 'Category' })).getByRole('button', { name: /^Biscuits/ }))
    await waitFor(() => expect(m.urls().some((u) => u.includes('category=Biscuits'))).toBe(true))
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search the catalogue' }), 'zzz')
    expect(await screen.findByText('No catalogue products match')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument()
  })

  it('lets staff read a catalogue item and its provenance, but not add it to the shop', async () => {
    mockRoutes(base({ 'GET /api/catalog/10': detail() }))
    renderIt('/catalogue?open=10', STAFF_USER)
    const drawer = await screen.findByRole('dialog', { name: /Maggi 2-Minute Noodles 70 g/ })
    expect(await within(drawer).findByText('MAGGI 2-minute noodles &amp; masala')).toBeInTheDocument()
    expect(within(drawer).queryByRole('button', { name: 'Add to my shop' })).toBeNull()
    expect(within(drawer).getByText(/Only the shop owner can add this product to the shop and set its price/)).toBeInTheDocument()
  })

  it('labels the row action honestly for staff', async () => {
    mockRoutes(base())
    renderIt('/catalogue', STAFF_USER)
    const row = (await screen.findByText('Maggi 2-Minute Noodles')).closest('tr') as HTMLElement
    expect(within(row).queryByRole('button', { name: 'Add to shop' })).toBeNull()
    expect(within(row).getByRole('button', { name: 'Details' })).toBeInTheDocument()
  })
})
