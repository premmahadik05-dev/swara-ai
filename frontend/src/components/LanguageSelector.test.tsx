import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { LanguageSelector } from './LanguageSelector'
import { LANG_META } from '../lib/languages'
import type { LangOption } from '../lib/useLanguages'
import type { LanguageMode } from '../types'
import { languageInfo } from '../test/fixtures'

const MODES: LanguageMode[] = [{ key: 'auto', name: 'Auto-detect', available: false, reason: 'Automatic language detection needs Prisma v3.0; this server uses prisma-v2.5.' }, { key: 'mixed', name: 'Mixed languages', available: false, reason: 'Needs Prisma v3.0.' }]
const options = (off: string[] = [], withInfo = true): LangOption[] => LANG_META.map((m) => {
  const info = withInfo ? languageInfo(m.key, { enabled: !off.includes(m.key) }) : undefined
  return { ...m, enabled: !off.includes(m.key), info }
})

function setup(props: Partial<Parameters<typeof LanguageSelector>[0]> = {}) {
  const onChange = vi.fn()
  render(<LanguageSelector value="gu" onChange={onChange} options={options()} modes={MODES} {...props} />)
  return onChange
}

describe('LanguageSelector', () => {
  it('shows the current language in its own script with its Gnani codes and an honest status', () => {
    setup()
    expect(screen.getByRole('button', { name: /Customer speaks/ })).toHaveTextContent('ગુજરાતી')
    expect(screen.getByText(/Speech: gu-IN \(Prisma\)/)).toHaveTextContent('Voice: Falak (Timbre)')
    expect(screen.getByText(/Not verified live/)).toBeInTheDocument()
  })

  it('lists all eleven languages and Auto-detect when opened', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    const group = within(screen.getByRole('radiogroup', { name: 'Languages' }))
    expect(group.getAllByRole('radio')).toHaveLength(12)
    for (const name of ['Marathi', 'Bengali', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Punjabi']) expect(group.getByText(new RegExp(name))).toBeInTheDocument()
  })

  it('marks the seven new languages as new and none of them as live checked', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    expect(screen.getAllByText('New in 2.3')).toHaveLength(7)
    expect(screen.queryByText('Live checked')).toBeNull()
    expect(screen.getAllByText('Not verified live').length).toBeGreaterThanOrEqual(11)
  })

  it('picks a language, closes the list and tells the parent', async () => {
    const onChange = setup()
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    await userEvent.click(screen.getByRole('radio', { name: /தமிழ்/ }))
    expect(onChange).toHaveBeenCalledWith('ta')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('lists a switched-off language but cannot pick it', async () => {
    const onChange = setup({ options: options(['bn']) })
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    const bn = screen.getByRole('radio', { name: /বাংলা/ })
    expect(bn).toBeDisabled()
    expect(screen.getByText('Switched off')).toBeInTheDocument()
    await userEvent.click(bn)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('says why Auto-detect is unavailable instead of offering it', async () => {
    const onChange = setup()
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    const auto = screen.getByRole('radio', { name: /Auto-detect/ })
    expect(auto).toBeDisabled()
    expect(screen.getByText(/needs Prisma v3.0; this server uses prisma-v2.5/)).toBeInTheDocument()
    await userEvent.click(auto)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('offers Auto-detect when the server says it is available', async () => {
    const onChange = setup({ modes: [{ key: 'auto', name: 'Auto-detect', available: true, reason: null }] })
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    await userEvent.click(screen.getByRole('radio', { name: /Auto-detect/ }))
    expect(onChange).toHaveBeenCalledWith('auto')
  })

  it('closes on Escape and returns focus to the button', async () => {
    setup()
    const btn = screen.getByRole('button', { name: /Customer speaks/ })
    await userEvent.click(btn)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(btn).toHaveFocus()
  })

  it('cannot be opened while a recording is in progress', async () => {
    setup({ disabled: true })
    expect(screen.getByRole('button', { name: /Customer speaks/ })).toBeDisabled()
  })

  it('still names the languages when the server could not be reached, without inventing details', async () => {
    setup({ options: options([], false) })
    expect(screen.getByText(/Details unavailable/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    expect(screen.getAllByRole('radio')).toHaveLength(12)
    expect(screen.queryByText('Live checked')).toBeNull()
  })

  it('shows a live pass only when the results say so', async () => {
    const opts = options().map((o) => o.key === 'mr' ? { ...o, info: languageInfo('mr', { verification: { tts: { status: 'passed' }, stt_code: { status: 'passed' }, stt_loopback: { status: 'not_run' }, stt_human: { status: 'not_run' } } }) } : o)
    setup({ options: opts, value: 'mr' })
    expect(screen.getByText(/Live checked/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Customer speaks/ }))
    expect(screen.getAllByText('Live checked')).toHaveLength(1)
  })
})
