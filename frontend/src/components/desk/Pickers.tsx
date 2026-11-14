import { useState } from 'react'
import { api } from '../../api/client'
import { useIsOwner } from '../../lib/auth'
import { fmtQty, rupees, unitLabel } from '../../lib/format'
import { useDataScope } from '../../lib/scope'
import type { Customer, Product } from '../../types'
import { Combobox } from '../Combobox'
import { CustomerForm } from '../CustomerForm'
import { Icon } from '../Icons'
import { Avatar, Badge, Button, DemoBadge } from '../ui'

export function CustomerPicker({ value, onChange, disabled }: { value: Customer | null; onChange: (c: Customer | null) => void; disabled?: boolean }) {
  const { includeDemo } = useDataScope()
  const owner = useIsOwner()
  const [editing, setEditing] = useState(false)
  const [creating, setCreating] = useState(false)
  if (!editing) {
    return (
      <div className="row nowrap between" aria-label="Customer">
        <div className="cell-user">
          <Avatar name={value?.name ?? 'Walk in'} />
          <div className="cell-main">
            <b className="truncate">{value ? value.name : 'Walk-in customer'}</b>
            <span className="faint xs">{value ? (value.is_synthetic ? 'Demo customer' : value.phone || 'Customer') : 'Not linked to a customer record'}</span>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={() => setEditing(true)} disabled={disabled} aria-label="Change customer">Change</Button>
      </div>
    )
  }
  return (
    <>
      <Combobox<Customer> label="Find a customer" placeholder="Search by name or phone" autoFocus initialLoad
        search={(q) => api.customers({ q, page_size: 6, include_synthetic: includeDemo, sort: 'recent' }).then((r) => r.items)}
        itemKey={(c) => c.id}
        renderOption={(c) => <><span className="cell-user"><Avatar name={c.name} /><span className="cell-main"><b>{c.name}</b><span className="faint xs">{c.phone || `${c.orders} orders`}</span></span></span>{c.is_synthetic && <DemoBadge />}</>}
        onSelect={(c) => { onChange(c); setEditing(false) }}
        extra={[
          { key: 'walkin', node: <span><b>Walk-in customer</b> <span className="faint xs">(no record)</span></span>, onPick: () => { onChange(null); setEditing(false) } },
          ...(owner ? [{ key: 'new', node: <span className="row tight"><Icon name="plus" size={15} /><b>New customer…</b></span>, onPick: () => setCreating(true) }] : []),
        ]} />
      <div style={{ marginTop: 6 }}><Button variant="link" onClick={() => setEditing(false)}>Cancel</Button></div>
      {creating && <CustomerForm onClose={() => setCreating(false)} onDone={(c) => { onChange(c); setCreating(false); setEditing(false) }} />}
    </>
  )
}

export function ProductPicker({ onAdd, disabled }: { onAdd: (p: Product) => void; disabled?: boolean }) {
  return (
    <Combobox<Product> label="Add an item to the bill" placeholder="Add an item: type a name…" disabled={disabled}
      search={(q) => api.inventory({ q, page_size: 8 }).then((r) => r.items)} itemKey={(p) => p.id}
      emptyText="No item with that name in your shop. Add it from the Catalogue or Inventory."
      hint="Type at least one letter. Names in Gujarati and Hindi work too."
      isDisabled={(p) => p.stock <= 0}
      renderOption={(p) => (
        <>
          <span className="cell-main"><b>{p.name_en}</b><span className="faint xs">{rupees(p.price_paise)} / {unitLabel(p.unit)}{p.brand ? ` · ${p.brand}` : ''}</span></span>
          {p.stock <= 0 ? <Badge tone="bad">Finished</Badge> : <span className="faint xs nowrap">{fmtQty(p.stock)} {unitLabel(p.unit)} left</span>}
        </>
      )}
      onSelect={onAdd} />
  )
}
