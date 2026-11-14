import { useId, useMemo, useState, type ReactNode } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { compactRupees, periodLabel, rupees } from '../lib/format'
import type { SalesPoint } from '../types'

/* Colours come from CSS variables (tokens.css) so a chart never carries a colour of its own.
   Categorical slots are assigned in fixed order: language gu=c1, hi=c2, hinglish=c3, en=c4. Only four hues are validated, so every later language
   (Marathi, Bengali, Tamil ...) is drawn in the muted tone and told apart by its name beside the bar, never by colour alone. Text never wears a series colour. */
export const LANG_COLOR: Record<string, string> = { gu: 'var(--c1)', hi: 'var(--c2)', hinglish: 'var(--c3)', en: 'var(--c4)' }
const GRID = 'var(--chart-grid)'
const AXIS = 'var(--chart-axis)'

/** Four equal, round-numbered steps that just cover the data (0, 4K, 8K, ...) instead of arbitrary ticks. */
export const niceTicks = (max: number): number[] => {
  if (!(max > 0)) return [0, 1]
  const e = 10 ** Math.floor(Math.log10(max / 4))
  const step = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((m) => m * e).find((v) => v * 4 >= max) ?? 10 * e
  return [0, 1, 2, 3, 4].map((i) => i * step)
}

interface TipProps { active?: boolean; payload?: { payload: Record<string, unknown> }[]; render: (row: Record<string, unknown>) => { title: string; rows: [string, string][]; note?: string } }
export function Tip({ active, payload, render }: TipProps) {
  if (!active || !payload?.length) return null
  const t = render(payload[0].payload)
  return (
    <div className="chart-tip">
      <div className="tt">{t.title}</div>
      {t.rows.map(([k, v]) => (<div key={k} className="tr"><b>{v}</b><span>{k}</span></div>))}
      {t.note && <div className="tn">{t.note}</div>}
    </div>
  )
}

/** A card for one chart with a "chart / table" switch, so every chart has a text equivalent. */
export function ChartCard({ title, sub, table, legend, actions, children, className = '' }: {
  title: string; sub?: ReactNode; table: ReactNode; legend?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string
}) {
  const [asTable, setAsTable] = useState(false)
  const id = useId()
  return (
    <section className={`card chart-card ${className}`.trim()} aria-labelledby={id}>
      <div className="card-head">
        <div className="t"><h2 id={id} className="h3">{title}</h2>{sub && <p>{sub}</p>}</div>
        <div className="row tight">
          {actions}
          <div className="seg" role="group" aria-label={`${title}: view`}>
            <button type="button" aria-pressed={!asTable} onClick={() => setAsTable(false)}>Chart</button>
            <button type="button" aria-pressed={asTable} onClick={() => setAsTable(true)}>Table</button>
          </div>
        </div>
      </div>
      <div className="card-body">
        {asTable ? <div className="table-wrap" style={{ maxHeight: 320, overflowY: 'auto' }}>{table}</div> : children}
        {!asTable && legend && <div className="legend">{legend}</div>}
      </div>
    </section>
  )
}

export function DataTable({ head, rows, wrapHead = false }: { head: string[]; rows: (string | number)[][]; wrapHead?: boolean }) {
  return (
    <table className={wrapHead ? 'tbl compact wrap-head' : 'tbl compact'}>
      <thead><tr>{head.map((h, i) => (<th key={h} className={i ? 'num' : ''}>{h}</th>))}</tr></thead>
      <tbody>{rows.map((r, i) => (<tr key={i}>{r.map((c, j) => (<td key={j} className={j ? 'num' : ''}>{c}</td>))}</tr>))}</tbody>
    </table>
  )
}

/** Revenue per day / week / month. Days are a line-area (many points); weeks and months are bars. The unfinished period is hatched. */
export type TrendMetric = 'revenue_paise' | 'orders' | 'avg_basket_paise'
const METRIC: Record<TrendMetric, { label: string; money: boolean }> = {
  revenue_paise: { label: 'sales', money: true }, orders: { label: 'orders', money: false }, avg_basket_paise: { label: 'average bill', money: true },
}

export function TrendChart({ series, grain, height = 280, metric = 'revenue_paise', fill = false }: { series: SalesPoint[]; grain: 'day' | 'week' | 'month'; height?: number; metric?: TrendMetric; fill?: boolean }) {
  const m = METRIC[metric]
  const max = Math.max(0, ...series.map((p) => (m.money ? p[metric] / 100 : p[metric])))
  const ticks = useMemo(() => niceTicks(max).map((v) => (m.money ? v * 100 : v)), [max, m.money])
  const hatch = useId().replace(/:/g, '')
  // A day still in progress must not be drawn as if it were a full day: the line would plunge at the right edge for no reason.
  // So the daily line is solid up to the last complete day and dashed from there to the unfinished one.
  const lastPartial = series.length > 0 && series[series.length - 1].partial
  const data = series.map((p, i) => ({
    ...p, label: periodLabel(p.period, grain, true), full: periodLabel(p.period, grain),
    v_done: p.partial ? null : p[metric],
    v_part: lastPartial && i >= series.length - 2 ? p[metric] : null,
  }))
  // Evenly spaced ticks counted back from the newest day, so the last label is always a tick and gaps are equal.
  const dayTicks = useMemo(() => {
    if (grain !== 'day') return undefined
    const k = Math.max(1, Math.ceil(data.length / 5))
    return data.filter((_, i) => (data.length - 1 - i) % k === 0).map((d) => d.label)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series, grain])
  const render = (r: Record<string, unknown>) => ({
    title: String(r.full),
    rows: [['sales', rupees(Number(r.revenue_paise))], ['orders', String(r.orders)], ['average bill', rupees(Number(r.avg_basket_paise))]] as [string, string][],
    note: r.partial ? 'Period still in progress' : undefined,
  })
  const common = { margin: { top: 10, right: 12, bottom: 0, left: 0 } }
  const axes = (
    <>
      <CartesianGrid stroke={GRID} vertical={false} />
      <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={grain === 'day' ? 28 : 8} interval="preserveStartEnd" ticks={dayTicks} />
      <YAxis tickFormatter={m.money ? compactRupees : (v: number) => String(v)} ticks={ticks} domain={[0, ticks[ticks.length - 1]]} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={false} width={50} />
      <Tooltip cursor={{ stroke: AXIS, strokeWidth: 1, strokeDasharray: '3 3' }} content={<Tip render={render} />} />
    </>
  )
  return (
    <div className={fill ? 'chart-fill' : undefined} style={fill ? { minHeight: height } : { height }} role="img" aria-label={`${m.label[0].toUpperCase()}${m.label.slice(1)} per ${grain}. Open the table view for the numbers.`}>
      <ResponsiveContainer width="100%" height="100%">
        {grain === 'day' ? (
          <AreaChart data={data} {...common}>
            {axes}
            {lastPartial && <Area type="monotone" dataKey="v_part" stroke="var(--c1)" strokeWidth={2} strokeDasharray="4 4" fill="none" isAnimationActive={false}
                  dot={false} activeDot={{ r: 4.5, fill: 'var(--chart-surface)', stroke: 'var(--c1)', strokeWidth: 2 }} />}
            <Area type="monotone" dataKey="v_done" stroke="var(--c1)" strokeWidth={2} fill="var(--c1)" fillOpacity={0.09} isAnimationActive={false}
                  dot={false} activeDot={{ r: 4.5, fill: 'var(--c1)', stroke: 'var(--chart-surface)', strokeWidth: 2 }} />
          </AreaChart>
        ) : (
          <BarChart data={data} {...common} barCategoryGap={grain === 'week' ? '22%' : '30%'}>
            <defs>
              <pattern id={hatch} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="6" height="6" fill="var(--c1)" fillOpacity={0.18} /><line x1="0" y1="0" x2="0" y2="6" stroke="var(--c1)" strokeWidth="2.4" />
              </pattern>
            </defs>
            {axes}
            <Bar dataKey={metric} radius={[4, 4, 0, 0]} isAnimationActive={false} maxBarSize={44}>
              {data.map((d) => <Cell key={d.period} fill={d.partial ? `url(#${hatch})` : 'var(--c1)'} stroke={d.partial ? 'var(--c1)' : undefined} />)}
            </Bar>
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

/** Ranked horizontal bars with the value written at the end of each bar (direct labels, no gridlines). */
/** Axis label that is cut with an ellipsis instead of wrapping onto a second line; the full name is in the tooltip and the table view. */
function ClippedTick({ x, y, payload, width }: { x?: number; y?: number; payload?: { value: string }; width: number }) {
  const full = String(payload?.value ?? '')
  const max = Math.max(6, Math.floor((width - 12) / 6.6))
  const text = full.length > max ? full.slice(0, max - 1).trimEnd() + '…' : full
  return <text x={(x ?? 0) - 6} y={y} dy={4} textAnchor="end" fill={AXIS} fontSize={12.5}><title>{full}</title>{text}</text>
}

export function HBars({ rows, fmt, color = 'var(--c1)', labelWidth = 120, fill = false }: { rows: { name: string; v: number; color?: string }[]; fmt: (n: number) => string; color?: string; labelWidth?: number; fill?: boolean }) {
  const h = Math.max(96, rows.length * 32 + 12)
  return (
    <div className={fill ? 'chart-fill' : undefined} style={fill ? { minHeight: h } : { height: h }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 2, right: 64, bottom: 2, left: 0 }} barCategoryGap={9}>
          <XAxis type="number" hide domain={[0, 'dataMax']} />
          <YAxis type="category" dataKey="name" width={labelWidth} tickLine={false} axisLine={{ stroke: GRID }} tick={<ClippedTick width={labelWidth} />} interval={0} />
          <Tooltip cursor={{ fill: 'var(--surface-3)', opacity: 0.6 }} content={<Tip render={(r) => ({ title: String(r.name), rows: [['', fmt(Number(r.v))]] })} />} />
          <Bar dataKey="v" barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {rows.map((r) => (<Cell key={r.name} fill={r.color ?? color} />))}
            <LabelList dataKey="v" position="right" formatter={(n: unknown) => fmt(Number(n))} style={{ fill: 'var(--text)', fontSize: 12.5, fontWeight: 600 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ColumnBars({ data, x, y, fmtX, fmtY = (n) => String(n), height = 260, tipTitle, tipLabel }: {
  data: Record<string, number>[]; x: string; y: string; fmtX: (n: number) => string; fmtY?: (n: number) => string; height?: number; tipTitle: (r: Record<string, unknown>) => string; tipLabel: string
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={4}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={x} tickFormatter={fmtX} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={{ stroke: GRID }} interval={2} />
          <YAxis tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={false} width={34} allowDecimals={false} />
          <Tooltip cursor={{ fill: 'var(--surface-3)', opacity: 0.6 }} content={<Tip render={(r) => ({ title: tipTitle(r), rows: [[tipLabel, fmtY(Number(r[y]))]] })} />} />
          <Bar dataKey={y} fill="var(--c1)" barSize={14} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Tiny trend line for KPI cards (plain SVG: no chart library cost per card). */
export function Sparkline({ values, width = 96, height = 30, label }: { values: number[]; width?: number; height?: number; label: string }) {
  if (values.length < 2) return null
  const max = Math.max(...values), min = Math.min(...values)
  const span = max - min || 1
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (width - 4) + 2, height - 3 - ((v - min) / span) * (height - 6)] as const)
  const d = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join('')
  const last = pts[pts.length - 1]
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} className="spark">
      <path d={`${d}L${last[0]} ${height}L${pts[0][0]} ${height}Z`} fill="var(--c1)" fillOpacity={0.1} />
      <path d={d} fill="none" stroke="var(--c1)" strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r={2.5} fill="var(--c1)" stroke="var(--chart-surface)" strokeWidth={1.5} />
    </svg>
  )
}

/** Stock health as one segmented bar: ok / running low / finished. */
export function HealthBar({ ok, low, out }: { ok: number; low: number; out: number }) {
  const total = Math.max(1, ok + low + out)
  const seg = [
    { k: 'In stock', n: ok, c: 'var(--ok)' },
    { k: 'Running low', n: low, c: 'var(--warn)' },
    { k: 'Finished', n: out, c: 'var(--bad)' },
  ]
  return (
    <div>
      <div className="healthbar" role="img" aria-label={seg.map((s) => `${s.k} ${s.n}`).join(', ')}>
        {seg.filter((s) => s.n > 0).map((s) => <i key={s.k} style={{ width: `${(s.n / total) * 100}%`, background: s.c }} />)}
      </div>
      <div className="legend">{seg.map((s) => <span key={s.k}><i style={{ background: s.c }} />{s.k} <b>{s.n}</b></span>)}</div>
    </div>
  )
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return <>{items.map((i) => <span key={i.label}><i style={{ background: i.color }} />{i.label}</span>)}</>
}

/** Value of stock added and of stock sold or written off, per day, from the stock ledger. Two lines, one rupee axis; each point is a full IST day. */
export function StockFlowChart({ series, height = 240 }: { series: { date: string; in_paise: number; out_paise: number }[]; height?: number }) {
  const max = Math.max(0, ...series.map((p) => Math.max(p.in_paise, p.out_paise) / 100))
  const ticks = useMemo(() => niceTicks(max).map((v) => v * 100), [max])
  const data = series.map((p) => ({ ...p, label: periodLabel(p.date, 'day', true), full: periodLabel(p.date, 'day') }))
  const step = Math.max(1, Math.ceil(data.length / 6))
  const xTicks = data.filter((_, i) => (data.length - 1 - i) % step === 0).map((d) => d.label)
  return (
    <div style={{ height }} role="img" aria-label="Value of stock added and of stock taken out, per day. Open the table view for the numbers.">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" ticks={xTicks} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={{ stroke: GRID }} interval="preserveStartEnd" />
          <YAxis tickFormatter={compactRupees} ticks={ticks} domain={[0, ticks[ticks.length - 1]]} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={false} width={50} />
          <Tooltip cursor={{ stroke: AXIS, strokeWidth: 1, strokeDasharray: '3 3' }} content={<Tip render={(r) => ({ title: String(r.full), rows: [['stock added', rupees(Number(r.in_paise))], ['stock taken out', rupees(Number(r.out_paise))]] })} />} />
          <Line type="monotone" dataKey="in_paise" stroke="var(--c1)" strokeWidth={2} dot={false} isAnimationActive={false} activeDot={{ r: 4.5, fill: 'var(--c1)', stroke: 'var(--chart-surface)', strokeWidth: 2 }} />
          <Line type="monotone" dataKey="out_paise" stroke="var(--c2)" strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} activeDot={{ r: 4.5, fill: 'var(--c2)', stroke: 'var(--chart-surface)', strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
