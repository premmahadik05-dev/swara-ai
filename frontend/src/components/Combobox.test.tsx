import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Combobox } from './Combobox'

type Item = { id: number; name: string }
const setup = (onSelect = vi.fn(), onWalkIn = vi.fn()) => {
  render(
    <Combobox<Item> label="Find a customer" placeholder="Search" initialLoad
      search={async (q) => (q ? [{ id: 7, name: 'Test Shopper' }] : [{ id: 1, name: 'Recent One' }])}
      itemKey={(c) => c.id} renderOption={(c) => <span>{c.name}</span>} onSelect={onSelect}
      extra={[{ key: 'walkin', node: <span>Walk-in customer</span>, onPick: onWalkIn }]} />,
  )
  return { onSelect, onWalkIn, box: screen.getByRole('combobox', { name: 'Find a customer' }) }
}

describe('Combobox keyboard use', () => {
  it('with a name typed, Enter picks the first match and not the pinned "Walk-in customer" row', async () => {
    const { box, onSelect, onWalkIn } = setup()
    await userEvent.type(box, 'tes')
    await screen.findByRole('option', { name: /Test Shopper/ })
    await userEvent.keyboard('{Enter}')
    expect(onSelect).toHaveBeenCalledWith({ id: 7, name: 'Test Shopper' })
    expect(onWalkIn).not.toHaveBeenCalled()
  })

  it('with nothing typed, the pinned row stays first so a person can still choose "Walk-in customer"', async () => {
    const { box, onSelect, onWalkIn } = setup()
    await userEvent.click(box)
    await screen.findByRole('option', { name: /Recent One/ })
    await userEvent.keyboard('{Enter}')
    expect(onWalkIn).toHaveBeenCalledTimes(1)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('arrow keys still reach the pinned row', async () => {
    const { box, onSelect, onWalkIn } = setup()
    await userEvent.type(box, 'tes')
    await screen.findByRole('option', { name: /Test Shopper/ })
    await userEvent.keyboard('{ArrowUp}{Enter}')
    expect(onWalkIn).toHaveBeenCalledTimes(1)
    expect(onSelect).not.toHaveBeenCalled()
  })
})
