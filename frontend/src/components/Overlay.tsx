import { useEffect, useId, useRef, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { Button } from './ui'

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Keeps Tab inside the overlay, puts focus in it when it opens and gives it back to the trigger when it closes. */
function useFocusTrap(ref: RefObject<HTMLElement>, onClose: () => void) {
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const node = ref.current
    if (!node) return
    const previous = document.activeElement as HTMLElement | null
    const first = node.querySelector<HTMLElement>('[data-autofocus]') ?? node.querySelector<HTMLElement>('input, select, textarea') ?? node.querySelector<HTMLElement>(FOCUSABLE)
    ;(first ?? node).focus()
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); closeRef.current(); return }
      if (e.key !== 'Tab') return
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null || el === document.activeElement)
      if (!items.length) { e.preventDefault(); return }
      const a = items[0], z = items[items.length - 1]
      if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus() }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus() }
    }
    node.addEventListener('keydown', onKey)
    return () => {
      node.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
      if (previous && document.contains(previous)) previous.focus()
    }
  }, [ref])
}

interface OverlayProps { title: string; subtitle?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; role?: 'dialog' | 'alertdialog' }

function Overlay({ kind, title, subtitle, onClose, children, footer, role = 'dialog' }: OverlayProps & { kind: 'dialog' | 'drawer' }) {
  const ref = useRef<HTMLDivElement>(null)
  const id = useId()
  const bodyId = useId()
  useFocusTrap(ref, onClose)
  return createPortal(
    <>
      <div className="scrim" onMouseDown={onClose} aria-hidden />
      <div ref={ref} className={kind} role={role} aria-modal="true" aria-labelledby={id} aria-describedby={role === 'alertdialog' ? bodyId : undefined} tabIndex={-1}>
        <div className="ov-head">
          <div className="grow"><h2 id={id}>{title}</h2>{subtitle && <div className="muted small" style={{ marginTop: 2 }}>{subtitle}</div>}</div>
          <Button variant="ghost" size="sm" iconOnly icon="x" aria-label="Close" onClick={onClose} />
        </div>
        <div className="ov-body" id={bodyId}>{children}</div>
        {footer && <div className="ov-foot">{footer}</div>}
      </div>
    </>,
    document.body,
  )
}

export const Dialog = (p: OverlayProps) => <Overlay kind="dialog" {...p} />
export const Drawer = (p: OverlayProps) => <Overlay kind="drawer" {...p} />
/** Older pages call this `Modal`. */
export const Modal = Dialog

/** Confirmation for destructive actions: says what will happen and names the consequence. */
export function ConfirmDialog({ title, body, confirmLabel, tone = 'danger', busy, onConfirm, onClose }: {
  title: string; body: ReactNode; confirmLabel: string; tone?: 'danger' | 'primary'; busy?: boolean; onConfirm: () => void; onClose: () => void
}) {
  return (
    <Dialog role="alertdialog" title={title} onClose={onClose} footer={<>
      <Button variant="secondary" onClick={onClose} disabled={busy}>Keep it</Button>
      <Button variant={tone === 'danger' ? 'solid-danger' : 'primary'} onClick={onConfirm} loading={busy} data-autofocus>{confirmLabel}</Button>
    </>}>
      <div className="muted">{body}</div>
    </Dialog>
  )
}
