import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PaymentsSettingsCard } from './PaymentsSettingsCard'
import { ToastProvider } from '../Toast'
import { json, mockRoutes, paymentConfig, settings } from '../../test/fixtures'
import type { PublicSettings } from '../../types'

afterEach(() => { vi.unstubAllGlobals() })
const withPayments = (p: PublicSettings['payments']): PublicSettings => ({ ...settings(), payments: p })
const renderIt = (s: PublicSettings, onSaved = vi.fn()) => render(<ToastProvider><PaymentsSettingsCard settings={s} onSaved={onSaved} /></ToastProvider>)

describe('PaymentsSettingsCard', () => {
  it('shows test mode and whether each secret is set, and never a secret', () => {
    const { container } = renderIt(withPayments(paymentConfig({ razorpay: true })))
    expect(screen.getByText('Test mode')).toBeInTheDocument()
    expect(screen.getByText('Razorpay is ready')).toBeInTheDocument()
    expect(screen.getByText('rzp_test_PLACEHOLDER01')).toBeInTheDocument()
    expect(screen.getAllByText('Set on the server (never shown)')).toHaveLength(2)
    expect(screen.getByText('http://localhost:8000/api/payments/webhooks/razorpay')).toBeInTheDocument()
    expect(container.querySelector('input[type="password"]')).toBeNull()   // keys are never typed here
    expect(container.textContent).not.toMatch(/rzp_(test|live)_[A-Za-z0-9]{20,}/)
  })

  it('says what is missing when Razorpay is not set up', () => {
    renderIt(withPayments(paymentConfig()))
    expect(screen.getByText('Razorpay is not set up')).toBeInTheDocument()
    expect(screen.getByText('Razorpay keys are not set.')).toBeInTheDocument()
    expect(screen.getByText('UPI QR needs a UPI ID')).toBeInTheDocument()
    expect(screen.getAllByText('Not set').length).toBeGreaterThanOrEqual(2)
  })

  it('warns loudly in live mode', () => {
    renderIt(withPayments({ ...paymentConfig({ razorpay: true }), mode: 'live' }))
    expect(screen.getByText('Live mode')).toBeInTheDocument()
    expect(screen.getByText(/Razorpay payments move real money/)).toBeInTheDocument()
  })

  it('checks the UPI ID shape, then saves it and the display name', async () => {
    const onSaved = vi.fn()
    const m = mockRoutes({ 'PUT /api/settings': () => settings() })
    renderIt(withPayments(paymentConfig()), onSaved)
    const id = screen.getByLabelText('Shop UPI ID')
    await userEvent.type(id, 'not a upi id')
    expect(screen.getByText(/does not look like a UPI ID/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save UPI details' })).toBeDisabled()
    await userEvent.clear(id)
    await userEvent.type(id, 'patelstore@okhdfcbank')
    await userEvent.type(screen.getByLabelText(/Name shown in the customer/), 'Patel Kirana')
    await userEvent.click(screen.getByRole('button', { name: 'Save UPI details' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(JSON.parse(m.calls[0].body!)).toEqual({ upi_vpa: 'patelstore@okhdfcbank', upi_payee_name: 'Patel Kirana' })
  })

  it('shows the server message when saving is refused', async () => {
    mockRoutes({ 'PUT /api/settings': () => json({ detail: { code: 'FORBIDDEN', message: 'Only the shop owner can change this.' } }, 403) })
    renderIt(withPayments(paymentConfig()))
    await userEvent.type(screen.getByLabelText('Shop UPI ID'), 'patelstore@okhdfcbank')
    await userEvent.click(screen.getByRole('button', { name: 'Save UPI details' }))
    expect(await screen.findByText('Only the shop owner can change this.')).toBeInTheDocument()
  })

  it('renders nothing for staff, who get no owner block from the server', () => {
    const { container } = renderIt(withPayments(paymentConfig({ owner: false })))
    expect(container.querySelector('.card')).toBeNull()
    expect(screen.queryByText('Payments')).not.toBeInTheDocument()
  })
})
