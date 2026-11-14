import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ChartCard, ColumnBars, DataTable, HBars, HealthBar, Legend, LANG_COLOR, StockFlowChart, TrendChart } from '../components/charts'
import { GridTable, type GridColumn } from '../components/GridTable'
import { Delta, KpiCard } from '../components/Kpi'
import { Badge, Card, Empty, ErrorNote, Note, PageHeader, Seg, SkeletonCard, SkeletonRows } from '../components/ui'
import { LANG_LATIN, compactRupees, fmtQty, pct, periodLabel, rupees, unitLabel, wholeRupees } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { useDataScope } from '../lib/scope'
import { compareAov, comparePeriods } from '../lib/stats'
import type { DemandRow, StockMovementRow } from '../types'

type Grain = 'day' | 'week' | 'month'
const SPAN: Record<Grain, { n: number; label: string; unit: string }> = {
  day: { n: 30, label: 'Last 30 days', unit: 'days' }, week: { n: 12, label: 'Last 12 weeks', unit: 'weeks' }, month: { n: 12, label: 'Last 12 months', unit: 'months' },
}
const SO_FAR: Record<Grain, string> = { day: 'Today so far', week: 'This week so far', month: 'This month so far' }
const STATUS: Record<string, { label: string; color: string }> = { confirmed: { label: 'Confirmed', color: 'var(--gold)' }, fulfilled: { label: 'Fulfilled', color: 'var(--ok)' }, cancelled: { label: 'Cancelled', color: 'var(--bad)' } }
const STOCK_STATUS: Record<StockMovementRow['status'], { label: string; tone: 'ok' | 'warn' | 'bad' }> = { ok: { label: 'In stock', tone: 'ok' }, low: { label: 'Reorder now', tone: 'warn' }, out: { label: 'Finished', tone: 'bad' } }
const hourLabel = (h: number) => `${h % 12 === 0 ? 12 : h % 12}${h < 12 ? 'am' : 'pm'}`

const coverBadge = (r: DemandRow) =>
  r.days_of_cover === null ? <Badge>No sales</Badge>
  : r.status === 'stockout_risk' ? <Badge tone="bad" dot>{r.days_of_cover} days</Badge>
  : r.status === 'overstocked' ? <Badge tone="info" dot>{Math.round(r.days_of_cover)} days</Badge>
  : <Badge tone="ok" dot>{Math.round(r.days_of_cover)} days</Badge>

const qtyCell = (r: StockMovementRow, v: number) => (v ? `${fmtQty(v)} ${unitLabel(r.unit)}` : <span className="faint">0</span>)
const stockColumns: GridColumn<StockMovementRow>[] = [
  { key: 'name', label: 'Product', value: (r) => r.name, render: (r) => <div className="cell-main"><b>{r.name}</b><span className="sub">{r.category}</span></div> },
  { key: 'opening', label: 'Opening', value: (r) => r.opening, num: true, render: (r) => qtyCell(r, r.opening), hint: 'Stock at the start of the period: today\'s stock with the period\'s movements taken back out' },
  { key: 'added', label: 'Added', value: (r) => r.added, num: true, render: (r) => qtyCell(r, r.added), hint: 'Restocks entered in Inventory' },
  { key: 'returned', label: 'Returned', value: (r) => r.returned, num: true, render: (r) => qtyCell(r, r.returned), hint: 'Put back by cancelling an order' },
  { key: 'sold', label: 'Sold', value: (r) => r.sold, num: true, render: (r) => qtyCell(r, r.sold), hint: 'Taken by confirmed orders' },
  { key: 'written_off', label: 'Written off', value: (r) => r.written_off, num: true, render: (r) => qtyCell(r, r.written_off), hint: 'Removed by a stock adjustment' },
  { key: 'current', label: 'Current', value: (r) => r.current, num: true, render: (r) => <b>{fmtQty(r.current)} {unitLabel(r.unit)}</b> },
  { key: 'status', label: 'Reorder status', value: (r) => STOCK_STATUS[r.status].label, render: (r) => <Badge tone={STOCK_STATUS[r.status].tone} dot>{STOCK_STATUS[r.status].label}</Badge>, hint: 'Compared with the reorder level set for the product' },
]

export default function Analytics() {
  const { includeDemo } = useDataScope()
  const [grain, setGrain] = useState<Grain>('day')
  const [days, setDays] = useState(30)
  const [showAll, setShowAll] = useState(false)
  const span = SPAN[grain]
  const sales = useAsync(() => api.salesSeries(grain, span.n * 2 + 1, includeDemo), [grain, includeDemo])
  const ov = useAsync(() => api.overview(days, includeDemo), [days, includeDemo])
  const inv = useAsync(() => api.inventorySummary(), [])
  const demand = useAsync(() => api.demand(days, includeDemo), [days, includeDemo])
  const [moveDays, setMoveDays] = useState(30)
  const move = useAsync(() => api.stockMovement(moveDays), [moveDays])
  const err = sales.error ?? ov.error ?? inv.error ?? demand.error ?? move.error

  const k = useMemo(() => {
    const all = sales.data?.series ?? []
    const shown = all.slice(-span.n)
    const rev = comparePeriods(all, span.n, (p) => p.revenue_paise)
    const ord = comparePeriods(all, span.n, (p) => p.orders)
    const aov = compareAov(all, span.n)
    const open = shown.find((p) => p.partial && p.orders > 0)   // the unfinished period: left out of the tiles above, shown beside them so a first day is not a row of zeros
    return { shown, rev, ord, aovNow: aov.cur, aovDelta: aov.delta, open }
  }, [sales.data, span.n])
  const soFar = (text: string | undefined) => (text ? <span className="faint xs" style={{ display: 'block' }}>{SO_FAR[grain]}: {text}</span> : null)
  const hasSales = !!sales.data && sales.data.totals.orders > 0
  const rows = demand.data?.products ?? []
  const visible = showAll ? rows : rows.slice(0, 10)
  const prevOk = demand.data?.previous_window.comparable ?? true

  return (
    <>
      <PageHeader title="Analytics" description="Sales, stock and demand, computed from the orders and products in the database each time you open this page."
        meta={<Badge tone={includeDemo ? 'warn' : 'ok'}>{includeDemo ? 'Includes generated demo data' : 'Only orders you recorded'}</Badge>} />
      <div className="stack">
        <ErrorNote error={err} onRetry={() => { sales.reload(); ov.reload(); inv.reload(); demand.reload(); move.reload() }} />
        <div className="card card-pad row between">
          <div className="row">
            <div className="field"><span className="label">Sales trend</span><Seg label="Trend grouping" value={grain} onChange={setGrain} options={[{ value: 'day', label: 'Daily' }, { value: 'week', label: 'Weekly' }, { value: 'month', label: 'Monthly' }]} /></div>
            <div className="field"><span className="label">Breakdowns and demand</span><Seg label="Breakdown period" value={String(days)} onChange={(v) => setDays(Number(v))} options={[{ value: '7', label: 'Last 7 days' }, { value: '30', label: 'Last 30 days' }, { value: '90', label: 'Last 90 days' }]} /></div>
          </div>
          <div className="muted small stack tight" style={{ maxWidth: '58ch' }}>
            <p style={{ margin: 0 }}><b>Sales trend</b> and the first three tiles count complete periods only; the unfinished one is marked and left out of comparisons.</p>
            <p style={{ margin: 0 }}><b>Breakdowns</b> run up to now, so today's orders so far are included. IST, weeks start on Monday, cancelled orders are not counted.</p>
          </div>
        </div>
        {includeDemo && sales.data && <Note tone="warn"><b>Demo data.</b> Orders before today are generated by the seed script, and the daily pattern (busy mornings, voice share) was set by that script. Treat the trends as an example of the screen, not as findings about a real shop.</Note>}

        <div className="kpi-grid">
          <KpiCard label={`Sales, ${span.label.toLowerCase()}`} icon="rupee" value={wholeRupees(k.rev.cur)} loading={sales.loading && !sales.data}
            foot={<><Delta value={k.rev.delta} suffix={`vs the ${span.n} ${span.unit} before`} />{soFar(k.open && wholeRupees(k.open.revenue_paise))}</>} spark={k.shown.filter((p) => !p.partial).map((p) => p.revenue_paise)} sparkLabel="Sales per period" />
          <KpiCard label="Orders" icon="orders" value={k.ord.cur.toLocaleString('en-IN')} loading={sales.loading && !sales.data}
            foot={<><Delta value={k.ord.delta} suffix={`vs the ${span.n} ${span.unit} before`} />{soFar(k.open && k.open.orders.toLocaleString('en-IN'))}</>} spark={k.shown.filter((p) => !p.partial).map((p) => p.orders)} sparkLabel="Orders per period" />
          <KpiCard label="Average order value" icon="cart" value={wholeRupees(k.aovNow)} loading={sales.loading && !sales.data}
            foot={<><Delta value={k.aovDelta} suffix={`vs the ${span.n} ${span.unit} before`} />{soFar(k.open && wholeRupees(k.open.avg_basket_paise))}</>} />
          <KpiCard label="Taken by voice" icon="mic" value={ov.data ? pct(ov.data.kpis.voice_share) : '-'} loading={ov.loading && !ov.data}
            foot={ov.data ? `of ${ov.data.kpis.orders.toLocaleString('en-IN')} orders in the last ${days} days, up to now` : undefined} />
        </div>

        <ChartCard title="Sales" sub={`${span.label}. Rupees, cancelled orders excluded.`}
          table={<DataTable head={['Period', 'Sales', 'Orders', 'Average bill']} rows={k.shown.map((p) => [periodLabel(p.period, grain) + (p.partial ? ' (in progress)' : ''), rupees(p.revenue_paise), p.orders, rupees(p.avg_basket_paise)])} />}
          legend={k.shown.some((p) => p.partial) ? <span>{grain === 'day' ? 'Dashed line: today so far, not a full day' : 'Hatched bar: period still in progress'}</span> : undefined}>
          {sales.loading && !sales.data ? <SkeletonCard lines={5} height={280} /> : !hasSales ? (
            <Empty title="No orders in this period" icon="chart">{includeDemo ? 'Seed the demo data or take an order on the Order desk.' : 'Demo data is off. Take an order on the Order desk and it will show here.'}</Empty>
          ) : <TrendChart series={k.shown} grain={grain} />}
        </ChartCard>

        {hasSales && (
          <div className="cols even">
            <ChartCard title="Orders" sub="Number of bills per period" table={<DataTable head={['Period', 'Orders']} rows={k.shown.map((p) => [periodLabel(p.period, grain), p.orders])} />}>
              <TrendChart series={k.shown} grain={grain} metric="orders" height={230} />
            </ChartCard>
            <ChartCard title="Average order value" sub="Sales divided by orders, per period" table={<DataTable head={['Period', 'Average bill']} rows={k.shown.map((p) => [periodLabel(p.period, grain), p.orders ? rupees(p.avg_basket_paise) : '-'])} />}>
              <TrendChart series={k.shown} grain={grain} metric="avg_basket_paise" height={230} />
            </ChartCard>
          </div>
        )}

        <div className="cols even">
          <ChartCard title="Best sellers" sub={`By sales, last ${days} days`} table={<DataTable head={['Product', 'Sales', 'Quantity']} rows={(ov.data?.top_products ?? []).map((x) => [x.name, rupees(x.revenue_paise), `${Math.round(x.qty * 10) / 10} ${unitLabel(x.unit)}`])} />}>
            {ov.loading && !ov.data ? <SkeletonCard lines={5} height={240} /> : ov.data?.top_products.length ? <HBars rows={ov.data.top_products.map((x) => ({ name: x.name, v: x.revenue_paise }))} fmt={compactRupees} labelWidth={150} /> : <Empty title="No sales in this period" icon="chart" />}
          </ChartCard>
          <ChartCard title="Sales by category" sub={`Last ${days} days`} table={<DataTable head={['Category', 'Sales']} rows={(ov.data?.category_mix ?? []).map((x) => [x.category, rupees(x.revenue_paise)])} />}>
            {ov.loading && !ov.data ? <SkeletonCard lines={5} height={240} /> : ov.data?.category_mix.length ? <HBars rows={ov.data.category_mix.slice(0, 8).map((x) => ({ name: x.category, v: x.revenue_paise }))} fmt={compactRupees} labelWidth={130} /> : <Empty title="No sales in this period" icon="chart" />}
          </ChartCard>
        </div>

        <Card title="Demand and stock cover" description={demand.data?.method} flush>
          {demand.loading && !demand.data ? <SkeletonRows rows={6} cols={6} /> : rows.length === 0 ? <Empty title="No sales to learn from yet" icon="trend">Demand figures appear once products have sold in the last {days} days.</Empty> : (
            <>
              <div className="table-wrap">
                <table className="tbl">
                  <thead><tr><th>Product</th><th className="num">Sold</th><th className="num">Per day</th><th className="num">In stock</th><th>Stock lasts</th><th className="num">Vs earlier</th><th className="num">Suggested reorder</th></tr></thead>
                  <tbody>
                    {visible.map((r) => (
                      <tr key={r.product_id}>
                        <td><div className="cell-main"><b>{r.name}</b><span className="sub">{r.category}</span></div></td>
                        <td className="num">{fmtQty(r.units_sold)} {unitLabel(r.unit)}</td>
                        <td className="num muted">{fmtQty(r.velocity_per_day)}</td>
                        <td className="num">{fmtQty(r.stock)} {unitLabel(r.unit)}</td>
                        <td>{coverBadge(r)}</td>
                        <td className="num">{r.trend_pct === null ? <span className="faint" title={prevOk ? 'No sales in the earlier period' : 'The earlier period has too little history to compare'}>{prevOk ? 'New' : '-'}</span> : <span className={`delta ${r.trend_pct > 0 ? 'up' : r.trend_pct < 0 ? 'down' : 'flat'}`}>{r.trend_pct > 0 ? '+' : ''}{r.trend_pct}%</span>}</td>
                        <td className="num">{r.suggested_reorder_qty > 0 ? <b>{fmtQty(r.suggested_reorder_qty)} {unitLabel(r.unit)}</b> : <span className="faint">None needed</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!prevOk && <p className="muted small card-pad" style={{ margin: 0, borderTop: '1px solid var(--line)' }}>"Vs earlier" is hidden: only {demand.data?.previous_window.days_with_orders} of the {days} days before this window have any orders, so a comparison would mislead. Pick a shorter window to see it.</p>}
              {rows.length > 10 && <div className="table-foot"><span>Showing {visible.length} of {rows.length} products, by sales</span><button type="button" className="btn secondary small" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show fewer' : 'Show all'}</button></div>}
            </>
          )}
        </Card>

        <div className="cols three">
          <Card title="Stock health" description="Active products by stock level">
            {inv.loading && !inv.data ? <SkeletonCard lines={2} /> : inv.data && <HealthBar {...inv.data.stock_health} />}
            {inv.data && (
              <><hr className="divider" /><dl className="kv">
                <dt>Value at selling price</dt><dd><b>{wholeRupees(inv.data.valuation_retail_paise)}</b></dd>
                <dt>Value at cost</dt><dd>{inv.data.valuation_cost_paise !== null ? <b>{wholeRupees(inv.data.valuation_cost_paise)}</b> : <span className="muted">Needs cost prices</span>}{inv.data.valuation_cost_paise !== null && <span className="faint xs"> ({inv.data.products_with_cost} items)</span>}</dd>
                <dt>Prices</dt><dd>{inv.data.price_basis.demo} demo, {inv.data.price_basis.shop} your own</dd>
              </dl></>
            )}
          </Card>
          <Card title="Stock value by category" description="At selling price">
            {inv.loading && !inv.data ? <SkeletonCard lines={4} /> : inv.data && <HBars rows={inv.data.by_category.slice(0, 7).map((c) => ({ name: c.category, v: c.retail_paise }))} fmt={compactRupees} labelWidth={110} />}
          </Card>
          <Card title="Not selling" description={inv.data ? `${inv.data.no_sales.items} items with stock and no sale in ${inv.data.no_sales.days} days` : undefined}>
            {inv.loading && !inv.data ? <SkeletonCard lines={4} /> : inv.data && inv.data.no_sales.top.length === 0 ? <p className="muted small" style={{ margin: 0 }}>Every item with stock has sold recently.</p> : inv.data && (
              <>
                <ul className="list-rows">{inv.data.no_sales.top.map((p) => <li key={p.product_id}><span className="grow truncate">{p.name}</span><b className="nowrap">{wholeRupees(p.retail_paise)}</b></li>)}</ul>
                <p className="muted small" style={{ margin: '10px 0 0' }}>{wholeRupees(inv.data.no_sales.retail_paise)} of stock tied up in these items. <Link to="/inventory">Open inventory</Link></p>
              </>
            )}
          </Card>
        </div>

        <div className="cols three">
          <ChartCard title="Language of the order" sub="Orders by the language the customer used" legend={<Legend items={[...Object.entries(LANG_COLOR).map(([k, c]) => ({ label: LANG_LATIN[k], color: c })), { label: 'Other languages', color: 'var(--c-muted)' }]} />}
            table={<DataTable head={['Language', 'Orders']} rows={(ov.data?.orders_by_language ?? []).map((x) => [LANG_LATIN[x.language] ?? x.language, x.orders])} />}>
            {ov.data ? <HBars rows={ov.data.orders_by_language.map((x) => ({ name: LANG_LATIN[x.language] ?? x.language, v: x.orders, color: LANG_COLOR[x.language] ?? 'var(--c-muted)' }))} fmt={(n) => n.toLocaleString('en-IN')} labelWidth={80} /> : <SkeletonCard lines={3} height={140} />}
          </ChartCard>
          <ChartCard title="How orders are taken" sub="Voice versus typed" table={<DataTable head={['Channel', 'Orders']} rows={(ov.data?.orders_by_channel ?? []).map((x) => [x.channel === 'voice' ? 'Voice' : 'Typed', x.orders])} />}>
            {ov.data ? <HBars rows={ov.data.orders_by_channel.map((x) => ({ name: x.channel === 'voice' ? 'Voice' : 'Typed', v: x.orders, color: x.channel === 'voice' ? 'var(--chart-ink)' : 'var(--c-muted)' }))} fmt={(n) => n.toLocaleString('en-IN')} labelWidth={70} /> : <SkeletonCard lines={3} height={140} />}
          </ChartCard>
          <ChartCard title="Busy hours" sub="Orders by hour of day (IST)" table={<DataTable head={['Hour', 'Orders']} rows={(ov.data?.orders_by_hour ?? []).filter((x) => x.orders).map((x) => [hourLabel(x.hour), x.orders])} />}>
            {ov.data ? <ColumnBars data={ov.data.orders_by_hour} x="hour" y="orders" fmtX={hourLabel} height={200} tipTitle={(r) => hourLabel(Number(r.hour))} tipLabel="orders" /> : <SkeletonCard lines={3} height={200} />}
          </ChartCard>
        </div>

        <div className="cols even">
          <ChartCard title="Order status" sub={`Orders in the last ${days} days, including cancelled`}
            legend={<Legend items={Object.values(STATUS).map((x) => ({ label: x.label, color: x.color }))} />}
            table={<DataTable head={['Status', 'Orders']} rows={(ov.data?.orders_by_status ?? []).map((x) => [STATUS[x.status]?.label ?? x.status, x.orders])} />}>
            {ov.data ? (ov.data.orders_by_status.some((x) => x.orders > 0) ? <HBars rows={ov.data.orders_by_status.map((x) => ({ name: STATUS[x.status]?.label ?? x.status, v: x.orders, color: STATUS[x.status]?.color }))} fmt={(n) => n.toLocaleString('en-IN')} labelWidth={90} /> : <Empty title="No orders in this period" icon="chart" />) : <SkeletonCard lines={3} height={140} />}
          </ChartCard>
          <Card title="Cancelled orders" description="Share of all orders in the period">
            {ov.data ? (
              <>
                <div className="big-figure">{ov.data.kpis.orders + ov.data.kpis.cancelled ? pct(ov.data.kpis.cancelled / (ov.data.kpis.orders + ov.data.kpis.cancelled), 1) : '-'}</div>
                <p className="muted small" style={{ margin: '8px 0 0' }}>{ov.data.kpis.cancelled.toLocaleString('en-IN')} of {(ov.data.kpis.orders + ov.data.kpis.cancelled).toLocaleString('en-IN')} orders. Cancelling puts the stock back on the shelf.</p>
              </>
            ) : <SkeletonCard lines={2} />}
          </Card>
        </div>

        <ChartCard title="Stock movement" sub={`Value of stock added and taken out each day, last ${moveDays} days, at today's selling prices`}
          actions={<Seg label="Stock movement period" value={String(moveDays)} onChange={(v) => setMoveDays(Number(v))} options={[{ value: '7', label: '7 days' }, { value: '30', label: '30 days' }, { value: '90', label: '90 days' }]} />}
          legend={move.data && move.data.movements > 0 ? <Legend items={[{ label: 'Stock added', color: 'var(--c1)' }, { label: 'Stock taken out (sold or written off)', color: 'var(--c2)' }]} /> : undefined}
          table={<DataTable head={['Day', 'Stock added', 'Stock taken out']} rows={(move.data?.series ?? []).map((p) => [periodLabel(p.date, 'day'), rupees(p.in_paise), rupees(p.out_paise)])} />}>
          {move.loading && !move.data ? <SkeletonCard lines={4} height={240} /> : !move.data || move.data.movements === 0 ? (
            <Empty title="No stock movements in this period" icon="box">Stock moves when an order is confirmed or cancelled and when you add stock in Inventory. The generated demo orders never touched the shelf, so they are not here.</Empty>
          ) : <StockFlowChart series={move.data.series} />}
        </ChartCard>

        <Card title="Inventory performance" description={move.data ? `${move.data.products_moved} of ${move.data.products_total} products moved in the last ${moveDays} days. ${move.data.method}` : undefined} flush>
          {move.loading && !move.data ? <SkeletonRows rows={6} cols={6} /> : (
            <GridTable rows={move.data?.rows ?? []} columns={stockColumns} rowKey={(r) => String(r.product_id)} noun="products" exportName={`inventory-performance-${moveDays}d`} pageSize={10} initialSort={{ key: 'sold', dir: 'desc' }}
              empty={<Empty title="Nothing to report yet" icon="package">No product has had a stock movement in this period.</Empty>} />
          )}
          {move.data?.truncated && <p className="muted small card-pad" style={{ margin: 0, borderTop: '1px solid var(--line)' }}>Showing the 60 products that sold the most. Narrow the period to see others.</p>}
        </Card>
      </div>
    </>
  )
}
