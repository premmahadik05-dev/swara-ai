import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, RequireAuth, safeNext, useAuth, useSignOut } from './auth'
import { api, csrfToken, setUnauthorizedHandler } from '../api/client'
import { USER, err, json, mockRoutes } from '../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); csrfToken.set(null); setUnauthorizedHandler(null) })

const Where = () => { const l = useLocation(); return <div data-testid="where">{l.pathname}{l.search}{(l.state as { expired?: boolean } | null)?.expired ? ' expired' : ''}</div> }
const Who = () => { const a = useAuth(); return <div><span data-testid="status">{a.status}</span><span data-testid="name">{a.user?.full_name ?? '-'}</span><span data-testid="notice">{a.notice ?? '-'}</span><span data-testid="boot">{a.bootError ?? '-'}</span></div> }

const renderApp = (path = '/dashboard') => render(
  <MemoryRouter initialEntries={[path]}>
    <AuthProvider>
      <Routes>
        <Route path="/sign-in" element={<><h1>Sign in page</h1><Where /><Who /></>} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<><h1>Dashboard page</h1><Who /></>} />
          <Route path="/orders" element={<><h1>Orders page</h1><Who /></>} />
        </Route>
      </Routes>
    </AuthProvider>
  </MemoryRouter>,
)

describe('safeNext', () => {
  it('allows same-site paths and refuses anything that could leave the site or loop', () => {
    expect(safeNext('/orders?open=3')).toBe('/orders?open=3')
    expect(safeNext('/analytics')).toBe('/analytics')
    for (const bad of ['https://evil.example', '//evil.example', '/\\evil.example', 'javascript:alert(1)', 'orders', '', null, undefined, '/sign-in', '/sign-up?x=1', '/reset-password']) {
      expect(safeNext(bad as string | null)).toBe('/dashboard')
    }
    expect(safeNext('//evil.example', '/x')).toBe('/x')
  })
})

describe('AuthProvider and RequireAuth', () => {
  it('sends a visitor to sign in, remembering where they were going', async () => {
    mockRoutes({ 'GET /api/auth/session': { authenticated: false } })
    renderApp('/orders?open=3')
    expect(await screen.findByRole('heading', { name: 'Sign in page' })).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('/sign-in?next=%2Forders%3Fopen%3D3')
  })

  it('shows the page, and keeps the CSRF token in memory only, when the cookie is valid', async () => {
    mockRoutes({ 'GET /api/auth/session': { authenticated: true, user: USER, csrf_token: 'tok-1', session: { id: 'a', expires_at: '2026-11-11T00:00:00Z', remember: false } } })
    renderApp('/dashboard')
    expect(await screen.findByRole('heading', { name: 'Dashboard page' })).toBeInTheDocument()
    expect(screen.getByTestId('name')).toHaveTextContent('Ramesh Patel')
    expect(csrfToken.get()).toBe('tok-1')
    expect(localStorage.length + sessionStorage.length).toBe(0)
  })

  it('shows a checking state, not the page, while it finds out', () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise(() => undefined)))
    renderApp('/dashboard')
    expect(screen.getByRole('status')).toHaveTextContent(/Checking your session/)
    expect(screen.queryByRole('heading', { name: 'Dashboard page' })).toBeNull()
  })

  it('treats an unreachable server as signed out and says why', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('x')))
    renderApp('/sign-in')
    await waitFor(() => expect(screen.getByTestId('boot')).toHaveTextContent(/Cannot reach the SWARA AI server/))
    expect(screen.getByTestId('status')).toHaveTextContent('out')
  })

  it('moves a signed-in person to the sign-in page, with an expiry notice, when any call says the session ended', async () => {
    mockRoutes({
      'GET /api/auth/session': { authenticated: true, user: USER, csrf_token: 'tok-1', session: { id: 'a', expires_at: 'x', remember: false } },
      'GET /api/orders': () => err(401, 'SESSION_EXPIRED', 'Your session has ended.'),
    })
    renderApp('/dashboard')
    await screen.findByRole('heading', { name: 'Dashboard page' })
    await expect(api.orders({})).rejects.toMatchObject({ status: 401 })
    expect(await screen.findByRole('heading', { name: 'Sign in page' })).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('/sign-in?next=%2Fdashboard expired')
    expect(csrfToken.get()).toBe('')       // the old token is gone
  })

  it('signs out: tells the server, forgets the user and the token', async () => {
    const { calls } = mockRoutes({
      'GET /api/auth/session': { authenticated: true, user: USER, csrf_token: 'tok-1', session: { id: 'a', expires_at: 'x', remember: false } },
      'POST /api/auth/logout': { ok: true },
    })
    const Out = () => { const a = useAuth(); return <button onClick={() => a.signOut()}>out</button> }
    render(<MemoryRouter><AuthProvider><Out /><Who /></AuthProvider></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('in'))
    await userEvent.click(screen.getByText('out'))
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('out'))
    expect(calls.find((c) => c.method === 'POST')?.url).toBe('/api/auth/logout')
    expect(csrfToken.get()).toBe('')
    expect(screen.getByTestId('notice')).toHaveTextContent('-')       // a chosen sign-out is not an "expired" notice
  })

  it('signing out of a protected page lands on the home page, not on a sign-in page that remembers it', async () => {
    mockRoutes({
      'GET /api/auth/session': { authenticated: true, user: USER, csrf_token: 'tok-1', session: { id: 'a', expires_at: 'x', remember: false } },
      'POST /api/auth/logout': { ok: true },
    })
    const Leave = () => { const out = useSignOut(); return <button onClick={() => { void out() }}>leave</button> }
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<><h1>Home page</h1><Where /></>} />
            <Route path="/sign-in" element={<><h1>Sign in page</h1><Where /></>} />
            <Route element={<RequireAuth />}><Route path="/dashboard" element={<><h1>Dashboard page</h1><Leave /></>} /></Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )
    await userEvent.click(await screen.findByText('leave'))
    expect(await screen.findByRole('heading', { name: 'Home page' })).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/$/)
  })

  it('still signs the browser out when the server cannot be reached', async () => {
    let n = 0
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (u: string) => {
      if (u.includes('/auth/session') && n++ === 0) return json({ authenticated: true, user: USER, csrf_token: 't', session: { id: 'a', expires_at: 'x', remember: false } })
      throw new TypeError('offline')
    }))
    const Out = () => { const a = useAuth(); return <button onClick={() => a.signOut()}>out</button> }
    render(<MemoryRouter><AuthProvider><Out /><Who /></AuthProvider></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('in'))
    await userEvent.click(screen.getByText('out'))
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('out'))
  })
})
