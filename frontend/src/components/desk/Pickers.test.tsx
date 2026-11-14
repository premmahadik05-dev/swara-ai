import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CustomerPicker } from './Pickers'
import { DataScopeProvider } from '../../lib/scope'
import { customer, mockRoutes } from '../../test/fixtures'
import { OWNER_USER, STAFF_USER, TestAuth } from '../../test/auth'
import type { AuthUser } from '../../types'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

const list = { total: 1, page: 1, page_size: 6, items: [customer({ id: 5, name: 'Meena Patel', is_synthetic: false })] }
const open = async (user: AuthUser) => {
  mockRoutes({ 'GET /api/customers': list })
  render(<TestAuth user={user}><DataScopeProvider><CustomerPicker value={null} onChange={() => undefined} /></DataScopeProvider></TestAuth>)
  await userEvent.click(screen.getByRole('button', { name: 'Change customer' }))
  return screen.findByRole('option', { name: /Meena Patel/ })
}

describe('CustomerPicker', () => {
  it('lets the owner find a customer, bill a walk-in, or start a new customer record', async () => {
    await open(OWNER_USER)
    expect(screen.getByRole('option', { name: /Walk-in customer/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /New customer/ })).toBeInTheDocument()
  })

  it('does not offer staff a way to create customer records (the server refuses it, so the screen does not tempt them)', async () => {
    await open(STAFF_USER)
    expect(screen.getByRole('option', { name: /Walk-in customer/ })).toBeInTheDocument()      // staff can still bill a walk-in
    expect(screen.queryByRole('option', { name: /New customer/ })).toBeNull()
  })
})
