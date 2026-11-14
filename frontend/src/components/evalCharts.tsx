import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Tip } from './charts'

/* Charts for the AI performance page. Same rules as charts.tsx: colours come from CSS variables, one axis, thin marks, a legend whenever there are
   two or more series, a table view beside every chart (ChartCard), and text never wears a series colour. */

const GRID = 'var(--chart-grid)'
const AXIS = 'var(--chart-axis)'

export interface CurveSeries { key: string; label: string; color: string; dash?: string }
export type CurveRow = { x: number; band?: [number, number] } & Record<string, number | [number, number] | undefined>

/** Lines over a numeric x (noise rate, %) with y as a percentage 0-100. `band` (optional) shades the min-max range of the series named by `bandOf`. */
export function CurveChart({ data, series, bandOf, bandLabel, height = 270, xTitle, yTitle, fmtY = (n) => `${n.toFixed(1)}%` }: {
  data: CurveRow[]; series: CurveSeries[]; bandOf?: string; bandLabel?: string; height?: number; xTitle: string; yTitle: string; fmtY?: (n: number) => string
}) {
  const band = bandOf ? series.find((s) => s.key === bandOf) : undefined
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 22, left: 6 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis type="number" dataKey="x" domain={['dataMin', 'dataMax']} padding={{ left: 12, right: 12 }} ticks={data.map((d) => d.x)} tickFormatter={(v) => `${v}%`} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={{ stroke: GRID }}
                 label={{ value: xTitle, position: 'insideBottom', offset: -12, fill: AXIS, fontSize: 12 }} />
          <YAxis type="number" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v) => `${v}%`} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={false} width={52}
                 label={{ value: yTitle, angle: -90, position: 'insideLeft', offset: 6, fill: AXIS, fontSize: 12, style: { textAnchor: 'middle' } }} />
          <Tooltip cursor={{ stroke: 'var(--line-strong)' }} content={<Tip render={(r) => {
            const b = r.band as [number, number] | undefined
            return {
              title: `${r.x}% of letters damaged`,
              rows: series.map((s) => [s.label, fmtY(Number(r[s.key]))] as [string, string]),
              note: band && b ? `${bandLabel ?? 'Range'}: ${fmtY(b[0])} to ${fmtY(b[1])}` : undefined,
            }
          }} />} />
          {band && <Area dataKey="band" stroke="none" fill={band.color} fillOpacity={0.14} isAnimationActive={false} activeDot={false} legendType="none" />}
          {series.map((s) => (
            <Line key={s.key} dataKey={s.key} stroke={s.color} strokeWidth={2} strokeDasharray={s.dash} isAnimationActive={false}
                  dot={{ r: 4, fill: s.color, stroke: 'var(--chart-surface)', strokeWidth: 2 }} activeDot={{ r: 5, fill: s.color, stroke: 'var(--chart-surface)', strokeWidth: 2 }} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

export interface VerdictRow { key: string; label: string; parts: { name: string; n: number; color: string; ink: string }[] }

/** One horizontal bar per row, split into how its items ended. Segments are separated by a 2px gap and print their count when wide enough;
 *  every count is also in the hover text and in the chart's table view. */
export function VerdictBars({ rows, labelWidth = 92 }: { rows: VerdictRow[]; labelWidth?: number }) {
  // One scale for every row: a bar is as long as its total relative to the largest, so a language with 7 sentences does not look as big as one with 195.
  const biggest = Math.max(1, ...rows.map((r) => r.parts.reduce((a, p) => a + p.n, 0)))
  return (
    <div className="vbars" role="list">
      {rows.map((r) => {
        const total = r.parts.reduce((a, p) => a + p.n, 0)
        const label = `${r.label}: ${r.parts.map((p) => `${p.name} ${p.n}`).join(', ')} of ${total}`
        return (
          <div key={r.key} className="vbar" role="listitem" style={{ gridTemplateColumns: `${labelWidth}px minmax(0, 1fr) 44px` }}>
            <span className="name">{r.label}</span>
            <span className="track" role="img" aria-label={label} style={{ width: `${(100 * total) / biggest}%` }}>
              {r.parts.filter((p) => p.n > 0).map((p) => (
                <i key={p.name} style={{ flexGrow: p.n, background: p.color, color: p.ink }} title={`${r.label}, ${p.name}: ${p.n} of ${total} (${total ? ((100 * p.n) / total).toFixed(1) : '0'}%)`}>{total && p.n / total >= 0.07 ? p.n : ''}</i>
              ))}
            </span>
            <span className="n">{total}</span>
          </div>
        )
      })}
    </div>
  )
}
