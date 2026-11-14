import { useMemo, useState, type ReactNode } from 'react'
import { toCsv } from '../lib/csv'
import { saveFile } from './ExportButton'
import { Button, Empty, Pagination, SearchBox, Seg } from './ui'
import { Icon } from './Icons'

/** One column of a GridTable. `value` is what the column sorts, searches and exports by; `render` only changes how a cell looks. */
export interface GridColumn<T> {
  key: string
  label: string
  value: (row: T) => string | number | null
  render?: (row: T) => ReactNode
  num?: boolean
  /** Hover text for the column heading (what the column means). */
  hint?: string
}
export interface GridFilter<T> { label: string; options: { value: string; label: string }[]; test: (row: T, value: string) => boolean }

type Dir = 'asc' | 'desc'

/** A client-side table: search, optional filter, click-to-sort headings, pagination, an empty state and a CSV download of what is currently filtered.
 *  For tables whose rows are all in memory (evaluation results, stock movement). Long server-side lists use their own paging instead. */
export function GridTable<T>({ rows, columns, rowKey, pageSize = 10, noun, exportName, searchLabel, filter, empty, initialSort }: {
  rows: T[]; columns: GridColumn<T>[]; rowKey: (row: T) => string; pageSize?: number; noun: string; exportName: string; searchLabel?: string
  filter?: GridFilter<T>; empty?: ReactNode; initialSort?: { key: string; dir: Dir }
}) {
  const [q, setQ] = useState('')
  const [fv, setFv] = useState(filter?.options[0]?.value ?? '')
  const [sort, setSort] = useState<{ key: string; dir: Dir } | null>(initialSort ?? null)
  const [page, setPage] = useState(1)

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    let out = rows.filter((r) => (!filter || filter.test(r, fv)) && (!needle || columns.some((c) => String(c.value(r) ?? '').toLowerCase().includes(needle))))
    if (sort) {
      const col = columns.find((c) => c.key === sort.key)
      if (col) {
        const sign = sort.dir === 'asc' ? 1 : -1
        // empty cells always go last, whichever way the column is sorted
        out = [...out].sort((a, b) => {
          const x = col.value(a), y = col.value(b)
          if (x === null && y === null) return 0
          if (x === null) return 1
          if (y === null) return -1
          return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'en', { numeric: true, sensitivity: 'base' })) * sign
        })
      }
    }
    return out
  }, [rows, columns, q, filter, fv, sort])

  const pages = Math.max(1, Math.ceil(shown.length / pageSize))
  const cur = Math.min(page, pages)
  const view = shown.slice((cur - 1) * pageSize, cur * pageSize)
  const toggle = (key: string) => { setSort((s) => (s?.key === key ? (s.dir === 'asc' ? { key, dir: 'desc' } : null) : { key, dir: 'asc' })); setPage(1) }
  const download = () => saveFile({ blob: new Blob([toCsv(columns.map((c) => c.label), shown.map((r) => columns.map((c) => c.value(r))))], { type: 'text/csv;charset=utf-8' }), filename: `swara-${exportName}.csv`, truncated: false })

  return (
    <div className="grid-table">
      <div className="toolbar">
        <SearchBox label={searchLabel ?? `Search ${noun}`} placeholder={`Search ${noun}`} value={q} onChange={(v) => { setQ(v); setPage(1) }} />
        {filter && <Seg label={filter.label} value={fv} onChange={(v) => { setFv(v); setPage(1) }} options={filter.options} />}
        <span className="grow" />
        <Button variant="secondary" size="sm" icon="download" onClick={download} disabled={shown.length === 0} title={`Download the ${shown.length} ${noun} shown (after search and filter) as a CSV file`}>CSV</Button>
      </div>
      {shown.length === 0 ? (
        <div className="card-pad">{empty ?? <Empty title={`No ${noun} match`} icon="search">{q || (filter && fv !== filter.options[0]?.value) ? 'Clear the search or the filter to see all rows.' : 'There is nothing to show yet.'}</Empty>}</div>
      ) : (
        <div className="table-wrap">
          <table className="tbl compact">
            <thead>
              <tr>
                {columns.map((c) => {
                  const active = sort?.key === c.key
                  return (
                    <th key={c.key} className={c.num ? 'num' : undefined} title={c.hint} aria-sort={active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                      <button type="button" onClick={() => toggle(c.key)}>{c.label}{active && <Icon name={sort!.dir === 'asc' ? 'sortUp' : 'sortDown'} size={13} />}</button>
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {view.map((r) => (
                <tr key={rowKey(r)}>{columns.map((c) => <td key={c.key} className={c.num ? 'num' : undefined}>{c.render ? c.render(r) : (c.value(r) ?? '-')}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {shown.length > 0 && <Pagination page={cur} pageSize={pageSize} total={shown.length} noun={noun} onPage={setPage} />}
    </div>
  )
}
