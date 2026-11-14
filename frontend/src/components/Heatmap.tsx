import { heatColor } from '../lib/evaluation'

/* Two plain-HTML matrices (no chart library): a heatmap of percentages and a confusion matrix of counts.
   Every cell prints its number, so colour is never the only carrier of meaning, and both are real <table>s a screen reader can walk. */

export interface HeatmapColumn { key: string; label: string; note?: string }
export interface HeatmapCell { value: number | null; text: string; detail: string }

/** Rows x metrics, percentages 0-100 on one gold ramp. A metric that was not measured for a row shows "n/a" on a plain hatched cell. */
export function Heatmap({ caption, rows, columns }: { caption: string; rows: { key: string; label: string; cells: HeatmapCell[] }[]; columns: HeatmapColumn[] }) {
  return (
    <div className="matrix-wrap">
      <table className="matrix heat">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className="corner">Language</th>
            {columns.map((c) => <th key={c.key} scope="col" title={c.note}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <th scope="row">{r.label}</th>
              {r.cells.map((c, i) => (
                <td key={columns[i].key} className={c.value === null ? 'na' : undefined} title={`${r.label}, ${columns[i].label}: ${c.text}. ${c.detail}`}
                    style={c.value === null ? undefined : { background: heatColor(c.value / 100) }}>
                  {c.text}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** True label (rows) against predicted label (columns), as counts. Cells are shaded by their share of the row, so a small class stays visible.
 *  `kind(rowIndex, colIndex)` says what a cell means: 'hit' (right, gold), 'miss' (a wrong answer, rose) or 'safe' (not a right answer but harmless, such as
 *  "asked which one", grey). Every non-zero cell prints its count. */
export type CellKind = 'hit' | 'miss' | 'safe'
export function ConfusionMatrix({ caption, rows, cols, matrix, kind, rowHeader, colHeader, totalLabel = 'Sentences' }: {
  caption: string; rows: string[]; cols: string[]; matrix: number[][]; kind: (r: number, c: number) => CellKind; rowHeader: string; colHeader: string; totalLabel?: string
}) {
  return (
    <div className="matrix-wrap">
      <table className="matrix conf">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr><th className="corner" scope="col" rowSpan={2}>{rowHeader}</th><th scope="colgroup" colSpan={cols.length} className="span">{colHeader}</th><th scope="col" rowSpan={2} className="tot">{totalLabel}</th></tr>
          <tr>{cols.map((c) => <th key={c} scope="col"><span>{c}</span></th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const total = matrix[i].reduce((a, v) => a + v, 0)
            return (
              <tr key={r}>
                <th scope="row">{r}</th>
                {matrix[i].map((v, j) => {
                  const share = total ? v / total : 0
                  const k = kind(i, j)
                  const bg = v === 0 ? undefined : k === 'hit' ? heatColor(share)
                    : k === 'safe' ? `color-mix(in srgb, var(--c-muted) ${Math.round(10 + share * 40)}%, var(--surface))`
                    : `color-mix(in srgb, var(--bad) ${Math.round(10 + share * 50)}%, var(--surface))`
                  return (
                    <td key={j} className={v === 0 ? 'zero' : k} style={bg ? { background: bg } : undefined}
                        title={`${r} predicted as ${cols[j]}: ${v} of ${total}`}>{v === 0 ? '·' : v}</td>
                  )
                })}
                <td className="tot">{total}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
