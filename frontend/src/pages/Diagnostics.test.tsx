import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Diagnostics from './Diagnostics'
import { json, voiceDiagnostics } from '../test/fixtures'
import { STAFF_USER, TestAuth } from '../test/auth'

afterEach(() => { vi.unstubAllGlobals() })

function mockApi(body = voiceDiagnostics(), status = 200) {
  const urls: string[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => { urls.push(url); return json(body, status) }))
  return urls
}
const renderIt = (user?: Parameters<typeof TestAuth>[0]['user']) =>
  render(<MemoryRouter><TestAuth user={user}><Diagnostics /></TestAuth></MemoryRouter>)

describe('Voice diagnostics', () => {
  it('shows server stage times and Gnani call health from the response', async () => {
    mockApi()
    renderIt()
    expect(await screen.findByRole('group', { name: 'Server time per spoken order' })).toHaveTextContent('1.53 s')
    expect(screen.getByRole('group', { name: 'Speech to text, median' })).toHaveTextContent('900 ms')
    const failed = screen.getByRole('group', { name: 'Gnani calls that failed' })
    expect(failed).toHaveTextContent('1')
    expect(failed).toHaveTextContent('Speech to text: 1 of 7 calls')
    expect(screen.getByText('Failed Gnani calls by type')).toBeInTheDocument()
  })

  it('keeps every table inside a scroll wrapper so a phone never scrolls sideways', async () => {
    mockApi()
    const { container } = renderIt()
    await screen.findByRole('group', { name: 'Server time per spoken order' })
    const tables = Array.from(container.querySelectorAll('table'))
    expect(tables.length).toBeGreaterThanOrEqual(3)
    for (const t of tables) expect(t.closest('.table-wrap')).not.toBeNull()
  })

  it('asks for 7 days by default and re-asks when the period changes', async () => {
    const urls = mockApi()
    renderIt()
    await screen.findByRole('group', { name: 'Server time per spoken order' })
    expect(urls[0]).toBe('/api/diagnostics/voice?hours=168')
    await userEvent.click(screen.getByRole('button', { name: '24 hours' }))
    await waitFor(() => expect(urls.at(-1)).toBe('/api/diagnostics/voice?hours=24'))
  })

  it('says "Not measured yet" instead of zeros when no spoken order exists', async () => {
    mockApi(voiceDiagnostics({ empty: true }))
    renderIt()
    const kpi = await screen.findByRole('group', { name: 'Server time per spoken order' })
    expect(kpi).toHaveTextContent('Not measured yet')
    expect(screen.getByRole('group', { name: 'Gnani calls that failed' })).toHaveTextContent('None made')
    expect(screen.getByText(/No spoken orders were recorded in this window/)).toBeInTheDocument()
    expect(screen.queryByText('Where the time goes')).not.toBeInTheDocument()
    expect(screen.getByText(/Not set. Voice is off and typing still works/)).toBeInTheDocument()
  })

  it('lists the slowest turns, marking a cached reply and a retried speech call', async () => {
    mockApi()
    renderIt()
    const slow = (await screen.findByText('Slowest spoken orders')).closest('section') as HTMLElement
    const rows = within(slow).getAllByRole('row')
    expect(rows.length).toBe(3)                      // heading + 2 turns
    expect(within(rows[1]).getByText('3.10 s')).toBeInTheDocument()
    expect(within(rows[1]).getByText('2')).toBeInTheDocument()   // two speech attempts
    expect(within(slow).getByText('Cached')).toBeInTheDocument()
  })

  it('describes how recordings ended in plain words', async () => {
    mockApi()
    renderIt()
    expect(await screen.findByText(/How recordings ended: sent after they stopped talking 3, sent by tapping 1\./)).toBeInTheDocument()
  })

  it('states the limits of what it measures', async () => {
    mockApi()
    renderIt()
    expect(await screen.findByText(/What this page can and cannot tell you/)).toBeInTheDocument()
    expect(screen.getByText(/shortens the wait for the bill, not the time until the voice plays/)).toBeInTheDocument()
  })

  it('does not call the API for staff and explains why', async () => {
    const urls = mockApi()
    renderIt(STAFF_USER)
    expect(screen.getByText('Only the shop owner can open this page')).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 20))
    expect(urls).toEqual([])
  })

  it('shows the server error with a retry when the request fails', async () => {
    mockApi({ detail: 'down' } as never, 500)
    renderIt()
    expect(await screen.findByRole('button', { name: /Try again|Retry/ })).toBeInTheDocument()
  })
})
