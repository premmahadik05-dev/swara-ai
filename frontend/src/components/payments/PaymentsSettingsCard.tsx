import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { PublicSettings } from '../../types'
import { useToast } from '../Toast'
import { Badge, Button, Card, Field, Note } from '../ui'

/** Same shape the server accepts. */
const VPA = /^[A-Za-z0-9._-]{2,64}@[A-Za-z][A-Za-z0-9]{1,31}$/

/** Owner only: the shop's UPI ID and what is set up for Razorpay. It shows whether each secret is set (yes or no), never the secret itself. */
export function PaymentsSettingsCard({ settings, onSaved }: { settings: PublicSettings; onSaved: () => void }) {
  const { toast } = useToast()
  const cfg = settings.payments
  const o = cfg.owner
  const [vpa, setVpa] = useState(o?.upi_vpa ?? '')
  const [payee, setPayee] = useState(o?.upi_payee_name ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { setVpa(o?.upi_vpa ?? ''); setPayee(o?.upi_payee_name ?? '') }, [o?.upi_vpa, o?.upi_payee_name])
  if (!o) return null
  const clean = vpa.trim()
  const problem = clean && !VPA.test(clean) ? 'That does not look like a UPI ID. It should look like name@bank, for example patelstore@okhdfcbank.' : null
  const dirty = clean !== o.upi_vpa || payee.trim() !== o.upi_payee_name
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (problem || !dirty) return
    setBusy(true); setErr(null)
    try { await api.putSettings({ upi_vpa: clean, upi_payee_name: payee.trim() }); toast('UPI details saved.', 'ok'); onSaved() }
    catch (e2) { setErr((e2 as Error).message) } finally { setBusy(false) }
  }
  const copy = async () => { try { await navigator.clipboard.writeText(o.webhook_url); toast('Webhook address copied.', 'ok') } catch { toast('Could not copy. Select the address and copy it.', 'bad') } }
  const ok = cfg.razorpay.enabled
  return (
    <Card title="Payments" description="Cash always works. UPI needs your shop's UPI ID. Razorpay needs keys in the server's .env file.">
      <div className="stack">
        <div className="row">
          <Badge tone={cfg.mode === 'live' ? 'warn' : 'info'} dot>{cfg.mode === 'live' ? 'Live mode' : 'Test mode'}</Badge>
          <Badge tone={ok ? 'ok' : undefined} dot>{ok ? 'Razorpay is ready' : 'Razorpay is not set up'}</Badge>
          <Badge tone={cfg.methods.upi.available ? 'ok' : undefined} dot>{cfg.methods.upi.available ? (cfg.methods.upi.mode === 'provider' ? 'UPI QR by Razorpay' : 'UPI QR by shop ID') : 'UPI QR needs a UPI ID'}</Badge>
        </div>
        {cfg.mode === 'live' && <Note tone="warn"><b>Live mode is on.</b> Razorpay payments move real money. Use test mode until you have checked every step.</Note>}
        {!ok && o.razorpay_problem && <Note tone="info">{o.razorpay_problem}</Note>}
        <dl className="kv">
          <dt>Razorpay key id</dt><dd>{cfg.razorpay.key_id ? <span className="mono-id">{cfg.razorpay.key_id}</span> : 'Not set'}</dd>
          <dt>Key secret</dt><dd>{o.key_secret_set ? 'Set on the server (never shown)' : 'Not set'}</dd>
          <dt>Webhook secret</dt><dd>{o.webhook_secret_set ? 'Set on the server (never shown)' : 'Not set'}</dd>
          <dt>Webhook address</dt><dd className="row tight"><span className="mono-id">{o.webhook_url}</span><Button size="sm" variant="secondary" onClick={() => void copy()}>Copy</Button></dd>
        </dl>
        <form className="stack tight" onSubmit={save} aria-label="UPI details">
          <Field label="Shop UPI ID" htmlFor="upi-vpa" error={err ?? (clean !== o.upi_vpa ? problem : null)} hint="Printed inside the QR code customers scan. It is not a secret. Leave it empty to turn the shop QR off.">
            <input id="upi-vpa" value={vpa} onChange={(e) => { setVpa(e.target.value); setErr(null) }} maxLength={100} autoComplete="off" spellCheck={false} placeholder="name@bank" />
          </Field>
          <Field label="Name shown in the customer's UPI app" htmlFor="upi-payee" hint="Leave it empty to use the shop name.">
            <input id="upi-payee" value={payee} onChange={(e) => setPayee(e.target.value)} maxLength={100} autoComplete="off" />
          </Field>
          <div className="row"><Button type="submit" loading={busy} disabled={!!problem || !dirty}>Save UPI details</Button></div>
        </form>
        <p className="muted small" style={{ margin: 0 }}>Keys and secrets are never typed into this page. They go in the server's .env file; see docs/RAZORPAY_SETUP.md.</p>
      </div>
    </Card>
  )
}
