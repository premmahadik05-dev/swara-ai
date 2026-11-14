import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { compactRupees, periodLabel, rupees } from '../../lib/format'
import type { PaymentTrendPoint } from '../../types'
import { Tip, niceTicks } from '../charts'

/** Fixed colour per way paid, so a filter never repaints it: cash c1, UPI c2, Razorpay c3. */
export const METHOD_COLOR = { cash: 'var(--c1)', upi: 'var(--c2)', razorpay: 'var(--c3)' } as const
const GRID = 'var(--chart-grid)'
const AXIS = 'var(--chart-axis)'
export type Grain = 'day' | 'week' | 'month'

/** The backend names months "2026-11"; periodLabel wants a full date. */
const iso = (period: string) => (period.length === 7 ? period + '-01' : period)
export const trendLabel = (period: string, grain: Grain, short = false) => periodLabel(iso(period), grain, short)

/** Money collected per day, week or month, stacked by way paid (a 2 px gap in the surface colour keeps the segments apart). */
export function PayTrendChart({ series, grain, height = 280 }: { series: PaymentTrendPoint[]; grain: Grain; height?: number }) {
  const data = series.map((p) => ({ ...p, label: trendLabel(p.period, grain, true), full: trendLabel(p.period, grain) }))
  const max = Math.max(0, ...series.map((p) => p.collected_paise / 100))
  const ticks = niceTicks(max).map((v) => v * 100)
  return (
    <div style={{ height }} role="img" aria-label={`Money collected per ${grain}, by way paid. Open the table view for the numbers.`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 0 }} barCategoryGap={grain === 'day' ? '14%' : '26%'}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={grain === 'day' ? 26 : 8} interval="preserveStartEnd" />
          <YAxis tickFormatter={compactRupees} ticks={ticks} domain={[0, ticks[ticks.length - 1]]} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={false} width={50} />
          <Tooltip cursor={{ fill: 'var(--surface-3)', opacity: 0.6 }} content={<Tip render={(r) => ({
            title: String(r.full),
            rows: [['total', rupees(Number(r.collected_paise))], ['cash', rupees(Number(r.cash_paise))], ['UPI', rupees(Number(r.upi_paise))], ['Razorpay', rupees(Number(r.razorpay_paise))], ['payments', String(r.count)]] as [string, string][],
          })} />} />
          <Bar dataKey="cash_paise" stackId="m" fill={METHOD_COLOR.cash} stroke="var(--chart-surface)" strokeWidth={2} isAnimationActive={false} maxBarSize={44} />
          <Bar dataKey="upi_paise" stackId="m" fill={METHOD_COLOR.upi} stroke="var(--chart-surface)" strokeWidth={2} isAnimationActive={false} maxBarSize={44} />
          <Bar dataKey="razorpay_paise" stackId="m" fill={METHOD_COLOR.razorpay} stroke="var(--chart-surface)" strokeWidth={2} radius={[4, 4, 0, 0]} isAnimationActive={false} maxBarSize={44} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
