import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SignUp from './SignUp'
import { AuthProvider } from '../../lib/auth'
import { csrfToken } from '../../api/client'
import { AUTH_CONFIG, USER, err, mockRoutes } from '../../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); csrfToken.set(null) })
const Where = () => { const l = useLocation(); return <div data-testid="where">{l.pathname}</div> }
const VISITOR = { 'GET /api/auth/session': { authenticated: false }, 'GET /api/auth/config': { ...AUTH_CONFIG, has_owner: false } }
const renderIt = () => render(<MemoryRouter initialEntries={['/sign-up']}><AuthProvider><Routes>
  <Route path="/sign-up" element={<SignUp />} /><Route path="*" element={<><h1>Landed</h1><Where /></>} /></Routes></AuthProvider></MemoryRouter>)

async function fillAll(over: Partial<Record<'name' | 'email' | 'pw' | 'confirm', string>> = {}, terms = true) {
  const v = { name: 'Ramesh Patel', email: 'ramesh@example.com', pw: 'Correct-Horse-9!', confirm: 'Correct-Horse-9!', ...over }
  await userEvent.type(await screen.findByLabelText('Full name'), v.name)
  await userEvent.type(screen.getByLabelText('E-mail address'), v.email)
  await userEvent.type(screen.getByLabelText('Password'), v.pw)
  await userEvent.type(screen.getByLabelText('Confirm password'), v.confirm)
  if (terms) await userEvent.click(screen.getByRole('checkbox', { name: /I accept the/ }))
}

describe('Sign up', () => {
  it('has every field labelled, links to the terms and privacy pages, and tells the first person they will be the owner', async () => {
    mockRoutes(VISITOR)
    renderIt()
    expect(await screen.findByRole('heading', { level: 1, name: 'Create your account' })).toBeInTheDocument()
    for (const l of ['Full name', 'E-mail address', 'Password', 'Confirm password']) expect(screen.getByLabelText(l)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Terms' })).toHaveAttribute('href', '/terms')
    expect(screen.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/privacy')
    expect(await screen.findByText(/this account will be the/)).toBeInTheDocument()
  })

  it('does not promise ownership when the server reserves it for a configured address', async () => {
    mockRoutes({ ...VISITOR, 'GET /api/auth/config': { ...AUTH_CONFIG, has_owner: false, owner_email_set: true } })
    renderIt()
    expect(await screen.findByText(/reserved for the e-mail address set by the person who installed it/)).toBeInTheDocument()
    expect(screen.queryByText(/this account will be the/)).toBeNull()
  })

  it('updates a strength meter and the rule list as the password is typed', async () => {
    mockRoutes(VISITOR)
    renderIt()
    await userEvent.type(await screen.findByLabelText('Password'), 'abc')
    expect(screen.getByRole('img', { name: 'Password strength: Too short' })).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Password'))
    await userEvent.type(screen.getByLabelText('Password'), 'Correct-Horse-9!-and-more')
    expect(screen.getByRole('img', { name: 'Password strength: Strong' })).toBeInTheDocument()
    expect(screen.getByText('At least 10 characters').closest('li')).toHaveClass('ok')
  })

  it('reports every kind of mistake next to its field, without calling the server', async () => {
    const { calls } = mockRoutes(VISITOR)
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Enter your full name (2 to 80 characters).')).toBeInTheDocument()
    expect(screen.getByLabelText('Full name')).toHaveFocus()
    await fillAll({ name: 'Ramesh', email: 'nope', pw: 'short', confirm: 'different' }, false)
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Enter a valid e-mail address.')).toBeInTheDocument()
    expect(screen.getByText('Use at least 10 characters.')).toBeInTheDocument()
    expect(screen.getByText('The two passwords do not match.')).toBeInTheDocument()
    expect(screen.getByText('Accept the Terms and Privacy Policy to continue.')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/api/auth/signup')).toBe(false)
  })

  it('creates the account, signs the person in and shows a success screen with the right role wording', async () => {
    const { calls } = mockRoutes({ ...VISITOR, 'POST /api/auth/signup': { verification_required: false, user: USER, csrf_token: 'c9' } })
    renderIt()
    await fillAll()
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('heading', { name: 'Your account is ready' })).toBeInTheDocument()
    expect(screen.getByText(/signed in as the shop owner/)).toBeInTheDocument()
    expect(JSON.parse(calls.find((c) => c.url === '/api/auth/signup')!.body!)).toEqual({
      full_name: 'Ramesh Patel', email: 'ramesh@example.com', password: 'Correct-Horse-9!', confirm_password: 'Correct-Horse-9!', accept_terms: true })
    expect(csrfToken.get()).toBe('c9')
    await userEvent.click(screen.getByRole('button', { name: 'Open the dashboard' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/dashboard'))
  })

  it('tells staff what staff can and cannot do', async () => {
    mockRoutes({ ...VISITOR, 'POST /api/auth/signup': { verification_required: false, user: { ...USER, role: 'staff' }, csrf_token: 'c9' } })
    renderIt()
    await fillAll()
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText(/Only the owner can change stock, prices and settings/)).toBeInTheDocument()
  })

  it('asks the person to check their inbox when e-mail confirmation is on, and does not sign them in', async () => {
    const { calls } = mockRoutes({ ...VISITOR, 'POST /api/auth/signup': { verification_required: true, user: null, csrf_token: null, email: 'ramesh@example.com' },
      'POST /api/auth/resend-verification': { ok: true, message: 'If that address is waiting to be confirmed, a new link is on its way.' } })
    renderIt()
    await fillAll()
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('heading', { name: 'Check your inbox' })).toBeInTheDocument()
    expect(screen.getByText('ramesh@example.com')).toBeInTheDocument()
    expect(csrfToken.get()).toBe('')
    await userEvent.click(screen.getByRole('button', { name: 'Send the link again' }))
    expect(await screen.findByText(/a new link is on its way/)).toBeInTheDocument()
    expect(calls.filter((c) => c.url.includes('resend')).length).toBe(1)
  })

  it.each([
    ['EMAIL_TAKEN', 'An account with this e-mail address already exists.', 'E-mail address'],
    ['WEAK_PASSWORD', 'That password is too common. Pick something less guessable.', 'Password'],
    ['BAD_NAME', 'Enter your full name.', 'Full name'],
  ])('puts the server error %s next to the field it is about', async (code, message, label) => {
    mockRoutes({ ...VISITOR, 'POST /api/auth/signup': () => err(code === 'EMAIL_TAKEN' ? 409 : 422, code, message) })
    renderIt()
    await fillAll()
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(screen.getByLabelText(label)).toHaveFocus()
    expect(screen.getByLabelText(label)).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows a closed notice when the server has turned sign-up off', async () => {
    mockRoutes({ ...VISITOR, 'GET /api/auth/config': { ...AUTH_CONFIG, signup_open: false } })
    renderIt()
    expect(await screen.findByRole('heading', { name: 'Sign-up is closed' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).toBeNull()
  })
})
