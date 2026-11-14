import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { QuickReplies } from './QuickReplies'
import type { PendingInfo } from '../types'

const pending = (kind: string, extra: Partial<PendingInfo> = {}): PendingInfo => ({ kind, product: null, options: [], remaining: 0, ...extra })

describe('QuickReplies', () => {
  it('offers the candidate products when the shop must ask which one', async () => {
    const onSend = vi.fn()
    render(<QuickReplies pending={pending('choose_product', { product: 'dal', options: [{ id: 1, name: 'Toor Dal' }, { id: 2, name: 'Moong Dal' }] })} awaiting="choose_product" onSend={onSend} />)
    expect(screen.getByText('Which dal?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Moong Dal' }))
    expect(onSend).toHaveBeenCalledWith('Moong Dal')
  })

  it.each(['confirm_partial', 'confirm_suggestion', 'confirm_unit'])('shows yes/no for %s', async (kind) => {
    const onSend = vi.fn()
    render(<QuickReplies pending={pending(kind)} awaiting={null} onSend={onSend} />)
    await userEvent.click(screen.getByRole('button', { name: 'No' }))
    expect(onSend).toHaveBeenCalledWith('no')
  })

  it.each(['need_qty', 'need_unit', 'need_pack_count', 'need_whole', 'unit_wrong'])('does not show yes/no for the amount question %s', (kind) => {
    render(<QuickReplies pending={pending(kind, { product: 'Rice' })} awaiting={null} onSend={() => undefined} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText(/Say or type the amount for Rice/)).toBeInTheDocument()
  })

  it('offers confirm / add more / cancel at the end of an order, and a way to finish while collecting', async () => {
    const onSend = vi.fn()
    const { rerender } = render(<QuickReplies pending={null} awaiting="confirm_order" onSend={onSend} />)
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Yes, confirm', 'Add more', 'Cancel order'])
    await userEvent.click(screen.getByRole('button', { name: 'Add more' }))
    expect(onSend).toHaveBeenCalledWith('no, add more')
    rerender(<QuickReplies pending={null} awaiting="more_items" onSend={onSend} />)
    expect(screen.getByRole('button', { name: "That's all" })).toBeInTheDocument()
  })

  it('renders nothing when there is nothing to answer, and respects disabled', () => {
    const { container, rerender } = render(<QuickReplies pending={null} awaiting={null} onSend={() => undefined} />)
    expect(container).toBeEmptyDOMElement()
    rerender(<QuickReplies pending={null} awaiting="confirm_order" onSend={() => undefined} disabled />)
    screen.getAllByRole('button').forEach((b) => expect(b).toBeDisabled())
  })
})
