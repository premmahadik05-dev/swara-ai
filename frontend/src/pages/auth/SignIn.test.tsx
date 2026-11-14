import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SignIn from './SignIn'
import { AuthProvider } from '../../lib/auth'
import { csrfToken } from '../../api/client'
import { AUTH_CONFIG, USER, err, mockRoutes } from '../../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); csrfToken.set(null) })
const Where = () => { const l = useLocation(); return <div data-testid="where">{l.pathname}{l.search}</div> }
const VISITOR = { 'GET /api/auth/session': { authenticated: false }, 'GET /api/auth/config': AUTH_CONFIG }

function renderIt(path = '/sign-in', state?: unknown) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: path.split('?')[0], search: path.includes('?') ? '?' + path.split('?')[1] : '', state }]}>
      <AuthProvider><Routes>
        <Route path="/sign-in" element={<SignIn />} />
        <Route path="*" element={<><h1>Landed</h1><Where /></>} />
      </Routes></AuthProvider>
    </MemoryRouter>,
  )
}
const fill = async (email: string, password: string) => {
  await userEvent.type(await screen.findByLabelText('E-mail address'), email)
  await userEvent.type(screen.getByLabelText('Password'), password)
}

describe('Sign in', () => {
  it('has labelled fields, a show/hide button, remember me and a forgot-password link', async () => {
    mockRoutes(VISITOR)
    renderIt()
    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeInTheDocument()
    const pw = screen.getByLabelText('Password') as HTMLInputElement
    expect(pw.type).toBe('password')
    expect(pw).toHaveAttribute('autocomplete', 'current-password')
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(pw.type).toBe('text')
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('checkbox', { name: /Keep me signed in/ })).not.toBeChecked()
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', '/forgot-password')
    expect(screen.getByRole('link', { name: 'Create an account' })).toHaveAttribute('href', '/sign-up')
  })

  it('checks the fields before calling the server and puts focus on the first problem', async () => {
    const { calls } = mockRoutes(VISITOR)
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Enter the e-mail address you signed up with.')).toBeInTheDocument()
    expect(screen.getByLabelText('E-mail address')).toHaveFocus()
    expect(screen.getByLabelText('E-mail address')).toHaveAttribute('aria-invalid', 'true')
    await userEvent.type(screen.getByLabelText('E-mail address'), 'ramesh@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Enter your password.')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toHaveFocus()
    expect(calls.some((c) => c.url === '/api/auth/login')).toBe(false)
  })

  it('signs in, sends the right body, and lands on the page the person was heading for', async () => {
    const { calls } = mockRoutes({ ...VISITOR, 'POST /api/auth/login': { user: USER, csrf_token: 'c1' } })
    renderIt('/sign-in?next=%2Forders%3Fopen%3D3')
    await fill('  Ramesh@Example.com ', 'Correct-Horse-9!')
    await userEvent.click(screen.getByRole('checkbox', { name: /Keep me signed in/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/orders?open=3'))
    expect(JSON.parse(calls.find((c) => c.url === '/api/auth/login')!.body!)).toEqual({ email: 'Ramesh@Example.com', password: 'Correct-Horse-9!', remember: true })
    expect(csrfToken.get()).toBe('c1')
  })

  it('ignores a ?next= that points off-site', async () => {
    mockRoutes({ ...VISITOR, 'POST /api/auth/login': { user: USER, csrf_token: 'c1' } })
    renderIt('/sign-in?next=https%3A%2F%2Fevil.example')
    await fill('ramesh@example.com', 'Correct-Horse-9!')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/dashboard'))
  })

  it('shows one plain message for a wrong password, clears the password and puts focus back on it', async () => {
    mockRoutes({ ...VISITOR, 'POST /api/auth/login': () => err(401, 'INVALID_CREDENTIALS', 'Incorrect e-mail or password.') })
    renderIt()
    await fill('ramesh@example.com', 'Wrong-Password-1!')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect e-mail or password.')
    expect((screen.getByLabelText('Password') as HTMLInputElement).value).toBe('')
    expect(screen.getByLabelText('Password')).toHaveFocus()
    expect(screen.getByLabelText('E-mail address')).toHaveValue('ramesh@example.com')
  })

  it('disables the button and says what is happening while the request runs', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((r) => { release = r })
    mockRoutes({ ...VISITOR, 'POST /api/auth/login': async () => { await gate; return { user: USER, csrf_token: 'c1' } } })
    renderIt()
    await fill('ramesh@example.com', 'Correct-Horse-9!')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    const busy = await screen.findByRole('button', { name: 'Signing in…' })
    expect(busy).toBeDisabled()
    expect(busy).toHaveAttribute('aria-busy', 'true')
    release()
  })

  it('shows the lock-out message from the server', async () => {
    mockRoutes({ ...VISITOR, 'POST /api/auth/login': () => err(429, 'TOO_MANY_ATTEMPTS', 'Too many failed attempts. Try again in 15 minute(s).', { retry_after_s: 900 }) })
    renderIt()
    await fill('ramesh@example.com', 'Wrong-Password-1!')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText(/Too many failed attempts/)).toBeInTheDocument()
  })

  it('offers to resend the link when the e-mail address is not confirmed yet', async () => {
    const { calls } = mockRoutes({
      ...VISITOR, 'POST /api/auth/login': () => err(403, 'EMAIL_NOT_VERIFIED', 'Confirm your e-mail address first.'),
      'POST /api/auth/resend-verification': { ok: true, message: 'If that address is waiting to be confirmed, a new link is on its way.' },
    })
    renderIt()
    await fill('ramesh@example.com', 'Correct-Horse-9!')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Send the link again' }))
    expect(await screen.findByText(/a new link is on its way/)).toBeInTheDocument()
    expect(JSON.parse(calls.find((c) => c.url === '/api/auth/resend-verification')!.body!)).toEqual({ email: 'ramesh@example.com' })
  })

  it('explains an ended session when the person was sent back here', async () => {
    mockRoutes(VISITOR)
    renderIt('/sign-in?next=%2Forders', { expired: true })
    expect(await screen.findByText(/Your session has ended, so you were signed out/)).toBeInTheDocument()
  })

  it('does not show the form to someone who is already signed in', async () => {
    mockRoutes({ 'GET /api/auth/session': { authenticated: true, user: USER, csrf_token: 'c', session: { id: 'a', expires_at: 'x', remember: false } }, 'GET /api/auth/config': AUTH_CONFIG })
    renderIt('/sign-in?next=%2Forders')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/orders'))
  })

  it('says sign-up is closed instead of inviting people to create an account', async () => {
    mockRoutes({ ...VISITOR, 'GET /api/auth/config': { ...AUTH_CONFIG, signup_open: false } })
    renderIt()
    expect(await screen.findByText(/Sign-up is closed on this server/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Create an account' })).toBeNull()
  })

  it('tells the person when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('x')))
    renderIt()
    expect(await screen.findByText(/Cannot reach the SWARA AI server/)).toBeInTheDocument()
  })
})
