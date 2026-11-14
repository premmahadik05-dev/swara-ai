import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GridTable, type GridColumn } from './GridTable'

interface Row { id: string; name: string; qty: number | null; kind: 'a' | 'b' }
const rows: Row[] = [
  { id: '1', name: 'Rice', qty: 5, kind: 'a' }, { id: '2', name: 'Atta', qty: null, kind: 'b' }, { id: '3', name: 'Dal', qty: 12, kind: 'a' },
  { id: '4', name: '=SUM(1)', qty: 1, kind: 'b' }, { id: '5', name: 'Oil', qty: 9, kind: 'a' },
]
const columns: GridColumn<Row>[] = [
  { key: 'name', label: 'Name', value: (r) => r.name },
  { key: 'qty', label: 'Quantity', value: (r) => r.qty, num: true },
]
const names = () => screen.getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[0].textContent)
const renderIt = (props: Partial<Parameters<typeof GridTable<Row>>[0]> = {}) =>
  render(<GridTable rows={rows} columns={columns} rowKey={(r) => r.id} noun="items" exportName="test" pageSize={3} {...props} />)

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('GridTable', () => {
  it('pages the rows and says which ones are shown', async () => {
    renderIt()
    expect(names()).toEqual(['Rice', 'Atta', 'Dal'])
    expect(screen.getByText('1–3 of 5 items')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(names()).toEqual(['=SUM(1)', 'Oil'])
    expect(screen.getByText('4–5 of 5 items')).toBeInTheDocument()
  })

  it('sorts a column ascending, then descending, then back to the original order, and keeps empty cells last either way', async () => {
    renderIt({ pageSize: 10 })
    const head = screen.getByRole('columnheader', { name: 'Quantity' })
    await userEvent.click(within(head).getByRole('button'))
    expect(head).toHaveAttribute('aria-sort', 'ascending')
    expect(names()).toEqual(['=SUM(1)', 'Rice', 'Oil', 'Dal', 'Atta'])
    await userEvent.click(within(head).getByRole('button'))
    expect(head).toHaveAttribute('aria-sort', 'descending')
    expect(names()).toEqual(['Dal', 'Oil', 'Rice', '=SUM(1)', 'Atta'])
    await userEvent.click(within(head).getByRole('button'))
    expect(head).toHaveAttribute('aria-sort', 'none')
    expect(names()).toEqual(['Rice', 'Atta', 'Dal', '=SUM(1)', 'Oil'])
  })

  it('searches every column, returns to page one, and shows an empty state with a way out', async () => {
    renderIt()
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await userEvent.type(screen.getByRole('searchbox'), 'dal')
    expect(names()).toEqual(['Dal'])
    await userEvent.clear(screen.getByRole('searchbox'))
    await userEvent.type(screen.getByRole('searchbox'), 'zzz')
    expect(screen.getByText('No items match')).toBeInTheDocument()
    expect(screen.getByText(/Clear the search or the filter/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'CSV' })).toBeDisabled()
  })

  it('filters with the segmented control', async () => {
    renderIt({ filter: { label: 'Kind', options: [{ value: 'all', label: 'All' }, { value: 'a', label: 'Kind A' }], test: (r, v) => v === 'all' || r.kind === v } })
    await userEvent.click(screen.getByRole('button', { name: 'Kind A' }))
    expect(names()).toEqual(['Rice', 'Dal', 'Oil'])
  })

  it('downloads what is shown as a CSV that a spreadsheet will not run as a formula', async () => {
    let blob: Blob | undefined
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})   // jsdom cannot follow a download link
    vi.stubGlobal('URL', { ...URL, createObjectURL: (b: Blob) => { blob = b; return 'blob:x' }, revokeObjectURL: () => {} })
    renderIt()
    await userEvent.type(screen.getByRole('searchbox'), 'sum')
    await userEvent.click(screen.getByRole('button', { name: 'CSV' }))
    expect(blob).toBeDefined()
    const bytes = new Uint8Array(await blob!.arrayBuffer())
    expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf])   // byte-order mark, so Excel on Windows reads the file as UTF-8
    expect(new TextDecoder('utf-8', { ignoreBOM: false }).decode(bytes)).toBe("Name,Quantity\r\n'=SUM(1),1\r\n")
  })

  it('shows the caller\'s own empty state when there are no rows at all', () => {
    renderIt({ rows: [], empty: <p>Nothing recorded yet</p> })
    expect(screen.getByText('Nothing recorded yet')).toBeInTheDocument()
    expect(screen.queryByRole('table')).toBeNull()
  })
})
