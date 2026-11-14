import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import NoiseLab from './NoiseLab'
import { ToastProvider } from '../components/Toast'
import { json } from '../test/fixtures'

afterEach(() => vi.unstubAllGlobals())

describe('NoiseLab', () => {
  it('builds a condition list, caps it, and blocks the run until a clip and a key exist', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json({ status: 'ok', db: 'ok', products: 65, gnani_configured: false, version: '1', store_name: 's' })))
    render(<ToastProvider><NoiseLab /></ToastProvider>)
    expect(screen.getByText(/stress test, not a field measurement/)).toBeInTheDocument()
    const run = screen.getByRole('button', { name: /Run on Gnani Prisma \(1 call\)/ })
    expect(run).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Add this condition' }))
    expect(screen.getByText('Crowd at 10 dB')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '0 dB' }))
    await userEvent.click(screen.getByRole('button', { name: 'Add this condition' }))
    await userEvent.click(screen.getByRole('button', { name: 'Add phone line only' }))
    expect(screen.getByRole('button', { name: /Run on Gnani Prisma \(4 calls\)/ })).toBeDisabled()
    await waitFor(() => expect(screen.getByText('Add your Gnani key in Settings first')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Add this condition' }))   // duplicate
    expect(screen.getAllByText('Crowd at 0 dB')).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: 'Remove Crowd at 0 dB' }))
    expect(screen.queryByText('Crowd at 0 dB')).toBeNull()
  })
})
