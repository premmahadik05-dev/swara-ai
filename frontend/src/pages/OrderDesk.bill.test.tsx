import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OrderDesk from './OrderDesk'
import { TestAuth } from '../test/auth'
import { ToastProvider } from '../components/Toast'
import { DataScopeProvider } from '../lib/scope'
import { RICE, customer, inventoryList, json, mockRoutes, product, settings, turn } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

const HEALTH = { status: 'ok', db: 'ok', products: 65, gnani_configured: false, version: '1', store_name: 'Demo' }
const rice = product({ id: 1, name_en: 'Rice', price_paise: 5800, unit: 'kg', stock: 40 })
const finished = product({ id: 3, name_en: 'Toor Dal', stock: 0, stock_status: 'out' })
const edit = (lines = [RICE], phase = 'collecting') => ({
  session_id: 's9', phase, awaiting: lines.length ? 'more_items' : null, pending: null,
  cart: { lines, total_paise: lines.reduce((t, l) => t + l.line_total_paise, 0) },
})
const base = (over: Record<string, unknown> = {}) => ({
  'GET /api/health': HEALTH, 'GET /api/settings': settings(),
  'GET /api/inventory': (u: URL) => inventoryList(u.searchParams.get('q') === 'dal' ? [finished] : [rice]),
  'POST /api/sessions': { session_id: 's9' },
  ...over,
})
const renderIt = () => render(<MemoryRouter><TestAuth><DataScopeProvider><ToastProvider><OrderDesk /></ToastProvider></DataScopeProvider></TestAuth></MemoryRouter>)
const addRice = async () => {
  await userEvent.type(screen.getByRole('combobox', { name: 'Add an item to the bill' }), 'ri')
  await userEvent.click(await screen.findByRole('option', { name: /Rice/ }))
}

describe('OrderDesk: editing the bill by hand', () => {
  it('adds an item from a search, creates the session on demand and shows the line and the total', async () => {
    const m = mockRoutes(base({ 'POST /api/sessions/s9/cart': edit() }))
    renderIt()
    await screen.findByText(/Typing works now/)
    await addRice()
    expect(await screen.findByRole('group', { name: 'Quantity of Rice' })).toBeInTheDocument()
    const post = m.calls.find((c) => c.url === '/api/sessions/s9/cart')!
    expect(JSON.parse(post.body!)).toEqual({ product_id: 1, qty: '1', mode: 'add' })
    expect(m.calls.findIndex((c) => c.url === '/api/sessions')).toBeLessThan(m.calls.findIndex((c) => c.url === '/api/sessions/s9/cart'))
    expect(screen.getAllByText('₹116').length).toBeGreaterThan(0)
  })

  it('does not let a finished item be picked', async () => {
    const m = mockRoutes(base())
    renderIt()
    await screen.findByText(/Typing works now/)
    await userEvent.type(screen.getByRole('combobox', { name: 'Add an item to the bill' }), 'dal')
    const opt = await screen.findByRole('option', { name: /Toor Dal/ })
    expect(opt).toHaveAttribute('aria-disabled', 'true')
    await userEvent.click(opt)
    expect(m.calls.some((c) => c.url.endsWith('/cart'))).toBe(false)
  })

  it('changes a quantity with the stepper (0.5 kg steps) and removes a line with the x button', async () => {
    const more = { ...RICE, qty: '2.5', line_total_paise: 14500 }
    let call = 0
    const m = mockRoutes(base({ 'POST /api/sessions/s9/cart': () => [edit(), edit([more]), edit([])][Math.min(call++, 2)] }))
    renderIt()
    await screen.findByText(/Typing works now/)
    await addRice()
    await userEvent.click(await screen.findByRole('button', { name: 'Increase Rice' }))
    await waitFor(() => expect(m.calls.filter((c) => c.url.endsWith('/cart'))).toHaveLength(2))
    expect(JSON.parse(m.calls.filter((c) => c.url.endsWith('/cart'))[1].body!)).toEqual({ product_id: 1, qty: '2.5', mode: 'set' })
    expect(await screen.findByDisplayValue('2.5')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove Rice' }))
    await waitFor(() => expect(JSON.parse(m.calls.filter((c) => c.url.endsWith('/cart'))[2].body!)).toMatchObject({ qty: '0', mode: 'set' }))
    expect(await screen.findByText('Nothing on the bill yet')).toBeInTheDocument()
  })

  it('commits a typed quantity on Enter and ignores nonsense', async () => {
    const m = mockRoutes(base({ 'POST /api/sessions/s9/cart': () => edit() }))
    renderIt()
    await screen.findByText(/Typing works now/)
    await addRice()
    const qty = await screen.findByRole('textbox', { name: /Rice quantity/ })
    await userEvent.clear(qty); await userEvent.type(qty, 'abc{Enter}')
    expect(m.calls.filter((c) => c.url.endsWith('/cart'))).toHaveLength(1)        // nothing sent
    expect(qty).toHaveValue('2')                                                  // reset to the real value
    await userEvent.clear(qty); await userEvent.type(qty, '3{Enter}')
    await waitFor(() => expect(m.calls.filter((c) => c.url.endsWith('/cart'))).toHaveLength(2))
    expect(JSON.parse(m.calls.filter((c) => c.url.endsWith('/cart'))[1].body!)).toMatchObject({ qty: '3', mode: 'set' })
  })

  it('stops the + button at the stock on the shelf', async () => {
    mockRoutes(base({ 'POST /api/sessions/s9/cart': () => edit([{ ...RICE, qty: '40', in_stock: 40, line_total_paise: 232000 }]) }))
    renderIt()
    await screen.findByText(/Typing works now/)
    await addRice()
    expect(await screen.findByRole('button', { name: 'Increase Rice' })).toBeDisabled()
  })

  it('keeps the bill as it was and shows the reason when the server refuses a change', async () => {
    let n = 0
    mockRoutes(base({ 'POST /api/sessions/s9/cart': () => (n++ === 0 ? edit() : json({ detail: { code: 'OUT_OF_STOCK', message: 'Only 40 kg of Rice left.' } }, 409)) }))
    renderIt()
    await screen.findByText(/Typing works now/)
    await addRice()
    await userEvent.click(await screen.findByRole('button', { name: 'Increase Rice' }))
    expect((await screen.findAllByText('Only 40 kg of Rice left.')).length).toBeGreaterThan(0)
    expect(screen.getByRole('textbox', { name: /Rice quantity/ })).toHaveValue('2')
  })

  it('links the order to the chosen customer when it is confirmed', async () => {
    const m = mockRoutes(base({
      'GET /api/customers': { total: 1, page: 1, page_size: 6, items: [customer()] },
      'POST /api/sessions/s9/cart': edit(),
      'POST /api/sessions/s9/confirm': turn({ session_id: 's9', phase: 'completed', awaiting: null, order: { id: 4, code: 'SW-4', status: 'confirmed', channel: 'text', language: 'gu', customer_id: 5, customer_name: 'Meena Patel', total_paise: 11600, is_synthetic: false, created_at: '2026-11-10T05:00:00Z', session_id: 's9', items: [] } }),
    }))
    renderIt()
    await screen.findByText(/Typing works now/)
    await userEvent.click(screen.getByRole('button', { name: 'Change customer' }))
    await userEvent.click(await screen.findByRole('option', { name: /Meena Patel/ }))
    expect(await screen.findByText('Meena Patel')).toBeInTheDocument()
    await addRice()
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm order' }))
    expect(await screen.findByRole('region', { name: 'Order confirmed' })).toBeInTheDocument()
    expect(JSON.parse(m.calls.find((c) => c.url === '/api/sessions/s9/confirm')!.body!)).toEqual({ customer_id: 5 })
    // after confirming, the bill is read-only
    expect(within(screen.getByRole('region', { name: 'Bill' })).queryByRole('button', { name: 'Increase Rice' })).toBeNull()
  })
})
