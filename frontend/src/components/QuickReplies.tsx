import type { PendingInfo } from '../types'

const YES_NO = new Set(['confirm_partial', 'confirm_suggestion', 'confirm_unit'])
const AMOUNT = new Set(['need_qty', 'need_unit', 'need_pack_count', 'need_whole', 'unit_wrong'])

/** Tap-to-answer chips for the assistant's follow-up question. Each chip sends the same text a customer would say. */
export function QuickReplies({ pending, awaiting, onSend, disabled }: {
  pending: PendingInfo | null
  awaiting: string | null
  onSend: (text: string) => void
  disabled?: boolean
}) {
  let title = ''
  let items: { label: string; text: string }[] = []
  if (pending?.kind === 'choose_product') {
    title = `Which ${pending.product ?? 'item'}?`
    items = pending.options.map((o) => ({ label: o.name, text: o.name }))
  } else if (pending && YES_NO.has(pending.kind)) {
    title = 'Please answer'
    items = [{ label: 'Yes', text: 'yes' }, { label: 'No', text: 'no' }]
  } else if (pending && AMOUNT.has(pending.kind)) {
    return <div className="note warn small">Say or type the amount{pending.product ? ` for ${pending.product}` : ''}, for example "2 kg", "half kilo" or "teen".</div>
  } else if (awaiting === 'confirm_order') {
    title = 'Place this order?'
    items = [{ label: 'Yes, confirm', text: 'yes' }, { label: 'Add more', text: 'no, add more' }, { label: 'Cancel order', text: 'cancel' }]
  } else if (awaiting === 'more_items') {
    title = 'Anything else?'
    items = [{ label: "That's all", text: 'bas itna hi' }]
  }
  if (!items.length) return null
  return (
    <div className="stack" aria-label="Quick replies">
      <div className="label">{title}</div>
      <div className="quick">
        {items.map((i) => (<button key={i.label} disabled={disabled} onClick={() => onSend(i.text)}>{i.label}</button>))}
      </div>
    </div>
  )
}
