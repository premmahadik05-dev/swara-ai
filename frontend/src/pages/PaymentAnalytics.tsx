import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ChartCard, DataTable, HBars, Legend } from '../components/charts'
import { KpiCard } from '../components/Kpi'
import { METHOD_COLOR, PayTrendChart, trendLabel, type Grain } from '../components/payments/PayCharts'
import { Badge, Empty, ErrorNote, Note, PageHeader, Seg, SkeletonCard } from '../components/ui'
import { useIsOwner } from '../lib/auth'
import { pct, plural, rupees, wholeRupees } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { METHOD_TEXT } from '../lib/payments'
import { useDataScope } from '../lib/scope'

const GRAINS: { value: Grain; label: string }[] = [{ value: 'day', label: 'Daily' }, { value: 'week', label: 'Weekly' }, { value: 'month', label: 'Monthly' }]

/** Owner only. Every number is added up from payment records in the database: nothing is estimated, and orders with no payment recorded are not counted as money. */
export default function PaymentAnalytics() {
  const owner = useIsOwner()
  const { includeDemo } = useDataScope()
  const [days, setDays] = useState('30')
  const [grain, setGrain] = useState<Grain>('day')
  const res = useAsync(() => (owner ? api.paymentAnalytics(Number(days), includeDemo) : Promise.resolve(null)), [owner, days, includeDemo])

  if (!owner) {
    return (
      <>
        <PageHeader title="Payment analytics" description="Money collected, by way paid." />
        <Empty title="Only the shop owner can open this page" icon="lock">Ask the owner to look at the payment totals, or sign in with the owner account.</Empty>
      </>
    )
  }
  const d = res.data
  const k = d?.kpis
  const series = d ? { day: d.daily, week: d.weekly, month: d.monthly }[grain] : []
  const empty = !!k && k.paid_count === 0 && k.pending_count === 0 && k.failed_count === 0 && k.refund_count === 0

  return (
    <>
      <PageHeader title="Payment analytics" description="Added up from the payment records in the database. Orders with no payment recorded are not counted as money received."
        meta={d ? <Badge tone={d.includes_demo_orders ? 'warn' : 'ok'}>{d.includes_demo_orders ? 'Includes generated demo data' : 'Only payments you recorded'}</Badge> : undefined}
        actions={<Link className="btn secondary" to="/payments">All payments</Link>} />
      <div className="stack">
        <div className="field"><span className="label">Period</span>
          <Seg label="Period" value={days} onChange={setDays} options={[{ value: '7', label: 'Last 7 days' }, { value: '30', label: 'Last 30 days' }, { value: '90', label: 'Last 90 days' }]} />
        </div>
        <ErrorNote error={res.error} onRetry={res.reload} />
        {res.loading && !d && <SkeletonCard lines={6} height={300} />}
        {k && d && (
          <>
            {k.needs_attention > 0 && <Note tone="warn"><b>{plural(k.needs_attention, 'payment')} need a look.</b> <Link to="/payments?attention=1">Show them</Link></Note>}
            <div className="kpi-grid">
              <KpiCard label="Collected" icon="wallet" value={wholeRupees(k.collected_paise)} foot={`${plural(k.paid_count, 'payment')} · average ${wholeRupees(k.average_paise)}${k.refunds_paise ? ` · ${wholeRupees(k.refunds_paise)} refunded, ${wholeRupees(k.net_paise)} kept` : ''}`} />
              <KpiCard label="Cash" icon="cash" value={wholeRupees(k.cash_paise)} foot="Recorded by staff at the counter or on delivery" />
              <KpiCard label="UPI" icon="qr" value={wholeRupees(k.upi_paise)} foot={k.upi_manual_paise ? `${wholeRupees(k.upi_manual_paise)} of it confirmed by hand, not verified by a provider` : 'QR payments'} />
              <KpiCard label="Razorpay" icon="card" value={wholeRupees(k.razorpay_paise)} foot="Confirmed by Razorpay" />
              <KpiCard label="Waiting" icon="clock" value={wholeRupees(k.pending_paise)} foot={`${plural(k.pending_count, 'payment')} not paid yet`} />
              <KpiCard label="Failed" icon="alert" value={plural(k.failed_count, 'payment')} foot={`${wholeRupees(k.failed_paise)} that did not go through`} />
              <KpiCard label="Refunds" icon="undo" value={wholeRupees(k.refunds_paise)} foot={`${plural(k.refund_count, 'refund')}${k.refunds_waiting_count ? ` · ${plural(k.refunds_waiting_count, 'refund')} (${wholeRupees(k.refunds_waiting_paise)}) waiting for Razorpay` : ''}`} />
            </div>
            {empty ? (
              <Empty title="No payments in this period" icon="wallet" action={<Link className="btn" to="/orders">Open Orders</Link>}>Open an order and choose Take payment. The totals appear here as payments are recorded.</Empty>
            ) : (
              <div className="pay-charts">
                <ChartCard title="Collected over time" sub={`${GRAINS.find((g) => g.value === grain)?.label} total, by way paid`}
                  actions={<Seg label="Trend grouping" value={grain} onChange={setGrain} options={GRAINS} />}
                  legend={<Legend items={[{ label: 'Cash', color: METHOD_COLOR.cash }, { label: 'UPI', color: METHOD_COLOR.upi }, { label: 'Razorpay', color: METHOD_COLOR.razorpay }]} />}
                  table={<DataTable head={['Period', 'Cash', 'UPI', 'Razorpay', 'Total', 'Payments']} rows={series.map((p) => [trendLabel(p.period, grain), rupees(p.cash_paise), rupees(p.upi_paise), rupees(p.razorpay_paise), rupees(p.collected_paise), p.count])} />}>
                  <PayTrendChart series={series} grain={grain} />
                </ChartCard>
                <ChartCard title="Way paid" sub="Share of the money collected"
                  table={<DataTable head={['Way paid', 'Collected', 'Share', 'Payments']} rows={d.by_method.map((m) => [METHOD_TEXT[m.method], rupees(m.collected_paise), pct(m.share), m.count])} />}>
                  <HBars rows={d.by_method.map((m) => ({ name: METHOD_TEXT[m.method], v: m.collected_paise, color: METHOD_COLOR[m.method] }))} fmt={(n) => wholeRupees(n)} labelWidth={90} />
                  <p className="muted small" style={{ marginTop: 10 }}>{d.by_method.map((m) => `${METHOD_TEXT[m.method]} ${pct(m.share)}`).join(' · ')}</p>
                </ChartCard>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
