import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { UpiQr } from './UpiQr'
import type { UpiInstructions } from '../../types'

const manual: UpiInstructions = {
  mode: 'manual', verified_by_provider: false, uri: 'upi://pay?pa=patelstore%40okhdfcbank&pn=Patel&am=172.00&cu=INR&tn=Bill%20SW-1&tr=PAY-1', qr_image_url: null,
  payee: 'patelstore@okhdfcbank', amount_paise: 17200, reference: 'PAY-261111-0007', order_code: 'SW-261111-0012', instructions: 'Ask the customer to scan the code.',
}

describe('UpiQr', () => {
  it('draws a QR from the payment link and writes the amount, order and reference beside it', () => {
    const { container } = render(<UpiQr upi={manual} />)
    expect(screen.getByRole('img', { name: /UPI QR code for ₹172, order SW-261111-0012/ })).toBeInTheDocument()
    expect(container.querySelector('svg path')?.getAttribute('d')?.length).toBeGreaterThan(200)
    expect(screen.getByText('₹172')).toBeInTheDocument()
    expect(screen.getByText('PAY-261111-0007')).toBeInTheDocument()
    expect(screen.getByText('patelstore@okhdfcbank')).toBeInTheDocument()
  })
  it('says plainly that a shop QR is not verified', () => {
    render(<UpiQr upi={manual} />)
    expect(screen.getByText('Not verified: a person must confirm')).toBeInTheDocument()
    expect(screen.queryByText(/Razorpay confirms/)).not.toBeInTheDocument()
  })
  it('shows a provider QR as an image from the provider and says the provider confirms it', () => {
    render(<UpiQr upi={{ ...manual, mode: 'provider', verified_by_provider: true, uri: null, qr_image_url: 'https://rzp.example/qr.png', payee: null }} />)
    expect(screen.getByRole('img', { name: /UPI QR code/ })).toHaveAttribute('src', 'https://rzp.example/qr.png')
    expect(screen.getByText('Razorpay confirms this payment')).toBeInTheDocument()
  })
  it('does not invent a QR when there is nothing to encode', () => {
    render(<UpiQr upi={{ ...manual, uri: null }} />)
    expect(screen.getByText('No QR could be made.')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
