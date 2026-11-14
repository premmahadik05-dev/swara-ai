import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Account from './Account'
import { ToastProvider } from '../components/Toast'
import { OWNER_USER, STAFF_USER, TestAuth } from '../test/auth'
import { err, mockRoutes } from '../test/fixtures'
import type { AuthUser } from '../types'

afterEach(() => vi.unstubAllGlobals())
const Where = () => { const l = useLocation(); return <div data-testid="where">{l.pathname}</div> }
const DEVICES = [
  { id: 'cur', device: 'Chrome on Windows', created_at: '2026-11-10T03:00:00Z', last_seen_at: '2026-11-10T08:00:00Z', expires_at: '2026-11-10T15:00:00Z', remember: false, current: true },
  { id: 'other', device: 'Firefox on Android', created_at: '2026-11-08T03:00:00Z', last_seen_at: '2026-11-09T08:00:00Z', expires_at: '2026-12-08T15:00:00Z', remember: true, current: false },
]
const TEAM = [{ ...OWNER_USER, is_active: true }, { ...STAFF_USER, is_active: true }]
const MSGS = [{ id: 7, name: 'Asha', email: 'asha@example.com', topic: 'Pricing', message: 'Do you support Marathi?', created_at: '2026-11-09T05:00:00Z', handled: false }]
const OWNER_ROUTES = { 'GET /api/auth/sessions': DEVICES, 'GET /api/auth/users': TEAM, 'GET /api/contact/messages': MSGS }

function renderIt(user: AuthUser = OWNER_USER, setUser = vi.fn(), signOut = vi.fn(async () => undefined)) {
  const view = render(
    <MemoryRouter initialEntries={['/account']}>
      <TestAuth user={user} over={{ setUser, signOut }}><ToastProvider><Routes>
        <Route path="/account" element={<Account />} /><Route path="*" element={<><h1>Landed</h1><Where /></>} />
      </Routes></ToastProvider></TestAuth>
    </MemoryRouter>,
  )
  return { ...view, setUser, signOut }
}

describe('Account', () => {
  it('shows the owner their details, devices, team and contact messages — and never anything secret', async () => {
    mockRoutes(OWNER_ROUTES)
    const { container } = renderIt()
    expect(await screen.findByRole('heading', { level: 1, name: 'Account' })).toBeInTheDocument()
    expect(screen.getByText('Shop owner', { selector: '.badge, .badge *' })).toBeInTheDocument()
    expect(await screen.findByText('Chrome on Windows')).toBeInTheDocument()
    expect(await screen.findByText('Meena Shah')).toBeInTheDocument()
    expect(await screen.findByText('Do you support Marathi?')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/password_hash|scrypt\$|csrf|token/i)
  })

  it('hides the team list and the contact inbox from staff, and does not even ask the server for them', async () => {
    const { calls } = mockRoutes({ 'GET /api/auth/sessions': DEVICES })
    renderIt(STAFF_USER)
    expect(await screen.findByText('Chrome on Windows')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Team' })).toBeNull()
    expect(screen.queryByText(/Messages from the contact form/)).toBeNull()
    expect(screen.getByText('Staff', { selector: '.badge, .badge *' })).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/api/auth/users' || c.url === '/api/contact/messages')).toBe(false)
  })

  describe('profile', () => {
    it('keeps Save disabled until something changes, then sends only what changed', async () => {
      const { calls } = mockRoutes({ ...OWNER_ROUTES, 'PATCH /api/auth/profile': { user: { ...OWNER_USER, full_name: 'Ramesh K Patel' } } })
      const { setUser } = renderIt()
      const save = await screen.findByRole('button', { name: 'Save changes' })
      expect(save).toBeDisabled()
      const name = screen.getAllByLabelText('Full name')[0]
      await userEvent.clear(name)
      await userEvent.type(name, '  Ramesh   K Patel ')
      expect(save).toBeEnabled()
      await userEvent.click(save)
      await waitFor(() => expect(setUser).toHaveBeenCalledWith(expect.objectContaining({ full_name: 'Ramesh K Patel' })))
      expect(JSON.parse(calls.find((c) => c.url === '/api/auth/profile')!.body!)).toEqual({ full_name: '  Ramesh   K Patel ' })
      expect(await screen.findByText('Profile saved.')).toBeInTheDocument()
    })

    it('saves the order-desk language on its own', async () => {
      const { calls } = mockRoutes({ ...OWNER_ROUTES, 'PATCH /api/auth/profile': { user: { ...OWNER_USER, preferences: { language: 'hi' } } } })
      renderIt()
      await userEvent.selectOptions(await screen.findByLabelText('Order desk language'), 'hi')
      await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
      await waitFor(() => expect(calls.some((c) => c.url === '/api/auth/profile')).toBe(true))
      expect(JSON.parse(calls.find((c) => c.url === '/api/auth/profile')!.body!)).toEqual({ language: 'hi' })
    })

    it('offers every language the Order desk speaks, and saves a new one such as Tamil', async () => {
      const { calls } = mockRoutes({ ...OWNER_ROUTES, 'PATCH /api/auth/profile': { user: { ...OWNER_USER, preferences: { language: 'ta' } } } })
      renderIt()
      const select = await screen.findByLabelText('Order desk language')
      expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['Gujarati (default)', 'Gujarati', 'Hindi', 'English', 'Hinglish', 'Marathi', 'Bengali', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Punjabi'])
      await userEvent.selectOptions(select, 'ta')
      await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
      await waitFor(() => expect(calls.some((c) => c.url === '/api/auth/profile')).toBe(true))
      expect(JSON.parse(calls.find((c) => c.url === '/api/auth/profile')!.body!)).toEqual({ language: 'ta' })
    })

    it('shows the server message when saving fails and leaves the person signed in', async () => {
      mockRoutes({ ...OWNER_ROUTES, 'PATCH /api/auth/profile': () => err(422, 'BAD_NAME', 'Enter your full name.') })
      const { setUser } = renderIt()
      const name = (await screen.findAllByLabelText('Full name'))[0]
      await userEvent.type(name, 'x')
      await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
      expect(await screen.findByText('Enter your full name.')).toBeInTheDocument()
      expect(setUser).not.toHaveBeenCalled()
    })

    it('says the e-mail address cannot be edited here and offers no field for it', async () => {
      mockRoutes(OWNER_ROUTES)
      renderIt()
      expect(await screen.findByText(/cannot be changed here/)).toBeInTheDocument()
      expect(screen.queryByLabelText('E-mail address')).toBeNull()
    })
  })

  describe('password', () => {
    const fill = async (cur: string, pw: string, conf: string) => {
      await userEvent.type(await screen.findByLabelText('Current password'), cur)
      await userEvent.type(screen.getByLabelText('New password'), pw)
      await userEvent.type(screen.getByLabelText('Confirm new password'), conf)
      await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
    }

    it('checks the new password locally first', async () => {
      const { calls } = mockRoutes(OWNER_ROUTES)
      renderIt()
      await fill('Old-Password-1!', 'short', 'short')
      expect(await screen.findByText('Use at least 10 characters.')).toBeInTheDocument()
      expect(screen.getByLabelText('New password')).toHaveFocus()
      expect(calls.some((c) => c.url === '/api/auth/change-password')).toBe(false)
    })

    it('needs the current password and a matching confirmation', async () => {
      mockRoutes(OWNER_ROUTES)
      renderIt()
      await userEvent.click(await screen.findByRole('button', { name: 'Change password' }))
      expect(await screen.findByText('Enter your current password.')).toBeInTheDocument()
      await userEvent.type(screen.getByLabelText('Current password'), 'Old-Password-1!')
      await userEvent.type(screen.getByLabelText('New password'), 'Correct-Horse-9!')
      await userEvent.type(screen.getByLabelText('Confirm new password'), 'Correct-Horse-8!')
      await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
      expect(await screen.findByText('The two passwords do not match.')).toBeInTheDocument()
    })

    it('changes the password, clears the fields and says how many other devices were signed out', async () => {
      const { calls } = mockRoutes({ ...OWNER_ROUTES, 'POST /api/auth/change-password': { ok: true, other_sessions_signed_out: 2 } })
      renderIt()
      await fill('Old-Password-1!', 'Correct-Horse-9!', 'Correct-Horse-9!')
      expect(await screen.findByText('Password changed. 2 other device(s) were signed out.')).toBeInTheDocument()
      expect((screen.getByLabelText('Current password') as HTMLInputElement).value).toBe('')
      expect(JSON.parse(calls.find((c) => c.url === '/api/auth/change-password')!.body!)).toEqual({ current_password: 'Old-Password-1!', new_password: 'Correct-Horse-9!' })
    })

    it('puts a wrong current password on that field', async () => {
      mockRoutes({ ...OWNER_ROUTES, 'POST /api/auth/change-password': () => err(403, 'WRONG_PASSWORD', 'The current password is not correct.') })
      renderIt()
      await fill('Nope-Nope-123!', 'Correct-Horse-9!', 'Correct-Horse-9!')
      expect(await screen.findByText('The current password is not correct.')).toBeInTheDocument()
      expect(screen.getByLabelText('Current password')).toHaveFocus()
    })

    it('puts a repeated password on the new-password field', async () => {
      mockRoutes({ ...OWNER_ROUTES, 'POST /api/auth/change-password': () => err(422, 'SAME_PASSWORD', 'Choose a password you have not just used.') })
      renderIt()
      await fill('Correct-Horse-9!', 'Correct-Horse-9!', 'Correct-Horse-9!')
      expect(await screen.findByText(/Choose a password you have not just used/)).toBeInTheDocument()
      expect(screen.getByLabelText('New password')).toHaveFocus()
    })
  })

  describe('signed-in devices', () => {
    it('marks this device, shows when each session ends, and signs another one out', async () => {
      const { calls } = mockRoutes({ ...OWNER_ROUTES, 'DELETE /api/auth/sessions/other': { ok: true, current: false } })
      renderIt()
      const row = (await screen.findByText('Firefox on Android')).closest('tr')!
      expect(within(screen.getByText('Chrome on Windows').closest('tr')!).getByText('This device')).toBeInTheDocument()
      expect(within(row).getByText('Kept signed in')).toBeInTheDocument()
      await userEvent.click(within(row).getByRole('button', { name: 'Sign out Firefox on Android' }))
      expect(await screen.findByText('That device was signed out.')).toBeInTheDocument()
      expect(calls.filter((c) => c.method === 'DELETE').map((c) => c.url)).toEqual(['/api/auth/sessions/other'])
      expect(calls.filter((c) => c.url === '/api/auth/sessions').length).toBeGreaterThanOrEqual(2)       // list reloaded
    })

    it('signing out of this device leaves the app and goes to the landing page', async () => {
      mockRoutes({ ...OWNER_ROUTES, 'DELETE /api/auth/sessions/cur': { ok: true, current: true } })
      const { signOut } = renderIt()
      await userEvent.click(await screen.findByRole('button', { name: 'Sign out of this device' }))
      await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/'))
      expect(signOut).toHaveBeenCalledTimes(1)
    })

    it('can sign out every other device at once', async () => {
      const { calls } = mockRoutes({ ...OWNER_ROUTES, 'POST /api/auth/sessions/revoke-others': { signed_out: 1 } })
      renderIt()
      await userEvent.click(await screen.findByRole('button', { name: 'Sign out all other devices' }))
      expect(await screen.findByText('1 device(s) signed out.')).toBeInTheDocument()
      expect(calls.some((c) => c.url === '/api/auth/sessions/revoke-others')).toBe(true)
    })

    it('does not offer "sign out all other devices" when there is only this one', async () => {
      mockRoutes({ ...OWNER_ROUTES, 'GET /api/auth/sessions': [DEVICES[0]] })
      renderIt()
      await screen.findByText('Chrome on Windows')
      expect(screen.queryByRole('button', { name: 'Sign out all other devices' })).toBeNull()
    })
  })

  describe('team and messages (owner)', () => {
    it('lets the owner turn staff off, but never the owner row', async () => {
      const { calls } = mockRoutes({ ...OWNER_ROUTES, 'POST /api/auth/users/2/active': { ...STAFF_USER, is_active: false } })
      renderIt()
      const staffRow = (await screen.findByText('Meena Shah')).closest('tr')!
      const ownerRow = screen.getAllByText('Ramesh Patel').map((n) => n.closest('tr')).find((r) => r && within(r).queryByText('Owner'))!
      expect(within(ownerRow).queryByRole('button')).toBeNull()
      await userEvent.click(within(staffRow).getByRole('button', { name: 'Turn off Meena Shah' }))
      expect(await screen.findByText('Account turned off and signed out.')).toBeInTheDocument()
      expect(JSON.parse(calls.find((c) => c.url === '/api/auth/users/2/active')!.body!)).toEqual({ active: false })
    })

    it('marks a contact message as handled', async () => {
      const { calls } = mockRoutes({ ...OWNER_ROUTES, 'POST /api/contact/messages/7/handled': { ok: true } })
      renderIt()
      expect(await screen.findByText('1 waiting for a reply')).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'Mark as handled' }))
      await waitFor(() => expect(calls.some((c) => c.url === '/api/contact/messages/7/handled')).toBe(true))
    })

    it('shows an empty state with directions when nobody has written in', async () => {
      mockRoutes({ ...OWNER_ROUTES, 'GET /api/contact/messages': [] })
      renderIt()
      expect(await screen.findByText('No messages yet')).toBeInTheDocument()
    })
  })

  it('the header Sign out button signs out and returns to the landing page', async () => {
    mockRoutes(OWNER_ROUTES)
    const { signOut } = renderIt()
    await userEvent.click((await screen.findAllByRole('button', { name: 'Sign out' }))[0])
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/'))
    expect(signOut).toHaveBeenCalledTimes(1)
  })

  it('shows a retry note when the device list cannot be loaded', async () => {
    mockRoutes({ ...OWNER_ROUTES, 'GET /api/auth/sessions': () => err(500, 'INTERNAL', 'Something went wrong.') })
    renderIt()
    expect(await screen.findAllByRole('button', { name: /Try again|Retry/ })).not.toHaveLength(0)
  })
})
