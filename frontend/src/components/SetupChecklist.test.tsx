import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SetupChecklist, hiddenKey } from './SetupChecklist'
import { clearApiCache } from '../api/client'
import { mockRoutes } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

const HEALTH = { status: 'ok', db: 'ok', products: 70, gnani_configured: false, version: '2', store_name: 'Patel Kirana & General Store (demo)', store_name_is_default: true }
const view = (over: { health?: object; prices?: { demo: number; shop: number }; realOrders?: number | undefined; userId?: number } = {}) => {
  const m = mockRoutes({ 'GET /api/health': { ...HEALTH, ...over.health } })
  const realOrders = 'realOrders' in over ? over.realOrders : 0
  return { ...m, ...render(<MemoryRouter><SetupChecklist userId={over.userId ?? 1} prices={over.prices ?? { demo: 65, shop: 5 }} realOrders={realOrders} /></MemoryRouter>) }
}
const row = (name: RegExp) => screen.getByText(name).closest('li') as HTMLElement

describe('SetupChecklist', () => {
  it('ticks each step from what the server reports, and says what is still open', async () => {
    view()
    const card = await screen.findByRole('region', { name: 'Set up your shop' })
    expect(within(card).getByText(/1 of 4 done/)).toBeInTheDocument()                      // only the prices: the owner has set 5 of their own
    expect(within(row(/Name your shop/)).getByText(/still says "Patel Kirana & General Store \(demo\)"/)).toBeInTheDocument()
    expect(within(row(/Set your own prices/)).getByText(/65 of 70 items still carry a placeholder demo price/)).toBeInTheDocument()
    expect(row(/Set your own prices/)).toHaveClass('done')
    expect(row(/Name your shop/)).not.toHaveClass('done')
    expect(within(row(/first real order/)).getByText(/Generated demo orders do not/)).toBeInTheDocument()
    expect(within(row(/Gnani key/)).getByText('Needed only for spoken orders. Typed orders work without it.')).toBeInTheDocument()
    expect(within(row(/Gnani key/)).getByText('(optional)')).toBeInTheDocument()
  })

  it('sends each open step to the screen where it is done, and gives finished steps no button', async () => {
    view()
    await screen.findByRole('region', { name: 'Set up your shop' })
    expect(within(row(/Name your shop/)).getByRole('link', { name: 'Rename' })).toHaveAttribute('href', '/settings')
    expect(within(row(/first real order/)).getByRole('link', { name: 'Open order desk' })).toHaveAttribute('href', '/order')
    expect(within(row(/Gnani key/)).getByRole('link', { name: 'Open settings' })).toHaveAttribute('href', '/settings')
    expect(within(row(/Set your own prices/)).queryByRole('link')).toBeNull()               // done
  })

  it('does not claim "every price is yours" for a shop with no items at all', async () => {
    view({ prices: { demo: 0, shop: 0 } })
    await screen.findByRole('region', { name: 'Set up your shop' })
    expect(within(row(/Set your own prices/)).getByText(/no items yet/)).toBeInTheDocument()
    expect(row(/Set your own prices/)).not.toHaveClass('done')
  })

  it('announces progress to a screen reader: each step says done or to do, and the bar has a text equivalent', async () => {
    view({ health: { store_name: 'Shah Kirana', store_name_is_default: false }, realOrders: 3 })
    await screen.findByRole('region', { name: 'Set up your shop' })
    expect(screen.getByRole('img', { name: '3 of 4 steps done' })).toBeInTheDocument()
    expect(within(row(/Name your shop/)).getByText(', done')).toBeInTheDocument()
    expect(within(row(/Gnani key/)).getByText(', to do')).toBeInTheDocument()
    expect(within(row(/first real order/)).getByText('3 orders recorded by you, apart from the generated demo orders.')).toBeInTheDocument()
  })

  it('disappears once every step is true, with nothing for the owner to dismiss', async () => {
    const { container } = view({ health: { store_name: 'Shah Kirana', store_name_is_default: false, gnani_configured: true }, realOrders: 1 })
    await new Promise((r) => setTimeout(r, 50))
    expect(container.textContent).toBe('')
  })

  it('shows nothing while the facts it depends on are still loading, and nothing if the server cannot be reached', async () => {
    const { container, unmount } = view({ realOrders: undefined })
    await new Promise((r) => setTimeout(r, 50))
    expect(container.textContent).toBe('')                                                  // orders count not known yet: no flash of wrong ticks
    unmount()
    clearApiCache()                                                                         // the first render's health answer is cached for a few seconds
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const again = render(<MemoryRouter><SetupChecklist userId={1} prices={{ demo: 1, shop: 0 }} realOrders={0} /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 50))
    expect(again.container.textContent).toBe('')                                            // an aid, not an error screen
  })

  it('can be hidden, and stays hidden for that person in this browser but not for someone else', async () => {
    const { unmount } = view({ userId: 7 })
    await userEvent.click(await screen.findByRole('button', { name: 'Hide the setup checklist' }))
    expect(screen.queryByRole('region', { name: 'Set up your shop' })).toBeNull()
    expect(localStorage.getItem(hiddenKey(7))).toBe('1')
    unmount()
    view({ userId: 7 })
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByRole('region', { name: 'Set up your shop' })).toBeNull()
    view({ userId: 8 })
    expect(await screen.findByRole('region', { name: 'Set up your shop' })).toBeInTheDocument()
  })
})
