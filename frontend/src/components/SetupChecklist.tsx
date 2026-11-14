import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../lib/hooks'
import type { InventorySummary } from '../types'
import { Icon } from './Icons'
import { Button, Card } from './ui'

/** The owner's first-run checklist. Every tick comes from state the server reports, never from a click on the checklist itself:
 *  the shop still has the built-in demo name, how many prices are the owner's own, whether a real (not generated) order exists,
 *  and whether a Gnani key is saved. Staff never see it. Hiding it is remembered for this person in this browser only. */
export const hiddenKey = (userId: number) => `swara.setup.hidden.${userId}`

interface Step { id: string; title: string; detail: string; done: boolean; to: string; action: string; optional?: boolean }

export function SetupChecklist({ userId, prices, realOrders }: { userId: number; prices: InventorySummary['price_basis'] | undefined; realOrders: number | undefined }) {
  const health = useAsync(() => api.health(), [])
  const [hidden, setHidden] = useState(() => { try { return localStorage.getItem(hiddenKey(userId)) === '1' } catch { return false } })
  const h = health.data
  // Wait until everything is known, so the card never flashes unticked boxes that then tick themselves.
  if (hidden || !h || !prices || realOrders === undefined) return null

  const items = prices.demo + prices.shop
  const steps: Step[] = [
    { id: 'name', title: 'Name your shop', done: !h.store_name_is_default, to: '/settings', action: 'Rename',
      detail: h.store_name_is_default ? `It still says "${h.store_name}". The name appears in the sidebar and on printed bills.` : `Showing as "${h.store_name}".` },
    { id: 'prices', title: 'Set your own prices', done: prices.shop > 0, to: '/inventory', action: 'Open inventory',
      detail: items === 0 ? 'The shop has no items yet. Add some from the Catalogue or Inventory.'
        : prices.demo > 0 ? `${prices.demo} of ${items} items still carry a placeholder demo price. Edit a price and it becomes yours.` : 'Every price is one you set.' },
    { id: 'order', title: 'Take your first real order', done: realOrders > 0, to: '/order', action: 'Open order desk',
      detail: realOrders > 0 ? `${realOrders} order${realOrders === 1 ? '' : 's'} recorded by you, apart from the generated demo orders.` : 'Orders from the Order desk count as real. Generated demo orders do not.' },
    { id: 'voice', title: 'Add your Gnani key for voice', done: h.gnani_configured, to: '/settings', action: 'Open settings', optional: true,
      detail: h.gnani_configured ? 'Saved on the server.' : 'Needed only for spoken orders. Typed orders work without it.' },
  ]
  const done = steps.filter((s) => s.done).length
  if (done === steps.length) return null

  const hide = () => { try { localStorage.setItem(hiddenKey(userId), '1') } catch { /* private mode: it will show again next visit */ } setHidden(true) }
  return (
    <Card title="Set up your shop" description={`${done} of ${steps.length} done. Ticks come from your shop's data, not from this list.`}
          actions={<Button variant="ghost" size="sm" onClick={hide} aria-label="Hide the setup checklist">Hide</Button>}>
      <div className="setup-bar" role="img" aria-label={`${done} of ${steps.length} steps done`}><span style={{ width: `${(done / steps.length) * 100}%` }} /></div>
      <ol className="setup-list">
        {steps.map((s) => (
          <li key={s.id} className={s.done ? 'done' : ''}>
            <span className="setup-tick" aria-hidden>{s.done && <Icon name="check" size={14} />}</span>
            <div className="setup-main">
              <b>{s.title}{s.optional && <span className="faint xs"> (optional)</span>}<span className="sr">{s.done ? ', done' : ', to do'}</span></b>
              <span className="muted small">{s.detail}</span>
            </div>
            {!s.done && <Link className="btn secondary small" to={s.to}>{s.action}</Link>}
          </li>
        ))}
      </ol>
    </Card>
  )
}
