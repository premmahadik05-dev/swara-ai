import { useState } from 'react'
import { api } from '../api/client'
import type { Customer } from '../types'
import { Dialog } from './Overlay'
import { useToast } from './Toast'
import { LANG_META } from '../lib/languages'
import { Button, ErrorNote, Field } from './ui'

const LANGS: readonly (readonly [string, string])[] = [['', 'Not set'], ...LANG_META.map((l) => [l.key, l.name] as const)]

/** Create or edit a customer. Phone is optional and validated by the server too. */
export function CustomerForm({ initial, onDone, onClose }: { initial?: Customer; onDone: (c: Customer) => void; onClose: () => void }) {
  const { toast } = useToast()
  const [f, setF] = useState({ name: initial?.name ?? '', phone: initial?.phone ?? '', language: initial?.language ?? '', notes: initial?.notes ?? '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Error | null>(null)
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value })
  const phoneOk = /^[0-9+()\- ]{0,20}$/.test(f.phone)
  const valid = f.name.trim().length > 0 && phoneOk

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    setBusy(true); setErr(null)
    try {
      const body = { name: f.name.trim(), phone: f.phone.trim(), language: f.language, notes: f.notes.trim() }
      const saved = initial ? await api.patchCustomer(initial.id, body) : await api.createCustomer(body)
      toast(initial ? 'Customer updated.' : `${saved.name} added. Pick them on the Order desk to link their orders.`, 'ok')
      onDone(saved)
    } catch (e2) { setErr(e2 as Error) } finally { setBusy(false) }
  }
  return (
    <Dialog title={initial ? `Edit ${initial.name}` : 'New customer'} subtitle={initial?.is_synthetic ? 'Demo customer: a placeholder, not a real person.' : undefined} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="customer-form" loading={busy} disabled={!valid}>{initial ? 'Save changes' : 'Add customer'}</Button></>}>
      <form id="customer-form" className="stack sm" onSubmit={submit}>
        <ErrorNote error={err} />
        <Field label="Name" htmlFor="c-name"><input id="c-name" type="text" value={f.name} onChange={set('name')} maxLength={80} required data-autofocus /></Field>
        <div className="grid2">
          <Field label="Phone (optional)" htmlFor="c-phone" error={phoneOk ? null : 'Use digits, spaces, + ( ) or -'}><input id="c-phone" type="tel" inputMode="tel" value={f.phone} onChange={set('phone')} maxLength={20} aria-invalid={!phoneOk} /></Field>
          <Field label="Usually orders in" htmlFor="c-lang">
            <select id="c-lang" value={f.language} onChange={set('language')}>{LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </Field>
        </div>
        <Field label="Notes (optional)" htmlFor="c-notes" hint="For example: delivery address, credit arrangement. Do not enter card or bank numbers.">
          <textarea id="c-notes" value={f.notes} onChange={set('notes')} maxLength={300} rows={3} />
        </Field>
      </form>
    </Dialog>
  )
}
