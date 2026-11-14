import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ForgotPassword from './ForgotPassword'
import ResetPassword from './ResetPassword'
import VerifyEmail from './VerifyEmail'
import { AUTH_CONFIG, err, mockRoutes } from '../../test/fixtures'

afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, '', '/') })
const at = (el: React.ReactNode, path: string) => { window.history.replaceState(null, '', path); return render(<MemoryRouter><Routes><Route path="*" element={el} /></Routes></MemoryRouter>) }

describe('Forgot password', () => {
  it('sends the request and shows the server wording (which never says whether the account exists)', async () => {
    const { calls } = mockRoutes({ 'GET /api/auth/config': { ...AUTH_CONFIG, email_configured: true },
      'POST /api/auth/forgot': { email_configured: true, message: 'If that address has an account, a reset link is on its way. It works once and expires in 1 hour.' } })
    at(<ForgotPassword />, '/forgot-password')
    await userEvent.type(await screen.findByLabelText('E-mail address'), 'ramesh@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText(/If that address has an account/)).toBeInTheDocument()
    expect(JSON.parse(calls.find((c) => c.url === '/api/auth/forgot')!.body!)).toEqual({ email: 'ramesh@example.com' })
  })

  it('validates the address first', async () => {
    mockRoutes({ 'GET /api/auth/config': { ...AUTH_CONFIG, email_configured: true } })
    at(<ForgotPassword />, '/forgot-password')
    await userEvent.type(await screen.findByLabelText('E-mail address'), 'nope')
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText('Enter the e-mail address you signed up with.')).toBeInTheDocument()
  })

  it('does not pretend: when the server cannot send e-mail it says so and shows the real fallback instead of a form', async () => {
    mockRoutes({ 'GET /api/auth/config': { ...AUTH_CONFIG, email_configured: false } })
    at(<ForgotPassword />, '/forgot-password')
    expect(await screen.findByText(/not set up to send e-mail, so a reset link cannot be sent/)).toBeInTheDocument()
    expect(screen.getByText(/auth_admin.py reset-password/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send reset link' })).toBeNull()
  })
})

describe('Reset password', () => {
  it('takes the token out of the address bar, checks the new password, and shows success', async () => {
    const { calls } = mockRoutes({ 'POST /api/auth/reset': { ok: true } })
    at(<ResetPassword />, '/reset-password?token=abcdefghij1234567890')
    expect(window.location.search).toBe('')                                // gone from the URL (and so from history and Referer)
    await userEvent.type(await screen.findByLabelText('New password'), 'short')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText('Use at least 10 characters.')).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('New password'))
    await userEvent.clear(screen.getByLabelText('Confirm new password'))
    await userEvent.type(screen.getByLabelText('New password'), 'Correct-Horse-9!')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'Correct-Horse-9!')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByRole('heading', { name: 'Password changed' })).toBeInTheDocument()
    expect(JSON.parse(calls.find((c) => c.url === '/api/auth/reset')!.body!)).toEqual({ token: 'abcdefghij1234567890', password: 'Correct-Horse-9!', confirm_password: 'Correct-Horse-9!' })
  })

  it('points to a new link when the token is expired or used', async () => {
    mockRoutes({ 'POST /api/auth/reset': () => err(400, 'INVALID_TOKEN', 'This link is invalid or has expired. Request a new one.') })
    at(<ResetPassword />, '/reset-password?token=abcdefghij1234567890')
    await userEvent.type(await screen.findByLabelText('New password'), 'Correct-Horse-9!')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'Correct-Horse-9!')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText(/invalid or has expired/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Request a new link' })).toHaveAttribute('href', '/forgot-password')
  })

  it('explains a link that has no code', async () => {
    mockRoutes({})
    at(<ResetPassword />, '/reset-password')
    expect(await screen.findByText(/missing its code/)).toBeInTheDocument()
  })
})

describe('Verify e-mail', () => {
  it('uses the one-time link exactly once and confirms', async () => {
    const { calls } = mockRoutes({ 'POST /api/auth/verify-email': { ok: true } })
    at(<VerifyEmail />, '/verify-email?token=abcdefghij1234567890')
    expect(await screen.findByRole('heading', { name: 'E-mail confirmed' })).toBeInTheDocument()
    expect(calls.filter((c) => c.url === '/api/auth/verify-email').length).toBe(1)
    expect(window.location.search).toBe('')
  })
  it('reports a bad link plainly', async () => {
    mockRoutes({ 'POST /api/auth/verify-email': () => err(400, 'INVALID_TOKEN', 'This link is invalid or has expired.') })
    at(<VerifyEmail />, '/verify-email?token=abcdefghij1234567890')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Could not confirm your e-mail' })).toBeInTheDocument())
    expect(screen.getByText(/invalid or has expired/)).toBeInTheDocument()
  })
})
