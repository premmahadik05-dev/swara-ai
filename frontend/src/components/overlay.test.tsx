import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog, Drawer } from './Overlay'

function Host({ onConfirm = () => undefined }: { onConfirm?: () => void }) {
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open drawer</button>
      {open && (
        <Drawer title="Details" onClose={() => setOpen(false)} footer={<button onClick={() => setConfirm(true)}>Delete</button>}>
          <input aria-label="First field" />
          <input aria-label="Second field" />
        </Drawer>
      )}
      {confirm && <ConfirmDialog title="Delete it?" body="This cannot be undone." confirmLabel="Delete" onClose={() => setConfirm(false)} onConfirm={onConfirm} />}
    </div>
  )
}

describe('Overlay', () => {
  it('moves focus into the drawer, keeps Tab inside it, and gives focus back to the trigger on Escape', async () => {
    render(<Host />)
    const trigger = screen.getByRole('button', { name: 'Open drawer' })
    await userEvent.click(trigger)
    const dlg = screen.getByRole('dialog', { name: 'Details' })
    expect(dlg).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByLabelText('First field')).toHaveFocus()
    for (let i = 0; i < 6; i++) { await userEvent.tab(); expect(dlg.contains(document.activeElement)).toBe(true) }
    await userEvent.tab({ shift: true })
    expect(dlg.contains(document.activeElement)).toBe(true)
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(trigger).toHaveFocus()
  })

  it('stops the page behind from scrolling while open and restores it after', async () => {
    render(<Host />)
    await userEvent.click(screen.getByRole('button', { name: 'Open drawer' }))
    expect(document.body.style.overflow).toBe('hidden')
    await userEvent.keyboard('{Escape}')
    expect(document.body.style.overflow).not.toBe('hidden')
  })

  it('a destructive confirmation is an alert dialog that names its consequence and defaults to the safe exit', async () => {
    const onConfirm = vi.fn()
    render(<Host onConfirm={onConfirm} />)
    await userEvent.click(screen.getByRole('button', { name: 'Open drawer' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    const alert = screen.getByRole('alertdialog', { name: 'Delete it?' })
    expect(alert).toHaveAccessibleDescription('This cannot be undone.')
    expect(onConfirm).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Keep it' }))
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
